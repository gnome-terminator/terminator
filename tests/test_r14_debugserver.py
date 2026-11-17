"""r14-1: debug server listens on a user-private AF_UNIX socket."""

import os
import shutil
import socket
import stat
import sys
import tempfile
import threading
import time

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')

import pytest

from terminatorlib import debugserver


@pytest.fixture(autouse=True)
def _restore_stdio():
    # handle() points stdio at the client socket, then back at the real
    # stdio. Put pytest's capture back after the server thread has exited.
    saved = (sys.stdin, sys.stdout, sys.stderr)
    yield
    sys.stdin, sys.stdout, sys.stderr = saved


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def _stop(thread, server):
    """shutdown, join, server_close. A second pass must not hang or raise."""
    if server is None:
        return
    for _ in range(2):
        stopper = threading.Thread(target=server.shutdown)
        stopper.daemon = True
        stopper.start()
        stopper.join(5)
        if stopper.is_alive():
            try:
                server.socket.close()
            except Exception:
                pass
            stopper.join(1)
            break
    if thread is not None:
        thread.join(5)
    server.server_close()
    server.server_close()
    if thread is not None and thread.is_alive():
        raise RuntimeError('debug server thread did not exit')


def _read_line(client):
    client.settimeout(3)
    data = b''
    while b'\n' not in data:
        chunk = client.recv(4096)
        if not chunk:
            break
        data += chunk
        if len(data) > 65536:
            break
    return data


def _welcome_and_restore(addr):
    """Connect, read the banner, close so handle() restores stdio."""
    saved = (sys.stdin, sys.stdout, sys.stderr)
    client = socket.socket(socket.AF_UNIX)
    try:
        client.settimeout(3)
        client.connect(addr)
        data = _read_line(client)
        assert b'terminator' in data
        client.shutdown(socket.SHUT_RDWR)
        client.close()
        deadline = time.time() + 3
        while time.time() < deadline:
            if (sys.stdin is sys.__stdin__ and sys.stdout is sys.__stdout__
                    and sys.stderr is sys.__stderr__):
                break
            time.sleep(0.02)
        else:
            raise AssertionError('handle() did not restore sys.stdout')
        return data
    finally:
        try:
            client.close()
        except Exception:
            pass
        sys.stdin, sys.stdout, sys.stderr = saved


@pytest.fixture
def scratch():
    # sun_path is 108 bytes. pytest's tmp_path plus terminator/debug/...
    # does not fit; keep the socket directory short.
    root = tempfile.mkdtemp(prefix='r14')
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _private_runtime(root, monkeypatch, mode=0o700):
    runtime = os.path.join(root, 'rt')
    os.mkdir(runtime)
    os.chmod(runtime, mode)
    monkeypatch.setenv('XDG_RUNTIME_DIR', runtime)
    monkeypatch.setenv('XDG_CACHE_HOME', os.path.join(root, 'ca'))
    return runtime


def test_handler_has_no_verify_request():
    assert 'verify_request' not in debugserver.PythonConsoleServer.__dict__


def test_runtime_socket_is_private_and_connects(scratch, monkeypatch):
    runtime = _private_runtime(scratch, monkeypatch)
    before = os.lstat(runtime).st_mode
    chmodmed = []
    real_chmod = debugserver.os.chmod

    def _track_chmod(path, mode):
        chmodmed.append(os.path.realpath(path) if isinstance(path, str) else path)
        return real_chmod(path, mode)

    monkeypatch.setattr(debugserver.os, 'chmod', _track_chmod)
    thread, server = debugserver.spawn({})
    try:
        assert thread.name == 'DebugServer'
        assert thread.daemon is True
        assert server.socket.family == socket.AF_UNIX
        addr = server.server_address
        assert isinstance(addr, str)
        assert addr.startswith(str(runtime) + os.sep)
        assert '127.0.0.1' not in addr
        assert _mode(addr) == 0o600
        assert os.path.realpath(str(runtime)) not in chmodmed
        assert os.lstat(runtime).st_mode == before
        _welcome_and_restore(addr)
    finally:
        _stop(thread, server)
    assert not os.path.exists(addr)


def test_replaces_stale_socket(scratch, monkeypatch):
    runtime = _private_runtime(scratch, monkeypatch)
    path = os.path.join(str(runtime), 'terminator-debug-%d.sock' % os.getpid())
    stale = socket.socket(socket.AF_UNIX)
    stale.bind(path)
    stale.close()
    assert stat.S_ISSOCK(os.lstat(path).st_mode)
    thread, server = debugserver.spawn({})
    try:
        assert server.server_address == path
        assert server.socket.family == socket.AF_UNIX
        assert _mode(path) == 0o600
        client = socket.socket(socket.AF_UNIX)
        client.settimeout(3)
        client.connect(path)
        client.close()
    finally:
        _stop(thread, server)
    assert not os.path.exists(path)


def test_refuses_to_replace_regular_file(scratch, monkeypatch):
    runtime = _private_runtime(scratch, monkeypatch)
    path = os.path.join(str(runtime), 'terminator-debug-%d.sock' % os.getpid())
    with open(path, 'w') as fh:
        fh.write('keep')
    with pytest.raises(OSError):
        debugserver.spawn({})
    assert os.path.isfile(path)
    with open(path) as fh:
        assert fh.read() == 'keep'


def test_refuses_to_replace_symlink(scratch, monkeypatch):
    runtime = _private_runtime(scratch, monkeypatch)
    real = os.path.join(scratch, 'real.sock')
    holder = socket.socket(socket.AF_UNIX)
    holder.bind(real)
    holder.close()
    path = os.path.join(str(runtime), 'terminator-debug-%d.sock' % os.getpid())
    os.symlink(str(real), path)
    with pytest.raises(OSError):
        debugserver.spawn({})
    assert os.path.islink(path)
    assert stat.S_ISSOCK(os.stat(real).st_mode)


def test_group_writable_runtime_is_not_used_or_chmodded(scratch, monkeypatch):
    runtime = _private_runtime(scratch, monkeypatch, mode=0o775)
    before = os.lstat(runtime).st_mode
    thread, server = debugserver.spawn({})
    try:
        addr = server.server_address
        assert not addr.startswith(runtime + os.sep)
        debug_dir = os.path.join(scratch, 'ca', 'terminator', 'debug')
        assert addr.startswith(debug_dir + os.sep)
        assert _mode(debug_dir) == 0o700
        assert _mode(addr) == 0o600
        assert os.lstat(runtime).st_mode == before
    finally:
        _stop(thread, server)


def test_symlink_runtime_dir_is_not_used(scratch, monkeypatch):
    real = os.path.join(scratch, 'real-runtime')
    os.mkdir(real)
    os.chmod(real, 0o700)
    link = os.path.join(scratch, 'runtime-link')
    os.symlink(real, link)
    before_link = os.lstat(link).st_mode
    before_real = os.stat(real).st_mode
    monkeypatch.setenv('XDG_RUNTIME_DIR', link)
    monkeypatch.setenv('XDG_CACHE_HOME', os.path.join(scratch, 'ca'))
    thread, server = debugserver.spawn({})
    try:
        addr = server.server_address
        assert not addr.startswith(real + os.sep)
        assert os.lstat(link).st_mode == before_link
        assert os.stat(real).st_mode == before_real
    finally:
        _stop(thread, server)


def test_cache_fallback_socket(scratch, monkeypatch):
    monkeypatch.delenv('XDG_RUNTIME_DIR', raising=False)
    cache = os.path.join(scratch, 'ca')
    monkeypatch.setenv('XDG_CACHE_HOME', cache)
    thread, server = debugserver.spawn({})
    try:
        addr = server.server_address
        debug_dir = os.path.join(cache, 'terminator', 'debug')
        assert addr.startswith(debug_dir + os.sep)
        assert isinstance(addr, str)
        assert '127.0.0.1' not in addr
        assert _mode(debug_dir) == 0o700
        assert _mode(addr) == 0o600
        assert server.socket.family == socket.AF_UNIX
    finally:
        _stop(thread, server)
    assert not os.path.exists(addr)


def test_cache_parent_loses_group_write_only(scratch, monkeypatch):
    monkeypatch.delenv('XDG_RUNTIME_DIR', raising=False)
    parent = os.path.join(scratch, 'ca', 'terminator')
    os.makedirs(parent)
    os.chmod(parent, 0o775)
    monkeypatch.setenv('XDG_CACHE_HOME', os.path.join(scratch, 'ca'))
    thread, server = debugserver.spawn({})
    try:
        assert _mode(parent) == 0o755
        debug_dir = os.path.join(parent, 'debug')
        assert _mode(debug_dir) == 0o700
        assert _mode(server.server_address) == 0o600
    finally:
        _stop(thread, server)


def test_unusable_cache_does_not_listen(scratch, monkeypatch):
    monkeypatch.delenv('XDG_RUNTIME_DIR', raising=False)
    cache = os.path.join(scratch, 'ca')
    os.mkdir(cache)
    blocker = os.path.join(cache, 'terminator')
    with open(blocker, 'w') as fh:
        fh.write('not-a-directory')
    monkeypatch.setenv('XDG_CACHE_HOME', cache)
    assert debugserver.spawn({}) is None
    assert os.listdir(cache) == ['terminator']
    assert os.path.isfile(blocker)


def _terminal(monkeypatch, address):
    from terminatorlib.terminal import Terminal

    class _Vte(object):
        def __init__(self):
            self.sync_args = None
            self.async_args = None

        def spawn_sync(self, *args):
            self.sync_args = args
            return (True, 123)

        def spawn_async(self, *args):
            self.async_args = args
            return 123

        def grab_focus(self):
            pass

        def feed(self, *_args):
            pass

    class _Opt(object):
        command = None
        execute = None
        working_directory = None

    class _Cfg(dict):
        def options_get(self):
            return _Opt()

    class _Term(object):
        def __init__(self):
            self.doing_layout = False
            self.debug_address = address
            self.dbus_name = None
            self.dbus_path = None

    class _Title(object):
        def update(self):
            pass

    class _Uuid(object):
        urn = 'urn:uuid:r14'

    term = Terminal.__new__(Terminal)
    term.__dict__['vte'] = _Vte()
    term.__dict__['config'] = _Cfg({
        'use_custom_command': False,
        'login_shell': False,
        'term': 'xterm-256color',
        'colorterm': 'truecolor',
    })
    term.__dict__['terminator'] = _Term()
    term.__dict__['relaunch_command'] = None
    term.__dict__['layout_command'] = None
    term.__dict__['directory'] = None
    term.__dict__['cwd'] = '/tmp'
    term.__dict__['uuid'] = _Uuid()
    term.__dict__['titlebar'] = _Title()
    term.__dict__['_scrollback_restored'] = True
    term.__dict__['_export_windowid'] = lambda: None
    return term


def test_debug_client_spawn_sync_argv(monkeypatch):
    import terminatorlib.util as util
    monkeypatch.setattr(util, 'is_flatpak', lambda: False)
    path = '/tmp/terminator-debug-r14.sock'
    term = _terminal(monkeypatch, path)
    term.spawn_child(respawn=True, debugserver=True)
    argv = term.vte.sync_args[2]
    assert path in argv
    assert '-c' in argv
    assert not any('telnet' in str(item) for item in argv)
    assert term.vte.async_args is None


def test_flatpak_debug_client_stays_local(monkeypatch):
    import terminatorlib.util as util
    calls = []

    def _flatpak_args(*args):
        calls.append(args)
        return ['flatpak-spawn']

    monkeypatch.setattr(util, 'is_flatpak', lambda: True)
    monkeypatch.setattr(util, 'get_flatpak_args', _flatpak_args)
    path = '/tmp/terminator-debug-r14.sock'
    term = _terminal(monkeypatch, path)
    term.spawn_child(respawn=True, debugserver=True)
    assert calls == []
    assert term.vte.async_args[2][0] == sys.executable
    assert term.vte.sync_args is None


def test_flatpak_normal_spawn_still_wraps(monkeypatch):
    import terminatorlib.util as util
    calls = []

    def _flatpak_args(args, envv, cwd):
        calls.append(list(args))
        return ['flatpak-spawn', '--host'] + list(args)

    monkeypatch.setattr(util, 'is_flatpak', lambda: True)
    monkeypatch.setattr(util, 'get_flatpak_args', _flatpak_args)
    term = _terminal(monkeypatch, None)
    term.spawn_child(respawn=True, debugserver=False)
    assert calls
    assert term.vte.async_args is not None
    assert term.vte.async_args[2][0] == 'flatpak-spawn'
