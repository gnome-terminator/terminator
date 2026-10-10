"""m13: interval flush is fair (no starvation by a chatty terminal) and Enter
snapshots history before a fullscreen TUI hides the normal screen."""
import types
import uuid as uuidlib

import pytest

from terminatorlib import scrollback as sb
import terminatorlib.terminator as tmod


class FakeTerm(object):
    def __init__(self):
        self.uuid = uuidlib.uuid4()


@pytest.fixture
def cache(monkeypatch):
    c = sb.ScrollbackCache()
    monkeypatch.setattr(c, '_enabled', True, raising=False)
    monkeypatch.setattr(c, '_disabled_by_error', None, raising=False)
    c._dirty = set()
    c._visit = {}
    c._tick = 0
    c._snap_at = {}
    flushed = []
    monkeypatch.setattr(c, '_flush_uuid',
                        lambda t, u, sync=False: (flushed.append(u),
                                                  c._dirty.discard(u)))
    c.flushed = flushed
    return c


def _with_terms(monkeypatch, terms):
    monkeypatch.setattr(tmod, 'Terminator',
                        lambda: types.SimpleNamespace(terminals=terms))


def test_chatty_terminal_does_not_starve_others(cache, monkeypatch):
    terms = [FakeTerm() for _ in range(5)]
    _with_terms(monkeypatch, terms)
    chatty = [str(t.uuid) for t in terms[:2]]
    quiet = {str(t.uuid) for t in terms[2:]}
    cache._dirty.update(str(t.uuid) for t in terms)
    seen = set()
    for _ in range(3):  # ceil(5/2)
        cache._on_interval()
        seen.update(cache.flushed)
        cache._dirty.update(chatty)  # continuous output re-dirties at once
    assert quiet <= seen


def test_quiet_terminal_flushed_within_bound_under_constant_load(cache, monkeypatch):
    terms = [FakeTerm() for _ in range(4)]
    _with_terms(monkeypatch, terms)
    ids = [str(t.uuid) for t in terms]
    for tick in range(20):
        cache._dirty.update(ids[:3])           # three chatty terminals
        if tick == 5:
            cache._dirty.add(ids[3])
        cache.flushed.clear()
        cache._on_interval()
        if ids[3] in cache.flushed:
            assert tick - 5 <= 1
            return
    pytest.fail('quiet terminal starved')


def test_snapshot_on_enter_only_when_dirty_and_rate_limited(cache, monkeypatch):
    t = FakeTerm(); u = str(t.uuid)
    monkeypatch.setattr(sb, 'in_alt_screen', lambda term: False)
    assert cache.snapshot_before_command(t, now=10.0) is False   # clean
    cache._dirty.add(u)
    assert cache.snapshot_before_command(t, now=10.0) is True
    assert cache.flushed == [u]
    cache._dirty.add(u)
    assert cache.snapshot_before_command(t, now=10.5) is False   # <1s
    assert cache.snapshot_before_command(t, now=11.2) is True


def test_snapshot_skipped_in_alt_screen(cache, monkeypatch):
    t = FakeTerm(); cache._dirty.add(str(t.uuid))
    monkeypatch.setattr(sb, 'in_alt_screen', lambda term: True)
    assert cache.snapshot_before_command(t, now=1.0) is False
    assert cache.flushed == []


def test_randomised_wait_bound(cache, monkeypatch):
    """Old set+rotating-index picked the same terminals for 50+ ticks in a
    simulation; LRU must keep every dirty terminal's wait <= ceil(N/2)."""
    import random
    rnd = random.Random(1234)
    for _trial in range(200):
        terms = [FakeTerm() for _ in range(rnd.randint(3, 8))]
        _with_terms(monkeypatch, terms)
        ids = [str(t.uuid) for t in terms]
        chatty = set(rnd.sample(ids, rnd.randint(1, len(ids) - 1)))
        cache._dirty = set(ids); cache._visit = {}; cache._tick = 0
        dirty_since = {u: 0 for u in ids}
        bound = (len(ids) + 1) // 2
        for tick in range(1, 40):
            cache.flushed.clear()
            cache._on_interval()
            for u in cache.flushed:
                dirty_since.pop(u, None)
            for u in list(dirty_since):
                assert tick - dirty_since[u] < bound + 1, (tick, u)
            for u in chatty | ({rnd.choice(ids)} if rnd.random() < .3 else set()):
                if u not in cache._dirty:
                    cache._dirty.add(u)
                    dirty_since.setdefault(u, tick)


def test_clear_all_resets_lru_and_snapshot_state(tmp_path, monkeypatch):
    from terminatorlib import scrollback as sb
    monkeypatch.setattr(sb, 'get_cache_dir', lambda: str(tmp_path))
    c = sb.ScrollbackCache()
    c._visit = {'a': 3}
    c._snap_at = {'a': 1.0}
    c.clear_all()
    assert c._visit == {} and c._snap_at == {}
    assert not hasattr(sb.ScrollbackCache, '_rotate_index')
