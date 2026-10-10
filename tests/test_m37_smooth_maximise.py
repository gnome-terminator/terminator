"""m37: smooth overlay-maximise animation (frame clock, server-side
snapshot, no VTE painting / resizing mid-flight, instant when animations
are disabled, rapid toggles, stall watchdog, session save deferral)."""
import time

import pytest
from gi.repository import Gtk, GLib

from terminatorlib import paneoverlay as po


def _pump(seconds=0.0):
    end = time.monotonic() + seconds
    while True:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        if time.monotonic() >= end:
            break
        time.sleep(0.005)


def _pump_until(pred, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        _pump(0.01)
        if pred():
            return True
    return pred()


# ---- Animator ------------------------------------------------------------

def _manual_animator(ticks, done, sync=True):
    src = {}
    anim = po.Animator(
        on_tick=lambda p, r: ticks.append((p, r)),
        on_done=lambda cancelled=False: done.append(cancelled),
        clock=lambda: 0.0,
        schedule=lambda cb: src.setdefault('cb', cb) and 7,
        unschedule=lambda sid: src.pop('cb', None),
        sync_first_frame=sync)
    return anim, src


def test_first_frame_is_time_origin():
    """Setup before the first painted frame must not eat progress."""
    ticks, done = [], []
    anim, src = _manual_animator(ticks, done)
    anim.start(200, easing=po.ease_out_cubic)
    assert src['cb'](5.0) is True          # first frame 5s "later"
    assert ticks[-1] == (0.0, 0.0)
    assert src['cb'](5.1) is True
    assert 0.0 < ticks[-1][0] < 1.0 and abs(ticks[-1][1] - 0.5) < 1e-9
    assert src['cb'](5.2) is False
    assert done == [False] and anim.progress == 1.0 and anim.ticks == 3


def test_without_sync_uses_clock_origin():
    ticks, done = [], []
    anim, src = _manual_animator(ticks, done, sync=False)
    anim.start(100)
    assert src['cb'](0.05) is True
    assert abs(ticks[-1][1] - 0.5) < 1e-9


def test_reverse_shortens_to_distance_left():
    ticks, done = [], []
    anim, src = _manual_animator(ticks, done)
    anim.start(200, easing=lambda t: t)    # linear for easy numbers
    src['cb'](0.0)
    src['cb'](0.05)                        # progress 0.25
    assert abs(anim.progress - 0.25) < 1e-9
    anim.reverse(200)
    assert anim.reversed and abs(anim._duration - 0.06) < 1e-9  # min 60ms
    anim2, src2 = _manual_animator([], [])
    anim2.start(200, easing=lambda t: t)
    src2['cb'](0.0)
    src2['cb'](0.15)                       # 0.75 → reverse covers 0.75
    anim2.reverse(200)
    assert abs(anim2._duration - 0.15) < 1e-9
    assert abs(anim2.progress - 0.75) < 1e-9   # no jump


def test_frame_clock_scheduler():
    assert po.frame_clock_scheduler(None) is None
    assert po.frame_clock_scheduler(Gtk.Label()) is None   # unrealized

    class Clock(object):
        def get_frame_time(self):
            return 2500000

    class W(object):
        removed = []

        def get_frame_clock(self):
            return Clock()

        def add_tick_callback(self, fn):
            self.fn = fn
            return 42

        def remove_tick_callback(self, tid):
            self.removed.append(tid)

    w = W()
    schedule, unschedule = po.frame_clock_scheduler(w)
    seen = []
    assert schedule(lambda now: seen.append(now) or True) == 42
    assert w.fn(w, Clock()) is True and seen == [2.5]
    unschedule(42)
    assert W.removed == [42]


# ---- drawing helpers -------------------------------------------------------

def test_paint_snapshot_stretches_surface():
    import cairo
    src = cairo.ImageSurface(cairo.FORMAT_RGB24, 10, 10)
    c = cairo.Context(src)
    c.set_source_rgb(1, 0, 0)
    c.paint()
    dst = cairo.ImageSurface(cairo.FORMAT_RGB24, 40, 40)
    cr = cairo.Context(dst)
    assert po.paint_snapshot(cr, (src, 10, 10), (10, 10, 20, 20)) is True
    dst.flush()
    data = dst.get_data()
    stride = dst.get_stride()

    def px(x, y):
        o = y * stride + x * 4
        return data[o + 2], data[o + 1], data[o]   # BGRx → RGB
    assert px(20, 20) == (255, 0, 0)
    assert px(5, 5) == (0, 0, 0)      # clipped to rect
    assert px(35, 35) == (0, 0, 0)
    assert po.paint_snapshot(cr, (src, 10, 10), (0, 0, 20, 20), 0.0) is False
    assert po.paint_snapshot(cr, None, (0, 0, 20, 20)) is False


def test_snapshot_area_prefers_surface():
    import cairo
    area = po.SnapshotArea()
    assert not area.has_content()
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, 4, 4)
    area.set_snap((surf, 4, 4))
    assert area.has_content() and area._pixbuf is None


# ---- controller in a real window -------------------------------------------

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
    t = Factory().make('Terminal')
    w.add(t)
    w.resize(900, 600)
    w.show_all()
    _pump(0.2)
    a = list(w.get_terminals())[0]
    w.split_axis(a, True)
    _pump(0.3)
    yield w
    for term in list(Terminator().terminals):
        if term.get_toplevel() is w:
            Terminator().deregister_terminal(term)
    if not getattr(w, 'isDestroyed', False):
        w.destroy()
    _pump()


def _pane(win):
    return list(win.get_terminals())[-1]


def _force_snapshot(monkeypatch):
    import cairo
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, 8, 8)
    monkeypatch.setattr(po, 'capture_widget_surface',
                        lambda w: (surf, 8, 8))


def test_reduce_motion_is_instant(win, monkeypatch):
    monkeypatch.setattr(po, 'should_reduce_motion', lambda c=None: True)
    t = _pane(win)
    assert win.overlay_maximise(t, animate=True)
    ov = win._overlay
    assert ov.is_active() and not ov.is_animating()
    assert ov.data['snapshot'] is None and not ov.data['frame_hidden']
    assert ov.data['dim']._alpha == pytest.approx(ov.DIM_ALPHA)
    assert win.overlay_restore(animate=True)
    assert not ov.is_active()


def test_expand_hides_live_terminal_until_handover(win, monkeypatch):
    _force_snapshot(monkeypatch)
    t = _pane(win)
    sizes = []
    t.vte.connect('size-allocate', lambda w, a: sizes.append(
        (a.width, a.height)))
    assert win.overlay_maximise(t, animate=True)
    ov = win._overlay
    data = ov.data
    assert ov.is_animating()
    # frame-clock driven, time origin = first frame
    assert ov._animator._sync_first and ov._animator._source is not None
    assert data['frame_hidden'] is True
    assert ov._on_frame_draw(data['frame'], None) is True
    n_alloc = len(set(sizes))
    seen_hidden = []
    while ov.is_animating():
        _pump(0.005)
        seen_hidden.append(bool(data['frame_hidden']))
    assert _pump_until(lambda: not ov.is_animating())
    assert ov._animator is None or not ov._animator.running
    assert True in seen_hidden
    assert data['frame_hidden'] is False
    assert ov._on_frame_draw(data['frame'], None) is False
    assert not data['snapshot'].get_visible()
    # the VTE never saw intermediate sizes (no per-frame PTY resize)
    assert len(set(sizes)) - n_alloc <= 1
    assert ov._watchdog is None


def test_restore_lands_on_current_slot(win, monkeypatch):
    t = _pane(win)
    assert win.overlay_maximise(t, animate=False)
    _pump(0.2)
    win.resize(700, 500)          # slot moves while maximised
    _pump(0.4)
    ov = win._overlay
    _force_snapshot(monkeypatch)
    ph = ov.data['placeholder']
    expect = po._rect_from_widget(ph, ov.data['overlay'])
    assert win.overlay_restore(animate=True)
    data = ov.data
    assert data['src_rect'] == expect
    assert data['fly_dst'] is not None and data['frame_hidden'] is True
    assert _pump_until(lambda: not ov.is_active())
    assert t.get_parent() is not None and t.get_toplevel() is win
    assert getattr(t, '_overlay_placeholder', None) is None


def test_rapid_toggles_end_consistent(win, monkeypatch):
    _force_snapshot(monkeypatch)
    t = _pane(win)
    ov = win._ensure_overlay()
    assert win.overlay_maximise(t, animate=True)
    _pump(0.03)
    assert win.overlay_maximise(t, animate=True)   # toggle → reverse
    assert ov.data['restore_pending'] and ov._animator.reversed
    _pump(0.01)
    assert win.overlay_maximise(t, animate=True)   # and back again
    assert not ov.data['restore_pending'] and not ov._animator.reversed
    assert _pump_until(lambda: not ov.is_animating())
    assert ov.is_active() and ov.data['frame_hidden'] is False
    assert ov.data['dim']._alpha == pytest.approx(ov.DIM_ALPHA)
    assert win.overlay_maximise(t, animate=True)   # restore
    assert win.overlay_restore(animate=False)      # cut short
    assert not ov.is_active() and ov._watchdog is None


def test_watchdog_finishes_stalled_animation(win, monkeypatch):
    _force_snapshot(monkeypatch)
    # a frame clock that never ticks (e.g. window iconified mid-flight)
    monkeypatch.setattr(po, 'frame_clock_scheduler',
                        lambda w: (lambda cb: 1, lambda tid: None))
    monkeypatch.setattr(po.OverlayController, 'WATCHDOG_STALL_S', 0.2)
    t = _pane(win)
    assert win.overlay_maximise(t, animate=True)
    ov = win._overlay
    assert ov.is_animating()
    assert _pump_until(lambda: not ov.is_animating(), 2.0)
    assert ov.is_active() and ov.data['emitted']
    assert ov.data['frame_hidden'] is False and ov._watchdog is None


def test_teardown_mid_animation_cancels_watchdog(win, monkeypatch):
    _force_snapshot(monkeypatch)
    t = _pane(win)
    assert win.overlay_maximise(t, animate=True)
    ov = win._overlay
    assert ov._watchdog is not None
    ov.teardown()
    assert ov._watchdog is None and ov.data is None


# ---- session save deferral ----------------------------------------------

def test_session_flush_waits_for_animation(monkeypatch):
    from terminatorlib import session as sess
    sm = sess.SessionManager.__new__(sess.SessionManager)
    saved, timers = [], []
    sm.save_now = lambda final=False: saved.append(final)
    animating = {'v': True}
    sm._overlay_animating = lambda: animating['v']
    monkeypatch.setattr(GLib, 'timeout_add',
                        lambda ms, fn: timers.append(ms) or 99)
    sm._timer = 1
    sm._anim_deferrals = 0
    assert sm._flush() is False
    assert saved == [] and sm._timer == 99 and timers == [sess.ANIM_DEFER_MS]
    animating['v'] = False
    sm._flush()
    assert saved == [False] and sm._anim_deferrals == 0
    # bounded: a stuck flag can't postpone saves forever
    animating['v'] = True
    for _ in range(sess.ANIM_DEFER_MAX):
        sm._flush()
    assert saved == [False]
    sm._flush()
    assert saved == [False, False]
