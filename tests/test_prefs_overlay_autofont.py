"""Preferences UI for overlay maximise (D-prefs) and auto font scale (E6),
plus page lookup by name instead of hard-coded index."""
import os

import pytest

gi = pytest.importorskip('gi')
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import Gtk  # noqa: E402


@pytest.fixture
def xdg(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    return tmp_path


NEW_WIDGETS = (
    'pane_overlay_maximise_checkbutton', 'reduce_motion_combo',
    'pane_anim_expand_spinbutton', 'pane_anim_restore_spinbutton',
    'auto_font_scale_checkbutton', 'auto_font_scale_badge_checkbutton',
    'reading_measure_spinbutton',
)


def test_glade_has_overlay_and_autofont_widgets():
    from terminatorlib import config
    path = os.path.join(os.path.dirname(config.__file__), 'preferences.glade')
    builder = Gtk.Builder()
    builder.add_from_file(path)
    for wid in NEW_WIDGETS:
        assert builder.get_object(wid) is not None, wid


def test_defaults_and_round_trip(xdg):
    from terminatorlib import terminal, prefseditor
    from terminatorlib.config import Config
    term = terminal.Terminal()
    pe = prefseditor.PrefsEditor(term=term)
    get = pe.builder.get_object
    cfg = Config()

    # Defaults ON
    assert get('pane_overlay_maximise_checkbutton').get_active() is True
    assert get('reduce_motion_combo').get_active_id() == 'system'
    assert int(get('pane_anim_expand_spinbutton').get_value()) == 200
    assert int(get('pane_anim_restore_spinbutton').get_value()) == 160
    assert get('auto_font_scale_checkbutton').get_active() is True
    assert get('auto_font_scale_badge_checkbutton').get_active() is True
    assert int(get('reading_measure_spinbutton').get_value()) == 45

    get('pane_overlay_maximise_checkbutton').set_active(False)
    assert cfg['pane_overlay_maximise'] is False
    get('reduce_motion_combo').set_active_id('on')
    assert cfg['reduce_motion'] == 'on'
    get('pane_anim_expand_spinbutton').set_value(300)
    assert cfg['pane_animation_expand_ms'] == 300
    get('pane_anim_restore_spinbutton').set_value(100)
    assert cfg['pane_animation_restore_ms'] == 100
    get('reading_measure_spinbutton').set_value(80)
    assert cfg['reading_measure_min_cols'] == 80
    get('auto_font_scale_badge_checkbutton').set_active(False)
    assert cfg['auto_font_scale_show_badge'] is False

    get('auto_font_scale_checkbutton').set_active(False)
    assert cfg['auto_font_scale'] is False
    assert not get('reading_measure_spinbutton').get_sensitive()
    assert not get('auto_font_scale_badge_checkbutton').get_sensitive()
    get('auto_font_scale_checkbutton').set_active(True)
    assert get('reading_measure_spinbutton').get_sensitive()
    pe.window.destroy()


def test_page_lookup_by_name(xdg):
    from terminatorlib import terminal, prefseditor
    term = terminal.Terminal()
    pe = prefseditor.PrefsEditor(term=term, cur_page='keybindings')
    get = pe.builder.get_object
    nb = get('notebook1')
    assert nb.get_nth_page(nb.get_current_page()) is get('vbox124')
    assert pe.resolve_page('session') == nb.page_num(get('session_page_scroller'))
    assert pe.resolve_page(2) == 2
    assert pe.resolve_page('no-such-page') == 0
    pe.window.destroy()


def test_terminal_keybindings_shortcut_uses_page_name(monkeypatch):
    from terminatorlib import terminal
    seen = {}
    monkeypatch.setattr(terminal, 'PrefsEditor',
                        lambda term, cur_page=0: seen.setdefault('page', cur_page))
    terminal.Terminal.key_preferences_keybindings(object())
    assert seen['page'] == 'keybindings'


def test_restore_maximised_listed_in_keybindings():
    from terminatorlib import prefseditor
    assert 'restore_maximised' in prefseditor.PrefsEditor.keybindingnames
