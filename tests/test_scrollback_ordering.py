"""m12: stale queued writes must not overwrite newer sync writes; restore keeps tail."""
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
    monkeypatch.setattr(sb.GLib, 'idle_add', lambda fn, *a: fn(*a))
    return c


def _run_worker(c, items):
    c._queue = queue.Queue()
    for it in items:
        c._queue.put(it)
    c._queue.put(('stop',))
    c._worker_loop()


def test_superseded_async_write_is_dropped(cache):
    u = str(uuidlib.uuid4())
    old = cache._bump(u)            # async write queued
    new = cache._bump(u)            # later sync write wins
    path = cache.path_for(u)
    with open(path, 'wb') as fh:
        fh.write(b'NEW')
    cache._last_hash[u] = 'h-new'
    _run_worker(cache, [('write', u, b'OLD', 'h-old', old)])
    assert open(path, 'rb').read() == b'NEW'
    assert cache._last_hash[u] == 'h-new'
    assert new == 2


def test_current_async_write_lands(cache):
    u = str(uuidlib.uuid4())
    s = cache._bump(u)
    _run_worker(cache, [('write', u, b'DATA', 'h', s)])
    assert open(cache.path_for(u), 'rb').read() == b'DATA'
    assert cache._last_hash[u] == 'h'


def test_delete_supersedes_queued_write(cache):
    u = str(uuidlib.uuid4())
    s = cache._bump(u)
    cache._queue = None
    cache.delete_uuid(u)            # no worker -> sync delete, bumps seq
    _run_worker(cache, [('write', u, b'LATE', 'h', s)])
    assert not os.path.exists(cache.path_for(u))


class _Vte(object):
    def __init__(self):
        self.fed = b''

    def feed(self, data):
        self.fed += data


class _Term(object):
    def __init__(self, u):
        self.uuid = u
        self.vte = _Vte()


def test_restore_keeps_newest_tail(cache, monkeypatch):
    u = str(uuidlib.uuid4())
    monkeypatch.setattr(sb, '_sm_restored_this_run', lambda: True)
    monkeypatch.setattr(sb, '_terminal_uuid_str', lambda t: t.uuid)
    monkeypatch.setattr(cache, '_max_kb', lambda: 1)
    cache._enabled = True
    lines = ['line%05d' % i for i in range(1000)]
    with open(cache.path_for(u), 'w') as fh:
        fh.write('\n'.join(lines) + '\n')
    t = _Term(u)
    assert cache.restore_into(t)
    out = t.vte.fed.decode('utf-8')
    assert 'line00999' in out
    assert 'line00000' not in out
    first = out.replace('\r', '').split('\n')[0]
    assert first in lines           # starts on a whole line


def _silence_flush_guards(monkeypatch):
    monkeypatch.setattr(sb, '_sm_safe_keep', lambda _u: False)
    monkeypatch.setattr(sb, '_sm_display_lost', lambda: False)
    monkeypatch.setattr(sb, 'cache_exclusion', lambda _t, _c: False)
    monkeypatch.setattr(sb, '_terminal_window_excluded', lambda _t: False)
    monkeypatch.setattr(sb, 'in_alt_screen', lambda _t: False)


class _RaisingVte(object):
    def get_cursor_position(self):
        raise RuntimeError('no cursor')


class _FlushTerm(object):
    def __init__(self, vte):
        self.vte = vte


def test_failed_export_keeps_the_cache(cache, monkeypatch):
    u = str(uuidlib.uuid4())
    path = cache.path_for(u)
    with open(path, 'wb') as fh:
        fh.write(b'KEEP')
    cache._last_hash[u] = 'keep-hash'
    cache._dirty.add(u)
    cache._config = {'scrollback_infinite': False}
    _silence_flush_guards(monkeypatch)
    writes = []
    real = sb.sbt.atomic_write_txt

    def spy(p, data, mode=0o600):
        writes.append(data)
        real(p, data, mode=mode)

    monkeypatch.setattr(sb.sbt, 'atomic_write_txt', spy)
    cache._flush_uuid(_FlushTerm(_RaisingVte()), u, sync=True)
    assert open(path, 'rb').read() == b'KEEP'
    assert cache._last_hash[u] == 'keep-hash'
    assert u in cache._dirty
    assert writes == []

    monkeypatch.setattr(sb, 'read_last_n_lines_raw',
                        lambda *_a, **_k: ('hello', False))
    cache._flush_uuid(_FlushTerm(_RaisingVte()), u, sync=True)
    assert b'hello' in open(path, 'rb').read()
    assert writes


def test_empty_export_is_a_successful_write(cache, monkeypatch):
    u = str(uuidlib.uuid4())
    path = cache.path_for(u)
    with open(path, 'wb') as fh:
        fh.write(b'OLD')
    cache._last_hash[u] = 'old-hash'
    cache._dirty.add(u)
    cache._config = {'scrollback_infinite': False}
    _silence_flush_guards(monkeypatch)
    writes = []
    real = sb.sbt.atomic_write_txt
    real_read = sb.read_last_n_lines_raw

    def spy(p, data, mode=0o600):
        writes.append(bytes(data))
        real(p, data, mode=mode)

    monkeypatch.setattr(sb.sbt, 'atomic_write_txt', spy)
    monkeypatch.setattr(sb, 'read_last_n_lines_raw',
                        lambda *_a, **_k: ('', False))
    cache._flush_uuid(_FlushTerm(object()), u, sync=True)
    assert open(path, 'rb').read() == b''
    assert u not in cache._dirty
    assert writes == [b'']
    cache._dirty.add(u)
    cache._flush_uuid(_FlushTerm(object()), u, sync=True)
    assert writes == [b'']

    writes[:] = []
    monkeypatch.setattr(cache, '_lines', lambda: 0)
    monkeypatch.setattr(sb, 'read_last_n_lines_raw', real_read)
    cache._dirty.add(u)
    cache._last_hash.pop(u, None)
    cache._flush_uuid(_FlushTerm(object()), u, sync=True)
    assert writes == [b'']
    assert u not in cache._dirty


def test_sync_oserror_keeps_dirty_and_retries(cache, monkeypatch):
    u = str(uuidlib.uuid4())
    path = cache.path_for(u)
    with open(path, 'wb') as fh:
        fh.write(b'KEEP')
    cache._last_hash[u] = 'keep-hash'
    cache._dirty.add(u)
    cache._config = {'scrollback_infinite': False}
    cache._fail_count = 0
    _silence_flush_guards(monkeypatch)
    monkeypatch.setattr(sb, 'read_last_n_lines_raw',
                        lambda *_a, **_k: ('hello', False))
    real = sb.sbt.atomic_write_txt

    def boom(p, data, mode=0o600):
        raise OSError('disk full')

    monkeypatch.setattr(sb.sbt, 'atomic_write_txt', boom)
    cache._flush_uuid(_FlushTerm(object()), u, sync=True)
    assert u in cache._dirty
    assert cache._last_hash[u] == 'keep-hash'
    assert open(path, 'rb').read() == b'KEEP'
    assert cache._disabled_by_error is not True

    monkeypatch.setattr(sb.sbt, 'atomic_write_txt', real)
    cache._flush_uuid(_FlushTerm(object()), u, sync=True)
    assert u not in cache._dirty
    assert b'hello' in open(path, 'rb').read()


def test_worker_oserror_restores_dirty(cache, monkeypatch):
    u = str(uuidlib.uuid4())
    seq = cache._bump(u)
    cache._last_hash[u] = 'old'
    cache._dirty.discard(u)
    cache._fail_count = 0

    def boom(p, data, mode=0o600):
        raise OSError('disk full')

    monkeypatch.setattr(sb.sbt, 'atomic_write_txt', boom)
    _run_worker(cache, [('write', u, b'DATA', 'h-new', seq)])
    assert u in cache._dirty
    assert cache._last_hash[u] == 'old'
    assert cache._fail_count == 1


def test_worker_oserror_does_not_restore_after_bump(cache, monkeypatch):
    u = str(uuidlib.uuid4())
    seq = cache._bump(u)
    cache._dirty.discard(u)
    pending = []
    monkeypatch.setattr(sb.GLib, 'idle_add', lambda fn, *a: pending.append((fn, a)) or 1)

    def boom(p, data, mode=0o600):
        raise OSError('disk full')

    monkeypatch.setattr(sb.sbt, 'atomic_write_txt', boom)
    _run_worker(cache, [('write', u, b'DATA', 'h-new', seq)])
    cache._bump(u)
    for fn, args in pending:
        fn(*args)
    assert u not in cache._dirty


def test_worker_render_error_restores_without_counting_failure(cache, monkeypatch):
    u = str(uuidlib.uuid4())
    seq = cache._bump(u)
    cache._dirty.discard(u)
    cache._fail_count = 0

    def boom(*_a, **_k):
        raise RuntimeError('bad payload')

    monkeypatch.setattr(sb, 'render_cache_text', boom)
    _run_worker(cache, [('write', u, ('src', True, 10, 1), 'h', seq)])
    assert u in cache._dirty
    assert (cache._fail_count or 0) == 0


def test_worker_seq_check_and_write_are_atomic_vs_sync(cache, monkeypatch):
    """Review fix: a sync write landing between the worker's seq check and its
    file write must not be overwritten by the stale async payload."""
    import threading
    u = str(uuidlib.uuid4())
    path = cache.path_for(u)
    old = cache._bump(u)
    real = sb.sbt.atomic_write_txt
    entered = threading.Event()
    release = threading.Event()

    def slow_write(p, data, mode=0o600):
        if data == b'OLD':
            entered.set()
            release.wait(2)
        real(p, data, mode=mode)
    monkeypatch.setattr(sb.sbt, 'atomic_write_txt', slow_write)
    t = threading.Thread(target=_run_worker,
                         args=(cache, [('write', u, b'OLD', 'h-old', old)]))
    t.start()
    assert entered.wait(2)
    done = threading.Event()

    def sync_writer():  # mimics _flush_uuid(sync=True)
        with cache._io_lock:
            cache._bump(u)
            real(path, b'NEW', mode=0o600)
        done.set()
    s = threading.Thread(target=sync_writer)
    s.start()
    assert not done.wait(0.2)   # blocked behind the in-flight worker write
    release.set()
    t.join(2); s.join(2)
    assert open(path, 'rb').read() == b'NEW'
