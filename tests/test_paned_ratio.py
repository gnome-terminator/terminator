"""Layout ratio waits for a real size instead of pinning the bar at 0."""

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import Gdk

import terminatorlib.paned as paned_mod
from terminatorlib.paned import HPaned
from terminatorlib.terminator import Terminator


def _paned(length, handle=8):
    paned = HPaned()
    state = {'length': length}
    positions = []
    paned.get_length = lambda: state['length']
    paned.get_handlesize = lambda: handle
    paned.set_pos = lambda pos: positions.append(pos)
    paned._length = state
    paned._positions = positions
    return paned


def test_empty_queue_defers_until_a_real_size(monkeypatch):
    app = Terminator()
    previous = app.doing_layout
    iterations = []
    try:
        app.doing_layout = True
        paned = _paned(1)
        paned.ratio = 0.25
        monkeypatch.setattr(paned_mod.Gtk, 'events_pending', lambda: False)
        monkeypatch.setattr(
            paned_mod.Gtk, 'main_iteration',
            lambda: iterations.append(1))
        paned.set_position_by_ratio()
        assert iterations == []
        assert paned._positions == []
        assert paned._ratio_size_id
        assert paned.ratio == 0.25
        paned._length['length'] = 400
        paned.ratio = 0.9
        paned.emit('size-allocate', Gdk.Rectangle())
        assert paned._positions == [paned.position_by_ratio(400, 8, 0.25)]
        assert paned.ratio == 0.25
        assert paned._ratio_size_id is None
    finally:
        app.doing_layout = previous


def test_pending_events_are_pumped_at_most_until_the_queue_drains(monkeypatch):
    app = Terminator()
    previous = app.doing_layout
    pending = {'left': 3}
    iterations = []
    try:
        app.doing_layout = True
        paned = _paned(1)
        paned.ratio = 0.5

        def events_pending():
            if pending['left'] > 0:
                pending['left'] -= 1
                return True
            return False

        monkeypatch.setattr(paned_mod.Gtk, 'events_pending', events_pending)
        monkeypatch.setattr(
            paned_mod.Gtk, 'main_iteration',
            lambda: iterations.append(1))
        paned.set_position_by_ratio()
        assert len(iterations) == 3
        assert len(iterations) <= 50
        assert paned._positions == []
        assert paned._ratio_size_id
    finally:
        app.doing_layout = previous


def test_length_growing_during_the_pump_sets_pos_once(monkeypatch):
    app = Terminator()
    previous = app.doing_layout
    steps = {'n': 0}
    try:
        app.doing_layout = True
        paned = _paned(1)
        paned.ratio = 0.25

        def events_pending():
            return steps['n'] < 2

        def main_iteration():
            steps['n'] += 1
            if steps['n'] == 2:
                paned._length['length'] = 800

        monkeypatch.setattr(paned_mod.Gtk, 'events_pending', events_pending)
        monkeypatch.setattr(paned_mod.Gtk, 'main_iteration', main_iteration)
        paned.set_position_by_ratio()
        assert paned._positions == [paned.position_by_ratio(800, 8, 0.25)]
        assert getattr(paned, '_ratio_size_id', None) is None
    finally:
        app.doing_layout = previous
