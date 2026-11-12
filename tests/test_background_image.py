"""Background image handlers go through Signalman, and leaving image
mode clears the surface."""

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')

from terminatorlib.signalman import Signalman
from terminatorlib.terminal import Terminal


class _Vte(object):
    def __init__(self):
        self.clear = None
        self._next = 1
        self.handlers = {}

    def connect(self, signal, handler, *args):
        hid = self._next
        self._next += 1
        self.handlers.setdefault(signal, []).append(hid)
        return hid

    def disconnect(self, hid):
        for signal, ids in list(self.handlers.items()):
            self.handlers[signal] = [item for item in ids if item != hid]

    def set_clear_background(self, value):
        self.clear = value

    def set_mouse_autohide(self, *_args):
        pass

    def set_backspace_binding(self, *_args):
        pass

    def set_delete_binding(self, *_args):
        pass

    def set_allow_bold(self, *_args):
        pass

    def set_colors(self, *_args):
        pass


def _draw_count(vte):
    return len(vte.handlers.get('draw', []))


def _term():
    term = Terminal.__new__(Terminal)
    term.vte = _Vte()
    term.cnxids = Signalman()
    term.background_image = None
    term.custom_font_size = True
    term.terminator = type('App', (), {'last_focused_term': None})()
    return term


def _patch_loader(monkeypatch, surface='surface', fail=False):
    import terminatorlib.terminal as terminal_mod

    def load(_path):
        if fail:
            raise OSError('missing')
        return object()

    monkeypatch.setattr(
        terminal_mod.GdkPixbuf.Pixbuf, 'new_from_file', staticmethod(load))
    monkeypatch.setattr(
        terminal_mod.Gdk, 'cairo_surface_create_from_pixbuf',
        lambda pixbuf, scale, window: surface)


def test_success_then_failure_leaves_one_handler_cleared(monkeypatch):
    term = _term()
    _patch_loader(monkeypatch)
    term.set_background_image('ok.png')
    assert term.background_image == 'surface'
    assert term._bg_image_scale == 1
    assert term.vte.clear is False
    assert _draw_count(term.vte) == 1

    _patch_loader(monkeypatch, fail=True)
    term.set_background_image('missing.png')
    assert term.background_image is None
    assert term.vte.clear is True
    assert _draw_count(term.vte) == 0

    _patch_loader(monkeypatch, surface='second')
    term.set_background_image('ok.png')
    assert term.background_image == 'second'
    assert term.vte.clear is False
    assert _draw_count(term.vte) == 1


def test_reconfigure_leaves_image_mode_clears_the_draw_handler(monkeypatch):
    from terminatorlib.scrollback import ScrollbackCache
    monkeypatch.setattr(ScrollbackCache, 'reconfigure', lambda self: None)
    term = _term()
    _patch_loader(monkeypatch)
    term.set_background_image('ok.png')
    assert _draw_count(term.vte) == 1

    class _Base(object):
        @property
        def profiles(self):
            raise RuntimeError('stop after the background branch')

    class _Cfg(dict):
        pass

    term.config = _Cfg({
        'exit_action': 'noop',
        'mouse_autohide': False,
        'backspace_binding': 'auto',
        'delete_binding': 'auto',
        'allow_bold': True,
        'use_theme_colors': False,
        'foreground_color': '#ffffff',
        'background_color': '#000000',
        'background_type': 'solid',
        'background_image': '/tmp/ok.png',
        'background_darkness': 0.5,
        'inactive_color_offset': 0.8,
        'inactive_bg_color_offset': 0.8,
        'palette': '',
    })
    term.config.base = _Base()
    try:
        term.reconfigure()
    except RuntimeError as ex:
        assert 'background branch' in str(ex)
    else:
        raise AssertionError('reconfigure returned past the background branch')
    assert term.background_image is None
    assert term.vte.clear is True
    assert _draw_count(term.vte) == 0
