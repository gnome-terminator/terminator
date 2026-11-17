"""r14-2 path_lookup, r14-3 cell_height migration, r14-5 flatpak shell."""

import os
import stat
import subprocess

import gi
gi.require_version('Gtk', '3.0')

import pytest

from terminatorlib import util


def test_missing_path_uses_fallbacks_in_order(monkeypatch):
    monkeypatch.delenv('PATH', raising=False)
    found = util.path_lookup('sh')
    candidates = [os.path.join(directory, 'sh') for directory in
                  ('/usr/local/bin', '/usr/bin', '/bin')]
    existing = [path for path in candidates if os.path.isfile(path)]
    if existing:
        assert found == existing[0]
        assert found.startswith(('/usr/local/bin', '/usr/bin', '/bin'))
    else:
        assert found is None
    assert util.path_lookup('r14-no-such-command-xyz') is None


def test_empty_path_does_not_substitute_fallbacks(monkeypatch, tmp_path):
    monkeypatch.setenv('PATH', '')
    monkeypatch.chdir(tmp_path)
    assert util.path_lookup('sh') is None


def test_leading_empty_segment_searches_later_dirs(monkeypatch, tmp_path):
    empty = tmp_path / 'empty'
    bindir = tmp_path / 'bin'
    empty.mkdir()
    bindir.mkdir()
    name = 'r14bin'
    (bindir / name).write_text('x')
    os.chmod(bindir / name, 0o644)
    monkeypatch.chdir(empty)
    monkeypatch.setenv('PATH', ':' + str(bindir))
    assert util.path_lookup(name) == os.path.join(str(bindir), name)


def test_middle_empty_segment_still_searches(monkeypatch, tmp_path):
    first = tmp_path / 'a'
    second = tmp_path / 'b'
    first.mkdir()
    second.mkdir()
    name = 'r14onlyb'
    (second / name).write_text('x')
    os.chmod(second / name, 0o644)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('PATH', str(first) + '::' + str(second))
    assert util.path_lookup(name) == os.path.join(str(second), name)


def test_absolute_and_dot_slash_short_circuit(monkeypatch, tmp_path):
    present = tmp_path / 'tool'
    present.write_text('x')
    os.chmod(present, 0o644)
    assert util.path_lookup(str(present)) == str(present)
    assert util.path_lookup(str(tmp_path / 'missing')) is None
    monkeypatch.chdir(tmp_path)
    assert util.path_lookup('./tool') == './tool'


_CONFIG = (
    b"    line_height = 1.0\r\n"
    b"# line_height\n"
    b"echo line_height\n"
    b"font = line_height\n"
    b"my_line_height = 1\n"
    b"line_height_extra = 2\n"
)
_CONFIG_MIGRATED = (
    b"    cell_height = 1.0\r\n"
    b"# line_height\n"
    b"echo line_height\n"
    b"font = line_height\n"
    b"my_line_height = 1\n"
    b"line_height_extra = 2\n"
)


def test_migrates_only_the_key_token(tmp_path):
    path = tmp_path / 'config'
    path.write_bytes(_CONFIG)
    util.update_config_to_cell_height(str(path))
    assert path.read_bytes() == _CONFIG_MIGRATED
    assert [entry.name for entry in tmp_path.iterdir()] == ['config']


def test_comments_and_values_do_not_replace(tmp_path, monkeypatch):
    path = tmp_path / 'config'
    original = b"# line_height\necho line_height\nfont = line_height\n"
    path.write_bytes(original)
    called = []
    real_replace = util.os.replace

    def _track(src, dst):
        called.append((src, dst))
        return real_replace(src, dst)

    monkeypatch.setattr(util.os, 'replace', _track)
    util.update_config_to_cell_height(str(path))
    assert called == []
    assert path.read_bytes() == original


def test_replace_oserror_keeps_original_and_tmp(tmp_path, monkeypatch):
    path = tmp_path / 'config'
    path.write_bytes(b"    line_height = 1.0\n")
    calls = []

    def _boom(src, dst):
        calls.append((src, dst))
        raise OSError('nope')

    monkeypatch.setattr(util.os, 'replace', _boom)
    util.update_config_to_cell_height(str(path))
    assert len(calls) == 1
    assert path.read_bytes() == b"    line_height = 1.0\n"
    assert [entry.name for entry in tmp_path.iterdir()] == ['config']


def test_symlink_target_keeps_mode(tmp_path):
    real_dir = tmp_path / 'real'
    real_dir.mkdir()
    target = real_dir / 'config'
    target.write_bytes(_CONFIG)
    os.chmod(target, 0o640)
    link = tmp_path / 'config'
    link.symlink_to(target)
    util.update_config_to_cell_height(str(link))
    assert link.is_symlink()
    assert os.readlink(link) == str(target)
    assert target.read_bytes() == _CONFIG_MIGRATED
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o640
    assert [entry.name for entry in real_dir.iterdir()] == ['config']


def test_missing_config_is_not_created(tmp_path):
    missing = tmp_path / 'config'
    util.update_config_to_cell_height(str(missing))
    assert not missing.exists()
    assert list(tmp_path.iterdir()) == []


def test_bom_key_is_rewritten_and_mode_kept(tmp_path):
    path = tmp_path / 'config'
    path.write_bytes(b'\xef\xbb\xbfline_height = 1.0\n')
    os.chmod(path, 0o640)
    util.update_config_to_cell_height(str(path))
    assert path.read_bytes() == b'\xef\xbb\xbfcell_height = 1.0\n'
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o640


def _assert_real_shell(result):
    assert result
    assert result != ''
    assert os.path.isfile(result)


@pytest.mark.parametrize('payload', [
    b'u:x:1:1:\xff:/home:/bin/sh\n',
    b'only:three:fields\n',
    b'u:x:1:1:g:/home:\n',
    b'u:x:1:1:g:/home: \t \n',
])
def test_flatpak_bad_getent_falls_through(monkeypatch, payload):
    monkeypatch.setattr(util, 'is_flatpak', lambda: True)
    monkeypatch.setattr(util.subprocess, 'check_output',
                        lambda *_a, **_k: payload)
    _assert_real_shell(util.shell_lookup())


def test_flatpak_nonzero_getent_falls_through(monkeypatch):
    monkeypatch.setattr(util, 'is_flatpak', lambda: True)

    def _boom(*_a, **_k):
        raise subprocess.CalledProcessError(1, ['flatpak-spawn'])

    monkeypatch.setattr(util.subprocess, 'check_output', _boom)
    _assert_real_shell(util.shell_lookup())


def test_flatpak_missing_spawn_falls_through(monkeypatch):
    monkeypatch.setattr(util, 'is_flatpak', lambda: True)

    def _boom(*_a, **_k):
        raise FileNotFoundError('flatpak-spawn')

    monkeypatch.setattr(util.subprocess, 'check_output', _boom)
    _assert_real_shell(util.shell_lookup())


def test_flatpak_passwd_keyerror_falls_through(monkeypatch):
    monkeypatch.setattr(util, 'is_flatpak', lambda: True)

    def _boom(_uid):
        raise KeyError('pw')

    monkeypatch.setattr(util.pwd, 'getpwuid', _boom)
    _assert_real_shell(util.shell_lookup())


def test_flatpak_host_shell_returned_verbatim(monkeypatch):
    monkeypatch.setattr(util, 'is_flatpak', lambda: True)
    monkeypatch.setattr(
        util.subprocess, 'check_output',
        lambda *_a, **_k: b'u:x:1:1:g:/home:/no/such/host-shell\n')
    assert not os.path.isfile('/no/such/host-shell')
    assert util.shell_lookup() == '/no/such/host-shell'


def test_non_flatpak_uses_passwd_shell(monkeypatch, tmp_path):
    shell = tmp_path / 'myshell'
    shell.write_text('x')
    monkeypatch.setattr(util, 'is_flatpak', lambda: False)

    def _no_getent(*_a, **_k):
        raise AssertionError('flatpak getent should not run')

    monkeypatch.setattr(util.subprocess, 'check_output', _no_getent)

    class _Pw(object):
        def __getitem__(self, index):
            if index == 6:
                return str(shell)
            if index == 0:
                return 'user'
            raise IndexError(index)

    monkeypatch.setattr(util.pwd, 'getpwuid', lambda _uid: _Pw())
    assert util.shell_lookup() == str(shell)
