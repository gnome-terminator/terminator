"""Unit tests for the Wave-style titlebar chrome (sub-plan C)."""

import os
import sys

import gi
import pytest

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
gi.require_version("Gtk", "3.0")

from gi.repository import Gtk, Gdk

from gi.repository import Gio

from terminatorlib import config as _config

# Test-env guard: Config.connect_gsetting_callbacks aborts the process
# (GLib-GIO-ERROR) when the org.gnome.desktop.interface schema is missing.
if 'org.gnome.desktop.interface' not in Gio.Settings.list_schemas():
    _config.Config.connect_gsetting_callbacks = lambda self: None

from terminatorlib import close_confirm
from terminatorlib.editablelabel import EditableLabel
from terminatorlib.terminal_popup_menu import TerminalPopupMenu
from terminatorlib.window import Window


class FakeEvent(object):
    def __init__(self, button, etype, x=1, y=1):
        self.button = button
        self.type = etype
        self.time = 0
        self.x = x
        self.y = y


class FakeConfig(dict):
    pass


def make_config(**extra):
    cfg = FakeConfig({
        'title_hide_sizetext': False,
        'title_use_system_font': True,
        'title_font': '',
        'show_titlebar': True,
        'titlebar_buttons': True,
        'titlebar_density': 'standard',
        'keybindings': {'toggle_zoom': '<Shift><Control>x',
                        'close_term': '<Shift><Control>w'},
    })
    cfg.update(extra)
    cfg.get_system_prop_font = lambda: 'Monospace 10'
    return cfg


class FakeTerminal(object):
    def __init__(self, config=None):
        self.config = config or make_config()
        self.is_held_open = False
        self.group = None
        self.popups = []
        self.focused = 0
        self.maximised = 0
        self.unzoomed = 0

    def grab_focus(self):
        self.focused += 1

    def popup_menu(self, widget, event=None, anchor=None,
                   skip_link_check=False):
        self.popups.append((widget, event, anchor, skip_link_check))

    def maximise(self):
        self.maximised += 1

    def unzoom(self):
        self.unzoomed += 1


@pytest.fixture
def titlebar():
    from terminatorlib.titlebar import Titlebar
    return Titlebar(FakeTerminal())


# --- EditableLabel (D15) -------------------------------------------------

def test_editable_label_double_click_emits_signal_without_editing():
    label = EditableLabel(double_click_edit=False)
    hits = []
    label.connect('double-clicked', lambda *_: hits.append(1))
    handled = label._on_click_text(label, FakeEvent(1, Gdk.EventType._2BUTTON_PRESS))
    assert handled is True
    assert hits == [1]
    assert not label.editing()


def test_editable_label_default_still_edits_on_double_click():
    label = EditableLabel()
    label._on_click_text(label, FakeEvent(1, Gdk.EventType._2BUTTON_PRESS))
    assert label.editing()


def test_editable_label_right_click_bubbles():
    label = EditableLabel(double_click_edit=False)
    assert label._on_click_text(label, FakeEvent(3, Gdk.EventType.BUTTON_PRESS)) is False


# --- Titlebar events ----------------------------------------------------

def test_titlebar_right_click_opens_menu_via_terminal_and_consumes(titlebar):
    event = FakeEvent(3, Gdk.EventType.BUTTON_PRESS)
    assert titlebar.on_button_press(titlebar, event) is True
    term = titlebar.terminal
    assert term.focused == 1
    assert term.popups == [(titlebar, event, None, True)]


def test_titlebar_single_left_click_not_consumed(titlebar):
    assert titlebar.on_button_press(
        titlebar, FakeEvent(1, Gdk.EventType.BUTTON_PRESS)) is False


def test_titlebar_double_click_toggles(titlebar, monkeypatch):
    monkeypatch.setattr(titlebar, '_pane_maximise_state',
                        lambda: (object(), False, True))
    assert titlebar.on_button_press(
        titlebar, FakeEvent(1, Gdk.EventType._2BUTTON_PRESS)) is True
    assert titlebar.terminal.maximised == 1
    monkeypatch.setattr(titlebar, '_pane_maximise_state',
                        lambda multiple=None: (object(), True, False))
    titlebar.label.emit('double-clicked')
    assert titlebar.terminal.unzoomed == 1


def test_toggle_noop_for_single_terminal(titlebar, monkeypatch):
    monkeypatch.setattr(titlebar, '_pane_maximise_state',
                        lambda: (object(), False, False))
    titlebar._toggle_pane_maximise()
    assert titlebar.terminal.maximised == 0
    assert titlebar.terminal.unzoomed == 0


def test_gear_press_opens_anchored_menu(titlebar):
    event = FakeEvent(1, Gdk.EventType.BUTTON_PRESS)
    assert titlebar._on_btn_press(titlebar.btn_gear, event, 'gear') is True
    assert titlebar.terminal.popups == [
        (titlebar.btn_gear, event, titlebar.btn_gear, True)]


def test_close_button_uses_request_close_terminal(titlebar, monkeypatch):
    calls = []
    monkeypatch.setattr(close_confirm, 'request_close_terminal',
                        lambda term: calls.append(term))
    btn = titlebar.btn_close
    titlebar._on_btn_press(btn, FakeEvent(1, Gdk.EventType.BUTTON_PRESS), 'close')
    titlebar._on_btn_release(btn, FakeEvent(1, Gdk.EventType.BUTTON_RELEASE,
                                            x=0, y=0), 'close')
    assert calls == [titlebar.terminal]


def test_menu_close_uses_request_close_terminal(monkeypatch):
    calls = []
    monkeypatch.setattr(close_confirm, 'request_close_terminal',
                        lambda term: calls.append(term))
    popup = TerminalPopupMenu.__new__(TerminalPopupMenu)
    popup.terminal = object()
    popup.close_terminal()
    assert calls == [popup.terminal]


def test_button_right_click_bubbles_and_double_click_swallowed(titlebar):
    btn = titlebar.btn_max
    assert titlebar._on_btn_press(btn, FakeEvent(3, Gdk.EventType.BUTTON_PRESS), 'maximise') is False
    assert titlebar._on_btn_press(btn, FakeEvent(1, Gdk.EventType._2BUTTON_PRESS), 'maximise') is True
    assert titlebar.terminal.maximised == 0


def test_maximise_button_insensitive_outside_window(titlebar):
    titlebar.refresh_maximise_state()
    assert not titlebar.btn_max.get_sensitive()


def test_maximise_icon_follows_state_only(titlebar, monkeypatch):
    monkeypatch.setattr(titlebar, '_pane_maximise_state',
                        lambda multiple=None: (object(), True, False))
    titlebar.refresh_maximise_state()
    assert titlebar.btn_max.get_sensitive()
    assert 'restore' in titlebar.btn_max.get_image().get_icon_name()[0]
    assert 'Ctrl' in titlebar.btn_max.get_tooltip_text()


# --- Scale badge (E API) --------------------------------------------------

def test_scale_badge_visibility(titlebar):
    titlebar.set_scale_badge(None, False)
    assert not titlebar.scale_badge.get_visible()
    titlebar.set_scale_badge(1.0, False)
    assert not titlebar.scale_badge.get_visible()
    titlebar.set_scale_badge(0.9, False)
    assert titlebar.scale_badge.get_visible()
    assert titlebar._badge_label.get_text() == '90%'
    assert not titlebar._badge_lock.get_visible()
    titlebar.set_scale_badge(1.0, True)
    assert titlebar.scale_badge.get_visible()
    assert titlebar._badge_lock.get_visible()


def test_badge_collapses_when_narrow(titlebar):
    titlebar.set_scale_badge(0.8, False)
    titlebar._collapse_level = titlebar._collapse_level_for(100)
    titlebar._apply_collapse()
    assert not titlebar.scale_badge.get_visible()
    titlebar._collapse_level = titlebar._collapse_level_for(1000)
    titlebar._apply_collapse()
    assert titlebar.scale_badge.get_visible()


# --- Chrome config -------------------------------------------------------

def test_density_and_buttons_config():
    from terminatorlib.titlebar import Titlebar
    tb = Titlebar(FakeTerminal(make_config(titlebar_density='bogus',
                                           titlebar_buttons=False)))
    ctx = tb.get_style_context()
    assert ctx.has_class('titlebar-density-standard')
    assert not tb.btn_close.get_visible()
    tb.config['titlebar_density'] = 'compact'
    tb.config['titlebar_buttons'] = True
    tb.apply_chrome_config()
    assert ctx.has_class('titlebar-density-compact')
    assert not ctx.has_class('titlebar-density-standard')
    assert tb.btn_close.get_visible()


def test_sizetext_only_while_timer_pending(titlebar):
    titlebar.termtext = 'shell'
    titlebar.update_terminal_size(80, 24)
    assert '80x24' in titlebar.label.get_text()
    titlebar._clear_sizetext()
    assert '80x24' not in titlebar.label.get_text()


# --- Window helpers (current-tab visible terminals) ----------------------

class FakeWin(object):
    def __init__(self, visible, zoomed=False, zoom_data=None):
        self._visible = visible
        self._zoomed = zoomed
        self.zoom_data = zoom_data

    def get_visible_terminals(self):
        return dict((t, None) for t in self._visible)

    def is_zoomed(self):
        return self._zoomed


def test_has_multiple_terms_counts_current_tab_only():
    a, b = object(), object()
    assert Window.has_multiple_terms(FakeWin([a])) is False
    assert Window.has_multiple_terms(FakeWin([a, b])) is True


def test_is_maximised_pane_shim():
    a, b = object(), object()
    win = FakeWin([a], zoomed=True, zoom_data={'widget': a, 'font_scale': False})
    assert Window.is_maximised_pane(win, a)
    assert not Window.is_maximised_pane(win, b)
    win = FakeWin([a], zoomed=True, zoom_data={'widget': a, 'font_scale': True})
    assert not Window.is_maximised_pane(win, a)
    assert not Window.is_maximised_pane(FakeWin([a]), a)


def test_window_has_pane_maximise_changed_signal():
    from gi.repository import GObject
    assert 'pane-maximise-changed' in GObject.signal_list_names(Window)


# --- Font lock menu hook (E) ---------------------------------------------

def _popup_with(terminal, config):
    popup = TerminalPopupMenu.__new__(TerminalPopupMenu)
    popup.terminal = terminal
    popup.config = config
    return popup


def test_font_lock_item_hidden_without_e():
    menu = Gtk.Menu()
    assert _popup_with(object(), {'auto_font_scale': True}).add_font_lock_item(menu) is None
    assert menu.get_children() == []


def test_font_lock_item_toggles():
    class Term(object):
        locked = False
        def get_auto_font_locked(self):
            return self.locked
        def set_auto_font_locked(self, value):
            self.locked = value
    term = Term()
    menu = Gtk.Menu()
    assert _popup_with(term, {'auto_font_scale': False}).add_font_lock_item(menu) is None
    item = _popup_with(term, {'auto_font_scale': True}).add_font_lock_item(menu)
    item.set_active(True)
    assert term.locked is True
