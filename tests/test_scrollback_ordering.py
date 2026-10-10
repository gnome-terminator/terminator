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
