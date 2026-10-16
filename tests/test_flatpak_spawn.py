"""Flatpak spawn_async reports the pid in the callback, and close()
kills only a positive integer pid."""

import os
import signal

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')

from terminatorlib.signalman import Signalman
from terminatorlib.terminal import Terminal


class _Cfg(object):
    def options_get(self):
        return None

    def __getitem__(self, key):
        return {
            'login_shell': False,
            'use_custom_command': False,
            'term': 'xterm-256color',
            'colorterm': 'truecolor',
        }[key]


class _Vte(object):
    def __init__(self):
        self.spawn_args = None
        self.spawn_return = 99999
        self.fed = []
        self.focused = False

    def grab_focus(self):
        self.focused = True

    def spawn_async(self, *args):
        self.spawn_args = args
        return self.spawn_return

    def feed(self, data):
        self.fed.append(data)


def _terminal():
    term = Terminal.__new__(Terminal)
    term.terminator = type('App', (), {
        'doing_layout': False,
        'dbus_name': None,
        'dbus_path': None,
        'terminals': [object()],
    })()
    term._scrollback_restored = True
    term.vte = _Vte()
    term.config = _Cfg()
    term.relaunch_command = None
    term.layout_command = None
    term.directory = None
    term.cwd = '/home/user'
    term.uuid = type('Uuid', (), {'urn': 'urn:uuid:flatpak-test'})()
    term._export_windowid = lambda: None
    term.titlebar = type('Bar', (), {'update': lambda self: None})()
    term.pid = None
    term.command = None
    return term


def _patch_flatpak(monkeypatch):
    monkeypatch.setattr('terminatorlib.util.is_flatpak', lambda: True)
    monkeypatch.setattr('terminatorlib.util.shell_lookup', lambda: '/bin/bash')
    monkeypatch.setattr(
        'terminatorlib.util.get_flatpak_args',
        lambda args, envv, cwd: ['flatpak-spawn', '--host'] + list(args))


def test_spawn_async_does_not_store_its_return_value(monkeypatch):
    _patch_flatpak(monkeypatch)
    term = _terminal()
    seen = {}

    def spawn_async(*args):
        seen['command_at_call'] = term.command
        seen['args'] = args
        return 99999

    term.vte.spawn_async = spawn_async
    assert term.spawn_child() is None
    assert seen['command_at_call'] == '/bin/bash'
    assert seen['args'][7] == -1
    assert seen['args'][9] == term._on_flatpak_spawned
    assert seen['args'][2][0] == 'flatpak-spawn'
    assert term.pid is None
    assert term.command == '/bin/bash'
    assert term.vte.fed == []


def test_sync_callback_failure_feeds_once(monkeypatch):
    _patch_flatpak(monkeypatch)
    term = _terminal()

    def spawn_async(*args):
        callback = args[9]
        callback(term.vte, -1, object(), None)
        return None

    term.vte.spawn_async = spawn_async
    # The callback already reported the failure, so the trailing feed is skipped.
    assert term.spawn_child() is None
    assert term.pid == -1
    from terminatorlib.translation import _
    assert term.vte.fed == [
        (_('Unable to start shell:') + '/bin/bash').encode('utf-8')]


def test_sync_callback_success_stores_the_wrapper_pid(monkeypatch):
    _patch_flatpak(monkeypatch)
    term = _terminal()

    def spawn_async(*args):
        args[9](term.vte, 4321, None, None)
        return None

    term.vte.spawn_async = spawn_async
    assert term.spawn_child() is None
    assert term.pid == 4321
    assert term.vte.fed == []


def _closable(pid):
    term = Terminal.__new__(Terminal)
    term.pid = pid
    term.terminator = type('App', (), {'terminals': [object(), term]})()
    term.cnxids = Signalman()
    term.vte = object()
    term.terminalbox = type('Box', (), {'remove': lambda self, widget: None})()
    term.get_toplevel = lambda: object()
    term.emit = lambda *args, **kwargs: None
    term._wait_for_shell_exit = lambda *args, **kwargs: None
    return term


def test_close_signals_only_a_positive_pid(monkeypatch):
    killed = []
    monkeypatch.setattr(os, 'kill', lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setattr(
        'terminatorlib.session.SessionManager.finalize',
        lambda self, closing=None: None)
    monkeypatch.setattr(
        'terminatorlib.scrollback.ScrollbackCache.on_terminal_close',
        lambda self, terminal: None)

    for pid in (None, -1, 0):
        killed[:] = []
        _closable(pid).close()
        assert killed == []

    killed[:] = []
    _closable(4321).close()
    assert killed == [(4321, signal.SIGHUP)]
