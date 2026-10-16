"""Preferences UI for session restore (A8), scrollback cache (B5) and
Wave-style title bars (C0)."""
import os
import json

import pytest

gi = pytest.importorskip('gi')
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import Gtk, Gdk  # noqa: E402


@pytest.fixture
def xdg(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    return tmp_path


def test_glade_loads_with_new_widgets():
    from terminatorlib import config
    path = os.path.join(os.path.dirname(config.__file__), 'preferences.glade')
    builder = Gtk.Builder()
    builder.add_from_file(path)
    for wid in ('restore_last_session_checkbutton', 'session_info_label',
                'session_save_as_layout_button', 'session_restore_prev_button',
                'session_clear_button', 'session_legacy_plugin_label',
                'scrollback_cache_checkbutton',
                'scrollback_cache_lines_spinbutton',
                'scrollback_cache_info_label',
                'titlebar_buttons_checkbutton', 'titlebar_density_combo',
                'pane_accent_colorbutton'):
        assert builder.get_object(wid) is not None, wid
    nb = builder.get_object('notebook1')
    labels = [nb.get_tab_label_text(nb.get_nth_page(i))
              for i in range(nb.get_n_pages())]
    assert labels.index('Session') == labels.index('Layouts') + 1
    assert labels.index('Keybindings') == 5
    assert labels.index('Panes') == labels.index('Global') + 1


def test_prefs_editor_reflects_defaults_and_writes(xdg):
    from terminatorlib import terminal, prefseditor
    from terminatorlib.config import Config
    term = terminal.Terminal()
    pe = prefseditor.PrefsEditor(term=term)
    get = pe.builder.get_object
    cfg = Config()
    # Defaults ON and matching config
    assert get('restore_last_session_checkbutton').get_active() is True
    assert get('scrollback_cache_checkbutton').get_active() is True
    assert int(get('scrollback_cache_lines_spinbutton').get_value()) == \
        int(cfg['scrollback_cache_lines'])
    assert get('titlebar_buttons_checkbutton').get_active() is True
    assert get('titlebar_density_combo').get_active_id() == 'standard'
    rgba = get('pane_accent_colorbutton').get_rgba()
    assert prefseditor.get_color_string(rgba.to_color()) == '#3fb950'
    assert get('notebook1').get_nth_page(5) is get('vbox124')

    # Round-trip writes
    get('titlebar_density_combo').set_active_id('compact')
    assert cfg['titlebar_density'] == 'compact'
    get('titlebar_buttons_checkbutton').set_active(False)
    assert cfg['titlebar_buttons'] is False
    get('restore_last_session_checkbutton').set_active(False)
    assert cfg['restore_last_session'] is False
    get('scrollback_cache_lines_spinbutton').set_value(500)
    assert cfg['scrollback_cache_lines'] == 500
    get('scrollback_cache_checkbutton').set_active(False)
    assert cfg['scrollback_cache'] is False
    assert not get('scrollback_cache_lines_spinbutton').get_sensitive()
    pe.window.destroy()


def test_session_info_and_suspend(xdg, monkeypatch):
    from terminatorlib import terminal, prefseditor
    from terminatorlib.session import SessionManager
    # Only the session owner may clear / use previous (m25 round-2 P2-3)
    monkeypatch.setattr(SessionManager, 'is_owner', lambda self: True)
    sess = SessionManager()
    path = sess.session_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + '.prev', 'w') as fh:
        json.dump({'version': 1, 'layout': {}}, fh)
    term = terminal.Terminal()
    pe = prefseditor.PrefsEditor(term=term)
    from terminatorlib.translation import _
    text = pe.builder.get_object('session_info_label').get_text()
    assert path in text
    assert _('A previous session is available') in text
    monkeypatch.setattr(pe, '_confirm', lambda *a: True)
    pe.on_session_restore_prev_button_clicked(None)
    assert os.path.isfile(path)
    assert not sess.is_writer()
    pe.on_session_clear_button_clicked(None)
    assert not os.path.exists(path)
    assert not os.path.exists(path + '.prev')
    pe.window.destroy()
    sess._disabled = False


def _isolated_options(tmp_path):
    from types import SimpleNamespace
    from terminatorlib import optionparse
    old = optionparse.options
    optionparse.options = SimpleNamespace(
        config=str(tmp_path / 'config-file'), profile=None, layout=None,
        command=None, execute=None, working_directory=None,
        forcedtitle=None, forcedicon=None, role=None, geometry=None)
    return old


def _selected_layout_name(editor):
    layoutlist = editor.builder.get_object('layoutlist')
    model, row = layoutlist.get_selection().get_selected()
    assert row is not None
    return model.get_value(row, 0)


@pytest.mark.parametrize('layoutname', [
    '__last_session__', '__internal_json_layout__', 'does-not-exist',
])
def test_missing_layoutname_still_fills_pages(xdg, monkeypatch, layoutname):
    from terminatorlib.borg import Borg
    from terminatorlib import optionparse
    state = Borg._Borg__shared_state
    saved = state.get('ConfigBase')
    state.pop('ConfigBase', None)
    old = _isolated_options(xdg)
    editor = None
    try:
        from terminatorlib.terminator import Terminator
        app = Terminator()
        monkeypatch.setattr(app, 'layoutname', layoutname)
        from terminatorlib import terminal, prefseditor
        editor = prefseditor.PrefsEditor(term=terminal.Terminal())
        model = editor.builder.get_object('keybindingtreeview').get_model()
        assert model.iter_n_children(None) > 0
        assert isinstance(editor.pluginiters, dict)
        assert _selected_layout_name(editor) == 'default'
    finally:
        if editor is not None and editor.window is not None:
            editor.window.destroy()
        optionparse.options = old
        state.pop('ConfigBase', None)
        if saved is not None:
            state['ConfigBase'] = saved


def test_existing_layoutname_is_highlighted(xdg, monkeypatch):
    from copy import deepcopy
    from terminatorlib.borg import Borg
    from terminatorlib import optionparse
    from terminatorlib.config import Config
    state = Borg._Borg__shared_state
    saved = state.get('ConfigBase')
    state.pop('ConfigBase', None)
    old = _isolated_options(xdg)
    editor = None
    try:
        cfg = Config()
        cfg.add_layout('mine', deepcopy(cfg.base.layouts['default']))
        from terminatorlib.terminator import Terminator
        app = Terminator()
        monkeypatch.setattr(app, 'layoutname', 'mine')
        from terminatorlib import terminal, prefseditor
        editor = prefseditor.PrefsEditor(term=terminal.Terminal())
        assert _selected_layout_name(editor) == 'mine'
    finally:
        if editor is not None and editor.window is not None:
            editor.window.destroy()
        optionparse.options = old
        state.pop('ConfigBase', None)
        if saved is not None:
            state['ConfigBase'] = saved
