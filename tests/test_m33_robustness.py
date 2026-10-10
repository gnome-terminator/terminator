"""m33: robustness fixes (flush budget, HiDPI snapshot, idle periodic skip,
scrollback re-enable after disk-full, dim layer without compositor)."""
import types
import uuid as uuidlib

import pytest

from terminatorlib import scrollback as sb
from terminatorlib import session as sess
from terminatorlib import paneoverlay as po
import terminatorlib.terminator as tmod


class FakeTerm(object):
    def __init__(self):
        self.uuid = uuidlib.uuid4()


@pytest.fixture
def cache(monkeypatch):
    c = sb.ScrollbackCache()
    monkeypatch.setattr(c, '_enabled', True, raising=False)
    monkeypatch.setattr(c, '_disabled_by_error', False, raising=False)
    monkeypatch.setattr(c, '_fail_count', 0, raising=False)
    monkeypatch.setattr(c, '_reenable_id', 0, raising=False)
    monkeypatch.setattr(c, '_timer_id', 0, raising=False)
    c._dirty = set(); c._visit = {}; c._tick = 0
    flushed = []
    monkeypatch.setattr(c, '_flush_uuid',
                        lambda t, u, sync=False: (flushed.append(u),
                                                  c._dirty.discard(u)))
    monkeypatch.setattr(c, '_maybe_queue_gc', lambda live: None)
    c.flushed = flushed
    return c


def _terms(monkeypatch, terms):
    monkeypatch.setattr(tmod, 'Terminator',
                        lambda: types.SimpleNamespace(terminals=terms))


# (1) flush budget
def test_flush_budget_values():
    assert sb.flush_budget(0) == 0
    assert sb.flush_budget(1) == 1
    assert sb.flush_budget(3) == 2
    assert sb.flush_budget(40) == 20
    assert sb.flush_budget(41) == 21


def test_forty_busy_panes_saved_within_two_ticks(cache, monkeypatch):
    terms = [FakeTerm() for _ in range(45)]
    _terms(monkeypatch, terms)
    ids = {str(t.uuid) for t in terms}
    seen = set()
    for _ in range(2):
        cache._dirty.update(ids)  # all keep producing output
        cache._on_interval()
        seen.update(cache.flushed)
    assert seen == ids


def test_time_budget_stops_tick_but_flushes_at_least_two(cache, monkeypatch):
    terms = [FakeTerm() for _ in range(10)]
    _terms(monkeypatch, terms)
    cache._dirty.update(str(t.uuid) for t in terms)
    clock = iter(range(0, 1000))
    monkeypatch.setattr(sb, '_monotonic', lambda: float(next(clock)))
    cache._on_interval()
    assert len(cache.flushed) == 2


# (4) disk full re-enable
def test_write_failures_schedule_reenable(cache, monkeypatch):
    calls = []
    monkeypatch.setattr(sb.GLib, 'timeout_add_seconds',
                        lambda s, cb: calls.append((s, cb)) or 7)
    monkeypatch.setattr(sb.GLib, 'timeout_add', lambda ms, cb: 9)
    for _ in range(3):
        cache._on_write_failed(OSError(28, 'No space left'))
    assert cache._disabled_by_error is True
    assert len(calls) == 1 and calls[0][0] == sb.REENABLE_COOLDOWN_S
    t = FakeTerm(); _terms(monkeypatch, [t])
    monkeypatch.setattr(sb, '_sm_display_lost', lambda: False)
    assert calls[0][1]() is False
    assert cache._disabled_by_error is False
    assert cache._fail_count == 0
    assert str(t.uuid) in cache._dirty
    assert cache._timer_id == 9


def test_reenable_skipped_when_display_lost(cache, monkeypatch):
    cache._disabled_by_error = True
    monkeypatch.setattr(sb, '_sm_display_lost', lambda: True)
    cache._try_reenable()
    assert cache._disabled_by_error is True


# (3) idle periodic
def test_periodic_tick_skips_when_idle(monkeypatch):
    sm = sess.SessionManager()
    monkeypatch.setattr(sm, 'is_writer', lambda: True)
    monkeypatch.setattr(sm, 'final_saving', False, raising=False)
    marks = []
    monkeypatch.setattr(sm, 'mark_dirty', lambda r='': marks.append(r))
    monkeypatch.setattr(sm, '_events_since_save', False, raising=False)
    monkeypatch.setattr(sm, '_idle_ticks', 0, raising=False)
    for _ in range(sess.PERIODIC_FORCE_EVERY - 1):
        assert sm._periodic_tick() is True
    assert marks == []
    sm._periodic_tick()  # safety-net forced save
    assert marks == ['periodic']
    sm._events_since_save = True
    sm._periodic_tick()
    assert marks == ['periodic', 'periodic']


def test_real_event_sets_flag_periodic_does_not(monkeypatch):
    sm = sess.SessionManager()
    monkeypatch.setattr(sm, '_events_since_save', False, raising=False)
    monkeypatch.setattr(sm, 'is_writer', lambda: False)  # stop after flag
    monkeypatch.setattr(tmod, 'Terminator',
                        lambda: types.SimpleNamespace(doing_layout=False))
    sm.mark_dirty('periodic')
    assert sm._events_since_save is False
    sm.mark_dirty('split')
    assert sm._events_since_save is True


# (2) HiDPI
class _Win(object):
    def __init__(self, scale):
        self._s = scale
    def get_scale_factor(self):
        return self._s


def test_scale_factor_detection():
    assert po._scale_factor(None, _Win(2)) == 2
    assert po._scale_factor(object(), None) == 1


def test_capture_uses_scaled_path_on_hidpi(monkeypatch):
    win = _Win(2)
    alloc = types.SimpleNamespace(width=100, height=50)
    widget = types.SimpleNamespace(get_window=lambda: win,
                                   get_allocation=lambda: alloc)
    term = types.SimpleNamespace(vte=widget)
    monkeypatch.setattr(po, '_widget_for_gdk_window', lambda w, g: w)
    monkeypatch.setattr(po, '_translate_xy', lambda a, b, x, y: (3, 4))
    got = []
    monkeypatch.setattr(po, '_capture_scaled',
                        lambda g, x, y, w, h, s: got.append((x, y, w, h, s))
                        or 'PB2X')
    assert po.capture_terminal_pixbuf(term) == 'PB2X'
    assert got[0][2:] == (100, 50, 2)


def test_capture_scaled_real_surface():
    cairo = pytest.importorskip('cairo')
    calls = {}
    def fake_set_source(cr, win, x, y):
        calls['xy'] = (x, y)
        cr.set_source_rgb(1, 0, 0)
    import terminatorlib.paneoverlay as m
    orig = m.Gdk.cairo_set_source_window
    m.Gdk.cairo_set_source_window = fake_set_source
    try:
        pb = po._capture_scaled(object(), 5, 6, 10, 8, 2)
    finally:
        m.Gdk.cairo_set_source_window = orig
    assert pb is not None
    assert (pb.get_width(), pb.get_height()) == (20, 16)
    assert calls['xy'] == (-5.0, -6.0)


# (5) no compositor
def _dim(monkeypatch, composited, own_window=False):
    d = po.DimLayer()
    monkeypatch.setattr(po, '_screen_composited', lambda w: composited)
    monkeypatch.setattr(d, 'get_has_window', lambda: own_window)
    monkeypatch.setattr(d, 'get_visible_window', lambda: own_window)
    return d


def test_dim_alpha_composited_unchanged(monkeypatch):
    d = _dim(monkeypatch, True); d.set_alpha(0.55)
    assert d.effective_alpha() == pytest.approx(0.55)


def test_dim_alpha_capped_without_compositor(monkeypatch):
    d = _dim(monkeypatch, False); d.set_alpha(0.9)
    assert d.effective_alpha() == pytest.approx(po.NO_COMPOSITE_MAX_ALPHA)


def test_dim_skipped_if_own_window_without_compositor(monkeypatch):
    d = _dim(monkeypatch, False, own_window=True); d.set_alpha(0.55)
    assert d.effective_alpha() == 0.0


def test_dimlayer_has_no_own_window_by_default():
    d = po.DimLayer()
    assert d.get_visible_window() is False


# m33 review follow-ups
def test_stop_cancels_pending_reenable(cache, monkeypatch):
    removed = []
    monkeypatch.setattr(sb.GLib, 'source_remove', lambda i: removed.append(i))
    cache._reenable_id = 42
    cache._cancel_reenable()
    assert cache._reenable_id == 0 and removed == [42]


def test_divider_release_marks_session_dirty(monkeypatch):
    from terminatorlib import paned
    marks = []
    monkeypatch.setattr(sess, 'try_mark_dirty', lambda r='': marks.append(r))
    monkeypatch.setattr(paned, '_schedule_auto_font_on_widget',
                        lambda w: None, raising=False)
    fake = types.SimpleNamespace(last_balance_time=0)
    ev = types.SimpleNamespace(button=1)
    assert paned.Paned.on_button_release(fake, None, ev) is False
    assert marks == ['paned.drag']
