"""r02-2 palette clicks connect once; r02-5 colour scheme load order."""
import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')

from types import SimpleNamespace

import pytest
from gi.repository import Gdk, Gtk

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


def _emit_button_press(widget):
    event = Gdk.Event.new(Gdk.EventType.BUTTON_PRESS)
    event.button.button = 1
    widget.emit('button-press-event', event)


def test_palette_click_connects_once(pe):
    calls = {'n': 0}

    def stub(widget):
        calls['n'] += 1

    pe.edit_palette_button = stub
    swatch = pe.builder.get_object('palette_colorpicker_1')
    _emit_button_press(swatch)
    assert calls['n'] == 1
    pe.set_profile_values(pe.config.get_profile())
    _emit_button_press(swatch)
    assert calls['n'] == 2


def _watch_queue_draw(widget, seen):
    original = widget.queue_draw

    def wrapped(*args, **kwargs):
        seen.append(widget)
        return original(*args, **kwargs)

    widget.queue_draw = wrapped


def test_builtin_scheme_switch_disables_swatches_and_redraws(pe):
    get = pe.builder.get_object
    combo = get('color_scheme_combobox')
    fore = get('foreground_colorbutton')
    back = get('background_colorbutton')
    assert combo.get_active() == 11
    combo.set_active(0)
    seen = []
    _watch_queue_draw(fore, seen)
    _watch_queue_draw(back, seen)
    combo.set_active(4)
    assert not fore.get_sensitive()
    assert not back.get_sensitive()
    name = [key for key, idx in pe.colorschemevalues.items() if idx == 4][0]
    assert pe.config['foreground_color'].lower() == pe.colourschemes[name][0]
    assert pe.config['background_color'].lower() == pe.colourschemes[name][1]
    assert fore in seen
    assert back in seen


def test_theme_colors_disable_scheme_and_swatches(pe):
    get = pe.builder.get_object
    colours = pe.colourschemes['black_on_white']
    pe.config['use_theme_colors'] = True
    pe.config['foreground_color'] = colours[0]
    pe.config['background_color'] = colours[1]
    pe.set_profile_values('default')
    combo = get('color_scheme_combobox')
    assert combo.get_active() == pe.colorschemevalues['black_on_white']
    assert combo.get_active() != 11
    assert not combo.get_sensitive()
    assert not get('foreground_colorbutton').get_sensitive()
    assert not get('background_colorbutton').get_sensitive()


def test_theme_colors_custom_stays_insensitive(pe):
    get = pe.builder.get_object
    pe.config['use_theme_colors'] = True
    pe.config['foreground_color'] = '#111111'
    pe.config['background_color'] = '#222222'
    pe.set_profile_values('default')
    fore = get('foreground_colorbutton')
    back = get('background_colorbutton')
    assert not fore.get_sensitive()
    assert not back.get_sensitive()
    pe.set_profile_values('default')
    assert not fore.get_sensitive()
    assert not back.get_sensitive()
    assert pe.config['foreground_color'].lower() == '#111111'
    assert pe.config['background_color'].lower() == '#222222'


def test_custom_without_theme_colors_is_sensitive(pe):
    get = pe.builder.get_object
    pe.config['use_theme_colors'] = False
    pe.config['foreground_color'] = '#111111'
    pe.config['background_color'] = '#222222'
    pe.set_profile_values('default')
    assert get('color_scheme_combobox').get_active() == 12
    assert get('color_scheme_combobox').get_sensitive()
    assert get('foreground_colorbutton').get_sensitive()
    assert get('background_colorbutton').get_sensitive()


def test_loading_custom_profile_keeps_its_colors(pe):
    from copy import copy
    from terminatorlib.config import DEFAULTS
    theme = copy(DEFAULTS['profiles']['default'])
    theme.update({
        'use_theme_colors': True,
        'foreground_color': pe.colourschemes['green_on_black'][0],
        'background_color': pe.colourschemes['green_on_black'][1],
    })
    custom = copy(DEFAULTS['profiles']['default'])
    custom.update({
        'use_theme_colors': False,
        'foreground_color': '#010101',
        'background_color': '#020202',
    })
    pe.config.base.profiles['themeon'] = theme
    pe.config.base.profiles['customb'] = custom
    pe.set_profile_values('themeon')
    pe.set_profile_values('customb')
    assert pe.config.base.profiles['customb']['foreground_color'].lower() == '#010101'
    assert pe.config.base.profiles['customb']['background_color'].lower() == '#020202'


class _FakeColorDialog:
    def __init__(self, title='', *args, **kwargs):
        self.title = title
        self._rgba = Gdk.RGBA()
        self._notify = None
        self.response = Gtk.ResponseType.CANCEL
        self.pick = None

    def set_rgba(self, rgba):
        self._rgba = rgba
        if self._notify is not None:
            self._notify(self, None)

    def get_rgba(self):
        return self._rgba

    def connect(self, signal, callback, *args):
        if signal == 'notify::rgba':
            self._notify = callback
        return 1

    def run(self):
        if self.pick:
            rgba = Gdk.RGBA()
            assert rgba.parse(self.pick)
            rgba.alpha = 1.0
            self.set_rgba(rgba)
        return self.response

    def destroy(self):
        pass


def test_color_dialog_ok_switches_to_custom(pe, monkeypatch):
    from terminatorlib import prefseditor
    dialogs = []

    def factory(*args, **kwargs):
        dialog = _FakeColorDialog(*args, **kwargs)
        dialog.response = Gtk.ResponseType.OK
        dialog.pick = '#010203'
        dialogs.append(dialog)
        return dialog

    monkeypatch.setattr(prefseditor.Gtk, 'ColorChooserDialog', factory)
    get = pe.builder.get_object
    assert get('color_scheme_combobox').get_active() == 11
    pe.on_foreground_colorbutton_click(None, None)
    assert dialogs
    assert get('color_scheme_combobox').get_active() == 12
    assert pe.config['foreground_color'].lower() == '#010203'


def test_color_dialog_cancel_restores_snapshot(pe, monkeypatch):
    from terminatorlib import prefseditor
    get = pe.builder.get_object
    scheme = get('color_scheme_combobox')
    before_scheme = scheme.get_active()
    before_fore = pe.config['foreground_color']
    before_back = pe.config['background_color']

    def factory(*args, **kwargs):
        dialog = _FakeColorDialog(*args, **kwargs)
        dialog.response = Gtk.ResponseType.CANCEL
        dialog.pick = '#010203'
        return dialog

    monkeypatch.setattr(prefseditor.Gtk, 'ColorChooserDialog', factory)
    pe.on_foreground_colorbutton_click(None, None)
    assert scheme.get_active() == before_scheme
    assert pe.config['foreground_color'] == before_fore
    assert pe.config['background_color'] == before_back

    pe.on_background_colorbutton_click(None, None)
    assert scheme.get_active() == before_scheme
    assert pe.config['foreground_color'] == before_fore
    assert pe.config['background_color'] == before_back


def test_background_dialog_open_notify_does_not_change_scheme(pe, monkeypatch):
    from terminatorlib import prefseditor
    get = pe.builder.get_object
    scheme = get('color_scheme_combobox')
    start = scheme.get_active()
    calls = []
    original = scheme.set_active

    def spy(index):
        calls.append(index)
        return original(index)

    scheme.set_active = spy

    def factory(*args, **kwargs):
        dialog = _FakeColorDialog(*args, **kwargs)
        dialog.response = Gtk.ResponseType.CANCEL
        dialog.pick = None
        return dialog

    monkeypatch.setattr(prefseditor.Gtk, 'ColorChooserDialog', factory)
    pe.on_background_colorbutton_click(None, None)
    assert 12 not in calls
    assert calls == [start]
    assert scheme.get_active() == start
