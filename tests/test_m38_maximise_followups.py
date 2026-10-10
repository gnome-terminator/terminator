"""m38: m37 review follow-ups (alpha-preserving snapshot, blank Wayland
snapshot fallback, public Animator.duration, defer cap, reverse mid-expand)."""
import cairo
import pytest
from gi.repository import GLib

from terminatorlib import paneoverlay as po
from test_m37_smooth_maximise import (  # noqa: F401  (fixture)
    win, _pane, _pump, _pump_until, _force_snapshot, _manual_animator)


def test_animator_duration_is_public():
    anim, src = _manual_animator([], [])
    anim.start(250)
    assert anim.duration == pytest.approx(0.25)


def _solid(fmt, rgba):
    s = cairo.ImageSurface(fmt, 32, 32)
    cr = cairo.Context(s)
    cr.set_source_rgba(*rgba)
    cr.set_operator(cairo.OPERATOR_SOURCE)
    cr.paint()
    return s


def test_surface_looks_blank():
    assert po.surface_looks_blank(
        _solid(cairo.FORMAT_RGB24, (0, 0, 0, 1)), 32, 32)
    assert po.surface_looks_blank(
        _solid(cairo.FORMAT_ARGB32, (1, 1, 1, 0)), 32, 32)
    assert not po.surface_looks_blank(
        _solid(cairo.FORMAT_RGB24, (0.2, 0.3, 0.4, 1)), 32, 32)
    # a single non-black stripe is enough
    s = _solid(cairo.FORMAT_RGB24, (0, 0, 0, 1))
    cr = cairo.Context(s)
    cr.set_source_rgb(1, 1, 1)
    cr.rectangle(0, 10, 32, 4)
    cr.fill()
    assert not po.surface_looks_blank(s, 32, 32)


def test_capture_keeps_alpha_on_rgba_visual(win, monkeypatch):
    seen = []
    real = type(win.get_window()).create_similar_surface

    def spy(self, content, w, h):
        seen.append(content)
        return real(self, content, w, h)
    t = _pane(win)
    monkeypatch.setattr(type(win.get_window()), 'create_similar_surface',
                        spy)
    monkeypatch.setattr(po, '_window_is_rgba', lambda w: True)
    assert po.capture_widget_surface(t) is not None
    monkeypatch.setattr(po, '_window_is_rgba', lambda w: False)
    assert po.capture_widget_surface(t) is not None
    assert seen == [cairo.CONTENT_COLOR_ALPHA, cairo.CONTENT_COLOR]


def test_blank_wayland_capture_falls_back(win, monkeypatch):
    t = _pane(win)
    monkeypatch.setattr(po, '_is_wayland', lambda w: True)
    monkeypatch.setattr(po, 'surface_looks_blank', lambda s, w, h: True)
    assert po.capture_widget_surface(t) is None
    monkeypatch.setattr(po, 'surface_looks_blank', lambda s, w, h: False)
    assert po.capture_widget_surface(t) is not None
    # not Wayland: never second-guessed (black terminals are legitimate)
    monkeypatch.setattr(po, '_is_wayland', lambda w: False)
    monkeypatch.setattr(po, 'surface_looks_blank', lambda s, w, h: True)
    assert po.capture_widget_surface(t) is not None


def test_blank_snapshot_uses_fade_path(win, monkeypatch):
    monkeypatch.setattr(po, 'should_reduce_motion', lambda c=None: False)
    monkeypatch.setattr(po, 'capture_widget_surface', lambda w: None)
    monkeypatch.setattr(po, 'capture_terminal_pixbuf', lambda t: None)
    t = _pane(win)
    assert win.overlay_maximise(t, animate=True)
    ov = win._overlay
    assert ov.data['snapshot'] is None and not ov.data['frame_hidden']
    assert _pump_until(lambda: not ov.is_animating())
    assert ov.is_active()


def test_reverse_mid_expand_unhides_terminal(win, monkeypatch):
    _force_snapshot(monkeypatch)
    t = _pane(win)
    ov = win._ensure_overlay()
    assert win.overlay_maximise(t, animate=True)
    assert ov.data['frame_hidden'] is True
    _pump(0.03)
    assert ov.is_animating()
    assert win.overlay_maximise(t, animate=True)   # reverse mid-expand
    assert ov._animator.reversed and ov.data['restore_pending']
    assert _pump_until(lambda: not ov.is_active())
    assert t.get_parent() is not None and t.get_toplevel() is win
    assert getattr(t, '_overlay_placeholder', None) is None
    assert t.get_visible() and t.get_child_visible()
    assert t.get_opacity() == pytest.approx(1.0)
    assert ov._watchdog is None


def test_session_defer_cap_saves_with_endless_animation(monkeypatch):
    from terminatorlib import session as sess
    sm = sess.SessionManager.__new__(sess.SessionManager)
    saved, timers = [], []
    sm.save_now = lambda final=False: saved.append(final)
    sm._overlay_animating = lambda: True        # never finishes
    monkeypatch.setattr(GLib, 'timeout_add',
                        lambda ms, fn: timers.append(fn) or len(timers))
    sm._timer = 1
    sm._anim_deferrals = 0
    sm._flush()
    while timers and not saved:                 # follow the retry chain
        timers.pop(0)()
    assert saved == [False]
    assert sm._anim_deferrals == 0 and sm._timer is None
    assert len(timers) == 0
    # counter was reset: the next burst gets the full budget again
    sm._flush()
    assert saved == [False] and sm._anim_deferrals == 1
