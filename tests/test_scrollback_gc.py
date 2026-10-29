"""m16: runtime total-size cleanup of the scrollback cache directory."""
import os
import queue
import uuid as uuidlib

import pytest

from terminatorlib import scrollback as sb


@pytest.fixture
def cache(tmp_path, monkeypatch):
    c = sb.ScrollbackCache()
    c._dir = str(tmp_path)
    c._seq = {}
    c._last_hash = {}
    c._dirty = set()
    c._last_gc = None
    c._bytes_since_gc = 0
    monkeypatch.setattr(sb.GLib, 'idle_add', lambda fn, *a: fn(*a))
    monkeypatch.setattr(c, '_total_mb', lambda: 1)
    # ScrollbackCache is a Borg: restore shared state so later tests are clean
    saved = (c._queue, c._started, c._last_gc, c._bytes_since_gc)
    yield c
    c._queue, c._started, c._last_gc, c._bytes_since_gc = saved


def _mk(c, u, size, mtime):
    p = c.path_for(u)
    with open(p, 'wb') as fh:
        fh.write(b'x' * size)
    os.utime(p, (mtime, mtime))
    return p


MB = 1024 * 1024


def test_under_cap_untouched(cache):
    u = str(uuidlib.uuid4())
    p = _mk(cache, u, 1000, 100)
    assert cache.enforce_total_cap() == []
    assert os.path.exists(p)


def test_prunes_oldest_first(cache):
    a, b, c_ = (str(uuidlib.uuid4()) for _ in range(3))
    _mk(cache, a, MB // 2, 100)
    _mk(cache, b, MB // 2, 200)
    _mk(cache, c_, MB // 2, 300)
    assert cache.enforce_total_cap() == [a]
    assert not os.path.exists(cache.path_for(a))
    assert os.path.exists(cache.path_for(b))


def test_orphans_pruned_before_live_even_if_newer(cache):
    live, orphan = str(uuidlib.uuid4()), str(uuidlib.uuid4())
    _mk(cache, live, MB * 3 // 4, 100)       # oldest but live
    _mk(cache, orphan, MB * 3 // 4, 900)
    cache._last_hash[live] = 'h'
    assert cache.enforce_total_cap({live}) == [orphan]
    assert os.path.exists(cache.path_for(live))
    assert cache._last_hash[live] == 'h'


def test_live_never_pruned_at_runtime(cache):
    a, b, o = (str(uuidlib.uuid4()) for _ in range(3))
    _mk(cache, a, MB, 100)
    _mk(cache, b, MB // 2, 200)
    _mk(cache, o, 10, 300)
    cache._last_hash[a] = 'h'
    assert cache.enforce_total_cap({a, b}) == [o]
    assert os.path.exists(cache.path_for(a)) and cache._last_hash[a] == 'h'
    assert a not in cache._dirty


def test_ignores_non_cache_files(cache, tmp_path):
    other = tmp_path / 'notes.txt'
    other.write_bytes(b'y' * (2 * MB))
    assert cache.enforce_total_cap() == []
    assert other.exists()


def test_does_not_bump_seq(cache):
    """A write queued after the gc item must still land."""
    a = str(uuidlib.uuid4())
    _mk(cache, a, 2 * MB, 100)
    s = cache._bump(a)
    cache._queue = queue.Queue()
    for it in [('gc', frozenset({a})), ('write', a, b'NEW', 'h', s), ('stop',)]:
        cache._queue.put(it)
    cache._worker_loop()
    assert open(cache.path_for(a), 'rb').read() == b'NEW'
    assert cache._last_hash[a] == 'h'


def test_worker_write_counts_bytes_and_throttle(cache):
    cache._started = True
    cache._queue = queue.Queue()
    assert cache._maybe_queue_gc(set(), now=1000) is False  # nothing written
    cache._bytes_since_gc = 10
    assert cache._maybe_queue_gc({'x'}, now=1000) is True
    assert cache._queue.get_nowait() == ('gc', frozenset({'x'}))
    cache._bytes_since_gc = 10
    assert cache._maybe_queue_gc(set(), now=1010) is False  # throttled
    assert cache._maybe_queue_gc(set(), now=1000 + cache.GC_MIN_INTERVAL_S) is True


def test_worker_write_increments_counter(cache):
    u = str(uuidlib.uuid4())
    s = cache._bump(u)
    cache._bytes_since_gc = 0
    cache._queue = queue.Queue()
    for it in [('write', u, b'12345', 'h', s), ('stop',)]:
        cache._queue.put(it)
    cache._worker_loop()
    assert cache._bytes_since_gc == 5


def test_counter_reset_and_increment_use_io_lock(cache):
    import threading
    cache._started = True
    cache._queue = queue.Queue()
    cache._bytes_since_gc = 5
    real = cache._io_lock
    seen = []

    class L(object):
        def __enter__(self):
            seen.append(1); return real.__enter__()
        def __exit__(self, *a):
            return real.__exit__(*a)
    cache._io_lock = L()
    try:
        assert cache._maybe_queue_gc(set(), now=5000) is True
    finally:
        cache._io_lock = real
    assert seen and cache._bytes_since_gc == 0
