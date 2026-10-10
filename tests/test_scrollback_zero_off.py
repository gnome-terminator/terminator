"""m17: 0 means disabled for scrollback_cache_total_mb / ttl_days."""
import os
import time
import uuid as uuidlib

import pytest

from terminatorlib import scrollback as sb


@pytest.fixture
def cache(tmp_path, monkeypatch):
    c = sb.ScrollbackCache()
    saved = (c._dir,)
    c._dir = str(tmp_path)
    cfg = {}
    monkeypatch.setattr(c, '_cfg', lambda k, d=None: cfg.get(k, d))
    monkeypatch.setattr(sb, '_sm_session_uuids', lambda: None)
    c.cfg = cfg
    yield c
    (c._dir,) = saved


@pytest.mark.parametrize('val,exp', [(0, 0), ('0', 0), (-3, 0), (None, 20),
                                     ('', 20), ('x', 20), (5, 5)])
def test_total_mb(cache, val, exp):
    cache.cfg['scrollback_cache_total_mb'] = val
    assert cache._total_mb() == exp


@pytest.mark.parametrize('val,exp', [(0, 0), (None, 7), (3, 3)])
def test_ttl_days(cache, val, exp):
    cache.cfg['scrollback_cache_ttl_days'] = val
    assert cache._ttl_days() == exp


def _mk(c, size, age_days):
    u = str(uuidlib.uuid4())
    p = c.path_for(u)
    with open(p, 'wb') as fh:
        fh.write(b'x' * size)
    t = time.time() - age_days * 86400
    os.utime(p, (t, t))
    return p


def test_zero_disables_startup_ttl_and_cap(cache):
    cache.cfg.update(scrollback_cache_total_mb=0, scrollback_cache_ttl_days=0)
    old = _mk(cache, 2 * 1024 * 1024, 365)
    big = _mk(cache, 30 * 1024 * 1024, 0)
    cache.cleanup_startup()
    assert os.path.exists(old) and os.path.exists(big)


def test_zero_disables_runtime_cap(cache):
    cache.cfg['scrollback_cache_total_mb'] = 0
    p = _mk(cache, 2 * 1024 * 1024, 0)
    assert cache.enforce_total_cap() == []
    assert os.path.exists(p)


def test_nonzero_still_enforced(cache):
    cache.cfg.update(scrollback_cache_total_mb=1, scrollback_cache_ttl_days=1)
    old = _mk(cache, 10, 5)
    cache.cleanup_startup()
    assert not os.path.exists(old)


def test_async_flush_bump_under_io_lock(cache, monkeypatch):
    import queue
    held = []
    real = cache._bump
    monkeypatch.setattr(cache, '_bump',
                        lambda u: (held.append(cache._io_lock.locked()), real(u))[1])
    saved_q = cache._queue
    cache._queue = queue.Queue()

    class T(object):
        vte = object()
    monkeypatch.setattr(sb, '_vte_caps', lambda: {'range_format': 1, 'range': 1})
    monkeypatch.setattr(sb, 'in_alt_screen', lambda t: False)
    monkeypatch.setattr(sb, 'read_last_n_lines_raw', lambda *a, **k: ('hi', False))
    monkeypatch.setattr(cache, '_config', {'scrollback_infinite': False}, raising=False)
    u = str(uuidlib.uuid4())
    cache._last_hash.pop(u, None)
    try:
        cache._flush_uuid(T(), u, sync=False)
        assert held == [True]
        assert cache._queue.get_nowait()[0] == 'write'
    finally:
        cache._queue = saved_q
