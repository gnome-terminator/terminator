"""m31: after a crash marker, fall back instead of starting empty."""
import json
import os

import pytest

from terminatorlib.session import SessionManager, FALLBACK_MARKER_FLAG


def _reset():
    from terminatorlib.borg import Borg
    Borg._Borg__shared_state.pop('SessionManager', None)


@pytest.fixture
def sm(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    _reset()
    s = SessionManager()
    assert s.acquire_lock()
    s._owns_session = True
    yield s
    try:
        os.close(s._lock_fd)
    except Exception:
        pass
    _reset()


def _write(path, uid):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump({'version': 1, 'layout': {
            'terminal1': {'type': 'Terminal', 'uuid': uid}}}, fh)


def _uid(data):
    return data['layout']['terminal1']['uuid']


def _marker(sm):
    with open(sm.restoring_path(), encoding='utf-8') as fh:
        return fh.read().splitlines()


def _crash_after_normal_restore(sm):
    assert sm.load() is not None
    sm.begin_restore()          # killed before the 10s clear


def test_crash_falls_back_to_prev_full_restore(sm):
    path = sm.session_path()
    _write(path, 'cur')
    _write(path + '.prev', 'p1')
    _crash_after_normal_restore(sm)
    assert sm.check_crash_marker() is True
    assert os.path.isfile(path + '.crashed')
    data = sm.load_crash_fallback()
    assert _uid(data) == 'p1'
    assert sm._loaded_from == path + '.prev'
    assert sm.safe_restore is False


def test_crash_falls_back_to_prev2(sm):
    path = sm.session_path()
    _write(path, 'cur')
    _write(path + '.prev2', 'p2')
    _crash_after_normal_restore(sm)
    assert sm.check_crash_marker()
    assert _uid(sm.load_crash_fallback()) == 'p2'
    assert sm.safe_restore is False


def test_no_candidate_restores_quarantined_in_safe_mode(sm):
    path = sm.session_path()
    _write(path, 'cur')
    _crash_after_normal_restore(sm)
    assert sm.check_crash_marker()
    data = sm.load_crash_fallback()
    assert _uid(data) == 'cur'
    assert sm._loaded_from == path + '.crashed'
    assert sm.safe_restore is True


def test_prev_source_crash_skips_quarantined_prev(sm):
    path = sm.session_path()
    _write(path + '.prev', 'p1')
    _write(path + '.prev2', 'p2')
    assert sm.load() is not None and sm._loaded_from == path + '.prev'
    sm.begin_restore()
    assert sm.check_crash_marker()
    assert os.path.isfile(path + '.prev.crashed')
    assert _uid(sm.load_crash_fallback()) == 'p2'


def test_fallback_marker_is_flagged_and_second_crash_goes_empty(sm):
    path = sm.session_path()
    _write(path, 'cur')
    _crash_after_normal_restore(sm)
    assert sm.check_crash_marker()
    assert sm.load_crash_fallback() is not None   # safe mode from .crashed
    sm.begin_restore()
    assert FALLBACK_MARKER_FLAG in _marker(sm)[2:]
    # killed again during the fallback restore
    _reset()
    sm2 = SessionManager()
    assert sm2.check_crash_marker() is True
    assert sm2.crash_fallback_ok is False
    assert sm2.load_crash_fallback() is None
    # original quarantined file is not clobbered
    assert os.path.isfile(path + '.crashed')


def test_second_crash_does_not_clobber_first_quarantine(sm):
    path = sm.session_path()
    _write(path, 'cur')
    _write(path + '.prev', 'p1')
    _crash_after_normal_restore(sm)
    assert sm.check_crash_marker()
    assert sm.load_crash_fallback() is not None
    sm.begin_restore()
    _write(path, 'during')      # a save during the fallback restore
    assert sm.check_crash_marker()
    with open(path + '.crashed', encoding='utf-8') as fh:
        assert _uid(json.load(fh)) == 'cur'
    with open(path + '.crashed.1', encoding='utf-8') as fh:
        assert _uid(json.load(fh)) == 'during'
    assert os.path.isfile(path + '.prev.crashed')
    assert sm.load_crash_fallback() is None


def test_rotation_keeps_fallback_flag(sm):
    path = sm.session_path()
    _write(path, 'cur')
    _write(path + '.prev', 'p1')
    _crash_after_normal_restore(sm)
    sm.check_crash_marker()
    sm.load_crash_fallback()
    sm.begin_restore()
    sm._describe_current = lambda: {
        'terminal1': {'type': 'Terminal', 'uuid': 'n1'}}
    assert sm.save_now() is True      # writes fresh session.json
    sm._describe_current = lambda: {
        'terminal1': {'type': 'Terminal', 'uuid': 'n2'}}
    assert sm.save_now() is True
    # m27 retarget (as done by a rotation) must keep the flag line
    sm._retarget_marker(path, {'.prev': '.prev2', '.prev2': None})
    assert _marker(sm)[1] == os.path.basename(path) + '.prev2'
    lines = _marker(sm)
    assert FALLBACK_MARKER_FLAG in lines[2:]


def test_normal_load_clears_fallback_state(sm):
    path = sm.session_path()
    _write(path, 'cur')
    _crash_after_normal_restore(sm)
    sm.check_crash_marker()
    sm.load_crash_fallback()
    assert sm.safe_restore
    _write(path, 'fresh')
    sm.clear_restoring_now()
    assert sm.load() is not None
    assert sm.safe_restore is False
    sm.begin_restore()
    assert FALLBACK_MARKER_FLAG not in _marker(sm)


def test_no_marker_no_fallback(sm):
    assert sm.check_crash_marker() is False
    assert sm.load_crash_fallback() is None


def test_safe_mode_blocks_scrollback_replay(sm, monkeypatch):
    from terminatorlib import scrollback
    sm.restored_this_run = True
    sm.safe_restore = True
    assert scrollback._sm_safe_restore() is True
    sm.safe_restore = False
    assert scrollback._sm_safe_restore() is False


def test_clear_session_files_removes_numbered_crashed(sm):
    path = sm.session_path()
    _write(path + '.crashed.1', 'x')
    _write(path + '.prev.crashed', 'y')
    sm.clear_session_files()
    assert not os.path.exists(path + '.crashed.1')
    assert not os.path.exists(path + '.prev.crashed')
