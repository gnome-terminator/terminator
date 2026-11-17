"""m29: scrollback cache writes nothing once the display is lost; watch_display
connects once; several saves during one restore chain the crash marker."""
import os
import types
import uuid as uuidlib

import pytest

from terminatorlib import scrollback as sb
import terminatorlib.terminator as tmod
from tests.test_m27_restore_rotation_guard import (  # noqa: F401
    sm, _write, _uid, _marker_src, _save_during_restore)


class FakeTerm(object):
    def __init__(self):
        self.uuid = uuidlib.uuid4()
        self.vte = object()


@pytest.fixture
def lost(monkeypatch):
    state = {'lost': False}
    fake = types.SimpleNamespace(_check_display_lost=lambda: state['lost'])
    monkeypatch.setattr(sb, '_session_manager', lambda: fake)
    return state


@pytest.fixture
def cache(monkeypatch, tmp_path):
    c = sb.ScrollbackCache()
    monkeypatch.setattr(c, '_enabled', True, raising=False)
    monkeypatch.setattr(c, '_disabled_by_error', None, raising=False)
    c._dirty, c._visit, c._tick, c._snap_at = set(), {}, 0, {}
    c._snap_pending = {}
    c._last_hash = {}
    reads = []
    monkeypatch.setattr(sb, 'read_last_n_lines_raw',
                        lambda *a, **k: (reads.append(1), ('x', False))[1])
    monkeypatch.setattr(sb, 'cache_exclusion', lambda t, cfg: False)
    monkeypatch.setattr(sb, '_terminal_window_excluded', lambda t: False)
    monkeypatch.setattr(sb, 'in_alt_screen', lambda t: False)
    monkeypatch.setattr(sb, '_sm_will_persist', lambda t: True)
    writes, deletes = [], []
    monkeypatch.setattr(sb.sbt, 'atomic_write_txt',
                        lambda p, d, mode=0: writes.append(p))
    monkeypatch.setattr(c, 'delete_uuid', lambda u: deletes.append(u),
                        raising=False)
    monkeypatch.setattr(c, 'path_for', lambda u: str(tmp_path / u))
    c._queue = types.SimpleNamespace(put=lambda item: writes.append(item))
    c.reads, c.writes, c.deletes = reads, writes, deletes
    return c


def test_interval_flush_skipped_when_display_lost(cache, lost, monkeypatch):
    t = FakeTerm()
    monkeypatch.setattr(tmod, 'Terminator',
                        lambda: types.SimpleNamespace(terminals=[t]))
    cache._dirty.add(str(t.uuid))
    lost['lost'] = True
    # m32: display loss is sticky, so the timer stops itself
    assert cache._on_interval() is False
    assert cache.writes == [] and cache.reads == []
    assert str(t.uuid) in cache._dirty
    lost['lost'] = False
    cache._on_interval()
    assert len(cache.writes) == 1


def test_terminal_close_flush_skipped_when_display_lost(cache, lost):
    t = FakeTerm()
    lost['lost'] = True
    cache.on_terminal_close(t)
    assert cache.writes == [] and cache.deletes == []
    lost['lost'] = False
    cache.on_terminal_close(t)
    assert len(cache.writes) == 1


def test_deferred_snapshot_skipped_when_display_lost(cache, lost,
                                                     monkeypatch):
    timers = []
    monkeypatch.setattr(sb.GLib, 'timeout_add',
                        lambda ms, fn: (timers.append(fn), 7)[1])
    calls = []
    monkeypatch.setattr(cache, 'snapshot_before_command',
                        lambda term, now=None: calls.append(term))
    t = FakeTerm()
    cache._defer_snapshot(t, str(t.uuid), 0.1)
    lost['lost'] = True
    assert timers[0]() is False
    assert calls == [] and cache.writes == []


def test_direct_flush_skipped_when_display_lost(cache, lost):
    t = FakeTerm()
    lost['lost'] = True
    cache._flush_uuid(t, str(t.uuid), sync=True)
    cache._flush_uuid(t, str(t.uuid), sync=False)
    assert cache.writes == [] and cache.reads == []


class _Disp(object):
    def __init__(self):
        self.n = 0

    def connect(self, name, cb):
        self.n += 1
        return self.n

    def is_closed(self):
        return False


def test_watch_display_connects_only_once(sm):
    a, b = _Disp(), _Disp()
    assert sm.watch_display(a) is True
    assert sm.watch_display(a) is True
    assert sm.watch_display(b) is True
    assert a.n == 1 and b.n == 0


def test_several_saves_during_one_restore_rotate_once(sm):
    """Rotation is once per run: later saves in the same restore keep the
    marker on .prev (the real source) and never push it on to .prev2."""
    path = sm.session_path()
    _write(path, 'src')
    assert sm.load() is not None and sm._loaded_from == path
    sm.begin_restore()
    assert _marker_src(sm) == 'session.json'
    for uid in ('n1', 'n2', 'n3'):
        _save_during_restore(sm, uid)
        assert _marker_src(sm) == 'session.json.prev'
        assert _uid(path + '.prev') == 'src'
    assert _uid(path) == 'n3'
    assert sm.check_crash_marker() is True
    assert _uid(path + '.prev.crashed') == 'src'


def test_marker_chain_follows_each_rotation(sm):
    """Each rotation retargets the marker: session.json -> .prev -> .prev2
    -> '-' (forced rotations stand in for successive runs)."""
    path = sm.session_path()
    _write(path, 'src')
    assert sm.load() is not None
    sm.begin_restore()
    expected = ['session.json.prev', 'session.json.prev2', '-']
    for n, want in enumerate(expected):
        sm._rotated_this_run = False
        _save_during_restore(sm, 'n%d' % n)
        assert _marker_src(sm) == want
    assert _uid(path + '.prev2') == 'n0'
    assert sm.check_crash_marker() is True
    # source already rotated away: only session.json is set aside (by
    # design), rotated copies are left alone
    crashed = sorted(n for n in os.listdir(os.path.dirname(path))
                     if n.endswith('.crashed'))
    assert crashed == ['session.json.crashed']
    assert _uid(path + '.prev2') == 'n0'
