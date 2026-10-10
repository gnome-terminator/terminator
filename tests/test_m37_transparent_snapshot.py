"""m37 transparent-snapshot fix (on top of m38's alpha capture): an alpha
snapshot keeps the window's alpha verbatim, replaces (not stacks on) the
dimmer under it like the live VTE, the placeholder paints nothing opaque in
an RGBA window, and a reverse during the expand hand-over re-hides the live
frame. (Content type + ANIM_DEFER_MAX cap are covered in test_m38.)"""
import time

import cairo
import pytest
from gi.repository import Gtk

from terminatorlib import paneoverlay as po


def _pump(seconds=0.0):
    end = time.monotonic() + seconds
    while True:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        if time.monotonic() >= end:
            break
        time.sleep(0.005)


# ---- translucency detection / content type --------------------------------

class _Visual(object):
    def __init__(self, depth):
        self.depth = depth

    def get_depth(self):
        return self.depth


class _Screen(object):
    def __init__(self, composited, rgba):
        self.composited, self.rgba = composited, rgba

    def is_composited(self):
        return self.composited

    def get_rgba_visual(self):
        return self.rgba


class _Win(object):
    def __init__(self, visual):
        self.visual = visual
        self.contents = []

    def get_visual(self):
        return self.visual

    def create_similar_surface(self, content, w, h):
        self.contents.append(content)
        return cairo.ImageSurface(
            cairo.FORMAT_ARGB32 if content == cairo.CONTENT_COLOR_ALPHA
            else cairo.FORMAT_RGB24, w, h)


class _Alloc(object):
    width, height = 20, 10


class _Widget(object):
    def __init__(self, screen, win):
        self.screen, self.win = screen, win

    def get_screen(self):
        return self.screen

    def get_window(self):
        return self.win

    def get_visual(self):
        return self.win.visual

    def get_allocation(self):
        return _Alloc()

    def translate_coordinates(self, dest, x, y):
        return (True, 3, 4)

    def get_parent(self):
        return None


def _widget(composited, depth=32, rgba_is_visual=True):
    vis = _Visual(depth)
    rgba = vis if rgba_is_visual else _Visual(32)
    return _Widget(_Screen(composited, rgba), _Win(vis))


def test_capture_keeps_alpha_verbatim(monkeypatch):
    calls = []

    def fake_source(cr, win, x, y):
        calls.append((x, y))
        cr.set_source_rgba(1, 0, 0, 0.5)     # translucent window pixels
    monkeypatch.setattr(po.Gdk, 'cairo_set_source_window', fake_source)
    monkeypatch.setattr(po, '_window_is_rgba', lambda w: True)
    w = _widget(True)
    surf, sw, sh = po.capture_widget_surface(w)
    assert w.win.contents == [cairo.CONTENT_COLOR_ALPHA]
    assert (sw, sh) == (20, 10) and calls == [(-3.0, -4.0)]
    # alpha kept verbatim (SOURCE copy), not flattened to opaque
    surf.flush()
    assert surf.get_data()[3] == 128
    monkeypatch.setattr(po, '_window_is_rgba', lambda w: False)
    w2 = _widget(False)
    po.capture_widget_surface(w2)
    assert w2.win.contents == [cairo.CONTENT_COLOR]


# ---- painting --------------------------------------------------------------

def _argb(w, h, rgba):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    c = cairo.Context(s)
    c.set_operator(cairo.OPERATOR_SOURCE)
    c.set_source_rgba(*rgba)
    c.paint()
    return s


def _alpha_at(surf, x, y):
    surf.flush()
    return surf.get_data()[y * surf.get_stride() + x * 4 + 3]


def test_snap_has_alpha():
    assert po.snap_has_alpha((_argb(2, 2, (0, 0, 0, .5)), 2, 2))
    assert not po.snap_has_alpha(
        (cairo.ImageSurface(cairo.FORMAT_RGB24, 2, 2), 2, 2))
    assert not po.snap_has_alpha(None)


def test_replace_does_not_stack_on_dimmer():
    """Under the snapshot sits the dimmer (black, alpha .55). The live
    translucent VTE replaces it; so must the snapshot."""
    snap = (_argb(10, 10, (0, 0, 0, 0.7)), 10, 10)
    dst = _argb(20, 20, (0, 0, 0, 0.55))
    cr = cairo.Context(dst)
    po.paint_snapshot(cr, snap, (0, 0, 20, 20), 1.0, replace=True)
    assert abs(_alpha_at(dst, 10, 10) - 178) <= 2      # .7, not .865
    over = _argb(20, 20, (0, 0, 0, 0.55))
    po.paint_snapshot(cairo.Context(over), snap, (0, 0, 20, 20), 1.0)
    assert _alpha_at(over, 10, 10) > 210                # OVER compounds
    # replace only inside the rect; outside untouched
    dst2 = _argb(20, 20, (0, 0, 0, 0.55))
    po.paint_snapshot(cairo.Context(dst2), snap, (5, 5, 10, 10), 1.0, True)
    assert abs(_alpha_at(dst2, 1, 1) - 140) <= 2
    # no transparent fringe at the rect edge (EXTEND_PAD)
    assert abs(_alpha_at(dst2, 5, 5) - 178) <= 2
    assert abs(_alpha_at(dst2, 14, 14) - 178) <= 2


def test_fading_snapshot_blends_over_even_with_replace():
    snap = (_argb(4, 4, (0, 0, 0, 1.0)), 4, 4)
    dst = _argb(4, 4, (0, 0, 0, 0.5))
    po.paint_snapshot(cairo.Context(dst), snap, (0, 0, 4, 4), 0.5,
                      replace=True)
    assert _alpha_at(dst, 2, 2) > 128      # blended, never punched out


def test_snapshot_area_replaces_only_alpha_snapshots(monkeypatch):
    seen = []
    monkeypatch.setattr(po, 'paint_snapshot',
                        lambda cr, snap, rect, a, replace=False:
                        seen.append(replace))
    area = po.SnapshotArea()
    cr = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, 4))
    area.set_snap((_argb(2, 2, (0, 0, 0, .5)), 2, 2))
    area._on_draw(area, cr)
    area.set_snap((cairo.ImageSurface(cairo.FORMAT_RGB24, 2, 2), 2, 2))
    area._on_draw(area, cr)
    assert seen == [True, False]


@pytest.mark.parametrize('translucent', [True, False])
def test_placeholder_no_opaque_fill_in_rgba_window(monkeypatch, translucent):
    monkeypatch.setattr(po, '_window_is_rgba', lambda w: translucent)
    ph = po.PanePlaceholder(None)
    dst = cairo.ImageSurface(cairo.FORMAT_ARGB32, 8, 8)
    ph._on_draw(ph, cairo.Context(dst))
    a = _alpha_at(dst, 0, 0)
    assert (a == 0) if translucent else (a == 255)


# ---- review: missing tests -------------------------------------------------

@pytest.fixture
def win(monkeypatch):
    from terminatorlib.terminal import Terminal
    from terminatorlib.terminator import Terminator
    from terminatorlib.factory import Factory
    monkeypatch.setattr(Terminal, 'spawn_child', lambda self, *a, **k: True)
    monkeypatch.setattr(Terminator(), 'terminals', [])
    monkeypatch.setattr(Terminator(), 'windows', [])
    monkeypatch.setattr(po, 'should_reduce_motion', lambda c=None: False)
    w = Factory().make('Window')
    w.add(Factory().make('Terminal'))
    w.resize(900, 600)
    w.show_all()
    _pump(0.2)
    w.split_axis(list(w.get_terminals())[0], True)
    _pump(0.3)
    yield w
    for term in list(Terminator().terminals):
        if term.get_toplevel() is w:
            Terminator().deregister_terminal(term)
    if not getattr(w, 'isDestroyed', False):
        w.destroy()
    _pump()


def test_reverse_mid_expand_rehides_frame(win, monkeypatch):
    """Restore requested during the expand hand-over cross-fade (live frame
    already shown): the reversed leg must hide the frame again and show the
    snapshot fully, then end restored."""
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, 8, 8)
    monkeypatch.setattr(po, 'capture_widget_surface', lambda w: (surf, 8, 8))
    cbs = []
    monkeypatch.setattr(po, 'frame_clock_scheduler',
                        lambda w: (lambda cb: cbs.append(cb) or len(cbs),
                                   lambda tid: None))
    t = list(win.get_terminals())[-1]
    assert win.overlay_maximise(t, animate=True)
    ov = win._overlay
    data = ov.data
    anim = ov._animator
    cbs[-1](10.0)                                 # first frame = origin
    assert data['frame_hidden'] is True
    end = 10.0 + anim.duration
    cbs[-1](end - 0.02)                           # inside the 60ms fade
    assert data['frame_hidden'] is False
    assert data['snapshot']._opacity < 1.0
    assert win.overlay_restore(animate=True)      # reverse mid-hand-over
    assert ov._animator.reversed and data['restore_pending']
    cbs[-1](20.0)                                 # first reversed frame
    assert data['frame_hidden'] is True
    assert data['snapshot']._opacity == 1.0
    cbs[-1](30.0)                                 # past the end
    assert not ov.is_active()
    assert t.get_toplevel() is win
