"""m21: persistence review fixes (unit level, no full app)."""
import json
import os
import subprocess
import sys
import time

import pytest

from terminatorlib import close_confirm as cc
from terminatorlib import scrollback_text as sbt
from terminatorlib.session import (
    SESSION_VERSION,
    SessionManager,
    is_explicit_launch,
    merge_window_fragments,
    sanitize_layout,
    tighten_dir,
)


def _reset_session_borg():
    from terminatorlib.borg import Borg
    Borg._Borg__shared_state.pop('SessionManager', None)


@pytest.fixture
def sm(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    _reset_session_borg()
    s = SessionManager()
    assert s.acquire_lock()
    s._owns_session = True
    yield s
    try:
        os.close(s._lock_fd)
    except Exception:
        pass
    _reset_session_borg()


def _w1():
    return {
        'child0': {'type': 'Window', 'parent': '', 'title': 'one',
                   'title_forced': 'True'},
        'child1': {'type': 'HPaned', 'parent': 'child0', 'order': '0'},
        'terminal2': {'type': 'Terminal', 'parent': 'child1', 'order': '0',
                      'uuid': 'u1'},
        'terminal3': {'type': 'Terminal', 'parent': 'child1', 'order': '1',
                      'uuid': 'u2'},
    }


def _w2():
    return {
        'child0': {'type': 'Window', 'parent': ''},
        'terminal1': {'type': 'Terminal', 'parent': 'child0', 'uuid': 'u3'},
    }


def _check_tree(layout):
    windows = [n for n, v in layout.items() if v['type'] == 'Window']
    for name, node in layout.items():
        if node['type'] != 'Window':
            assert node['parent'] in layout, (name, layout)
    for w in windows:
        assert len([n for n, v in layout.items()
                    if v.get('parent') == w]) == 1
    return windows


# --- P0-1 ---------------------------------------------------------------

def test_merge_window_fragments_renames_and_relinks():
    merged = merge_window_fragments(_w2(), [_w1()])
    assert len(_check_tree(merged)) == 2
    assert sorted(v['uuid'] for v in merged.values()
                  if v['type'] == 'Terminal') == ['u1', 'u2', 'u3']
    buffered = [n for n in merged if n.startswith('d5w0_')]
    assert len(buffered) == 4
    # buffered window does not steal focus from the live one
    assert merged['d5w0_child0']['last_active_window'] == 'False'


def test_d5_first_window_closes_first(sm):
    class W(object):
        pass
    w1, w2 = W(), W()
    sm._describe_windows = lambda windows: _w1() if windows == [w1] else {}
    sm._refresh_ratios = lambda w: None
    sm.note_window_closing(w1)
    assert sm._closing_buffer['uuids'] == {'u1', 'u2'}
    sm._describe_current = _w2
    assert sm.save_now(final=True)
    data = sm.load()
    assert len(_check_tree(data['layout'])) == 2
    layout = sanitize_layout(data['layout'])
    assert sum(1 for v in layout.values() if v['type'] == 'Terminal') == 3


def test_d5_two_buffered_windows_do_not_collide(sm):
    class W(object):
        pass
    w1, w2, w3 = W(), W(), W()
    sm._refresh_ratios = lambda w: None
    sm._describe_windows = lambda windows: _w1() if windows == [w1] else _w2()
    sm.note_window_closing(w1)
    sm.note_window_closing(w2)
    sm._describe_current = lambda: {
        'child0': {'type': 'Window', 'parent': ''},
        'terminal1': {'type': 'Terminal', 'parent': 'child0', 'uuid': 'u9'}}
    assert sm.save_now(final=True)
    layout = sm.load()['layout']
    assert len(_check_tree(layout)) == 3


def test_excluded_window_is_not_buffered(sm):
    class W(object):
        _session_excluded = True
    sm._describe_windows = lambda windows: _w1()
    sm.note_window_closing(W())
    assert sm._closing_buffer is None


# --- P1-2 rotation --------------------------------------------------------

def _write(path, layout):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump({'version': SESSION_VERSION, 'layout': layout}, fh)


def test_first_write_of_run_backs_up_previous_session(sm):
    path = sm.session_path()
    _write(path, {'old': {'type': 'Terminal', 'uuid': 'old'}})
    sm._describe_current = lambda: {
        'terminal1': {'type': 'Terminal', 'uuid': 'new1'}}
    assert sm.save_now(final=False)
    with open(path + '.prev', encoding='utf-8') as fh:
        assert 'old' in json.load(fh)['layout']
    # Later writes (incl. final) of the same run do not rotate again
    sm._describe_current = lambda: {
        'terminal1': {'type': 'Terminal', 'uuid': 'new2'}}
    assert sm.save_now(final=True)
    with open(path + '.prev', encoding='utf-8') as fh:
        assert 'old' in json.load(fh)['layout']
    assert not os.path.exists(path + '.prev2')


def test_rotation_without_session_keeps_prev(sm):
    path = sm.session_path()
    _write(path + '.prev', {'p': {'type': 'Terminal', 'uuid': 'p'}})
    sm._describe_current = lambda: {
        'terminal1': {'type': 'Terminal', 'uuid': 'n'}}
    assert sm.save_now()
    assert os.path.isfile(path + '.prev')
    assert not os.path.exists(path + '.prev2')


# --- P1-3 malformed ------------------------------------------------------

@pytest.mark.parametrize('payload', [[1, 2], 'str', 5, None])
def test_non_object_session_is_moved_to_corrupt(sm, payload):
    path = sm.session_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh)
    assert sm.load() is None
    assert os.path.isfile(path + '.corrupt')
    assert not os.path.exists(path)


def test_layout_not_dict_is_moved_to_corrupt(sm):
    path = sm.session_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump({'version': 1, 'layout': [1]}, fh)
    assert sm.load() is None
    assert os.path.isfile(path + '.corrupt')


def test_sanitize_drops_malformed_nodes():
    out = sanitize_layout({'a': 'x', 'b': {'parent': ''}, 'c': {'type': 3},
                           'd': {'type': 'Terminal', 'uuid': 'u'}})
    assert list(out) == ['d']
    assert sanitize_layout(['nope']) == {}


def test_restore_failed_keeps_bad_copy(sm):
    path = sm.session_path()
    _write(path, {'t': {'type': 'Terminal'}})
    sm.restored_this_run = True
    sm.restore_failed(TypeError('boom'))
    assert os.path.isfile(path + '.bad')
    assert os.path.isfile(path)
    assert sm.restored_this_run is False


def test_restore_prev_session_malformed_does_not_suspend(sm):
    path = sm.session_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + '.prev', 'w', encoding='utf-8') as fh:
        fh.write('[1]')
    assert sm.restore_prev_session() is False
    assert not sm.writes_suspended()


def test_clear_session_files_removes_corrupt(sm):
    path = sm.session_path()
    _write(path + '.corrupt', {})
    sm.clear_session_files()
    assert not os.path.exists(path + '.corrupt')


# --- P1-4 title ------------------------------------------------------------

def test_sanitize_keeps_user_window_title_and_marks_it():
    out = sanitize_layout({'w': {'type': 'Window', 'title': 'Mine'},
                           'x': {'type': 'Window', 'title': ''}})
    assert out['w']['title'] == 'Mine' and out['w']['title_forced'] == 'True'
    assert 'title' not in out['x'] and 'title_forced' not in out['x']


# --- P1-5 ownership --------------------------------------------------------

class Opt(object):
    def __init__(self, **kw):
        self.layout_from_default = True
        self.layout = 'default'
        self.command = None
        self.execute = None
        self.working_directory = None
        self.configjson = None
        self.__dict__.update(kw)


@pytest.mark.parametrize('kw,explicit', [
    ({}, False),
    ({'working_directory': '/tmp'}, False),
    ({'command': 'htop'}, True),
    ({'execute': ['ssh', 'x']}, True),
    ({'layout': 'work', 'layout_from_default': False}, True),
    ({'layout': 'default', 'layout_from_default': False}, False),
    ({'configjson': '/x.json'}, True),
    # DBus string form
    ({'command': '', 'execute': '', 'layout': 'default',
      'layout_from_default': 'True', 'working_directory': '/home'}, False),
    ({'command': '', 'execute': 'vim', 'layout': 'default',
      'layout_from_default': ''}, True),
])
def test_is_explicit_launch(kw, explicit):
    assert is_explicit_launch(Opt(**kw)) is explicit


@pytest.mark.parametrize('kw', [
    {'working_directory': '/tmp'}, {'command': 'htop'},
    {'layout': 'work', 'layout_from_default': False}])
def test_lock_holder_owns_session_whatever_the_options(sm, kw):
    sm._owns_session = False
    sm.set_owner_from_options(Opt(**kw))
    assert sm.is_writer()


def test_describe_current_skips_excluded_windows(sm, monkeypatch):
    from terminatorlib.terminator import Terminator

    class W(object):
        def __init__(self, uid, excluded=False):
            self.uid = uid
            self._session_excluded = excluded

        def describe_layout(self, count, parent, layout, order, save_cwd):
            layout['child%d' % count] = {'type': 'Window', 'parent': ''}
            layout['terminal%d' % (count + 1)] = {
                'type': 'Terminal', 'parent': 'child%d' % count,
                'uuid': self.uid}
            return count + 2

        def get_children(self):
            return []
    monkeypatch.setattr(Terminator(), 'windows',
                        [W('keep'), W('drop', excluded=True)])
    layout = sm._describe_current()
    assert [v['uuid'] for v in layout.values()
            if v['type'] == 'Terminal'] == ['keep']


# --- P1-6 exit paths -------------------------------------------------------

def test_sigint_is_hooked(sm, monkeypatch):
    import signal
    from gi.repository import GLib
    seen = []
    monkeypatch.setattr(GLib, 'unix_signal_add',
                        lambda prio, sig, cb, data: seen.append(sig))
    monkeypatch.setattr(sm, '_ensure_periodic', lambda: None)
    sm._signals_installed = False
    sm.install_signal_handlers()
    assert set(seen) >= {signal.SIGTERM, signal.SIGHUP, signal.SIGINT}


def test_script_finalizes_after_main_loop():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, 'terminator'), encoding='utf-8') as fh:
        src = fh.read()
    tail = src[src.index('Gtk.main()'):]
    assert 'finally:' in tail and 'finalize()' in tail
    # Scrollback cache start is outside the session-setup try
    head = src[src.index('# B: start scrollback cache'):]
    assert head.index('ScrollbackCache().start()') < head.index('TERMINATOR.create_layout')


# --- P2: save backoff ------------------------------------------------------

def test_save_failures_back_off(sm, monkeypatch):
    from gi.repository import GLib
    delays = []
    monkeypatch.setattr(GLib, 'timeout_add',
                        lambda ms, cb, *a: delays.append(ms) or 1)
    monkeypatch.setattr(sm, '_any_legacy_zoom', lambda: False)
    sm.mark_dirty('a')
    sm._timer = None
    sm._write_failures = 3
    sm.mark_dirty('b')
    sm._timer = None
    sm._write_failures = 50
    sm.mark_dirty('c')
    assert delays[0] == 1500
    assert delays[1] == 8000
    assert delays[2] == 300000


def test_unwritable_session_counts_failures(sm, tmp_path, monkeypatch):
    target = tmp_path / 'ro'
    target.mkdir()
    os.chmod(str(target), 0o500)
    try:
        monkeypatch.setattr(sm, 'session_path',
                            lambda: str(target / 'sub' / 'session.json'))
        sm._describe_current = lambda: {
            'terminal1': {'type': 'Terminal', 'uuid': 'u'}}
        if os.geteuid() == 0:
            pytest.skip('root ignores permissions')
        assert sm.save_now() is False
        assert sm._write_failures == 1
    finally:
        os.chmod(str(target), 0o700)


# --- P2: dirs 0700 ---------------------------------------------------------

def test_tighten_dir(tmp_path):
    d = tmp_path / 'd'
    d.mkdir()
    os.chmod(str(d), 0o755)
    tighten_dir(str(d))
    assert os.stat(str(d)).st_mode & 0o777 == 0o700


def test_state_dir_is_tightened(sm):
    path = sm.state_dir()
    os.chmod(path, 0o755)
    sm.state_dir()
    assert os.stat(path).st_mode & 0o777 == 0o700


# --- P2: scrollback --------------------------------------------------------

def test_ttl_spares_caches_of_restored_session(sm, tmp_path, monkeypatch):
    from terminatorlib import scrollback as sb
    cache = sb.ScrollbackCache()
    d = tmp_path / 'cache' / 'terminator' / 'scrollback'
    d.mkdir(parents=True)
    keep = '11111111-1111-1111-1111-111111111111'
    orphan = '22222222-2222-2222-2222-222222222222'
    old = time.time() - 30 * 86400
    for u in (keep, orphan):
        p = d / ('%s.txt' % u)
        p.write_text('x')
        os.utime(str(p), (old, old))
    monkeypatch.setattr(cache, '_dir', str(d))
    monkeypatch.setattr(cache, '_ttl_days', lambda: 7)
    monkeypatch.setattr(cache, '_total_mb', lambda: 0)
    sm._loaded_session_uuids = {keep}
    cache.cleanup_startup()
    assert (d / ('%s.txt' % keep)).exists()
    assert not (d / ('%s.txt' % orphan)).exists()


def test_atomic_write_txt_loops_on_short_writes(tmp_path, monkeypatch):
    real_write = os.write
    monkeypatch.setattr(sbt.os, 'write',
                        lambda fd, data: real_write(fd, bytes(data[:3])))
    path = str(tmp_path / 'c.txt')
    sbt.atomic_write_txt(path, b'hello world')
    with open(path, 'rb') as fh:
        assert fh.read() == b'hello world'


def test_atomic_write_txt_zero_write_keeps_old(tmp_path, monkeypatch):
    path = str(tmp_path / 'c.txt')
    sbt.atomic_write_txt(path, b'good')
    monkeypatch.setattr(sbt.os, 'write', lambda fd, data: 0)
    with pytest.raises(OSError):
        sbt.atomic_write_txt(path, b'truncated?')
    with open(path, 'rb') as fh:
        assert fh.read() == b'good'
    assert [n for n in os.listdir(str(tmp_path)) if n.endswith('.tmp')] == []


@pytest.fixture
def sleeper():
    proc = subprocess.Popen(['sleep', '30'])
    yield proc
    proc.kill()
    proc.wait()


class FakeTerm(object):
    def __init__(self, pid=None, profile='default'):
        self.pid = pid
        self.profile = profile
        self.vte = None

    def get_profile(self):
        return self.profile


def test_cache_exclusion_profiles_and_commands(sleeper):
    from terminatorlib.scrollback import cache_exclusion
    cfg = {'scrollback_cache_exclude_profiles': ['secret'],
           'scrollback_cache_exclude_commands': ['/usr/bin/sleep']}
    assert cache_exclusion(FakeTerm(profile='secret'), cfg) == 'profile'
    assert cache_exclusion(FakeTerm(pid=sleeper.pid), cfg) == 'command'
    assert cache_exclusion(FakeTerm(pid=os.getpid()), cfg) is None
    assert cache_exclusion(FakeTerm(profile='secret'), {}) is None


def test_separator_is_english_msgid_and_translated():
    assert all(ord(c) < 0x2E80 for c in sbt.SEPARATOR_TEMPLATE)
    assert 'text' not in sbt.SEPARATOR_TEMPLATE.lower()
    label = sbt.format_separator(None, translate=lambda s: 'T:' + s)
    assert label.startswith('T:')


def test_cache_info_text_does_not_claim_plain_text():
    from terminatorlib.prefseditor import scrollback_cache_info_text
    t = scrollback_cache_info_text('/c', 0, 0, 7, 20)
    assert 'Plain text only' not in t


# --- P2: config /tmp, help text -------------------------------------------

def test_config_has_no_tmp_debug_dump():
    import inspect
    from terminatorlib import config
    assert '/tmp/terminator_configspec' not in inspect.getsource(config)


def test_clear_session_help_text():
    from terminatorlib import optionparse
    import inspect
    src = inspect.getsource(optionparse)
    assert 'then exit setup' not in src
    assert 'before starting' in src


# --- close confirmation ----------------------------------------------------

def test_pid_unknown_does_not_prompt():
    need, procs = cc.should_confirm_processes([FakeTerm(pid=None)])
    assert need is False and procs == []
    need, _ = cc.should_confirm_processes([FakeTerm(pid=-1)])
    assert need is False


def test_exited_child_does_not_prompt(sleeper):
    t = FakeTerm(pid=sleeper.pid)
    assert cc.should_confirm_processes([t])[0] is True
    t.child_exited = True
    assert cc.should_confirm_processes([t])[0] is False


def test_gone_pid_does_not_prompt():
    proc = subprocess.Popen(['true'])
    proc.wait()
    assert cc.should_confirm_processes([FakeTerm(pid=proc.pid)])[0] is False


def test_reused_pid_is_ignored(sleeper):
    pytest.importorskip('psutil')
    t = FakeTerm(pid=sleeper.pid)
    t.spawn_time = time.time() - 3600   # our child started an hour ago
    assert cc.relevant_processes_for_terminal(t) == []
    t.spawn_time = time.time()
    assert cc.relevant_processes_for_terminal(t)


def test_never_ask_disables_process_dialog(sleeper, monkeypatch):
    from terminatorlib.config import Config
    cfg = Config()
    old = cfg['ask_before_closing']
    try:
        cfg['ask_before_closing'] = 'never'
        assert cc.should_confirm_processes([FakeTerm(pid=sleeper.pid)]) \
            == (False, [])
    finally:
        cfg['ask_before_closing'] = old


def test_more_shells_recognised():
    for name in ('nu', 'xonsh', 'elvish', 'pwsh', 'ion', 'mksh', 'yash'):
        assert name in cc.SHELL_BASENAMES


def test_child_exited_handlers_clear_pid():
    from terminatorlib.terminal import Terminal

    class T(object):
        pid = 4242
        child_exited = False
        _note_child_exited = Terminal._note_child_exited

        def held_open(self, respawn=False):
            self.held = True

        def spawn_child(self, respawn=False):
            self.spawned = True

        def emit(self, sig):
            self.emitted = sig
    t = T()
    Terminal._on_child_exited_hold(t, None, 0)
    assert t.pid is None and t.child_exited and t.held
    t = T()
    Terminal._on_child_exited_close(t, None, 0)
    assert t.pid is None and t.emitted == 'close-term'
    t = T()
    Terminal._on_child_exited_restart(t, None, 0)
    assert t.spawned and t.pid is None
