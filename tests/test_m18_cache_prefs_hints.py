"""m18: prefs hints (0 = off, live files bounded per-file) and GC/seq locking."""
import queue
import threading

import pytest

from terminatorlib import scrollback as sb

gi = pytest.importorskip('gi')
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')
from terminatorlib.prefseditor import scrollback_cache_info_text  # noqa: E402


def test_info_text_values():
    t = scrollback_cache_info_text('/c', 2, 2048, 7, 20)
    assert '7 days' in t and '20 MiB' in t and '2 KiB' in t
    assert '0 = off' in t and 'scrollback_cache_max_kb' in t


def test_info_text_zero_is_off():
    t = scrollback_cache_info_text('/c', 0, 0, 0, 0)
    assert 'ttl_days = 0' in t and 'total_mb = 0' in t
    assert '0 days' not in t and '0 MiB' not in t


def test_info_text_bad_values():
    t = scrollback_cache_info_text('/c', 0, 0, 'x', None)
    assert 'off' in t


@pytest.fixture
def cache():
    c = sb.ScrollbackCache()
    saved = (c._queue, c._started, c._last_gc, c._bytes_since_gc, c._seq)
    c._seq = {}
    c._last_gc = None
    yield c
    c._queue, c._started, c._last_gc, c._bytes_since_gc, c._seq = saved


class _Spy(object):
    def __init__(self, real, log):
        self.real, self.log = real, log
    def __enter__(self):
        self.real.acquire(); self.log.append('in'); return self
    def __exit__(self, *a):
        self.log.append('out'); self.real.release()
    def locked(self):
        return self.real.locked()


def test_gc_check_reads_counter_under_lock(cache):
    cache._started = True
    cache._queue = queue.Queue()
    real, log = cache._io_lock, []

    class C(object):
        """counter whose truthiness records whether the lock is held"""
        def __bool__(self):
            log.append(('read', real.locked())); return True
    cache._bytes_since_gc = C()
    cache._io_lock = _Spy(real, log)
    try:
        assert cache._maybe_queue_gc(set(), now=9000) is True
    finally:
        cache._io_lock = real
    assert ('read', True) in log and cache._bytes_since_gc == 0


def test_gc_check_zero_counter_does_not_set_last_gc(cache):
    cache._started = True
    cache._queue = queue.Queue()
    cache._bytes_since_gc = 0
    assert cache._maybe_queue_gc(set(), now=9000) is False
    assert cache._last_gc is None


def test_bump_unlocked_takes_lock(cache):
    real, log = cache._io_lock, []
    cache._io_lock = _Spy(real, log)
    try:
        assert cache._bump('u') == 1
    finally:
        cache._io_lock = real
    assert log == ['in', 'out']


def test_bump_locked_no_deadlock(cache):
    done = []
    def run():
        with cache._io_lock:
            done.append(cache._bump('u'))
    t = threading.Thread(target=run); t.start(); t.join(2)
    assert done == [1] and not cache._io_lock.locked()
