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


def test_toggle_zoom_has_default_binding():
    from terminatorlib.config import DEFAULTS
    kb = DEFAULTS['keybindings']
    assert kb['toggle_zoom'] == '<Shift><Control>x'
    assert kb['restore_maximised'] == '<Shift>Escape'
    others = [v for k, v in kb.items() if k != 'toggle_zoom' and v]
    assert kb['toggle_zoom'] not in others


def test_wave_titlebar_defaults_not_legacy_red():
    from terminatorlib.config import DEFAULTS
    prof = DEFAULTS['profiles']['default']
    assert prof['title_transmit_bg_color'].lower() != '#c80003'
    assert prof['title_inactive_bg_color'].lower() != '#c0bebf'
    # Group/broadcast receive colour stays distinct from both bars
    assert prof['title_receive_bg_color'] not in (
        prof['title_transmit_bg_color'], prof['title_inactive_bg_color'])


def test_auto_font_min_rows_default_is_low():
    from terminatorlib.config import DEFAULTS
    assert int(DEFAULTS['global_config']['auto_font_scale_min_rows']) <= 12


def test_add_source_icon_path_idempotent():
    import terminatorlib.util as util
    util._SOURCE_ICON_PATH_ADDED = False

    class Theme(object):
        def __init__(self):
            self.paths = []

        def get_search_path(self):
            return list(self.paths)

        def append_search_path(self, p):
            self.paths.append(p)

    th = Theme()
    assert util.add_source_icon_path(th) is True
    assert util.add_source_icon_path(th) is False
    assert len(th.paths) == 1 and th.paths[0].endswith(os.path.join('data', 'icons'))
    util._SOURCE_ICON_PATH_ADDED = False


def test_edit_done_without_change_does_not_mark_dirty(monkeypatch):
    from terminatorlib.terminal import Terminal
    calls = []

    class TB(object):
        val = None

        def get_custom_string(self):
            return self.val

    class V(object):
        def grab_focus(self):
            pass

    class T(object):
        _session_custom_title = None
        titlebar = TB()
        vte = V()

        def _session_mark_dirty(self, reason):
            calls.append(reason)

    t = T()
    Terminal.on_edit_done(t, None)
    assert calls == []
    t.titlebar.val = 'build'
    Terminal.on_edit_done(t, None)
    assert calls == ['title']
    Terminal.on_edit_done(t, None)
    assert calls == ['title']
    t.titlebar.val = None
    Terminal.on_edit_done(t, None)
    assert calls == ['title', 'title']


def test_maximise_default_shortcut_and_handlers():
    from terminatorlib.config import DEFAULTS
    from terminatorlib.terminal import Terminal
    kb = DEFAULTS['keybindings']
    assert kb['maximise'] == '<Shift><Control>Return'
    vals = [v for k, v in kb.items() if v and k != 'maximise']
    assert '<Shift><Control>Return' not in vals
    for name in ('maximise', 'zoom', 'unzoom', 'toggle_zoom', 'restore_maximised'):
        assert callable(getattr(Terminal, 'key_' + name))
