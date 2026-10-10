"""m25 follow-ups: _any_legacy_zoom (GTK-free), final-save guard,
deregister_window marks dirty."""
import json
import os

import pytest

from terminatorlib.session import SessionManager


def _reset():
    from terminatorlib.borg import Borg
    Borg._Borg__shared_state.pop('SessionManager', None)


class FakeWin:
    def __init__(self, zoomed=False, overlay=False):
        self._z, self._o = zoomed, overlay
        self.unzoomed = 0

    def is_zoomed(self):
        return self._z

    def is_overlay_maximised(self):
        return self._o

    def unzoom(self):
        self.unzoomed += 1


class FakeTerminator:
    doing_layout = False

    def __init__(self, windows):
        self.windows = windows


@pytest.fixture
def sm(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    _reset()
    s = SessionManager()
    yield s
    try:
        os.close(s._lock_fd)
    except Exception:
        pass
    _reset()


def _patch_windows(monkeypatch, windows):
    import terminatorlib.terminator as tmod
    ft = FakeTerminator(windows)
    monkeypatch.setattr(tmod, 'Terminator', lambda: ft)
    return ft


@pytest.mark.parametrize('wins, expected', [
    ([], False),
    ([FakeWin()], False),
    ([FakeWin(zoomed=True)], True),                    # legacy zoom
    ([FakeWin(zoomed=False, overlay=True)], False),    # overlay only
    ([FakeWin(zoomed=True, overlay=True)], False),     # both: overlay wins
    ([FakeWin(zoomed=True, overlay=True), FakeWin(zoomed=True)], True),
    ([object()], False),                               # no is_zoomed attr
])
def test_any_legacy_zoom(sm, monkeypatch, wins, expected):
    _patch_windows(monkeypatch, wins)
    assert sm._any_legacy_zoom() is expected


def test_any_legacy_zoom_swallows_errors(sm, monkeypatch):
    class Boom(FakeWin):
        def is_zoomed(self):
            raise RuntimeError('x')
    _patch_windows(monkeypatch, [Boom()])
    assert sm._any_legacy_zoom() is False


def test_unzoom_legacy_all_skips_overlay(sm, monkeypatch):
    a, b, c = FakeWin(zoomed=True), FakeWin(zoomed=True, overlay=True), FakeWin()
    _patch_windows(monkeypatch, [a, b, c])
    sm._unzoom_legacy_all()
    assert (a.unzoomed, b.unzoomed, c.unzoomed) == (1, 0, 0)


def _one_pane():
    return {'child0': {'type': 'Window', 'parent': ''},
            'terminal1': {'type': 'Terminal', 'parent': 'child0',
                          'uuid': 'u1'}}


def test_final_save_refuses_detached_tree(sm, monkeypatch):
    assert sm.acquire_lock()
    sm._owns_session = True
    _patch_windows(monkeypatch, [FakeWin(zoomed=True)])
    monkeypatch.setattr(SessionManager, '_describe_current',
                        lambda self: _one_pane())
    assert sm.save_now(final=True) is False
    assert not os.path.exists(sm.session_path())


def test_final_save_writes_when_not_zoomed(sm, monkeypatch):
    assert sm.acquire_lock()
    sm._owns_session = True
    _patch_windows(monkeypatch, [FakeWin()])
    monkeypatch.setattr(SessionManager, '_describe_current',
                        lambda self: _one_pane())
    assert sm.save_now(final=True)
    with open(sm.session_path()) as f:
        assert 'layout' in json.load(f)


def test_deregister_window_marks_dirty(monkeypatch):
    import terminatorlib.session as smod
    from terminatorlib.terminator import Terminator
    calls = []
    monkeypatch.setattr(smod, 'try_mark_dirty', lambda r='': calls.append(r))
    t = Terminator()
    w1, w2 = object(), object()
    saved = list(t.windows)
    t.windows[:] = [w1, w2]
    try:
        t.deregister_window(w1)
    finally:
        t.windows[:] = saved
    assert calls == ['deregister_window']
