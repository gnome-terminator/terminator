"""M36: the left-hand terminal/grouping icon of pane title bars is hidden
by default (titlebar_show_icon=False); grouping stays reachable and the
broadcast state gets a text indication."""
import os
import sys
import time

import gi
import pytest

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
gi.require_version("Gtk", "3.0")

from gi.repository import Gtk, Gdk, Gio

from terminatorlib import config as _config

if 'org.gnome.desktop.interface' not in Gio.Settings.list_schemas():
    _config.Config.connect_gsetting_callbacks = lambda self: None

from tests.test_titlebar_chrome import FakeTerminal, FakeEvent, make_config


def _pump(seconds=0.0):
    end = time.monotonic() + seconds
    while True:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        if time.monotonic() >= end:
            break
        time.sleep(0.01)


_COLOURS = {k: v for k, v in _config.DEFAULTS['profiles']['default'].items()
            if k.startswith('title_') and k.endswith('_color')}


def _tb(**extra):
    from terminatorlib.titlebar import Titlebar
    cfg = dict(_COLOURS)
    cfg.update(extra)
    tb = Titlebar(FakeTerminal(make_config(**cfg)))
    # Fake terminals have no VTE style context; keep the titlebar shown
    tb.get_desired_visibility = lambda: True
    return tb


class _Other(object):
    group = None


def test_config_default_is_false():
    assert _config.DEFAULTS['global_config']['titlebar_show_icon'] is False


def test_icons_hidden_by_default():
    tb = _tb(titlebar_show_icon=False)
    assert tb.termicon.get_visible() is False
    assert tb.groupicon.get_visible() is False
    # no dangling separator when nothing is left of the title
    assert tb._group_sep.get_visible() is False


def test_missing_key_means_hidden():
    from terminatorlib.titlebar import Titlebar
    tb = Titlebar(FakeTerminal(make_config()))  # FakeConfig without the key -> default hidden
    assert tb.groupicon.get_visible() is False
    assert tb.termicon.get_visible() is False


def test_icons_shown_when_enabled_and_toggle_live():
    tb = _tb(titlebar_show_icon=True)
    assert tb.groupicon.get_visible() is True
    if tb._termicon_ok:
        assert tb.termicon.get_visible() is True
    assert tb._group_sep.get_visible() is True
    tb.config['titlebar_show_icon'] = False
    tb.apply_chrome_config()
    assert tb.groupicon.get_visible() is False
    assert tb.termicon.get_visible() is False
    tb.config['titlebar_show_icon'] = True
    tb.apply_chrome_config()
    assert tb.groupicon.get_visible() is True


def test_update_does_not_resurrect_icon():
    tb = _tb(titlebar_show_icon=False)
    tb.update(tb.terminal)  # active terminal path sets an icon name
    assert tb.groupicon.get_visible() is False
    tb.update(_Other())
    assert tb.groupicon.get_visible() is False


def _set_groupsend(monkeypatch, tb, mode):
    monkeypatch.setattr(tb.terminator, 'groupsend',
                        tb.terminator.groupsend_type[mode])


def test_broadcast_text_on_sender_when_icon_hidden(monkeypatch):
    tb = _tb(titlebar_show_icon=False)
    _set_groupsend(monkeypatch, tb, 'all')
    tb.update(tb.terminal)
    assert tb.broadcastlabel.get_text() == 'Broadcast: all'
    assert tb.broadcastlabel.get_visible() is True
    assert tb._group_sep.get_visible() is True
    _set_groupsend(monkeypatch, tb, 'off')
    tb.update(tb.terminal)
    assert tb.broadcastlabel.get_visible() is False
    assert tb._group_sep.get_visible() is False


def test_group_broadcast_text_needs_a_group(monkeypatch):
    tb = _tb(titlebar_show_icon=False)
    _set_groupsend(monkeypatch, tb, 'group')
    tb.update(tb.terminal)
    assert tb.broadcastlabel.get_visible() is False
    tb.terminal.group = 'g1'
    tb.update(tb.terminal)
    assert tb.broadcastlabel.get_text() == 'Broadcast: group'
    assert tb.broadcastlabel.get_visible() is True


def test_receiver_gets_no_broadcast_text(monkeypatch):
    tb = _tb(titlebar_show_icon=False)
    _set_groupsend(monkeypatch, tb, 'all')
    tb.update(_Other())
    assert tb.broadcastlabel.get_visible() is False


def test_no_broadcast_text_when_icon_shown(monkeypatch):
    tb = _tb(titlebar_show_icon=True)
    _set_groupsend(monkeypatch, tb, 'all')
    tb.update(tb.terminal)
    assert tb.broadcastlabel.get_visible() is False


def test_group_name_still_shown_and_separator(monkeypatch):
    tb = _tb(titlebar_show_icon=False)
    tb.set_group_label('work')
    assert tb.grouplabel.get_visible() is True
    assert tb._group_sep.get_visible() is True
    tb.set_group_label(None)
    assert tb._group_sep.get_visible() is False


def test_narrow_collapse_hides_broadcast_and_group(monkeypatch):
    tb = _tb(titlebar_show_icon=False)
    _set_groupsend(monkeypatch, tb, 'all')
    tb.set_group_label('work')
    tb.update(tb.terminal)
    tb._collapse_level = tb._collapse_level_for(tb.COLLAPSE_GROUP_PX - 1)
    tb._apply_collapse()
    assert tb.broadcastlabel.get_visible() is False
    assert tb.grouplabel.get_visible() is False
    # gear/max still follow their own thresholds
    assert tb.btn_gear.get_visible() is True
    tb._collapse_level = tb._collapse_level_for(tb.COLLAPSE_MAX_PX - 1)
    tb._apply_collapse()
    assert tb.btn_gear.get_visible() is False
    assert tb.btn_max.get_visible() is False
    assert tb.btn_close.get_visible() is True
    tb._collapse_level = 0
    tb._apply_collapse()
    assert tb.broadcastlabel.get_visible() is True
    assert tb.grouplabel.get_visible() is True


def test_group_box_click_still_wired():
    """The group box (now group name / broadcast text) keeps the click
    handler that opens the grouping menu."""
    tb = _tb(titlebar_show_icon=False)
    hits = []
    tb.connect_icon(lambda w, e: hits.append(e) or True)
    ev = Gdk.Event.new(Gdk.EventType.BUTTON_PRESS)
    ev.button.button = 1
    tb.ebox.emit('button-press-event', ev)
    assert len(hits) == 1


# --- context menu ---------------------------------------------------------

@pytest.fixture
def win(monkeypatch):
    from terminatorlib.terminal import Terminal
    from terminatorlib.terminator import Terminator
    from terminatorlib.factory import Factory
    monkeypatch.setattr(Terminal, 'spawn_child', lambda self, *a, **k: True)
    monkeypatch.setattr(Terminator(), 'terminals', [])
    monkeypatch.setattr(Terminator(), 'windows', [])
    w = Factory().make('Window')
    t = Factory().make('Terminal')
    w.add(t)
    w.resize(800, 500)
    w.show_all()
    _pump(0.2)
    yield w
    for term in list(Terminator().terminals):
        if term.get_toplevel() is w:
            Terminator().deregister_terminal(term)
    if not getattr(w, 'isDestroyed', False):
        w.destroy()
    _pump()


def _menu_labels(monkeypatch, term):
    from terminatorlib.terminal_popup_menu import TerminalPopupMenu
    captured = []
    monkeypatch.setattr(Gtk.Menu, 'popup_at_pointer',
                        lambda self, *a: captured.append(self))
    monkeypatch.setattr(Gtk.Menu, 'popup_at_widget',
                        lambda self, *a: captured.append(self))
    TerminalPopupMenu(term).show(term, None, skip_link_check=True)
    assert captured
    menu = captured[-1]
    labels = [i.get_label() for i in menu.get_children()
              if isinstance(i, Gtk.MenuItem)
              and not isinstance(i, Gtk.SeparatorMenuItem)]
    return labels


def test_real_terminal_icons_hidden_and_menu_has_grouping(win, monkeypatch):
    from terminatorlib.config import Config
    cfg = Config()
    term = list(win.get_terminals())[0]
    old = cfg['titlebar_show_icon']
    try:
        cfg['titlebar_show_icon'] = False
        term.titlebar.apply_chrome_config()
        assert term.titlebar.groupicon.get_visible() is False
        assert term.titlebar.termicon.get_visible() is False
        assert cfg['show_titlebar'] is True
        assert 'Grouping' in _menu_labels(monkeypatch, term)
        cfg['titlebar_show_icon'] = True
        term.titlebar.apply_chrome_config()
        assert term.titlebar.groupicon.get_visible() is True
        # icon is clickable again -> menu keeps upstream behaviour
        assert 'Grouping' not in _menu_labels(monkeypatch, term)
    finally:
        cfg['titlebar_show_icon'] = old


def test_prefs_checkbox(monkeypatch):
    from terminatorlib.prefseditor import PrefsEditor
    from terminatorlib import prefseditor
    gl = os.path.join(os.path.dirname(prefseditor.__file__),
                      'preferences.glade')
    builder = Gtk.Builder()
    builder.add_from_file(gl)
    cb = builder.get_object('titlebar_show_icon_checkbutton')
    assert cb is not None
    assert cb.get_label() == 'Show icon at the left of terminal title bars'
    # shares the Panes > Title bars grid
    assert cb.get_parent() is builder.get_object('panes_title_grid')
    assert hasattr(PrefsEditor, 'on_titlebar_show_icon_checkbutton_toggled')


def test_prefs_editor_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    from terminatorlib import terminal, prefseditor
    from terminatorlib.config import Config
    cfg = Config()
    old = cfg['titlebar_show_icon']
    try:
        cfg['titlebar_show_icon'] = False
        term = terminal.Terminal()
        pe = prefseditor.PrefsEditor(term=term)
        cb = pe.builder.get_object('titlebar_show_icon_checkbutton')
        assert cb.get_active() is False
        cb.set_active(True)
        assert cfg['titlebar_show_icon'] is True
        cb.set_active(False)
        assert cfg['titlebar_show_icon'] is False
        pe.window.destroy()
    finally:
        cfg['titlebar_show_icon'] = old
