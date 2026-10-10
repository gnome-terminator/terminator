"""m21: end-to-end session save -> load -> sanitize -> create_layout under
Xvfb with real widgets (covers splits, cwd, uuids, user window title, the
D5 two-window close buffer and legacy layout titles)."""
import json
import os

import gi
import pytest

gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import Gtk  # noqa: E402

from terminatorlib.session import SESSION_LAYOUT_NAME


def _pump():
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)


def _reset_session_borg():
    from terminatorlib.borg import Borg
    Borg._Borg__shared_state.pop('SessionManager', None)


@pytest.fixture
def env(tmp_path, monkeypatch):
    from terminatorlib.terminal import Terminal
    from terminatorlib.terminator import Terminator
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    monkeypatch.setattr(Terminal, 'spawn_child', lambda self, *a, **k: True)
    # No shell -> report the directory the terminal was given / restored to
    monkeypatch.setattr(Terminal, 'get_cwd',
                        lambda self: getattr(self, 'directory', None)
                        or getattr(self, 'cwd', None) or str(tmp_path))
    monkeypatch.setattr(Terminator(), 'terminals', [])
    monkeypatch.setattr(Terminator(), 'windows', [])
    # create_layout() records layoutname; prefs later highlights it
    monkeypatch.setattr(Terminator(), 'layoutname',
                        getattr(Terminator(), 'layoutname', None))
    monkeypatch.setattr(Terminator(), 'last_active_window',
                        getattr(Terminator(), 'last_active_window', None))
    _reset_session_borg()
    from terminatorlib.session import SessionManager
    sm = SessionManager()
    assert sm.acquire_lock()
    sm._owns_session = True
    yield tmp_path, sm
    for w in list(Terminator().windows):
        for t in list(w.get_terminals()):
            Terminator().deregister_terminal(t)
        try:
            w.title.destroy()
        except Exception:
            pass
        Terminator().deregister_window(w)
        w.isDestroyed = True
        w.destroy()
    _pump()
    try:
        os.close(sm._lock_fd)
    except Exception:
        pass
    from terminatorlib.config import Config
    Config().base.layouts.pop(SESSION_LAYOUT_NAME, None)
    Config().base.layouts.pop('m21legacy', None)
    _reset_session_borg()


def _make_window(dirs):
    """Window with len(dirs) terminals (one split when 2)."""
    from terminatorlib.factory import Factory
    w = Factory().make('Window')
    t = Factory().make('Terminal')
    t.directory = dirs[0]
    w.add(t)
    w.show_all()
    _pump()
    if len(dirs) > 1:
        w.split_axis(t, False)
        _pump()
        others = [x for x in w.get_terminals() if x is not t]
        others[0].directory = dirs[1]
    return w


def _restore(sm):
    """What the terminator script does on restore."""
    from terminatorlib.config import Config
    from terminatorlib.terminator import Terminator
    data = sm.load()
    assert data is not None
    layout = sm.sanitize_layout(data['layout'])
    Config().base.layouts[SESSION_LAYOUT_NAME] = layout
    before = list(Terminator().windows)
    Terminator().create_layout(SESSION_LAYOUT_NAME)
    Terminator().layout_done()
    _pump()
    return [w for w in Terminator().windows if w not in before]


def _close_all(windows):
    from terminatorlib.terminator import Terminator
    for w in windows:
        for t in list(w.get_terminals()):
            Terminator().deregister_terminal(t)
        w.title.destroy()
        Terminator().deregister_window(w)
        w.isDestroyed = True
        w.destroy()
    _pump()


def test_round_trip_splits_cwd_uuid_and_user_title(env):
    tmp, sm = env
    d1 = tmp / 'proj'
    d2 = tmp / 'logs'
    d1.mkdir()
    d2.mkdir()
    w = _make_window([str(d1), str(d2)])
    w.title.force_title('My pinned title')
    uuids = sorted(str(t.uuid) for t in w.get_terminals())
    assert sm.save_now(final=True)
    _close_all([w])

    restored = _restore(sm)
    assert len(restored) == 1
    rw = restored[0]
    assert rw.title.forced and rw.title.persist
    assert rw.title.text == 'My pinned title'
    terms = rw.get_terminals()
    assert sorted(str(t.uuid) for t in terms) == uuids
    assert sorted(t.directory for t in terms) == sorted([str(d1), str(d2)])
    from terminatorlib.paned import Paned
    assert isinstance(rw.get_child(), Paned)


def test_d5_first_window_closed_first_restores_both(env):
    """P0-1: W1 (split) closes, then W2 within the grace period."""
    from terminatorlib.terminator import Terminator
    tmp, sm = env
    w1 = _make_window([str(tmp), str(tmp)])
    w2 = _make_window([str(tmp)])
    w1.title.force_title('first')
    all_uuids = sorted(str(t.uuid) for w in (w1, w2) for t in w.get_terminals())

    sm.note_window_closing(w1)
    _close_all([w1])
    assert Terminator().windows == [w2]
    assert sm.save_now(final=True)
    _close_all([w2])

    with open(sm.session_path(), encoding='utf-8') as fh:
        layout = json.load(fh)['layout']
    windows = [n for n, v in layout.items() if v['type'] == 'Window']
    assert len(windows) == 2
    for name in windows:
        kids = [n for n, v in layout.items() if v.get('parent') == name]
        assert len(kids) == 1, layout

    restored = _restore(sm)
    assert len(restored) == 2
    got = sorted(str(t.uuid) for w in restored for t in w.get_terminals())
    assert got == all_uuids
    titles = sorted(w.title.text for w in restored if w.title.forced)
    assert titles == ['first']


def test_legacy_layout_dynamic_title_is_not_forced(env):
    """Upstream layouts carry the dynamic title without a marker."""
    from terminatorlib.config import Config
    from terminatorlib.terminator import Terminator
    tmp, sm = env
    Config().base.layouts['m21legacy'] = {
        'window0': {'type': 'Window', 'parent': '',
                    'title': 'user@host: ~'},
        'terminal1': {'type': 'Terminal', 'parent': 'window0'},
    }
    Terminator().create_layout('m21legacy')
    Terminator().layout_done()
    _pump()
    (w,) = Terminator().windows
    assert not w.title.forced


def test_create_layout_ignores_malformed_entries(env):
    from terminatorlib.config import Config
    from terminatorlib.terminator import Terminator
    Config().base.layouts['m21legacy'] = {
        'window0': {'type': 'Window', 'parent': ''},
        'junk': 'x',
        'notype': {'parent': 'window0'},
        'terminal1': {'type': 'Terminal', 'parent': 'window0'},
    }
    Terminator().create_layout('m21legacy')
    Terminator().layout_done()
    _pump()
    assert len(Terminator().windows) == 1


def test_explicit_windows_excluded_from_session(env):
    tmp, sm = env
    plain = _make_window([str(tmp)])
    explicit = _make_window([str(tmp)])
    sm.exclude_windows([explicit])
    assert sm.save_now(final=True)
    with open(sm.session_path(), encoding='utf-8') as fh:
        layout = json.load(fh)['layout']
    uuids = {v.get('uuid') for v in layout.values() if v['type'] == 'Terminal'}
    assert uuids == {str(t.uuid) for t in plain.get_terminals()}
