"""m32: scrollback timers/worker honour display loss; delete is frozen too."""
import queue
import types

from terminatorlib import scrollback as sb
from tests.test_m29_displaylost_cache import (  # noqa: F401
    cache, lost, FakeTerm)


def test_interval_timer_stops_and_cancels_pending(cache, lost, monkeypatch):
    removed = []
    monkeypatch.setattr(sb.GLib, 'source_remove', lambda sid: removed.append(sid))
    cache._timer_id = 7
    cache._snap_pending = {'u1': 42}
    lost['lost'] = True
    assert cache._on_interval() is False
    assert cache._timer_id == 0
    assert removed == [42] and cache._snap_pending == {}


def test_interval_stops_even_when_clean(cache, lost):
    cache._dirty = set()
    lost['lost'] = True
    assert cache._on_interval() is False


def test_delete_uuid_skipped_when_display_lost(monkeypatch, tmp_path):
    c = sb.ScrollbackCache()
    f = tmp_path / 'x.txt'
    f.write_text('keep')
    monkeypatch.setattr(c, 'path_for', lambda u: str(f))
    monkeypatch.setattr(sb, '_session_manager', lambda: types.SimpleNamespace(
        _check_display_lost=lambda: True, _display_lost=True))
    c.delete_uuid('u1')
    assert f.read_text() == 'keep'


def test_worker_drops_queued_items_after_display_loss(monkeypatch, tmp_path):
    c = sb.ScrollbackCache()
    sm = types.SimpleNamespace(_display_lost=False)
    monkeypatch.setattr(sb, '_session_manager', lambda: sm)
    f = tmp_path / 'u1.txt'
    f.write_text('old')
    monkeypatch.setattr(c, 'path_for', lambda u: str(f))
    writes = []
    monkeypatch.setattr(sb.sbt, 'atomic_write_txt',
                        lambda p, d, mode=0: writes.append(d))
    monkeypatch.setattr(sb.GLib, 'idle_add', lambda *a: None)
    c._seq = {'u1': 1}
    q = queue.Queue()
    c._queue = q
    q.put(('write', 'u1', b'new', 'h', 1))
    q.put(('delete', 'u1'))
    q.put(('stop',))
    sm._display_lost = True  # lost after the items were queued
    c._worker_loop()
    assert writes == [] and f.read_text() == 'old'


def test_worker_still_writes_without_display_loss(monkeypatch, tmp_path):
    c = sb.ScrollbackCache()
    monkeypatch.setattr(sb, '_session_manager',
                        lambda: types.SimpleNamespace(_display_lost=False))
    monkeypatch.setattr(c, 'path_for', lambda u: str(tmp_path / 'u1.txt'))
    writes = []
    monkeypatch.setattr(sb.sbt, 'atomic_write_txt',
                        lambda p, d, mode=0: writes.append(d))
    monkeypatch.setattr(sb.GLib, 'idle_add', lambda *a: None)
    c._seq = {'u1': 1}
    c._bytes_since_gc = 0
    q = queue.Queue()
    c._queue = q
    q.put(('write', 'u1', b'new', 'h', 1))
    q.put(('stop',))
    c._worker_loop()
    assert writes == [b'new']
