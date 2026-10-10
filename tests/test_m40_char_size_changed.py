"""m40: runtime cell-size changes (Xft DPI / text scaling / font) must not
leave auto font size working from a stale base cell."""
import types
from unittest import mock

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import GObject, Vte

from terminatorlib import terminal as terminal_mod
from terminatorlib.autofont import base_cell_stale


def test_vte_has_char_size_changed_signal():
    vte = Vte.Terminal()  # signals exist once the class is initialised
    assert GObject.signal_lookup('char-size-changed', type(vte))


def test_stale_exact_at_unit_scale():
    assert not base_cell_stale((10, 20), (10, 20), 1.0)
    assert base_cell_stale((10, 20), (11, 20), 1.0)
    assert base_cell_stale((10, 20), (10, 21), 1.0)


def test_stale_tolerates_rounding_at_tier_scale():
    assert not base_cell_stale((10, 20), (8, 16), 0.8)
    assert not base_cell_stale((10, 20), (9, 17), 0.8)
    # 96 -> 120 dpi (x1.25) while on tier 0.8
    assert base_cell_stale((10, 20), (10, 20), 0.8)


def test_stale_bad_input_is_not_stale():
    assert not base_cell_stale(None, (10, 20), 1.0)
    assert not base_cell_stale((10, 20), None, 1.0)
    assert not base_cell_stale((10, 20), (0, 20), 1.0)
    assert not base_cell_stale((10, 20), (10, 20), 0)
    assert not base_cell_stale(('x', 1), (10, 20), 1.0)


def _term(base, scale, hinting=False, autofont=True, toplevel=None):
    t = types.SimpleNamespace()
    t._base_cell = base
    t.config = {'geometry_hinting': hinting}
    t.titlebar = mock.Mock()
    t.vte = mock.Mock()
    t.vte.get_font_scale.return_value = scale
    t.vte.get_column_count.return_value = 80
    t.vte.get_row_count.return_value = 24
    t._auto_font_enabled = lambda: autofont
    t.get_toplevel = lambda: toplevel
    t.schedule_auto_font_scale = mock.Mock()
    return t


def _call(t, cw, ch):
    terminal_mod.Terminal._on_vte_char_size_changed(t, t.vte, cw, ch)


def test_unit_scale_change_updates_base_and_reschedules():
    t = _term((10, 20), 1.0)
    _call(t, 12, 25)
    assert t._base_cell == (12, 25)
    t.schedule_auto_font_scale.assert_called_once_with()
    t.titlebar.update_terminal_size.assert_called_once_with(80, 24)


def test_own_tier_change_keeps_base():
    t = _term((10, 20), 0.8)
    _call(t, 8, 16)
    assert t._base_cell == (10, 20)
    t.schedule_auto_font_scale.assert_not_called()


def test_dpi_change_at_tier_drops_base():
    t = _term((10, 20), 0.8)
    _call(t, 10, 20)
    assert t._base_cell is None
    t.schedule_auto_font_scale.assert_called_once_with()


def test_no_base_cell_only_refreshes_readout():
    t = _term(None, 1.0)
    _call(t, 12, 25)
    assert t._base_cell is None
    t.schedule_auto_font_scale.assert_not_called()
    t.titlebar.update_terminal_size.assert_called_once()


def test_geometry_hints_refreshed_when_hinting_without_autofont():
    win = mock.Mock(spec=['deferred_set_rough_geometry_hints'])
    t = _term(None, 1.0, hinting=True, autofont=False, toplevel=win)
    _call(t, 9, 18)
    win.deferred_set_rough_geometry_hints.assert_called_once_with()


def test_geometry_hints_not_touched_with_autofont():
    win = mock.Mock(spec=['deferred_set_rough_geometry_hints'])
    t = _term(None, 1.0, hinting=True, autofont=True, toplevel=win)
    _call(t, 9, 18)
    win.deferred_set_rough_geometry_hints.assert_not_called()


def test_hint_failure_does_not_skip_base_check():
    win = mock.Mock(spec=['deferred_set_rough_geometry_hints'])
    win.deferred_set_rough_geometry_hints.side_effect = RuntimeError
    t = _term((10, 20), 1.0, hinting=True, autofont=False, toplevel=win)
    _call(t, 12, 25)
    assert t._base_cell == (12, 25)


def test_zero_signal_args_fall_back_to_vte_metrics():
    t = _term((10, 20), 1.0)
    t.vte.get_char_width.return_value = 11
    t.vte.get_char_height.return_value = 22
    _call(t, 0, 0)
    assert t._base_cell == (11, 22)


def test_real_terminal_connects_handler():
    term = terminal_mod.Terminal()
    try:
        ids = term.cnxids.cnxids.get(term.vte, {})
        assert 'char-size-changed' in ids
    finally:
        term.destroy()
