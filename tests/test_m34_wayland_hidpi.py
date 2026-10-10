"""m34: Wayland graceful degradation + HiDPI.

The unit lane runs on Xvfb (X11), so Wayland is simulated by giving the
helpers fake GdkDisplay objects / patching Window.can_set_position, and
HiDPI by faking get_scale_factor / the Pango context.
"""
import os
import types

import pytest

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Pango  # noqa: E402

from terminatorlib import util  # noqa: E402
from tests.test_m25_round2_fixes import _pump, app, sess  # noqa: F401,E402


class _GType(object):
    def __init__(self, name):
        self.name = name


def _fake_display(gtype_name):
    cls = type(gtype_name.replace('Gdk', ''), (object,),
               {'__gtype__': _GType(gtype_name)})
    return cls()


# ---- backend detection ------------------------------------------------------

@pytest.mark.parametrize('gtype,expected', [
    ('GdkX11Display', 'X11'),
    ('GdkWaylandDisplay', 'WAYLAND'),
    ('GdkBroadwayDisplay', 'OTHER'),
])
def test_display_manager_from_gtype(gtype, expected):
    assert util.display_manager(_fake_display(gtype)) == expected
    assert util.is_x11(_fake_display(gtype)) == (expected == 'X11')


def test_display_manager_real_display_is_x11():
    # the unit lane runs on Xvfb
    assert util.display_manager() == 'X11'
    assert util.is_x11()


def _no_display(monkeypatch):
    from gi.repository import Gdk
    monkeypatch.setattr(Gdk.Display, 'get_default', staticmethod(lambda: None))


@pytest.mark.parametrize('env,expected', [
    ({}, 'X11'),
    ({'WAYLAND_DISPLAY': 'wayland-0'}, 'WAYLAND'),
    ({'GDK_BACKEND': 'wayland'}, 'WAYLAND'),
    # XWayland: Wayland session but GTK forced onto X11
    ({'WAYLAND_DISPLAY': 'wayland-0', 'GDK_BACKEND': 'x11'}, 'X11'),
    ({'WAYLAND_DISPLAY': 'wayland-0', 'GDK_BACKEND': 'x11,wayland'}, 'X11'),
])
def test_display_manager_env_fallback(monkeypatch, env, expected):
    _no_display(monkeypatch)
    for k in ('WAYLAND_DISPLAY', 'GDK_BACKEND'):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert util.display_manager() == expected


def test_real_display_beats_env(monkeypatch):
    # WAYLAND_DISPLAY set but the open display is X11 (XWayland): X11 APIs
    # work, so the backend must say X11 (upstream said WAYLAND).
    monkeypatch.setenv('WAYLAND_DISPLAY', 'wayland-0')
    assert util.display_manager() == 'X11'
    assert util.display_manager(_fake_display('GdkWaylandDisplay')) == \
        'WAYLAND'


def test_bare_gdkdisplay_falls_back_to_env(monkeypatch):
    monkeypatch.setenv('WAYLAND_DISPLAY', 'w')
    monkeypatch.delenv('GDK_BACKEND', raising=False)
    assert util.display_manager(_fake_display('GdkDisplay')) == 'WAYLAND'


# ---- window positions --------------------------------------------------------

def _wayland(monkeypatch, *windows):
    from terminatorlib.window import Window
    monkeypatch.setattr(Window, 'can_set_position', lambda self: False)


def test_can_set_position_follows_display(app):
    w = app(1)
    assert w.can_set_position() is True
    w.get_display = lambda: _fake_display('GdkWaylandDisplay')
    assert w.can_set_position() is False


def test_layout_omits_position_on_wayland(app, monkeypatch):
    w = app(1)
    lay = {}
    w.describe_layout(0, None, lay, 0)
    win = [v for v in lay.values() if v['type'] == 'Window'][0]
    assert 'position' in win          # X11: kept as before
    _wayland(monkeypatch)
    lay = {}
    w.describe_layout(0, None, lay, 0)
    win = [v for v in lay.values() if v['type'] == 'Window'][0]
    assert 'position' not in win
    # size, maximised and fullscreen state are still saved
    assert 'size' in win and 'maximised' in win and 'fullscreen' in win
    assert list(win['size']) == list(w.get_size())


def _layout_with_position(pos='123:45'):
    return {
        'window0': {'type': 'Window', 'parent': '', 'position': pos,
                    'size': [700, 500], 'maximised': 'True',
                    'fullscreen': 'False'},
        'terminal1': {'type': 'Terminal', 'parent': 'window0'},
    }


def _run_create_layout(monkeypatch, layout):
    from terminatorlib.terminator import Terminator
    from terminatorlib.window import Window
    from terminatorlib.config import Config
    calls = {'move': [], 'resize': [], 'max': []}
    fake = types.SimpleNamespace(
        move=lambda x, y: calls['move'].append((x, y)),
        resize=lambda x, y: calls['resize'].append((x, y)),
        set_maximised=lambda v: calls['max'].append(v),
        set_fullscreen=lambda v: None,
        create_layout=lambda d: None,
        title=types.SimpleNamespace(force_title=lambda t: None),
        can_set_position=lambda: Window.can_set_position(fake),
        get_display=lambda: fake.display,
        ismaximised=False, isfullscreen=False)
    fake.display = None
    t = Terminator()
    monkeypatch.setattr(t, 'new_window', lambda *a, **k: (fake, None))
    monkeypatch.setattr(Config(), 'layout_get_config',
                        lambda name: layout, raising=False)
    monkeypatch.setattr(t.config, 'layout_get_config',
                        lambda name: layout, raising=False)
    return t, fake, calls


def test_restore_skips_move_on_wayland(monkeypatch):
    t, fake, calls = _run_create_layout(monkeypatch, _layout_with_position())
    fake.display = _fake_display('GdkWaylandDisplay')
    t.create_layout('x')
    assert calls['move'] == []
    assert calls['resize'] == [(700, 500)]
    assert calls['max'] == [True]


def test_restore_moves_on_x11_and_tolerates_junk(monkeypatch):
    t, fake, calls = _run_create_layout(monkeypatch, _layout_with_position())
    fake.display = _fake_display('GdkX11Display')
    t.create_layout('x')
    assert calls['move'] == [(123, 45)]
    t, fake, calls = _run_create_layout(monkeypatch,
                                        _layout_with_position('a:b'))
    fake.display = _fake_display('GdkX11Display')
    t.create_layout('x')            # no ValueError
    assert calls['move'] == [] and calls['resize'] == [(700, 500)]


def test_remember_position_only_on_x11(app, monkeypatch):
    w = app(1)
    w._remember_position()
    assert w.position is not None
    _wayland(monkeypatch)
    w._remember_position()
    assert w.position is None
    assert w._server_time() == 0


# ---- hide / iconify without a global hotkey ----------------------------------

def test_hidefunc_iconifies_without_global_hotkey(monkeypatch, app):
    from terminatorlib.window import Window
    from terminatorlib.config import Config
    monkeypatch.setattr(Window, 'can_set_position', lambda self: False)
    assert Config()['keybindings']['hide_window']
    w = app(1)
    assert w.hidefunc == w.iconify
    assert not w.hidebound


def test_toggle_brings_back_window_iconified_by_us(app, monkeypatch):
    w = app(1)
    calls = []
    monkeypatch.setattr(w, 'iconify', lambda: calls.append('iconify'))
    monkeypatch.setattr(w, 'deiconify', lambda: calls.append('deiconify'))
    monkeypatch.setattr(w, 'present', lambda: calls.append('present'))
    monkeypatch.setattr(w, 'is_active', lambda: False)
    w.hidefunc = w.iconify
    _wayland(monkeypatch)
    w.on_hide_window()
    assert calls == ['iconify'] and w._iconified_by_hide
    w.on_hide_window()              # GDK never reports ICONIFIED on Wayland
    assert calls == ['iconify', 'deiconify', 'present']
    assert not w._iconified_by_hide
    w.on_hide_window()
    assert calls[-1] == 'iconify'
    w.on_focus_in(w, None)          # user restored it from the taskbar
    assert not w._iconified_by_hide


def test_hide_on_lose_focus_iconify_sets_flag(app, monkeypatch):
    w = app(1)
    calls = []
    monkeypatch.setattr(w, 'iconify', lambda: calls.append('iconify'))
    w.hidefunc = w.iconify
    _wayland(monkeypatch)
    monkeypatch.setitem(w.config.base.global_config, 'hide_on_lose_focus',
                        True)
    w.preventHide = False
    w.on_focus_out(w, None)
    assert calls == ['iconify'] and w._iconified_by_hide
    assert w.position is None


# ---- WINDOWID ----------------------------------------------------------------

def test_windowid_is_real_xid_on_x11(app, monkeypatch):
    monkeypatch.setenv('WINDOWID', 'stale')
    w = app(1)
    t = w.get_terminals()[0]
    xid = t._export_windowid()
    assert xid and os.environ['WINDOWID'] == str(xid)
    assert xid == w.get_window().get_xid()


def test_windowid_dropped_on_wayland(app, monkeypatch):
    monkeypatch.setenv('WINDOWID', '12345')
    w = app(1)
    t = w.get_terminals()[0]
    monkeypatch.setattr(t.vte, 'get_display',
                        lambda: _fake_display('GdkWaylandDisplay'))
    assert t._export_windowid() is None
    assert 'WINDOWID' not in os.environ


# ---- HiDPI: text scale + titlebar thresholds --------------------------------

class _FakeDesc(object):
    def __init__(self, pt, absolute=False):
        self.pt, self.absolute = pt, absolute

    def get_size(self):
        return int(self.pt * Pango.SCALE)

    def get_size_is_absolute(self):
        return self.absolute


def _fake_widget(pt=10, res=96.0, absolute=False, scale=1):
    desc = _FakeDesc(pt, absolute)
    return types.SimpleNamespace(
        get_pango_context=lambda: types.SimpleNamespace(
            get_font_description=lambda: desc),
        get_screen=lambda: types.SimpleNamespace(
            get_resolution=lambda: res),
        get_scale_factor=lambda: scale)


@pytest.mark.parametrize('kw,expected', [
    ({}, 1.0),
    ({'res': 144.0}, 1.5),                 # GDK_DPI_SCALE=1.5 / Xft.dpi 144
    ({'pt': 15}, 1.5),                     # big desktop font
    ({'pt': 8}, 1.0),                      # never shrink thresholds
    ({'res': -1.0}, 1.0),                  # unknown resolution -> 96
    ({'pt': 20, 'absolute': True}, 1.5),   # absolute px size
    ({'res': 96.0 * 10}, 4.0),             # capped
    ({'scale': 2}, 1.0),                   # GDK_SCALE: logical px already
])
def test_text_scale(kw, expected):
    assert util.text_scale(_fake_widget(**kw)) == pytest.approx(expected)


def test_text_scale_real_widget():
    assert util.text_scale(Gtk.Label()) >= 1.0
    assert util.text_scale(object()) == 1.0


def test_window_scale_factor():
    assert util.window_scale_factor(_fake_widget(scale=2)) == 2
    assert util.window_scale_factor(_fake_widget(scale=0)) == 1
    assert util.window_scale_factor(object()) == 1


def test_titlebar_thresholds_scale_with_text(app):
    w = app(1)
    tb = w.get_terminals()[0].titlebar
    tb._text_scale = 1.0
    assert tb._collapse_level_for(300) == 1
    assert tb._collapse_level_for(330) == 0
    tb._text_scale = 1.5     # GDK_DPI_SCALE=1.5: 320px -> 480px
    assert tb._collapse_level_for(330) == 3     # < 240 * 1.5
    assert tb._collapse_level_for(400) == 2     # < 280 * 1.5
    assert tb._collapse_level_for(479) == 1
    assert tb._collapse_level_for(481) == 0
    assert tb._collapse_level_for(200) == 5
    tb._text_scale = 9.0
    tb._reset_text_scale()          # style-updated: recomputed from Pango
    assert tb._threshold_scale() == pytest.approx(util.text_scale(tb))
    assert tb._threshold_scale() >= 1.0


# ---- HiDPI: background image -------------------------------------------------

def test_background_image_native_resolution_at_scale2(app, tmp_path):
    import cairo
    from gi.repository import GdkPixbuf
    w = app(1)
    t = w.get_terminals()[0]
    pb = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 400, 200)
    pb.fill(0xff0000ff)
    path = str(tmp_path / 'bg.png')
    pb.savev(path, 'png', [], [])
    t.set_background_image(path)
    assert t.background_image is not None
    w1 = _fake_widget(scale=1)
    assert t._background_image_size(w1) == (400.0, 200.0)
    w2 = _fake_widget(scale=2)
    assert t._background_image_size(w2) == (200.0, 100.0)
    assert t.background_image.get_device_scale() == (2.0, 2.0)
    # draws without error at scale 2 into a device-scaled surface
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 200, 100)
    surf.set_device_scale(2, 2)
    cr = cairo.Context(surf)
    t.vte.get_scale_factor = lambda: 2
    t.background_draw(t.vte, cr)
    t._background_image_size(w1)
    assert t.background_image.get_device_scale() == (1.0, 1.0)
