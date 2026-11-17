"""m26: follow-ups to the round-2 excluded-window fixes (reviewer P3s).

In-process GTK (real Window/Terminal, no child shells) with a temporary
session owner, so the close/destroy orderings are exercised for real.
"""
import json
import os
import time

import pytest
from gi.repository import Gtk


def _pump(seconds=0.0):
    end = time.monotonic() + seconds
    while True:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        if time.monotonic() >= end:
            break
        time.sleep(0.01)


def _reset_borgs():
    from terminatorlib.borg import Borg
    for name in ('SessionManager', 'ScrollbackCache'):
        Borg._Borg__shared_state.pop(name, None)


@pytest.fixture
def sess(tmp_path, monkeypatch):
    """A session-owning SessionManager + running ScrollbackCache in tmp."""
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    from terminatorlib import terminator as termmod
    monkeypatch.setattr(termmod.Gtk, 'main_quit', lambda *a: None)
    _reset_borgs()
    from terminatorlib.session import SessionManager
    from terminatorlib.scrollback import ScrollbackCache
    s = SessionManager()
    assert s.acquire_lock()
    s._owns_session = True
    cache = ScrollbackCache()
    cache.start()
    assert cache._enabled
    yield s
    try:
        cache.stop(join_timeout=1.0)
    except Exception:
        pass
    try:
        os.close(s._lock_fd)
    except Exception:
        pass
    _reset_borgs()


@pytest.fixture
def app(monkeypatch):
    """Factory for windows with N terminals; cleans up everything."""
    from terminatorlib.terminal import Terminal
    from terminatorlib.terminator import Terminator
    from terminatorlib.factory import Factory
    monkeypatch.setattr(Terminal, 'spawn_child', lambda self, *a, **k: True)
    monkeypatch.setattr(Terminator(), 'terminals', [])
    monkeypatch.setattr(Terminator(), 'windows', [])
    made = []

    def make(n=1):
        w = Factory().make('Window')
        t = Factory().make('Terminal')
        w.add(t)
        w.resize(1000, 700)
        w.show_all()
        _pump(0.1)
        for _ in range(n - 1):
            last = w.get_terminals()[-1]
            last.get_parent().split_axis(last, True)
            _pump(0.1)
        made.append(w)
        return w

    yield make
    for term in list(Terminator().terminals):
        try:
            Terminator().terminals.remove(term)
        except ValueError:
            pass
    for w in made:
        if not getattr(w, 'isDestroyed', False):
            w._session_destroy_handled = True
            Gtk.Window.destroy(w)
    _pump()


def _session_terms(sess):
    data = sess.load()
    assert data, 'no session written'
    return [v for v in data['layout'].values() if v.get('type') == 'Terminal']


def _feed(term, text):
    term.vte.feed((text + '\r\n').encode('utf-8'))
    _pump(0.05)



# ---- (a) exclusion survives detach ------------------------------------------

def test_detached_pane_of_excluded_window_writes_no_cache(sess, app):
    from terminatorlib.scrollback import ScrollbackCache
    from terminatorlib.session import SessionManager
    w = app(1)
    SessionManager().exclude_windows([w])
    t = w.get_terminals()[0]
    assert t._session_window_excluded is True
    _feed(t, 'M26_DETACHED')
    w.remove(t)                       # like the fallback close path
    _pump(0.05)
    assert t.get_toplevel() is t
    sess.final_saving = True
    assert sess.will_persist(t) is False
    cache = ScrollbackCache()
    cache._flush_uuid(t, str(t.uuid), sync=True)
    assert not os.path.exists(cache.path_for(str(t.uuid)))


def test_closeterm_records_exclusion_before_detach(sess, app):
    from terminatorlib.session import terminal_is_excluded
    w = app(2)
    w._session_excluded = True        # set directly, nothing recorded yet
    t = w.get_terminals()[0]
    t.__dict__.pop('_session_window_excluded', None)
    t.get_parent().closeterm(t)
    _pump(0.05)
    assert t._session_window_excluded is True
    assert terminal_is_excluded(t) is True


def test_detached_pane_of_normal_window_still_persists(sess, app):
    w = app(1)
    app(1)
    t = w.get_terminals()[0]
    from terminatorlib.session import terminal_is_excluded
    assert terminal_is_excluded(t) is False
    w.remove(t)
    _pump(0.05)
    sess.final_saving = True
    assert sess.will_persist(t) is True


# ---- (b) growing window marks old panes dirty -------------------------------

def test_grown_window_marks_existing_panes_dirty(sess, app):
    from terminatorlib.scrollback import ScrollbackCache
    from terminatorlib.session import SessionManager, note_window_grown
    w = app(1)
    SessionManager().exclude_windows([w])
    t = w.get_terminals()[0]
    _feed(t, 'M26_EARLY_OUTPUT')
    cache = ScrollbackCache()
    cache._dirty.discard(str(t.uuid))
    note_window_grown(w)
    assert not w._session_excluded
    assert t._session_window_excluded is False
    assert str(t.uuid) in cache._dirty
    cache._flush_uuid(t, str(t.uuid), sync=True)
    path = cache.path_for(str(t.uuid))
    assert os.path.exists(path)
    with open(path, encoding='utf-8', errors='replace') as fh:
        assert 'M26_EARLY_OUTPUT' in fh.read()
