"""m26 P1-1: a failed first write of a run must not lose the session."""
import errno
import json
import os

import pytest

from terminatorlib.session import SessionManager


def _reset_session_borg():
    from terminatorlib.borg import Borg
    Borg._Borg__shared_state.pop('SessionManager', None)


@pytest.fixture
def sm(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    _reset_session_borg()
    s = SessionManager()
    assert s.acquire_lock()
    s._owns_session = True
    yield s
    try:
        os.close(s._lock_fd)
    except Exception:
        pass
    _reset_session_borg()


def _write(path, layout):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump({'version': 1, 'layout': layout}, fh)


def _layout(uid):
    return {'terminal1': {'type': 'Terminal', 'uuid': uid}}


def test_failed_first_write_keeps_session_json(sm, monkeypatch):
    path = sm.session_path()
    _write(path, _layout('old'))
    sm._describe_current = lambda: _layout('new')

    real_dump = json.dump

    def full_disk(*a, **kw):
        raise OSError(errno.ENOSPC, 'No space left on device')
    monkeypatch.setattr(json, 'dump', full_disk)
    assert sm.save_now() is False
    monkeypatch.setattr(json, 'dump', real_dump)

    # session.json untouched, not rotated away, no tmp left behind
    assert os.path.isfile(path)
    with open(path, encoding='utf-8') as fh:
        assert 'old' in json.dumps(json.load(fh))
    assert not os.path.exists(path + '.prev')
    assert not [f for f in os.listdir(os.path.dirname(path))
                if f.endswith('.tmp')]
    assert sm._rotated_this_run is False

    # a later successful write still rotates the old run into .prev
    assert sm.save_now() is True
    with open(path + '.prev', encoding='utf-8') as fh:
        assert json.load(fh)['layout']['terminal1']['uuid'] == 'old'
    with open(path, encoding='utf-8') as fh:
        assert json.load(fh)['layout']['terminal1']['uuid'] == 'new'
    assert sm._rotated_this_run is True


def test_rotation_happens_once_per_run(sm):
    path = sm.session_path()
    _write(path + '.prev', _layout('p'))
    _write(path, _layout('old'))
    sm._describe_current = lambda: _layout('a')
    assert sm.save_now()
    sm._describe_current = lambda: _layout('b')
    assert sm.save_now()
    with open(path + '.prev', encoding='utf-8') as fh:
        assert json.load(fh)['layout']['terminal1']['uuid'] == 'old'
    with open(path + '.prev2', encoding='utf-8') as fh:
        assert json.load(fh)['layout']['terminal1']['uuid'] == 'p'


def test_load_falls_back_to_prev_when_missing(sm):
    path = sm.session_path()
    _write(path + '.prev', _layout('prev'))
    data = sm.load()
    assert data['layout']['terminal1']['uuid'] == 'prev'
    assert sm._loaded_from == path + '.prev'


def test_load_falls_back_to_prev2(sm):
    path = sm.session_path()
    _write(path + '.prev2', _layout('p2'))
    assert sm.load()['layout']['terminal1']['uuid'] == 'p2'


def test_load_corrupt_quarantines_then_falls_back(sm):
    path = sm.session_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as fh:
        fh.write('{nope')
    _write(path + '.prev', _layout('prev'))
    assert sm.load()['layout']['terminal1']['uuid'] == 'prev'
    assert os.path.isfile(path + '.bad')
    assert not os.path.exists(path)


def test_load_prefers_session_json(sm):
    path = sm.session_path()
    _write(path, _layout('cur'))
    _write(path + '.prev', _layout('prev'))
    assert sm.load()['layout']['terminal1']['uuid'] == 'cur'
    assert sm._loaded_from == path


def test_load_nothing_valid(sm):
    assert sm.load() is None


def test_restore_failed_copies_the_file_actually_loaded(sm):
    path = sm.session_path()
    _write(path + '.prev', _layout('prev'))
    sm.load()
    sm.restored_this_run = True
    sm.restore_failed(ValueError('x'))
    with open(path + '.bad', encoding='utf-8') as fh:
        assert json.load(fh)['layout']['terminal1']['uuid'] == 'prev'
