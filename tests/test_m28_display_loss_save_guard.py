"""m28: a lost X display / abnormal teardown must never overwrite the session."""
import json
import os

import pytest

from terminatorlib.session import SessionManager


def _reset():
    from terminatorlib.borg import Borg
    Borg._Borg__shared_state.pop('SessionManager', None)


def _full():
    return {
        'child0': {'type': 'Window', 'parent': ''},
        'child1': {'type': 'HPaned', 'parent': 'child0', 'order': '0'},
        'terminal2': {'type': 'Terminal', 'parent': 'child1', 'order': '0', 'uuid': 'u1'},
        'terminal3': {'type': 'Terminal', 'parent': 'child1', 'order': '1', 'uuid': 'u2'},
    }


def _degraded():
    return {
        'child0': {'type': 'Window', 'parent': ''},
        'terminal1': {'type': 'Terminal', 'parent': 'child0', 'uuid': 'u1'},
    }


class FakeTerm:
    doing_layout = False
    windows = []
    terminals = []


class FakeDisplay:
    def __init__(self):
        self.closed = False
        self.handlers = []

    def is_closed(self):
        return self.closed

    def connect(self, name, cb):
        assert name == 'closed'
        self.handlers.append(cb)
        return len(self.handlers)

    def fire_closed(self, is_error=True):
        self.closed = True
        for cb in self.handlers:
            cb(self, is_error)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    _reset()
    s = SessionManager()
    assert s.acquire_lock()
    s._owns_session = True
    state = {'layout': _full, 'timers': [], 'removed': []}
    import terminatorlib.terminator as tmod
    monkeypatch.setattr(tmod, 'Terminator', lambda: FakeTerm())
    monkeypatch.setattr(SessionManager, '_any_legacy_zoom', lambda self: False)
    monkeypatch.setattr(SessionManager, '_describe_current',
                        lambda self: state['layout']())
    disp = FakeDisplay()
    from gi.repository import Gdk, GLib
    monkeypatch.setattr(Gdk.Display, 'get_default', staticmethod(lambda: disp))

    def fake_add(delay, fn, *a):
        state['timers'].append(fn)
        return len(state['timers'])
    monkeypatch.setattr(GLib, 'timeout_add', fake_add)
    monkeypatch.setattr(GLib, 'source_remove',
                        lambda tid: state['removed'].append(tid))
    yield s, state, disp
    try:
        os.close(s._lock_fd)
    except Exception:
        pass
    _reset()


def _saved(s):
    with open(s.session_path(), encoding='utf-8') as fh:
        return json.load(fh)['layout']


def _nterms(layout):
    return sum(1 for v in layout.values() if v.get('type') == 'Terminal')


def test_normal_save_still_works(env):
    s, state, disp = env
    assert s.save_now() is True
    assert _nterms(_saved(s)) == 2


def test_closed_signal_freezes_saves(env):
    s, state, disp = env
    assert s.save_now() is True
    assert s.watch_display() is True
    assert s.watch_display() is True  # idempotent
    assert len(disp.handlers) == 1
    disp.fire_closed()
    state['layout'] = _degraded
    assert s.save_now() is False
    assert s.save_now(final=True) is False
    assert _nterms(_saved(s)) == 2


def test_is_closed_detected_without_signal(env):
    s, state, disp = env
    assert s.save_now() is True
    disp.closed = True
    state['layout'] = _degraded
    assert s.save_now(final=True) is False
    assert s._display_lost is True
    # sticky even if the display object later looks fine
    disp.closed = False
    assert s.save_now() is False
    assert _nterms(_saved(s)) == 2


def test_pending_timer_cancelled_and_no_new_timer(env):
    s, state, disp = env
    s.mark_dirty('split')
    assert s._timer is not None
    s.note_display_lost('test')
    assert s._timer is None
    assert state['removed']
    n = len(state['timers'])
    s.mark_dirty('after-loss')
    assert len(state['timers']) == n
    assert s._timer is None


def test_stale_timer_firing_after_loss_does_not_write(env):
    s, state, disp = env
    assert s.save_now() is True
    s._last_change_hash = None
    s.mark_dirty('x')
    fn = state['timers'][-1]
    disp.fire_closed() if disp.handlers else None
    disp.closed = True
    state['layout'] = _degraded
    fn()
    assert _nterms(_saved(s)) == 2


def test_closing_buffer_dropped_and_not_refilled(env):
    s, state, disp = env
    s._closing_buffer = {'deadline': 0, 'windows': [_full()], 'uuids': {'u1'}}
    s.note_display_lost('test')
    assert s._closing_buffer is None

    class W:
        _session_excluded = False
    s.note_window_closing(W())
    assert s._closing_buffer is None


def test_finalize_after_loss_keeps_file_and_skips_scrollback(env, monkeypatch):
    s, state, disp = env
    assert s.save_now() is True
    calls = []
    import terminatorlib.scrollback as sb

    class FakeCache:
        def flush_all(self, **kw):
            calls.append('flush')

        def stop(self, **kw):
            calls.append('stop')
    monkeypatch.setattr(sb, 'ScrollbackCache', FakeCache)
    monkeypatch.setattr(SessionManager, '_unzoom_legacy_all', lambda self: None)
    disp.fire_closed() if disp.handlers else None
    disp.closed = True
    state['layout'] = lambda: {}
    s.finalize()
    assert _nterms(_saved(s)) == 2
    assert calls == ['stop']


def test_no_default_display_is_not_loss(env, monkeypatch):
    s, state, disp = env
    from gi.repository import Gdk
    monkeypatch.setattr(Gdk.Display, 'get_default', staticmethod(lambda: None))
    assert s.save_now() is True
    assert s.watch_display() is False
