"""Tests for top-level window title ownership and coalescing (WindowTitle)."""

import os
import sys

import gi

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
gi.require_version("Gtk", "3.0")

import pytest

from terminatorlib.window import WindowTitle, terminal_for_widget


class FakeClock:
    """Stand-in for GLib.timeout_add/source_remove."""

    def __init__(self):
        self.sources = {}
        self.next_id = 1
        self.delays = []

    def timeout_add(self, delay, callback):
        sid = self.next_id
        self.next_id += 1
        self.sources[sid] = callback
        self.delays.append(delay)
        return sid

    def source_remove(self, sid):
        self.sources.pop(sid, None)

    def fire(self):
        for sid, callback in list(self.sources.items()):
            self.sources.pop(sid, None)
            callback()


class FakeWindow:
    """Record titles passed to the native window."""

    def __init__(self):
        self.titles = []
        self.focus = None
        self.terminator = None
        self.isDestroyed = False

    def set_title(self, title):
        self.titles.append(title)

    def get_title(self):
        return self.titles[-1] if self.titles else None

    def get_focus(self):
        return self.focus


class FakeVte:
    def __init__(self, terminal, focused=False):
        self.terminal = terminal
        self.focused = focused

    def is_focus(self):
        return self.focused

    def get_parent(self):
        return self.terminal


class FakeTerminal:
    """Duck-types the bits of Terminal that WindowTitle uses."""

    def __init__(self, window, name, focused=False):
        self.window = window
        self.name = name
        self.title = name
        self.vte = FakeVte(self, focused)

    def get_vte(self):
        return self.vte

    def get_toplevel(self):
        return self.window

    def get_parent(self):
        return self.window

    def get_window_title(self):
        return self.title

    def osc(self, wt, text):
        self.title = text
        wt.set_title(self, text)


def make(config=None):
    window = FakeWindow()
    clock = FakeClock()
    cfg = {'window_title_mode': 'focused', 'window_title_fixed': 'Terminator'}
    cfg.update(config or {})
    wt = WindowTitle(window, config=cfg, timeout_add=clock.timeout_add,
                     source_remove=clock.source_remove)
    return window, clock, wt


def test_background_terminals_cannot_override_window_title():
    window, clock, wt = make()
    a, b, c = (FakeTerminal(window, n) for n in 'abc')
    wt.focus_changed(a)
    clock.fire()
    for i in range(50):
        b.osc(wt, 'b %d' % i)
        c.osc(wt, 'c %d' % i)
    clock.fire()
    assert window.titles == ['a']
    a.osc(wt, 'a 1')
    clock.fire()
    assert window.titles == ['a', 'a 1']


def test_owner_title_applies_even_when_vte_lacks_focus():
    """Focus on a titlebar button / overlay chrome must not freeze the title
    (the old is_focus() guard dropped these)."""
    window, clock, wt = make()
    a = FakeTerminal(window, 'a', focused=False)
    b = FakeTerminal(window, 'b', focused=False)
    wt.focus_changed(a)
    a.osc(wt, 'vim foo')
    b.osc(wt, 'b junk')
    clock.fire()
    assert window.get_title() == 'vim foo'


def test_osc_updates_are_coalesced_into_single_source():
    window, clock, wt = make()
    a = FakeTerminal(window, 'a')
    wt.focus_changed(a)
    clock.fire()
    for i in range(100):
        a.osc(wt, 'prompt %d' % i)
    assert len(clock.sources) == 1
    assert clock.delays[-1] == WindowTitle.DEBOUNCE_MS
    assert window.titles == ['a']          # nothing applied synchronously
    clock.fire()
    assert window.titles == ['a', 'prompt 99']


def test_unchanged_title_is_not_reapplied():
    window, clock, wt = make()
    a = FakeTerminal(window, 'a')
    wt.focus_changed(a)
    clock.fire()
    a.osc(wt, 'x')
    clock.fire()
    a.osc(wt, 'y')
    a.osc(wt, 'x')
    clock.fire()
    assert window.titles == ['a', 'x']


def test_focus_change_takes_title_once_from_new_owner():
    window, clock, wt = make()
    a, b = FakeTerminal(window, 'a'), FakeTerminal(window, 'b')
    wt.focus_changed(a)
    clock.fire()
    a.osc(wt, 'a busy')               # pending debounce from a
    b.title = 'b idle'
    wt.focus_changed(b)               # re-arms with short focus delay
    assert len(clock.sources) == 1
    assert clock.delays[-1] == WindowTitle.FOCUS_DELAY_MS
    clock.fire()
    assert window.get_title() == 'b idle'
    a.osc(wt, 'a again')
    clock.fire()
    assert window.get_title() == 'b idle'
    # focus_changed for the current owner is a no-op
    wt.focus_changed(b)
    assert not clock.sources


def test_transient_focus_hops_collapse_to_final_owner():
    """Tab switch: Gtk focuses the first pane, then Terminator refocuses the
    last active one - the window must not flicker through the first."""
    window, clock, wt = make()
    a, b = FakeTerminal(window, 'a'), FakeTerminal(window, 'b')
    wt.focus_changed(b)
    clock.fire()
    wt.focus_changed(a)
    wt.focus_changed(b)
    clock.fire()
    assert window.titles == ['b']


def test_owner_closed_falls_back_to_focused_terminal():
    window, clock, wt = make()
    a, b = FakeTerminal(window, 'a'), FakeTerminal(window, 'b')
    wt.focus_changed(a)
    clock.fire()
    a.window = None                   # removed from the window
    window.focus = b.vte              # Gtk moved focus to the sibling
    wt.terminal_removed(a)
    clock.fire()
    assert wt.owner is b
    assert window.get_title() == 'b'


def test_stale_owner_detected_on_next_title_change():
    """Owner detached to another window without notification."""
    window, clock, wt = make()
    a, b = FakeTerminal(window, 'a'), FakeTerminal(window, 'b')
    wt.focus_changed(a)
    clock.fire()
    a.window = object()
    window.focus = b.vte
    a.osc(wt, 'a elsewhere')
    b.osc(wt, 'b here')
    clock.fire()
    assert wt.owner is b
    assert window.get_title() == 'b here'


def test_focus_change_ignores_foreign_terminal():
    window, clock, wt = make()
    a = FakeTerminal(window, 'a')
    other = FakeTerminal(object(), 'other')
    wt.focus_changed(a)
    wt.focus_changed(other)
    assert wt.owner is a


def test_fixed_mode_ignores_terminals():
    window, clock, wt = make({'window_title_mode': 'fixed',
                              'window_title_fixed': 'Work'})
    a = FakeTerminal(window, 'a')
    wt.update()
    wt.focus_changed(a)
    a.osc(wt, 'a busy')
    clock.fire()
    assert window.titles == ['Work']


def test_bad_mode_value_falls_back_to_focused():
    window, clock, wt = make({'window_title_mode': 'bogus'})
    assert wt.mode() == 'focused'


def test_force_title_has_precedence_and_unforce_restores_owner():
    window, clock, wt = make({'window_title_mode': 'fixed'})
    a = FakeTerminal(window, 'a')
    wt.focus_changed(a)
    wt.force_title('Forced')
    assert window.get_title() == 'Forced'
    a.osc(wt, 'a busy')
    clock.fire()
    assert window.get_title() == 'Forced'
    wt._config['window_title_mode'] = 'focused'
    wt.force_title(None)
    assert window.get_title() == 'a busy'


def test_initial_title_is_not_literal_none():
    window, clock, wt = make()
    wt.update()
    assert window.titles == ['Terminator']


def test_destroy_cancels_pending_source():
    window, clock, wt = make()
    a = FakeTerminal(window, 'a')
    wt.focus_changed(a)
    clock.fire()
    a.osc(wt, 'later')
    assert clock.sources
    wt.destroy()
    assert not clock.sources
    a.osc(wt, 'after destroy')
    assert not clock.sources
    assert window.titles == ['a']


def test_terminal_for_widget_walks_up_from_vte():
    window = FakeWindow()
    a = FakeTerminal(window, 'a')
    assert terminal_for_widget(a.vte) is a
    assert terminal_for_widget(None) is None
    assert terminal_for_widget(window) is None


def test_config_defaults_present():
    from terminatorlib.config import DEFAULTS
    assert DEFAULTS['global_config']['window_title_mode'] == 'focused'
    assert DEFAULTS['global_config']['window_title_fixed'] == 'Terminator'


# -- review follow-ups -------------------------------------------------------

def test_programmatic_title_does_not_override_forced_title():
    window, clock, wt = make()
    wt.force_title('pinned')
    wt.set_title(None, 'plugin text')
    clock.fire()
    assert window.get_title() == 'pinned'


def test_focus_unset_after_owner_detached_hands_title_on():
    """Owner detached to another window: Gtk unsets the focus widget
    (set-focus None) and revalidate() must move the title to the fallback."""
    window, clock, wt = make()
    a, b = FakeTerminal(window, 'a'), FakeTerminal(window, 'b')
    wt.focus_changed(a)
    clock.fire()
    a.window = object()               # now lives in another toplevel
    window.focus = b.vte
    wt.revalidate()
    clock.fire()
    assert wt.owner is b
    assert window.get_title() == 'b'


def test_revalidate_keeps_live_owner():
    window, clock, wt = make()
    a, b = FakeTerminal(window, 'a'), FakeTerminal(window, 'b')
    wt.focus_changed(a)
    clock.fire()
    window.focus = b.vte
    wt.revalidate()
    assert wt.owner is a
    assert not wt.pending()


def _real_window():
    from terminatorlib.factory import Factory
    return Factory().make('Window')


def _window_layout(window):
    layout = {}
    window.describe_layout(0, 'root', layout, 0)
    return layout['child0']


def test_layout_omits_dynamic_window_title():
    """Saving a layout must not store the terminal-driven title, otherwise
    create_layout() force_title()s it and pins the window title forever."""
    window = _real_window()
    try:
        window.title.text = 'vim notes.txt'
        window.title.forced = False
        assert 'title' not in _window_layout(window)
        window.title.force_title('My Project')
        assert _window_layout(window)['title'] == 'My Project'
        window.title.force_title(None)
        assert 'title' not in _window_layout(window)
    finally:
        window.title.destroy()
        window.terminator.deregister_window(window)
        window.isDestroyed = True


def test_layout_omits_cli_forced_title():
    """-T/--title is forced for this run only; it must not be saved."""
    window = _real_window()
    try:
        window.title.force_title('one-off', persist=False)
        assert window.title.forced
        assert 'title' not in _window_layout(window)
        window.title.force_title('Mine')
        assert _window_layout(window)['title'] == 'Mine'
    finally:
        window.title.destroy()
        window.terminator.deregister_window(window)
        window.isDestroyed = True


def test_force_title_marks_session_dirty(monkeypatch):
    import terminatorlib.session as session
    calls = []
    monkeypatch.setattr(session, 'try_mark_dirty',
                        lambda reason='': calls.append(reason))
    window, clock, wt = make()
    wt.force_title('A')
    wt.force_title('A')          # unchanged: no extra save
    wt.force_title(None)
    wt.force_title('cli', persist=False)
    wt.force_title(None)         # was not persisted: nothing to save
    assert calls == ['window-title', 'window-title']


def test_header_bar_matches_gnome_terminal_actions():
    from terminatorlib.window import Window

    class Host(object):
        _borderless = False
        _header_title_bound = True
        _header_button = Window._header_button
        _on_header_new_tab = Window._on_header_new_tab
        _on_header_tab_panel_toggled = Window._on_header_tab_panel_toggled
        _on_header_find = Window._on_header_find
        _on_header_menu = Window._on_header_menu

        def set_titlebar(self, bar):
            self.installed = bar

        def get_title(self):
            return 'Shallow Clone Install'

        def connect(self, *_args):
            return 0

    host = Host()
    Window._install_header_bar(host)
    assert host.installed is host._header_bar
    assert host._header_bar.get_show_close_button() is True
    assert host._header_new_tab.get_parent() is not None
    assert host._header_find.get_parent() is not None
    assert host._header_menu.get_parent() is not None

    skipped = Host()
    skipped._borderless = True
    Window._install_header_bar(skipped)
    assert not hasattr(skipped, 'installed')

    class Term(object):
        def __init__(self):
            self.searched = False
            self.menu = None

        def key_search(self):
            self.searched = True

        def popup_menu(self, widget, anchor=None, skip_link_check=False):
            self.menu = (widget, anchor, skip_link_check)

    class Win(object):
        def __init__(self):
            self.term = Term()
            self.made = None

        def _header_terminal(self):
            return self.term

        def tab_new(self, widget=None):
            self.made = widget

    win = Win()
    Window._on_header_find(win, None)
    Window._on_header_menu(win, 'menu-button')
    assert win.term.searched is True
    assert win.term.menu == ('menu-button', 'menu-button', True)

    class NB(object):
        def __init__(self):
            self.shown = True
            self.pos = None

        def get_show_tabs(self):
            return self.shown

        def set_show_tabs(self, value):
            self.shown = bool(value)

        def set_tab_pos(self, pos):
            self.pos = pos

    class Panel(object):
        def __init__(self):
            self.nb = NB()
            self.config = {'tab_position': 'left'}

        def is_child_notebook(self):
            return True

        def get_child(self):
            return self.nb

        _sync_tab_panel_button = Window._sync_tab_panel_button

    panel = Panel()
    Window._set_tab_panel_visible(panel, False)
    assert panel.nb.shown is False
    Window._set_tab_panel_visible(panel, True)
    assert panel.nb.shown is True


def test_header_title_sync_does_not_recurse():
    """notify::title must not loop with HeaderBar.set_title."""
    from gi.repository import Gtk
    from terminatorlib.window import Window

    class Host(Gtk.Window):
        _borderless = False
        _header_button = Window._header_button
        _on_header_new_tab = Window._on_header_new_tab
        _on_header_tab_panel_toggled = Window._on_header_tab_panel_toggled
        _on_header_find = Window._on_header_find
        _on_header_menu = Window._on_header_menu
        _sync_header_title = Window._sync_header_title

    win = Host()
    Window._install_header_bar(win)
    assert win._header_bar.get_visible() is True
    win.set_title('layout title')
    assert win._header_bar.get_title() == 'layout title'
    win.set_title('another title')
    assert win._header_bar.get_title() == 'another title'
    win.destroy()
