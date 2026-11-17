"""Scaled zoom enlarges the font on a two-way split.

The old scaler took the smaller of the column ratio and the row ratio,
and gave up when either axis was unchanged. A horizontal or vertical
split only grows one axis, so the pane filled the window and the text
stayed the same size.
"""
import os
import time

import pytest
from gi.repository import Gtk, Pango

from terminatorlib.terminal import zoom_font_scale_factor


def test_one_axis_grows_scales_by_that_axis():
    # Side-by-side: width doubles, height stays. Font must grow.
    factor = zoom_font_scale_factor(600, 800, 1200, 800)
    assert factor == pytest.approx(1.94, abs=0.02)
    # Stacked: height doubles, width stays.
    factor = zoom_font_scale_factor(1200, 400, 1200, 800)
    assert factor == pytest.approx(1.94, abs=0.02)


def test_both_axes_use_the_larger_growth():
    factor = zoom_font_scale_factor(600, 400, 1200, 800)
    assert factor == pytest.approx(1.94, abs=0.02)


def test_unchanged_size_stops_without_scaling():
    assert zoom_font_scale_factor(600, 400, 600, 400) == 1.0
    assert zoom_font_scale_factor(600, 400, 605, 402) == 1.0


def test_mid_reparent_keeps_waiting():
    assert zoom_font_scale_factor(600, 400, 1, 1) is None
    assert zoom_font_scale_factor(600, 400, 40, 30) is None
    assert zoom_font_scale_factor(0, 400, 1200, 800) is None


def test_factor_is_capped():
    assert zoom_font_scale_factor(2, 400, 1200, 800) == 8.0


def _pump(seconds=0.0):
    end = time.monotonic() + seconds
    while True:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        if time.monotonic() >= end:
            break
        time.sleep(0.01)


@pytest.fixture
def zoom_window(monkeypatch):
    """One real window. No child shells, no session quit."""
    from terminatorlib.borg import Borg
    from terminatorlib.factory import Factory
    from terminatorlib.terminal import Terminal
    from terminatorlib.terminator import Terminator
    import terminatorlib.terminator as termmod

    monkeypatch.setattr(Terminal, 'spawn_child', lambda self, *a, **k: True)
    monkeypatch.setattr(termmod.Gtk, 'main_quit', lambda *a: None)
    for name in ('SessionManager', 'ScrollbackCache', 'Config', 'Terminator'):
        Borg._Borg__shared_state.pop(name, None)
    app = Terminator()
    app.terminals = []
    app.windows = []
    app.config['restore_last_session'] = False
    app.config['auto_font_scale'] = True
    app.config['geometry_hinting'] = False
    made = []

    def make(vertical):
        win = Factory().make('Window')
        term = Factory().make('Terminal')
        win.add(term)
        win.resize(1200, 800)
        win.show_all()
        _pump(0.25)
        term.get_parent().split_axis(term, vertical)
        _pump(0.25)
        made.append(win)
        return win

    yield make
    for term in list(Terminator().terminals):
        try:
            Terminator().terminals.remove(term)
        except ValueError:
            pass
    for win in made:
        if not getattr(win, 'isDestroyed', False):
            win._session_destroy_handled = True
            Gtk.Window.destroy(win)
    _pump()
    for name in ('SessionManager', 'ScrollbackCache', 'Config', 'Terminator'):
        Borg._Borg__shared_state.pop(name, None)


def _pt(term):
    return term.vte.get_font().get_size() / Pango.SCALE


def test_two_way_split_zooms_font_and_restores(zoom_window):
    from terminatorlib.terminator import Terminator
    for vertical in (True, False):
        win = zoom_window(vertical)
        term = win.get_terminals()[0]
        before = _pt(term)
        base = term._base_cell
        term.key_scaled_zoom()
        _pump(0.4)
        assert win.is_zoomed()
        assert _pt(term) > before * 1.5
        assert term._auto_font_mode == 'scaled_zoom'
        assert term._base_cell == base
        term.key_scaled_zoom()
        _pump(0.4)
        assert not win.is_zoomed()
        assert _pt(term) == pytest.approx(before, abs=0.2)
        assert len(win.get_terminals()) == 2
        assert len(Terminator().terminals) >= 2
