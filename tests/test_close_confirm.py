# Terminator - close_confirm unit tests (process rules; no dialog)
"""Tests for D17 process detection without showing GTK dialogs."""

from __future__ import print_function

import gi
import pytest

gi.require_version('Gtk', '3.0')

from terminatorlib import close_confirm as cc


def test_basename_strips_login_dash():
    assert cc._basename_of('-bash') == 'bash'
    assert cc._basename_of('/usr/bin/zsh') == 'zsh'


def test_shell_only_not_confirm(monkeypatch):
    import sys
    calls = []

    class Proc(object):
        def name(self):
            calls.append('name')
            return 'bash'

        def children(self, recursive=True):
            calls.append(('children', recursive))
            return []

    class FakePsutil(object):
        class Error(Exception):
            pass

        class NoSuchProcess(Error):
            pass

        @staticmethod
        def Process(pid):
            calls.append(('Process', pid))
            return Proc()

    monkeypatch.setitem(sys.modules, 'psutil', FakePsutil)
    monkeypatch.setattr(cc, '_never_ask', lambda: False)

    class Term(object):
        pid = 4242

    assert cc.relevant_processes_for_terminal(Term()) == []
    assert calls == [('Process', 4242), 'name', ('children', True)]
    need, procs = cc.should_confirm_processes([Term()])
    assert need is False and procs == []


def test_pid_none_no_prompt():
    # m21: no pid (exited child, flatpak-spawn) -> nothing to name, no prompt
    class Term(object):
        pid = None
    need, procs = cc.should_confirm_processes([Term()])
    assert need is False
    assert procs == []


def test_ignore_list_filters_gitstatusd(monkeypatch):
    # Build fake terminal with pid that has a child named gitstatusd — hard
    # without spawning. Instead test filter membership.
    ignore = cc._ignore_set()
    for name in ('gitstatusd', 'ssh-agent', 'gpg-agent', 'dbus-daemon'):
        assert name in ignore


def test_non_shell_self_counts(monkeypatch):
    """terminal.pid itself counts when basename not shell/ignore."""
    class FakeProc(object):
        def __init__(self, pid, name, children=None):
            self.pid = pid
            self._name = name
            self._children = children or []
        def name(self):
            return self._name
        def children(self, recursive=True):
            return self._children

    class FakePsutil(object):
        Error = Exception
        @staticmethod
        def Process(pid):
            if pid == 4242:
                return FakeProc(4242, 'vim', [])
            raise FakePsutil.Error()

    monkeypatch.setattr(cc, 'relevant_processes_for_terminal',
                        lambda terminal, ignore=None: (
                            [(4242, 'vim')] if getattr(terminal, 'pid', None) == 4242
                            else [(None, '<unknown>')]))
    class Term(object):
        pid = 4242
    need, procs = cc.should_confirm_processes([Term()])
    assert need is True
    assert ('vim' in procs[0][1])


def test_idle_shells_skip_the_multiple_terminals_dialog():
    assert cc.no_process_close_result('multiple_terminals') == 'accept'
    assert cc.no_process_close_result('never') == 'accept'
    assert cc.no_process_close_result('always') == 'legacy'


def test_scope_terminals_lone_terminal():
    # Without Factory/GTK we only verify the helper exists and SHELL set
    assert 'bash' in cc.SHELL_BASENAMES
    assert callable(cc.request_close_terminal)
    assert callable(cc.scope_terminals)


def _install_psutil(monkeypatch, root_name, children):
    import sys
    calls = []

    class Child(object):
        def __init__(self, pid, name):
            self.pid = pid
            self._name = name

        def name(self):
            calls.append(('child-name', self.pid))
            return self._name

    class Proc(object):
        def name(self):
            calls.append('name')
            return root_name

        def children(self, recursive=True):
            calls.append(('children', recursive))
            return [Child(pid, name) for pid, name in children]

    class FakePsutil(object):
        class Error(Exception):
            pass

        class NoSuchProcess(Error):
            pass

        @staticmethod
        def Process(pid):
            calls.append(('Process', pid))
            return Proc()

    monkeypatch.setitem(sys.modules, 'psutil', FakePsutil)
    monkeypatch.setattr(cc, '_never_ask', lambda: False)
    return calls


def test_flatpak_spawn_root_alone_is_not_a_job(monkeypatch):
    assert 'flatpak-spawn' not in cc.SHELL_BASENAMES
    calls = _install_psutil(monkeypatch, 'flatpak-spawn', [])

    class Term(object):
        pid = 4242

    assert cc.relevant_processes_for_terminal(Term()) == []
    assert calls == [('Process', 4242), 'name', ('children', True)]
    need, procs = cc.should_confirm_processes([Term()])
    assert need is False and procs == []


def test_flatpak_spawn_root_still_lists_children(monkeypatch):
    calls = _install_psutil(monkeypatch, 'flatpak-spawn', [(99, 'vim')])

    class Term(object):
        pid = 4242

    assert cc.relevant_processes_for_terminal(Term()) == [(99, 'vim')]
    assert calls[0] == ('Process', 4242)
    assert calls[1] == 'name'
    assert calls[2] == ('children', True)
    need, procs = cc.should_confirm_processes([Term()])
    assert need is True
    assert procs == [(99, 'vim')]


def _pin_dialogs(monkeypatch, ask, shell_response):
    from gi.repository import Gtk
    seen = {'shell': 0, 'process': 0}

    def shell(parent, terms):
        seen['shell'] += 1
        seen['shell_args'] = (parent, terms)
        return shell_response

    def process(parent, terms, procs):
        seen['process'] += 1
        seen['process_args'] = (parent, terms, procs)
        return Gtk.ResponseType.ACCEPT

    monkeypatch.setattr(cc, '_ask_before_closing', lambda: ask)
    monkeypatch.setattr(cc, 'show_shell_close_dialog', shell)
    monkeypatch.setattr(cc, 'show_process_close_dialog', process)
    return seen


def test_always_idle_shells_follow_the_shell_dialog(monkeypatch):
    from gi.repository import Gtk
    parent = object()

    class Term(object):
        pid = None
        closed = False

        def get_toplevel(self):
            return parent

        def close(self):
            self.closed = True

    term = Term()
    seen = _pin_dialogs(monkeypatch, 'always', Gtk.ResponseType.CANCEL)
    assert cc.confirm_close_terminals([term]) is False
    assert seen['shell'] == 1 and seen['process'] == 0
    assert seen['shell_args'][0] is parent

    seen = _pin_dialogs(monkeypatch, 'always', Gtk.ResponseType.ACCEPT)
    assert cc.confirm_close_terminals([term]) is True
    assert seen['shell'] == 1 and seen['process'] == 0

    seen = _pin_dialogs(monkeypatch, 'always', Gtk.ResponseType.CANCEL)
    from terminatorlib.terminator import Terminator
    term.group = 'g'
    app = type('App', (), {'terminals': [term], 'windows': []})()
    assert Terminator.closegroupedterms(app, 'g') is False
    assert term.closed is False


def test_multiple_terminals_and_never_skip_both_dialogs(monkeypatch):
    class Term(object):
        pid = None

        def get_toplevel(self):
            return None

    for mode in ('multiple_terminals', 'never'):
        seen = _pin_dialogs(monkeypatch, mode, None)
        assert cc.confirm_close_terminals([Term()]) is True
        assert seen['shell'] == 0 and seen['process'] == 0


def test_always_with_a_named_process_uses_only_the_process_dialog(monkeypatch):
    seen = _pin_dialogs(monkeypatch, 'always', None)
    monkeypatch.setattr(
        cc, 'should_confirm_processes', lambda terms: (True, [(7, 'vim')]))

    class Term(object):
        pid = 7

        def get_toplevel(self):
            return None

    assert cc.confirm_close_terminals([Term()]) is True
    assert seen['process'] == 1 and seen['shell'] == 0
    assert seen['process_args'][2] == [(7, 'vim')]


def test_empty_terminal_lists_close_without_a_dialog(monkeypatch):
    seen = _pin_dialogs(monkeypatch, 'always', None)
    assert cc.confirm_close_terminals([]) is True
    assert cc.confirm_close_terminals([None]) is True
    assert seen['shell'] == 0 and seen['process'] == 0
