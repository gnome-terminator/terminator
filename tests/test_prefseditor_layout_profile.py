"""r02-1: layout profile chooser rebuild must not duplicate or clobber."""
import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')

from types import SimpleNamespace

import pytest

from terminatorlib.borg import Borg


@pytest.fixture
def pe(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    from terminatorlib import optionparse
    state = Borg._Borg__shared_state
    saved = state.get('ConfigBase')
    state.pop('ConfigBase', None)
    old = optionparse.options
    optionparse.options = SimpleNamespace(
        config=str(tmp_path / 'config-file'), profile=None, layout=None,
        command=None, execute=None, working_directory=None,
        forcedtitle=None, forcedicon=None, role=None, geometry=None)
    from terminatorlib import terminal, prefseditor
    editor = None
    try:
        term = terminal.Terminal()
        editor = prefseditor.PrefsEditor(term=term)
        yield editor
    finally:
        if editor is not None and editor.window is not None:
            editor.window.destroy()
        optionparse.options = old
        state.pop('ConfigBase', None)
        if saved is not None:
            state['ConfigBase'] = saved


def _chooser_texts(chooser):
    model = chooser.get_model()
    texts = []
    row = model.get_iter_first()
    while row is not None:
        texts.append(model.get_value(row, 0))
        row = model.iter_next(row)
    return texts


def _terminal_name(layout):
    for name, section in layout.items():
        if section.get('type') == 'Terminal':
            return name
    raise AssertionError('no terminal in layout')


def test_update_profiles_replaces_model(pe):
    editor = pe.layouteditor
    editor.update_profiles()
    editor.update_profiles()
    chooser = pe.builder.get_object('layout_profile_chooser')
    profiles = sorted(pe.config.list_profiles())
    assert _chooser_texts(chooser) == profiles


def test_set_layout_item_selects_saved_profile(pe):
    assert pe.config.add_profile('zeta', None)
    layout = pe.config.layout_get_config('default')
    term_name = _terminal_name(layout)
    layout[term_name]['profile'] = 'zeta'
    editor = pe.layouteditor
    editor.layout_item = None
    editor.update_profiles()
    editor.layout_name = 'default'
    editor.layout_item = term_name
    before = layout[term_name]['profile']
    editor.set_layout_item(term_name)
    chooser = pe.builder.get_object('layout_profile_chooser')
    assert chooser.get_active_text() == 'zeta'
    assert layout[term_name]['profile'] == before == 'zeta'


def test_update_profiles_does_not_clobber_saved_profile(pe):
    assert pe.config.add_profile('zeta', None)
    layout = pe.config.layout_get_config('default')
    term_name = _terminal_name(layout)
    layout[term_name]['profile'] = 'zeta'
    editor = pe.layouteditor
    editor.layout_name = 'default'
    editor.layout_item = term_name
    editor.update_profiles()
    chooser = pe.builder.get_object('layout_profile_chooser')
    assert chooser.get_active_text() == 'zeta'
    assert layout[term_name]['profile'] == 'zeta'
    editor.update_profiles()
    assert layout[term_name]['profile'] == 'zeta'
    assert chooser.get_active_text() == 'zeta'


def test_update_profiles_missing_name_does_not_raise(pe):
    layout = pe.config.layout_get_config('default')
    term_name = _terminal_name(layout)
    layout[term_name]['profile'] = 'gone'
    editor = pe.layouteditor
    editor.layout_name = 'default'
    editor.layout_item = term_name
    editor.update_profiles()
    assert layout[term_name]['profile'] == 'gone'
