"""Follow-up slot tests: dirty hooks, scrollback suspend, restart handler."""

from __future__ import print_function

import inspect
import os

import pytest


def _reset_borg(name):
    from terminatorlib.borg import Borg
    Borg._Borg__shared_state.pop(name, None)


@pytest.fixture
def state_home(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    _reset_borg('SessionManager')
    _reset_borg('ScrollbackCache')
    yield tmp_path
    _reset_borg('SessionManager')
    _reset_borg('ScrollbackCache')


def test_scrollback_start_respects_suspended_writes(state_home, monkeypatch):
    from terminatorlib.session import SessionManager
    from terminatorlib.scrollback import ScrollbackCache

    sm = SessionManager()
    sm.acquire_lock()

    class Opt(object):
        pass

    o = Opt()
    o.layout_from_default = True
    o.layout = 'default'
    o.command = None
    o.execute = None
    o.working_directory = None
    o.configjson = None
    sm.set_owner_from_options(o)
    assert sm.is_owner() and sm.is_writer()

    cache = ScrollbackCache()
    # Avoid depending on full Config defaults: force want=True via _cfg
    monkeypatch.setattr(cache, '_cfg', lambda key, default=None: {
        'scrollback_cache': True,
        'scrollback_cache_lines': 2000,
        'scrollback_cache_max_kb': 512,
        'scrollback_cache_interval_s': 20,
        'scrollback_cache_total_mb': 20,
        'scrollback_cache_ttl_days': 7,
    }.get(key, default))

    cache.start()
    assert cache._enabled is True
    cache.stop(join_timeout=0.2)

    sm.suspend_writes('prefs clear')
    assert sm.writes_suspended()
    cache.start()
    assert cache._enabled is False


def test_child_exited_handlers_pass_respawn_not_debugserver():
    """exit_action=restart must not bind spawn_child with user-data True."""
    src = inspect.getsource(
        __import__('terminatorlib.terminal', fromlist=['Terminal']).Terminal.reconfigure)
    assert '_on_child_exited_restart' in src
    assert '_on_child_exited_hold' in src
    # The old buggy form must be gone
    assert 'self.spawn_child, True' not in src
    assert 'self.held_open, True' not in src

    restart = inspect.getsource(
        __import__('terminatorlib.terminal', fromlist=['Terminal']).Terminal._on_child_exited_restart)
    assert 'spawn_child(respawn=True)' in restart
    assert 'debugserver' not in restart


def test_describe_layout_skips_default_profile():
    """Pre-existing typo used `layout != \"default\"` (always True)."""
    import terminatorlib.terminal as term_mod
    src = inspect.getsource(term_mod.Terminal.describe_layout)
    assert 'if profile != "default"' in src
    assert 'if layout != "default"' not in src


def test_request_close_uses_logical_parent():
    import terminatorlib.close_confirm as cc
    src = inspect.getsource(cc.request_close_terminal)
    assert 'logical_parent' in src


def test_restore_into_encodes_bytes_for_vte_feed(state_home, monkeypatch):
    """VTE 0.80 feed() rejects str; restore_into must encode UTF-8."""
    from terminatorlib.session import SessionManager
    from terminatorlib.scrollback import ScrollbackCache
    import terminatorlib.scrollback as sbmod

    sm = SessionManager()
    sm.acquire_lock()

    class Opt(object):
        pass
    o = Opt()
    o.layout_from_default = True
    o.layout = 'default'
    o.command = o.execute = o.working_directory = o.configjson = None
    sm.set_owner_from_options(o)
    sm.restored_this_run = True

    cache = ScrollbackCache()
    monkeypatch.setattr(cache, '_cfg', lambda key, default=None: {
        'scrollback_cache': True,
        'scrollback_cache_lines': 2000,
        'scrollback_cache_max_kb': 512,
        'scrollback_cache_interval_s': 20,
        'scrollback_cache_total_mb': 20,
        'scrollback_cache_ttl_days': 7,
    }.get(key, default))
    cache.start()

    uid = '12345678-1234-5678-1234-567812345678'
    path = cache.path_for(uid)
    assert path
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('hello scrollback\nline2\n')

    fed = []

    class FakeVte(object):
        def feed(self, data):
            fed.append(data)
            if not isinstance(data, (bytes, bytearray)):
                raise TypeError('Must be number, not str')

    class FakeTerm(object):
        uuid = uid
        vte = FakeVte()

    assert cache.restore_into(FakeTerm()) is True
    assert fed and isinstance(fed[0], (bytes, bytearray))
    assert b'hello scrollback' in fed[0]
    cache.stop(join_timeout=0.2)
