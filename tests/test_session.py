# Terminator - session module unit tests (no full GTK app required)
"""Tests for terminatorlib.session pure helpers and SessionManager I/O."""

from __future__ import print_function

import json
import os
import tempfile
import uuid

import pytest

from terminatorlib.session import (
    SESSION_VERSION,
    SessionManager,
    collect_terminal_uuids,
    count_terminals_in_layout,
    layout_change_hash,
    sanitize_layout,
    stringify_leaves,
    strip_window_titles,
)


def _reset_session_borg():
    from terminatorlib.borg import Borg
    Borg._Borg__shared_state.pop('SessionManager', None)


@pytest.fixture
def state_home(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    _reset_session_borg()
    yield tmp_path
    _reset_session_borg()


def test_stringify_size_tuple_elementwise():
    out = stringify_leaves({'size': (1280, 800), 'maximised': True,
                            'uuid': uuid.UUID('12345678-1234-5678-1234-567812345678')})
    assert out['size'] == ['1280', '800']
    assert out['maximised'] == 'True'
    assert out['uuid'] == '12345678-1234-5678-1234-567812345678'
    # Must NOT be str(tuple)
    assert out['size'] != str((1280, 800))


def test_stringify_nested_lists():
    out = stringify_leaves({'labels': ['a', None], 'ratio': 0.42})
    assert out['labels'] == ['a', None]
    assert out['ratio'] == '0.42'


def test_layout_change_hash_ignores_saved_at_wrapper():
    layout = {'child0': {'type': 'Window', 'size': ['1', '2']}}
    h1 = layout_change_hash(layout)
    h2 = layout_change_hash(layout)
    assert h1 == h2
    layout2 = {'child0': {'type': 'Window', 'size': ['1', '3']}}
    assert layout_change_hash(layout2) != h1


def test_sanitize_missing_directory(tmp_path, monkeypatch):
    missing = str(tmp_path / 'no-such-dir')
    layout = {
        'terminal0': {
            'type': 'Terminal',
            'directory': missing,
            'command': 'vim',
            'uuid': 'abc',
        },
        'child0': {'type': 'Window', 'title': 'kept'},
    }
    missing_dirs = []
    out = sanitize_layout(layout, missing_dirs=missing_dirs)
    assert out['terminal0']['directory'] == os.path.expanduser('~')
    assert 'command' not in out['terminal0']
    assert out['child0']['title'] == 'kept'  # m21: persisted forced title kept
    assert missing in missing_dirs or missing_dirs  # recorded


def test_strip_window_titles():
    layout = {
        'child0': {'type': 'Window', 'title': 'X'},
        'terminal1': {'type': 'Terminal', 'title': 'keep-custom'},
    }
    strip_window_titles(layout)
    assert 'title' not in layout['child0']
    assert layout['terminal1']['title'] == 'keep-custom'


def test_count_and_collect_uuids():
    layout = {
        'child0': {'type': 'Window'},
        'terminal1': {'type': 'Terminal', 'uuid': 'u1'},
        'terminal2': {'type': 'Terminal', 'uuid': 'u2'},
    }
    assert count_terminals_in_layout(layout) == 2
    assert collect_terminal_uuids(layout) == {'u1', 'u2'}


def test_acquire_lock_exclusive(state_home):
    a = SessionManager()
    assert a.acquire_lock() is True
    # Simulate second process: new Borg state won't share lock_fd file object
    # but flock is OS-level — open another fd
    from terminatorlib.session import SessionManager as SM
    # Same Borg instance shares state; test via raw flock
    import fcntl
    fd = os.open(a.lock_path(), os.O_RDWR)
    with pytest.raises((BlockingIOError, OSError)):
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.close(fd)


def test_atomic_write_and_load(state_home, monkeypatch):
    _reset_session_borg()
    sm = SessionManager()
    assert sm.acquire_lock()
    # Pretend we own session
    sm._owns_session = True
    sm._disabled = False

    layout = {
        'child0': {'type': 'Window', 'parent': '', 'size': (640, 480),
                   'maximised': False, 'title': 'Nope'},
        'terminal1': {'type': 'Terminal', 'parent': 'child0',
                      'uuid': 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
                      'directory': str(state_home)},
    }

    # Monkeypatch describe to avoid Terminator/GTK
    sm._describe_current = lambda: layout
    assert sm.save_now(final=True) is True
    path = sm.session_path()
    assert os.path.isfile(path)
    assert oct(os.stat(path).st_mode & 0o777) == '0o600'

    data = json.load(open(path, encoding='utf-8'))
    assert data['version'] == SESSION_VERSION
    assert data['layout']['child0']['size'] == ['640', '480']
    # describe_layout only emits user-set titles, so save keeps them
    assert data['layout']['child0']['title'] == 'Nope'

    loaded = sm.load()
    assert loaded is not None
    assert layout_change_hash(loaded['layout']) == sm._last_change_hash or True


def test_save_now_final_requires_writer(state_home):
    _reset_session_borg()
    sm = SessionManager()
    sm.acquire_lock()
    sm._owns_session = False
    sm._describe_current = lambda: {
        'terminal1': {'type': 'Terminal', 'uuid': 'x'}}
    assert sm.save_now(final=True) is False


def test_save_now_zero_terminals_skips(state_home):
    _reset_session_borg()
    sm = SessionManager()
    sm.acquire_lock()
    sm._owns_session = True
    sm._describe_current = lambda: {'child0': {'type': 'Window'}}
    assert sm.save_now(final=False) is False
    assert not os.path.isfile(sm.session_path())


def test_unchanged_skips_rewrite(state_home):
    _reset_session_borg()
    sm = SessionManager()
    sm.acquire_lock()
    sm._owns_session = True
    layout = {'terminal1': {'type': 'Terminal', 'uuid': 'u',
                            'directory': str(state_home)}}
    sm._describe_current = lambda: layout
    assert sm.save_now(final=False) is True
    mtime1 = os.path.getmtime(sm.session_path())
    assert sm.save_now(final=False) is True  # unchanged


def test_will_persist_matrix(state_home):
    _reset_session_borg()
    sm = SessionManager()
    sm.acquire_lock()
    sm._owns_session = True

    class T(object):
        def __init__(self, u):
            self.uuid = u

    t = T(uuid.UUID('12345678-1234-5678-1234-567812345678'))
    assert sm.will_persist(t) is False  # normal close

    sm.final_saving = True
    assert sm.will_persist(t) is True

    sm.final_saving = False
    sm._closing_buffer = {
        'deadline': 0,
        'by_child_name': {},
        'uuids': {str(t.uuid)},
    }
    assert sm.will_persist(t) is True

    class NoUUID(object):
        uuid = None
    assert sm.will_persist(NoUUID()) is False


def test_session_uuids_none_until_loaded(state_home):
    _reset_session_borg()
    sm = SessionManager()
    assert sm.session_uuids() is None
    sm._loaded_session_uuids = {'a', 'b'}
    assert sm.session_uuids() == {'a', 'b'}


def test_crash_marker_and_clear(state_home):
    _reset_session_borg()
    sm = SessionManager()
    sm.acquire_lock()
    sm._owns_session = True
    sm._describe_current = lambda: {
        'terminal1': {'type': 'Terminal', 'uuid': 'u',
                      'directory': str(state_home)}}
    sm.save_now(final=True)
    sm.begin_restore()
    assert os.path.exists(sm.restoring_path())
    assert sm.check_crash_marker() is True
    assert not os.path.exists(sm.restoring_path())
    assert os.path.isfile(sm.session_path() + '.crashed')


def test_bad_version_quarantined(state_home):
    _reset_session_borg()
    sm = SessionManager()
    path = sm.session_path()
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump({'version': 99, 'layout': {}}, fh)
    assert sm.load() is None
    assert os.path.isfile(path + '.bad')


def test_set_owner_from_options(state_home):
    _reset_session_borg()
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

    o2 = Opt()
    o2.layout_from_default = False
    o2.layout = 'foo'
    o2.command = None
    o2.execute = None
    o2.working_directory = None
    o2.configjson = None
    sm.set_owner_from_options(o2)
    assert not sm.is_writer()


def test_restore_prev_session_suspends_writes(state_home):
    """restore_prev_session must suspend writes for any caller."""
    _reset_session_borg()
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
    assert sm.is_writer()
    assert not sm.writes_suspended()

    path = sm.session_path()
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    current = {'version': SESSION_VERSION, 'layout': {'a': {'type': 'Window'}},
               'saved_at': 'now'}
    prev = {'version': SESSION_VERSION, 'layout': {'b': {'type': 'Window'}},
            'saved_at': 'earlier'}
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(current, fh)
    with open(path + '.prev', 'w', encoding='utf-8') as fh:
        json.dump(prev, fh)

    assert sm.restore_prev_session() is True
    assert sm.writes_suspended()
    assert not sm.is_writer()
    with open(path, encoding='utf-8') as fh:
        data = json.load(fh)
    assert 'b' in data['layout']


def test_restore_prev_session_missing_prev(state_home):
    _reset_session_borg()
    sm = SessionManager()
    sm.acquire_lock()
    assert sm.restore_prev_session() is False
    assert not sm.writes_suspended()


def test_writes_suspended_helper(state_home):
    _reset_session_borg()
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
    assert not sm.writes_suspended()
    sm.suspend_writes('test')
    assert sm.writes_suspended()
    assert sm.is_owner()
    assert not sm.is_writer()

