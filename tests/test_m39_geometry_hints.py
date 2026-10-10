"""m39: geometry hinting path in on_vte_size_allocate.

window.py used GLib without importing it, so with geometry_hinting=True
every size allocation raised NameError and skipped auto font sizing."""
import types
from unittest import mock

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")

from terminatorlib import window as window_mod
from terminatorlib import terminal as terminal_mod


def test_window_module_imports_glib():
    assert hasattr(window_mod, 'GLib')


def _fake_window():
    w = types.SimpleNamespace(pending_set_rough_geometry_hint=False,
                              calls=[])
    w.set_rough_geometry_hints = lambda: w.calls.append('set')
    w.do_deferred_set_rough_geometry_hints = lambda: \
        window_mod.Window.do_deferred_set_rough_geometry_hints(w)
    return w


def test_deferred_hints_schedules_once_and_runs():
    w = _fake_window()
    added = []
    with mock.patch.object(window_mod.GLib, 'idle_add',
                           side_effect=lambda f, *a: added.append(f) or 1):
        window_mod.Window.deferred_set_rough_geometry_hints(w)
        window_mod.Window.deferred_set_rough_geometry_hints(w)
    assert len(added) == 1
    assert added[0]() is False
    assert w.calls == ['set']
    assert w.pending_set_rough_geometry_hint is False


def _fake_terminal(hinting, toplevel):
    t = types.SimpleNamespace()
    t.config = {'geometry_hinting': hinting}
    t.titlebar = mock.Mock()
    t.vte = mock.Mock()
    t.vte.get_column_count.return_value = 80
    t.vte.get_row_count.return_value = 24
    t.get_toplevel = lambda: toplevel
    t._auto_font_on_size_allocate = mock.Mock()
    return t


def test_size_allocate_hinting_on_calls_deferred_and_autofont():
    win = mock.Mock(spec=['deferred_set_rough_geometry_hints',
                          'disable_geometry_hints'])
    t = _fake_terminal(True, win)
    terminal_mod.Terminal.on_vte_size_allocate(t, None, None)
    win.deferred_set_rough_geometry_hints.assert_called_once_with()
    win.disable_geometry_hints.assert_not_called()
    t._auto_font_on_size_allocate.assert_called_once_with()


def test_size_allocate_hinting_off_disables():
    win = mock.Mock(spec=['deferred_set_rough_geometry_hints',
                          'disable_geometry_hints'])
    t = _fake_terminal(False, win)
    terminal_mod.Terminal.on_vte_size_allocate(t, None, None)
    win.disable_geometry_hints.assert_called_once_with()
    t._auto_font_on_size_allocate.assert_called_once_with()


def test_size_allocate_non_window_toplevel_still_autofonts():
    t = _fake_terminal(True, object())
    terminal_mod.Terminal.on_vte_size_allocate(t, None, None)
    t._auto_font_on_size_allocate.assert_called_once_with()


def test_size_allocate_autofont_runs_even_if_hint_raises():
    win = mock.Mock(spec=['deferred_set_rough_geometry_hints'])
    win.deferred_set_rough_geometry_hints.side_effect = RuntimeError('x')
    t = _fake_terminal(True, win)
    try:
        terminal_mod.Terminal.on_vte_size_allocate(t, None, None)
    except RuntimeError:
        pass
    t._auto_font_on_size_allocate.assert_called_once_with()


def test_deferred_size_allocate_is_one_shot():
    t = types.SimpleNamespace(pending_on_vte_size_allocate=True)
    t.on_vte_size_allocate = mock.Mock()
    assert terminal_mod.Terminal.do_deferred_on_vte_size_allocate(
        t, None, None) is False
    assert t.pending_on_vte_size_allocate is False
