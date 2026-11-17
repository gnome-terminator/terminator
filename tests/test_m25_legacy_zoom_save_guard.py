"""m25: legacy zoom must not write a one-pane session; layout replay."""
import json
import os

import pytest

from terminatorlib.session import SessionManager, count_terminals_in_layout


def _reset():
    from terminatorlib.borg import Borg
    Borg._Borg__shared_state.pop('SessionManager', None)


def _full():
    return {
        'child0': {'type': 'Window', 'parent': ''},
        'child1': {'type': 'HPaned', 'parent': 'child0', 'order': '0'},
        'terminal2': {'type': 'Terminal', 'parent': 'child1', 'order': '0', 'uuid': 'u1'},
        'terminal3': {'type': 'Terminal', 'parent': 'child1', 'order': '1', 'uuid': 'u2'},
    }


def _zoomed():
    return {
        'child0': {'type': 'Window', 'parent': ''},
        'terminal1': {'type': 'Terminal', 'parent': 'child0', 'uuid': 'u1'},
    }


class FakeTerm:
    doing_layout = False


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    _reset()
    s = SessionManager()
    assert s.acquire_lock()
    s._owns_session = True
    state = {'zoom': False, 'timers': []}
    ft = FakeTerm()
    import terminatorlib.terminator as tmod
    monkeypatch.setattr(tmod, 'Terminator', lambda: ft)
    monkeypatch.setattr(SessionManager, '_any_legacy_zoom',
                        lambda self: state['zoom'])
    monkeypatch.setattr(SessionManager, '_describe_current',
                        lambda self: _zoomed() if state['zoom'] else _full())
    from gi.repository import GLib

    def fake_add(delay, fn, *a):
        state['timers'].append(fn)
        return len(state['timers'])
    monkeypatch.setattr(GLib, 'timeout_add', fake_add)
    yield s, state, ft
    try:
        os.close(s._lock_fd)
    except Exception:
        pass
    _reset()


def _saved_terms(s):
    p = s.session_path()
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return count_terminals_in_layout(json.load(f)['layout'])


def test_pending_timer_fired_during_zoom_does_not_write_one_pane(env):
    s, state, _ = env
    s.mark_dirty('split')
    assert len(state['timers']) == 1
    state['zoom'] = True
    state['timers'].pop()()          # timer fires while zoomed
    assert _saved_terms(s) is None   # nothing written
    assert s._pending_after_zoom
    state['zoom'] = False
    s.mark_dirty('unzoom')           # window._legacy_unzoom does this
    state['timers'].pop()()
    assert _saved_terms(s) == 2
    assert not s._pending_after_zoom


def test_mark_dirty_during_zoom_sets_pending(env):
    s, state, _ = env
    state['zoom'] = True
    s.mark_dirty('cwd')
    assert state['timers'] == []
    assert s._pending_after_zoom


def test_doing_layout_sets_pending_and_replays(env):
    s, state, ft = env
    ft.doing_layout = True
    s.mark_dirty('during-layout')
    assert state['timers'] == [] and s._pending_after_layout
    ft.doing_layout = False
    s.mark_dirty('layout_done')      # Terminator.layout_done does this
    assert len(state['timers']) == 1 and not s._pending_after_layout
    state['timers'].pop()()
    assert _saved_terms(s) == 2
