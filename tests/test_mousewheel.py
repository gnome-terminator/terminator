"""Modifier + wheel: mask tests are parenthesized, and smooth deltas
accumulate per combo."""

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import Gdk

from terminatorlib.terminal import Terminal


class _Event(object):
    def __init__(self, direction, delta_y, state):
        self.direction = direction
        self.delta_y = delta_y
        self.state = state


def _app(term, others, target_terms):
    calls = {'targets': 0}

    class App(object):
        terminals = [term] + list(others)

        def get_target_terms(self, widget):
            calls['targets'] += 1
            return list(target_terms)

    term.terminator = App()
    return calls


def _term(zoom=True):
    term = Terminal.__new__(Terminal)
    term.config = {'disable_mousewheel_zoom': False}
    term.actions = []
    if zoom:
        term.zoom_in = lambda: term.actions.append(('in', term))
        term.zoom_out = lambda: term.actions.append(('out', term))
        term.scroll_by_page = lambda pages: term.actions.append(('page', pages))
    return term


def _peer(name):
    peer = Terminal.__new__(Terminal)
    peer.actions = []
    peer.zoom_in = lambda: peer.actions.append(('in', peer))
    peer.zoom_out = lambda: peer.actions.append(('out', peer))
    return peer


def _wheel(term, direction, delta, state):
    return term.on_mousewheel(None, _Event(direction, delta, state))


def test_control_alone_zooms_this_terminal():
    term = _term()
    peer = _peer('peer')
    grouped = _peer('group')
    calls = _app(term, [peer], [grouped])
    state = Gdk.ModifierType.CONTROL_MASK
    assert _wheel(term, Gdk.ScrollDirection.UP, 0, state) is True
    assert term.actions == [('in', term)]
    assert peer.actions == []
    assert grouped.actions == []
    assert calls['targets'] == 0


def test_shift_alone_pages_this_terminal():
    term = _term()
    calls = _app(term, [], [term])
    state = Gdk.ModifierType.SHIFT_MASK
    assert _wheel(term, Gdk.ScrollDirection.DOWN, 0, state) is True
    assert term.actions == [('page', 1)]
    # Shift still resolves the group before paging this terminal only.
    assert calls['targets'] == 1


def test_control_super_zooms_every_terminal():
    term = _term()
    peer = _peer('peer')
    grouped = _peer('group')
    calls = _app(term, [peer], [grouped])
    state = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD4_MASK
    assert _wheel(term, Gdk.ScrollDirection.UP, 0, state) is True
    assert term.actions == [('in', term)]
    assert peer.actions == [('in', peer)]
    assert grouped.actions == []
    assert calls['targets'] == 0


def test_control_shift_super_zooms_every_terminal_not_the_group():
    term = _term()
    peer = _peer('peer')
    grouped = _peer('group')
    calls = _app(term, [peer], [grouped])
    state = (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
             | Gdk.ModifierType.MOD4_MASK)
    assert _wheel(term, Gdk.ScrollDirection.DOWN, 0, state) is True
    assert ('out', term) in term.actions
    assert peer.actions == [('out', peer)]
    assert grouped.actions == []
    assert calls['targets'] == 0


def test_control_shift_zooms_the_group():
    term = _term()
    peer = _peer('peer')
    grouped = _peer('group')
    calls = _app(term, [peer], [grouped])
    state = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
    assert _wheel(term, Gdk.ScrollDirection.UP, 0, state) is True
    assert term.actions == []
    assert peer.actions == []
    assert grouped.actions == [('in', grouped)]
    assert calls['targets'] == 1


def test_smooth_zoom_accumulates_to_one_step_and_keeps_the_leftover():
    term = _term()
    _app(term, [], [])
    state = Gdk.ModifierType.CONTROL_MASK
    assert _wheel(term, Gdk.ScrollDirection.SMOOTH, -0.6, state) is True
    assert term.actions == []
    assert term._wheel_zoom_remainder == -0.6
    assert _wheel(term, Gdk.ScrollDirection.SMOOTH, -0.6, state) is True
    assert term.actions == [('in', term)]
    assert abs(term._wheel_zoom_remainder - -0.2) < 1e-9


def test_direction_reversal_drops_the_remainder():
    term = _term()
    _app(term, [], [])
    state = Gdk.ModifierType.CONTROL_MASK
    assert _wheel(term, Gdk.ScrollDirection.SMOOTH, 0.6, state) is True
    assert _wheel(term, Gdk.ScrollDirection.SMOOTH, -0.4, state) is True
    assert term.actions == []
    assert abs(term._wheel_zoom_remainder - -0.4) < 1e-9


def test_zoom_and_page_remainders_stay_separate():
    term = _term()
    _app(term, [], [])
    ctrl = Gdk.ModifierType.CONTROL_MASK
    shift = Gdk.ModifierType.SHIFT_MASK
    assert _wheel(term, Gdk.ScrollDirection.SMOOTH, -0.4, ctrl) is True
    assert term._wheel_zoom_remainder == -0.4
    assert _wheel(term, Gdk.ScrollDirection.SMOOTH, 0.4, shift) is True
    assert term._wheel_zoom_remainder == 0.0
    assert term._wheel_page_remainder == 0.4
    assert term.actions == []
    assert _wheel(term, Gdk.ScrollDirection.SMOOTH, 0.7, shift) is True
    assert term.actions == [('page', 1)]
    assert abs(term._wheel_page_remainder - 0.1) < 1e-9


def test_zero_delta_does_not_zoom_or_clear_the_remainder():
    term = _term()
    _app(term, [], [])
    state = Gdk.ModifierType.CONTROL_MASK
    assert _wheel(term, Gdk.ScrollDirection.SMOOTH, -0.6, state) is True
    assert _wheel(term, Gdk.ScrollDirection.SMOOTH, 0, state) is False
    assert term.actions == []
    assert term._wheel_zoom_remainder == -0.6


def test_disabled_zoom_returns_false_for_control_shift():
    term = _term()
    term.config['disable_mousewheel_zoom'] = True
    _app(term, [], [term])
    state = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
    assert _wheel(term, Gdk.ScrollDirection.UP, 0, state) is False
    assert term.actions == []


def test_discrete_steps_do_not_touch_the_remainder():
    term = _term()
    _app(term, [], [])
    state = Gdk.ModifierType.CONTROL_MASK
    assert _wheel(term, Gdk.ScrollDirection.SMOOTH, 0.6, state) is True
    assert _wheel(term, Gdk.ScrollDirection.UP, 0, state) is True
    assert _wheel(term, Gdk.ScrollDirection.DOWN, 0, state) is True
    assert term.actions == [('in', term), ('out', term)]
    assert abs(term._wheel_zoom_remainder - 0.6) < 1e-9


def test_horizontal_discrete_is_ignored():
    term = _term()
    _app(term, [], [])
    state = Gdk.ModifierType.CONTROL_MASK
    assert _wheel(term, Gdk.ScrollDirection.LEFT, 0, state) is False
    assert _wheel(term, Gdk.ScrollDirection.RIGHT, 0, state) is False
    assert term.actions == []


def test_smooth_below_one_still_returns_true():
    term = _term()
    _app(term, [], [])
    state = Gdk.ModifierType.SHIFT_MASK
    assert _wheel(term, Gdk.ScrollDirection.SMOOTH, 0.4, state) is True
    assert term.actions == []
