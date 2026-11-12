"""r10: profile/layout rename guards, plugin config, debug filters, layout copy."""
import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')

from types import SimpleNamespace

import pytest
from configobj import ConfigObj

from terminatorlib.borg import Borg


@pytest.fixture(autouse=True)
def _reset_config_borg():
    # A bare pop leaves Terminator.config.base on the old dict while later
    # Config() calls allocate a new one. Put the original dict back.
    state = Borg._Borg__shared_state
    saved = state.get('ConfigBase')
    state.pop('ConfigBase', None)
    yield
    state.pop('ConfigBase', None)
    if saved is not None:
        state['ConfigBase'] = saved


@pytest.fixture
def isolated(tmp_path):
    from terminatorlib import optionparse
    old = optionparse.options
    path = tmp_path / 'config'
    optionparse.options = SimpleNamespace(config=str(path), profile=None)
    yield SimpleNamespace(path=path)
    optionparse.options = old


def _config():
    from terminatorlib.config import Config
    return Config()


def test_debug_level_with_filters_table():
    from terminatorlib.optionparse import debug_level_with_filters
    assert debug_level_with_filters(None, 'Config', None) == 1
    assert debug_level_with_filters(None, None, 'load') == 1
    assert debug_level_with_filters(0, 'Config', None) == 1
    assert debug_level_with_filters(2, 'Config', None) == 2
    assert debug_level_with_filters(1, None, None) == 1
    assert debug_level_with_filters(None, None, None) is None
    assert debug_level_with_filters(None, '', '') is None
    assert debug_level_with_filters(None, '', 'load') == 1
    assert debug_level_with_filters(0, None, None) == 0


def test_rename_profile_guards(isolated):
    conf = _config()
    assert conf.rename_profile('missing', 'other') is False
    assert 'other' not in conf.base.profiles
    assert conf.rename_profile('ghost', 'ghost') is False
    assert 'ghost' not in conf.base.profiles

    assert conf.add_profile('a', None)
    assert conf.add_profile('b', None)
    conf.base.profiles['a']['font'] = 'Afont'
    conf.base.profiles['b']['font'] = 'Bfont'
    id_a = conf.base.profiles['a']
    id_b = conf.base.profiles['b']
    assert conf.rename_profile('a', 'b') is False
    assert conf.base.profiles['a'] is id_a
    assert conf.base.profiles['b'] is id_b
    assert conf.base.profiles['a']['font'] == 'Afont'
    assert conf.base.profiles['b']['font'] == 'Bfont'

    assert conf.rename_profile('a', 'a') is True
    assert conf.base.profiles['a'] is id_a

    assert conf.rename_profile('a', '__internal_json_profile__') is False
    assert 'a' in conf.base.profiles
    assert '__internal_json_profile__' not in conf.base.profiles

    conf.set_profile('a', force=True)
    assert conf.rename_profile('a', 'a2') is True
    assert 'a' not in conf.base.profiles
    assert conf.base.profiles['a2'] is id_a
    assert conf.profile == 'a2'

    assert conf.add_profile('c', None)
    id_c = conf.base.profiles['c']
    assert conf.rename_profile('c', 'c2') is True
    assert conf.profile == 'a2'
    assert conf.base.profiles['c2'] is id_c

    assert conf.rename_profile('default', 'other') is False
    assert 'default' in conf.base.profiles
    assert 'other' not in conf.base.profiles
    assert conf.rename_profile('default', 'default') is True


def test_rename_layout_guards(isolated):
    conf = _config()
    assert conf.rename_layout('missing', 'other') is False
    assert 'other' not in conf.base.layouts
    assert conf.rename_layout('ghost', 'ghost') is False

    assert conf.add_layout('lay_a', {'window0': {'type': 'Window', 'parent': ''}})
    assert conf.add_layout('lay_b', {'window0': {'type': 'Window', 'parent': ''}})
    id_a = conf.base.layouts['lay_a']
    id_b = conf.base.layouts['lay_b']
    assert conf.rename_layout('lay_a', 'lay_b') is False
    assert conf.base.layouts['lay_a'] is id_a
    assert conf.base.layouts['lay_b'] is id_b

    assert conf.rename_layout('lay_a', 'lay_a') is True
    assert conf.base.layouts['lay_a'] is id_a

    for reserved in ('__internal_json_layout__', '__last_session__'):
        assert conf.rename_layout('lay_a', reserved) is False
        assert 'lay_a' in conf.base.layouts
        assert reserved not in conf.base.layouts

    profile_before = conf.profile
    assert conf.rename_layout('lay_a', 'lay_a2') is True
    assert 'lay_a' not in conf.base.layouts
    assert conf.base.layouts['lay_a2'] is id_a
    assert conf.profile == profile_before
    assert conf.rename_layout('default', 'default') is True


def test_del_profile_keeps_default(isolated):
    conf = _config()
    original = conf.base.profiles['default']
    original['font'] = 'ChangedFont'
    conf.options_get().profile = 'default'
    assert conf.profile == 'default'
    conf.del_profile('default')
    assert conf.base.profiles['default'] is original
    assert conf.base.profiles['default']['font'] == 'ChangedFont'
    assert conf.profile == 'default'
    assert conf.options_get().profile == 'default'
    assert conf.base.get_item('font', 'default') == 'ChangedFont'

    assert conf.add_profile('other', None)
    conf.set_profile('other', force=True)
    conf.del_profile('default')
    assert conf.profile == 'other'
    assert 'default' in conf.base.profiles


def test_del_profile_in_use_non_default(isolated):
    conf = _config()
    assert conf.add_profile('other', None)
    conf.set_profile('other', force=True)
    assert conf.options_get().profile is None
    conf.del_profile('other')
    assert 'other' not in conf.base.profiles
    assert conf.profile == 'default'
    assert conf.base.get_item('font') == conf.base.profiles['default']['font']

    assert conf.add_profile('cli', None)
    conf.set_profile('cli', force=True)
    conf.options_get().profile = 'cli'
    conf.del_profile('cli')
    assert 'cli' not in conf.base.profiles
    assert conf.options_get().profile is None


def test_missing_default_profile_is_copied(isolated):
    from terminatorlib.config import DEFAULTS
    conf = _config()
    conf.base.profiles.pop('default')
    assert conf.base.get_item('font', 'default') == DEFAULTS['profiles']['default']['font']
    conf.base.profiles['default']['font'] = 'ZZZ'
    assert DEFAULTS['profiles']['default']['font'] != 'ZZZ'
    assert conf.base.set_item('font', 'Z', profile='default') is True
    assert conf.base.profiles['default']['font'] == 'Z'
    assert DEFAULTS['profiles']['default']['font'] != 'Z'
    with pytest.raises(KeyError):
        conf.base.set_item('font', 'Q', profile='missing-profile')


def test_plugin_set_does_not_touch_user_config(isolated):
    conf = _config()
    font_before = conf.base.profiles['default']['font']
    focus_before = conf.base.global_config['focus']
    global_before = dict(conf.base.global_config)
    keybindings_before = conf.base.keybindings
    tree = {'x': 1}
    assert conf.plugin_set('Plug', 'font', tree) is True
    assert conf.base.profiles['default']['font'] == font_before
    assert conf.base.global_config == global_before
    assert conf.base.global_config['focus'] == focus_before
    assert conf.base.plugins['Plug']['font'] is tree
    assert conf.plugin_get('Plug', 'font') is tree

    assert conf.plugin_set('Plug', 'focus', 'x') is True
    assert conf.base.global_config['focus'] == focus_before
    assert conf.plugin_get('Plug', 'focus') == 'x'

    assert conf.plugin_set('Plug', 'keybindings', {'nope': True}) is True
    assert conf.base.keybindings is keybindings_before
    assert conf.plugin_get('Plug', 'keybindings') == {'nope': True}

    conf.plugin_set_config('Other', {'a': 1, 'b': 0, 'c': False, 'd': ''})
    assert conf.plugin_get('Other', 'a') == 1
    assert conf.plugin_get('Other', 'b') == 0
    assert conf.plugin_get('Other', 'c') is False
    assert conf.plugin_get('Other', 'd') == ''
    assert conf.plugin_get_config('Other')['a'] == 1
    assert conf.plugin_get('Other', 'missing', 1) == 1
    with pytest.raises(KeyError, match='unknown key missing'):
        conf.plugin_get('Other', 'missing')
    with pytest.raises(KeyError, match='unknown key missing0'):
        conf.plugin_get('Other', 'missing0', 0)


def test_profile_cell_size_does_not_shadow_global(isolated):
    from terminatorlib.config import DEFAULTS
    from terminatorlib.util import dict_diff
    conf = _config()
    assert 'cell_width' not in DEFAULTS['profiles']['default']
    assert 'cell_height' not in DEFAULTS['profiles']['default']
    assert DEFAULTS['global_config']['cell_width'] == 1.0
    assert DEFAULTS['global_config']['cell_height'] == 1.0
    conf.base.profiles['default']['cell_width'] = 9.0
    assert conf.base.get_item('cell_width') == conf.base.global_config['cell_width']
    assert conf.base.global_config['cell_width'] == 1.0

    working = dict(DEFAULTS['profiles']['default'])
    working['cell_width'] = '1.7'
    working['cell_height'] = '1.4'
    diff = dict_diff(DEFAULTS['profiles']['default'], working)
    assert 'cell_width' not in diff
    assert 'cell_height' not in diff


def test_load_drops_profile_cell_size(isolated):
    parser = ConfigObj()
    parser['global_config'] = {'cell_width': '1.2'}
    parser['keybindings'] = {}
    parser['profiles'] = {
        'default': {
            'cell_width': '1.7',
            'cell_height': '1.4',
            'font': 'Mono 10',
        },
    }
    parser['layouts'] = {
        'default': {
            'window0': {'type': 'Window', 'parent': ''},
            'child1': {'type': 'Terminal', 'parent': 'window0'},
        },
    }
    parser['plugins'] = {}
    parser.filename = str(isolated.path)
    parser.write()
    text = isolated.path.read_text()
    assert 'line_height' not in text

    conf = _config()
    assert conf.base.global_config['cell_width'] == pytest.approx(1.2)
    assert 'cell_width' not in conf.base.profiles['default']
    assert 'cell_height' not in conf.base.profiles['default']
    assert 1.7 not in conf.base.global_config.values()
    assert '1.7' not in conf.base.global_config.values()
    assert 'line_height' not in isolated.path.read_text()


def test_copy_layout_item_requires_uuid(isolated):
    conf = _config()
    src = {
        't1': {'type': 'Terminal', 'command': 'a'},
        't2': {'type': 'Terminal', 'command': 'b'},
        'win': {'type': 'Window', 'command': 'nope'},
    }
    dst = {
        'd1': {'type': 'Terminal', 'command': 'keep1'},
        'd2': {'type': 'Terminal', 'command': 'keep2'},
    }
    conf.copy_layout_item(src, dst, 'command')
    assert dst['d1']['command'] == 'keep1'
    assert dst['d2']['command'] == 'keep2'

    src = {
        't1': {'type': 'Terminal', 'uuid': None, 'command': 'a'},
        't2': {'type': 'Terminal', 'uuid': '', 'command': 'b'},
    }
    dst = {
        'd1': {'type': 'Terminal', 'uuid': None, 'command': 'old'},
        'd2': {'type': 'Terminal', 'uuid': '', 'command': 'old'},
    }
    conf.copy_layout_item(src, dst, 'command')
    assert dst['d1']['command'] == 'old'
    assert dst['d2']['command'] == 'old'

    src = {
        't1': {'type': 'Terminal', 'uuid': 'u1', 'command': 'first'},
        't2': {'type': 'Terminal', 'uuid': 'u1', 'command': ''},
    }
    dst = {'d1': {'type': 'Terminal', 'uuid': 'u1', 'command': 'old'}}
    conf.copy_layout_item(src, dst, 'command')
    assert dst['d1']['command'] == ''

    src = {'t1': {'type': 'Terminal', 'uuid': 'u1', 'flag': False}}
    dst = {'d1': {'type': 'Terminal', 'uuid': 'u1', 'flag': True}}
    conf.copy_layout_item(src, dst, 'flag')
    assert dst['d1']['flag'] is False

    src = {'t1': {'type': 'Terminal', 'uuid': 'u1', 'command': 'ignored'}}
    dst = {'d1': {'type': 'Terminal', 'uuid': 'u1', 'command': 'old'}}
    conf.copy_layout_item(src, dst, 'missing')
    assert dst['d1']['command'] == 'old'


class _Cell:
    def __init__(self, text):
        self._text = text

    def get_property(self, name):
        assert name == 'text'
        return self._text


class _Builder:
    def get_object(self, name):
        raise AssertionError('builder used: %s' % name)


def test_profile_rename_false_skips_save_and_builder(isolated):
    from terminatorlib.prefseditor import PrefsEditor

    class Cfg:
        def __init__(self):
            self.saved = False

        def rename_profile(self, old, new):
            return False

        def save(self):
            self.saved = True

    pe = PrefsEditor.__new__(PrefsEditor)
    pe.config = Cfg()
    pe.builder = _Builder()
    pe.previous_profile_selection = 'old'
    pe.on_profile_name_edited(_Cell('old'), '0', 'new')
    assert pe.config.saved is False
    assert pe.previous_profile_selection == 'old'


def test_layout_rename_false_skips_save_and_builder(isolated):
    from terminatorlib.prefseditor import PrefsEditor

    class Cfg:
        def __init__(self):
            self.saved = False

        def rename_layout(self, old, new):
            return False

        def save(self):
            self.saved = True

    class Editor:
        layout_name = 'old'

    pe = PrefsEditor.__new__(PrefsEditor)
    pe.config = Cfg()
    pe.builder = _Builder()
    pe.layouteditor = Editor()
    pe.previous_layout_selection = 'old'
    pe.on_layout_name_edited(_Cell('old'), '0', 'new')
    assert pe.config.saved is False
    assert pe.previous_layout_selection == 'old'
    assert pe.layouteditor.layout_name == 'old'
