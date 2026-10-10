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
