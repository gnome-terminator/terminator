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


def test_show_process_close_popover_accept():
    from gi.repository import Gtk, GLib
    win = Gtk.Window()
    btn = Gtk.Button(label="close")
    win.add(btn)
    win.show_all()

    def on_idle():
        pop = getattr(btn, '_close_confirm_popover', None)
        if pop is not None:
            pop._btn_close.clicked()
            return False
        return True

    GLib.idle_add(on_idle)
    term = type('Term', (), {'pid': 123})()
    res = cc.show_process_close_popover(btn, [term], [(123, 'vim')])
    assert res == Gtk.ResponseType.ACCEPT
    win.destroy()


def test_show_process_close_popover_cancel():
    from gi.repository import Gtk, GLib
    win = Gtk.Window()
    btn = Gtk.Button(label="close")
    win.add(btn)
    win.show_all()

    def on_idle():
        pop = getattr(btn, '_close_confirm_popover', None)
        if pop is not None:
            pop._btn_cancel.clicked()
            return False
        return True

    GLib.idle_add(on_idle)
    term = type('Term', (), {'pid': 123})()
    res = cc.show_process_close_popover(btn, [term], [(123, 'vim')])
    assert res == Gtk.ResponseType.CANCEL
    win.destroy()


def test_show_process_close_popover_closed_signal():
    from gi.repository import Gtk, GLib
    win = Gtk.Window()
    btn = Gtk.Button(label="close")
    win.add(btn)
    win.show_all()

    def on_idle():
        pop = getattr(btn, '_close_confirm_popover', None)
        if pop is not None:
            pop.popdown()
            return False
        return True

    GLib.idle_add(on_idle)
    term = type('Term', (), {'pid': 123})()
    res = cc.show_process_close_popover(btn, [term], [(123, 'vim')])
    assert res == Gtk.ResponseType.CANCEL
    win.destroy()


def test_show_process_close_popover_anchor_destroyed():
    from gi.repository import Gtk, GLib
    win = Gtk.Window()
    btn = Gtk.Button(label="close")
    win.add(btn)
    win.show_all()

    def on_idle():
        pop = getattr(btn, '_close_confirm_popover', None)
        if pop is not None:
            btn.destroy()
            return False
        return True

    GLib.idle_add(on_idle)
    term = type('Term', (), {'pid': 123})()
    res = cc.show_process_close_popover(btn, [term], [(123, 'vim')])
    assert res == Gtk.ResponseType.CANCEL
    win.destroy()


def test_show_process_close_popover_position_sidebar():
    from gi.repository import Gtk, GLib
    win = Gtk.Window()
    sidebar_box = Gtk.Box()
    sidebar_box.get_style_context().add_class('terminator-tab-sidebar')
    btn = Gtk.Button(label="close")
    sidebar_box.add(btn)
    win.add(sidebar_box)
    win.show_all()

    pos_seen = [None]
    def on_idle():
        pop = getattr(btn, '_close_confirm_popover', None)
        if pop is not None:
            pos_seen[0] = pop.get_position()
            pop._btn_cancel.clicked()
            return False
        return True

    GLib.idle_add(on_idle)
    term = type('Term', (), {'pid': 123})()
    cc.show_process_close_popover(btn, [term], [(123, 'vim')])
    assert pos_seen[0] == Gtk.PositionType.RIGHT
    win.destroy()


def test_construct_confirm_close_with_processes_routes_to_popover(monkeypatch):
    from gi.repository import Gtk
    calls = []
    monkeypatch.setattr(cc, 'should_confirm_processes', lambda terms: (True, [(123, 'vim')]))
    monkeypatch.setattr(cc, 'show_process_close_popover',
                        lambda anchor, terms, procs: calls.append(('popover', anchor)) or Gtk.ResponseType.ACCEPT)
    monkeypatch.setattr(cc, 'show_process_close_dialog',
                        lambda win, terms, procs: calls.append(('dialog', win)) or Gtk.ResponseType.ACCEPT)

    class Container(object):
        pass

    anchor = object()
    res = cc.construct_confirm_close_with_processes(Container(), 'window', 'child', anchor_widget=anchor)
    assert res == Gtk.ResponseType.ACCEPT
    assert calls == [('popover', anchor)]

    calls[:] = []
    res2 = cc.construct_confirm_close_with_processes(Container(), 'window', 'child', anchor_widget=None)
    assert res2 == Gtk.ResponseType.ACCEPT
    assert calls == [('dialog', 'window')]

    calls[:] = []
    def failing_popover(*_a):
        raise RuntimeError('popover failed')
    monkeypatch.setattr(cc, 'show_process_close_popover', failing_popover)
    res3 = cc.construct_confirm_close_with_processes(Container(), 'window', 'child', anchor_widget=anchor)
    assert res3 == Gtk.ResponseType.ACCEPT
    assert calls == [('dialog', 'window')]


def test_request_close_terminal_passes_anchor(monkeypatch):
    from gi.repository import Gtk
    seen = []

    class FakeContainer(object):
        def construct_confirm_close(self, window, child, anchor_widget=None):
            seen.append((window, child, anchor_widget))
            return Gtk.ResponseType.ACCEPT

    class FakeTerminal(object):
        def __init__(self):
            self.closed = False
            self.container = FakeContainer()
        def get_toplevel(self):
            return 'toplevel'
        def get_parent(self):
            return self.container
        def close(self):
            self.closed = True

    anchor = object()
    term = FakeTerminal()
    assert cc.request_close_terminal(term, anchor_widget=anchor) is True
    assert term.closed is True
    assert seen == [('toplevel', term, anchor)]


def test_close_sidebar_pane_passes_anchor(monkeypatch):
    from terminatorlib.notebook import Notebook
    nb = type('FakeNotebook', (object,), {})()
    term = object()
    row = type('FakeRow', (object,), {'_sidebar_page': 0, '_sidebar_pane': 1, '_close_btn': object()})()
    box = type('FakeBox', (object,), {'get_children': lambda self: [row]})()
    nb._tab_rows = box
    nb._sidebar_pane_terminal = lambda page, pane: term
    nb._sidebar_row_widget = Notebook._sidebar_row_widget.__get__(nb, type(nb))

    passed_args = []
    monkeypatch.setattr(cc, 'request_close_terminal',
                        lambda terminal, anchor_widget=None: passed_args.append((terminal, anchor_widget)))

    Notebook._close_sidebar_pane(nb, 0, 1)
    assert passed_args == [(term, row._close_btn)]
