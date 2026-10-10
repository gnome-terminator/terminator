"""m27: a save during restore rotates files; the crash marker must follow."""
import json
import os

import pytest

from terminatorlib.session import SessionManager


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


def _uid(path):
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)['layout']['terminal1']['uuid']


def _marker_src(sm):
    with open(sm.restoring_path(), encoding='utf-8') as fh:
        lines = fh.read().splitlines()
    return lines[1] if len(lines) > 1 else None


def _save_during_restore(sm, uid='new'):
    sm._describe_current = lambda: {
        'terminal1': {'type': 'Terminal', 'uuid': uid}}
    assert sm.save_now() is True


def test_restore_prev_then_save_then_crash_quarantines_real_source(sm):
    path = sm.session_path()
    _write(path + '.prev', 'src')
    assert sm.load() is not None and sm._loaded_from == path + '.prev'
    sm.begin_restore()
    # load() only falls back to .prev when session.json is missing, so via
    # load() alone no rotation happens; simulate a session.json appearing
    # (e.g. restore_prev_session / external copy) before the first save.
    _write(path, 'cur')
    _save_during_restore(sm)
    assert _uid(path + '.prev2') == 'src'
    assert _marker_src(sm) == 'session.json.prev2'
    assert sm.check_crash_marker() is True
    assert not os.path.exists(path + '.prev2')
    assert _uid(path + '.prev2.crashed') == 'src'
    assert sm.load() is None  # no crash loop on the bad session


def test_restore_session_json_then_save_then_crash(sm):
    path = sm.session_path()
    _write(path, 'src')
    _write(path + '.prev', 'older')
    assert sm.load() is not None and sm._loaded_from == path
    sm.begin_restore()
    _save_during_restore(sm)
    assert _uid(path + '.prev') == 'src'
    assert _marker_src(sm) == 'session.json.prev'
    assert sm.check_crash_marker() is True
    assert not os.path.exists(path + '.prev')
    data = sm.load()
    # falls back to the older session, not the one that crashed
    assert data['layout']['terminal1']['uuid'] == 'older'


def test_legacy_marker_without_source_follows_session_json(sm):
    path = sm.session_path()
    _write(path, 'src')
    with open(sm.restoring_path(), 'w') as fh:
        fh.write('2026-01-01T00:00:00\n')
    _save_during_restore(sm)
    assert _marker_src(sm) == 'session.json.prev'


def test_restore_prev2_overwritten_drops_source(sm):
    path = sm.session_path()
    _write(path + '.prev', 'p1')
    _write(path + '.prev2', 'src')
    os.makedirs(os.path.dirname(sm.restoring_path()), exist_ok=True)
    with open(sm.restoring_path(), 'w') as fh:
        fh.write('t\nsession.json.prev2\n')
    _write(path, 'cur')
    _save_during_restore(sm)
    assert _marker_src(sm) == '-'
    assert sm.check_crash_marker() is True


def test_no_marker_rotation_does_not_create_marker(sm):
    path = sm.session_path()
    _write(path, 'a')
    _save_during_restore(sm)
    assert not os.path.exists(sm.restoring_path())


@pytest.mark.parametrize('name', [
    '../x', 'x', '../session.json.prev', 'session.json',
    'session.json.bad', 'session.json.prev/../../x', '', '   ',
])
def test_marker_naming_unexpected_files(sm, tmp_path, name):
    path = sm.session_path()
    d = os.path.dirname(path)
    _write(path + '.prev', 'keep')
    _write(path + '.bad', 'bad')
    outside = tmp_path / 'x'
    outside.write_text('outside')
    (tmp_path / 'state' / 'x').write_text('sibling')
    with open(sm.restoring_path(), 'w') as fh:
        fh.write('t\n%s\n' % name)
    assert sm.check_crash_marker() is True
    assert outside.read_text() == 'outside'
    assert (tmp_path / 'state' / 'x').read_text() == 'sibling'
    assert os.path.exists(path + '.bad')
    if os.path.basename(name.strip()) == 'session.json.prev':
        assert os.path.exists(path + '.prev.crashed')
    else:
        assert _uid(path + '.prev') == 'keep'
    assert sorted(f for f in os.listdir(d) if f.endswith('.crashed')) in (
        [], ['session.json.prev.crashed'])


def test_marker_absolute_paths(sm, tmp_path):
    path = sm.session_path()
    other = tmp_path / 'elsewhere'
    other.mkdir()
    (other / 'session.json.prev').write_text('foreign')
    (other / 'session.json').write_text('foreign')
    _write(path + '.prev', 'local')
    for name in (str(other / 'session.json'), '/etc/passwd',
                 str(other / 'session.json.prev')):
        _write(path + '.prev', 'local')
        with open(sm.restoring_path(), 'w') as fh:
            fh.write('t\n%s\n' % name)
        assert sm.check_crash_marker() is True
        # never touches files outside the session directory
        assert (other / 'session.json.prev').read_text() == 'foreign'
        assert (other / 'session.json').read_text() == 'foreign'
    assert os.path.exists('/etc/passwd')


def test_binary_marker_does_not_abort(sm):
    path = sm.session_path()
    _write(path, 'a')
    with open(sm.restoring_path(), 'wb') as fh:
        fh.write(b'\xff\xfe\x00garbage\n\xff\n')
    assert sm.check_crash_marker() is True
    assert os.path.exists(path + '.crashed')
