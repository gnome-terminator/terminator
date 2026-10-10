"""m25: round-2 integration review fixes (reviews/2026-10-10-round2-integration.md).

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


# ---- P1-1 ------------------------------------------------------------------

def test_p1_1_close_while_maximised_keeps_maximised_pane(sess, app):
    w = app(2)
    t1 = w.get_terminals()[0]
    assert w.overlay_maximise(t1, animate=False)
    w.destroy()
    _pump(0.1)
    terms = _session_terms(sess)
    assert len(terms) == 2
    flagged = [t for t in terms if t.get('maximised_pane') == 'True']
    assert [t['uuid'] for t in flagged] == [str(t1.uuid)]


def test_p1_1_d5_fragment_keeps_maximised_pane(sess, app):
    w = app(2)
    other = app(1)
    t1 = w.get_terminals()[0]
    assert w.overlay_maximise(t1, animate=False)
    w.destroy()
    _pump(0.1)
    frag = sess._closing_buffer['windows'][0]
    assert any(v.get('maximised_pane') == 'True' and v['uuid'] == str(t1.uuid)
               for v in frag.values() if v.get('type') == 'Terminal')
    assert other in sess_windows()


def sess_windows():
    from terminatorlib.terminator import Terminator
    return Terminator().windows


# ---- P1-2 ------------------------------------------------------------------

def test_p1_2_last_pane_close_flushes_latest_output(sess, app):
    from terminatorlib.scrollback import ScrollbackCache
    w = app(1)
    t = w.get_terminals()[0]
    uid = str(t.uuid)
    _feed(t, 'M25_LAST_OUTPUT_MARKER')
    t.emit('close-term')          # exit / Ctrl+Shift+W / titlebar X path
    _pump(0.1)
    path = ScrollbackCache().path_for(uid)
    assert os.path.isfile(path), 'last pane output was not flushed'
    with open(path, encoding='utf-8') as fh:
        assert 'M25_LAST_OUTPUT_MARKER' in fh.read()
    # The final save describes what was open: this pane (P2-6 decision).
    assert [x['uuid'] for x in _session_terms(sess)] == [uid]


def test_p1_2_last_pane_close_drops_recently_closed_sibling(sess, app):
    """Closing B then the last pane A: the final save holds A only (it used
    to keep the stale debounced layout with B, whose cache was deleted)."""
    w = app(2)
    a, b = w.get_terminals()
    b.emit('close-term')
    _pump(0.05)
    a.emit('close-term')
    _pump(0.1)
    assert [x['uuid'] for x in _session_terms(sess)] == [str(a.uuid)]


def test_p1_2_finalize_flushes_deregistered_closing_terminal(sess, app):
    """Terminal.close fallback: finalize(closing=t) flushes t as well."""
    from terminatorlib.scrollback import ScrollbackCache
    from terminatorlib.terminator import Terminator
    w = app(1)
    t = w.get_terminals()[0]
    _feed(t, 'M25_FALLBACK_MARKER')
    Terminator().terminals.remove(t)
    sess.finalize(closing=t)
    with open(ScrollbackCache().path_for(str(t.uuid)), encoding='utf-8') as fh:
        assert 'M25_FALLBACK_MARKER' in fh.read()


# ---- P1-3 ------------------------------------------------------------------

def test_p1_3_strip_live_ids():
    from terminatorlib.session import strip_live_ids
    lay = {'w': {'type': 'Window', 'last_active_term': 'u1'},
           't': {'type': 'Terminal', 'uuid': 'u1', 'maximised_pane': 'True',
                 'directory': '/tmp'}}
    strip_live_ids(lay)
    assert lay == {'w': {'type': 'Window'},
                   't': {'type': 'Terminal', 'directory': '/tmp'}}


def test_p1_3_remap_layout_uuids_keeps_focus_refs():
    from terminatorlib.session import remap_layout_uuids
    lay = {'w': {'type': 'Window', 'last_active_term': 'a'},
           'n': {'type': 'Notebook', 'last_active_term': ['a', 'b', 'zz']},
           'ta': {'type': 'Terminal', 'uuid': 'a'},
           'tb': {'type': 'Terminal', 'uuid': 'b'},
           'w2': {'type': 'Window', 'last_active_term': 'gone'}}
    fresh = iter(['N1', 'N2'])
    mapping = remap_layout_uuids(lay, new_uuid=lambda: next(fresh))
    assert {lay['ta']['uuid'], lay['tb']['uuid']} == {'N1', 'N2'}
    assert lay['w']['last_active_term'] == mapping['a'] == lay['ta']['uuid']
    assert lay['n']['last_active_term'] == [mapping['a'], mapping['b'], '']
    assert 'last_active_term' not in lay['w2']


def test_p1_3_layout_uuid_of_live_terminal_is_not_reused(app):
    from terminatorlib.factory import Factory
    from terminatorlib.terminator import Terminator
    w = app(1)
    live = w.get_terminals()[0]
    t = Factory().make('Terminal')
    try:
        mine = t.uuid
        t.create_layout({'uuid': str(live.uuid)})
        assert t.uuid != live.uuid and t.uuid == mine
        free = '12345678-1234-5678-1234-567812345678'
        t.create_layout({'uuid': free})
        assert str(t.uuid) == free
    finally:
        if t in Terminator().terminals:
            Terminator().terminals.remove(t)
        t.destroy()


def test_p1_3_user_layout_gets_fresh_uuids(monkeypatch):
    from terminatorlib import session
    from terminatorlib.terminator import Terminator
    term = Terminator()
    seen = []

    def fake_remap(layout, new_uuid=None):
        seen.append(dict(layout))
        layout.clear()           # stop create_layout right after the remap

    monkeypatch.setattr(session, 'remap_layout_uuids', fake_remap)
    class _Stop(Exception):
        pass

    def stop(*a, **k):
        raise _Stop()
    monkeypatch.setattr(term, 'new_window', stop)
    monkeypatch.setattr(term, 'doing_layout', False)
    monkeypatch.setattr(term, 'prelayout_windows', None)
    monkeypatch.setattr(term, 'last_active_window', None)
    lay = {'w': {'type': 'Window', 'parent': ''},
           't': {'type': 'Terminal', 'parent': 'w', 'uuid': 'u1'}}
    monkeypatch.setattr(term.config, 'layout_get_config', lambda name: lay)
    with pytest.raises(_Stop):
        term.create_layout('mylayout')
    assert len(seen) == 1
    with pytest.raises(_Stop):
        term.create_layout(session.SESSION_LAYOUT_NAME)
    assert len(seen) == 1        # the restored session keeps its uuids


class _Model(list):
    def get_path(self, it):
        return 0


class _Tree(object):
    def __init__(self):
        self.model = _Model()

    def get_model(self):
        return self.model

    def set_cursor(self, *a, **k):
        pass


def test_p1_3_prefs_add_layout_strips_uuids(monkeypatch):
    from terminatorlib.prefseditor import PrefsEditor
    from terminatorlib.terminator import Terminator
    monkeypatch.setattr(Terminator(), 'describe_layout', lambda *a, **k: {
        'w': {'type': 'Window', 'last_active_term': 'u1'},
        't': {'type': 'Terminal', 'uuid': 'u1', 'maximised_pane': 'True'}})
    tree = _Tree()
    added = {}

    class Cfg(object):
        def add_layout(self, name, layout):
            added[name] = layout
            return True

        def save(self):
            pass

    class Builder(object):
        def get_object(self, name):
            return tree

    class Fake(object):
        config = Cfg()
        builder = Builder()
    PrefsEditor.on_layoutaddbutton_clicked(Fake(), None)
    (layout,) = added.values()
    assert 'uuid' not in layout['t'] and 'maximised_pane' not in layout['t']
    assert 'last_active_term' not in layout['w']


# ---- P2-1 / P2-2 legacy zoom ---------------------------------------------

def test_p2_1_d5_fragment_of_zoomed_window_is_complete(sess, app):
    w = app(2)
    app(1)
    t1 = w.get_terminals()[0]
    w.zoom(t1, font_scale=True)
    _pump(0.05)
    assert w.is_zoomed() and len(w.get_terminals()) == 1
    sess.note_window_closing(w)
    frag = sess._closing_buffer['windows'][0]
    assert sum(1 for v in frag.values() if v.get('type') == 'Terminal') == 2


def test_p2_2_destroying_zoomed_window_closes_hidden_terminals(sess, app):
    from terminatorlib.terminator import Terminator
    w = app(2)
    other = app(1)
    hidden = w.get_terminals()[1]
    w.zoom(w.get_terminals()[0], font_scale=True)
    _pump(0.05)
    w.destroy()
    _pump(0.1)
    assert hidden not in Terminator().terminals
    assert Terminator().terminals == other.get_terminals()


# ---- P2-3 non-owner prefs ----------------------------------------------------

def test_p2_3_non_owner_cannot_clear_or_use_previous(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    _reset_borgs()
    from terminatorlib.prefseditor import PrefsEditor
    from terminatorlib.session import SessionManager
    sm = SessionManager()
    assert not sm.is_owner()
    calls = []
    monkeypatch.setattr(SessionManager, 'clear_session_files',
                        lambda self: calls.append('clear'))
    monkeypatch.setattr(SessionManager, 'restore_prev_session',
                        lambda self: calls.append('prev'))
    monkeypatch.setattr(SessionManager, 'suspend_writes',
                        lambda self, r='': calls.append('suspend'))
    os.makedirs(os.path.dirname(sm.session_path()), exist_ok=True)
    open(sm.session_path() + '.prev', 'w').close()

    class Obj(object):
        def __init__(self):
            self.sensitive = True

        def set_sensitive(self, v):
            self.sensitive = v

        def get_active(self):
            return True

    objs = {}

    class Builder(object):
        def get_object(self, name):
            return objs.setdefault(name, Obj())

    class Fake(object):
        builder = Builder()
        notices = []
        _session_owner = staticmethod(PrefsEditor._session_owner)
        _refuse_if_not_owner = PrefsEditor._refuse_if_not_owner
        update_session_sensitivity = PrefsEditor.update_session_sensitivity

        def update_session_info(self, notice=None):
            self.notices.append(notice)

        def _confirm(self, *a):
            calls.append('confirm')
            return True

    f = Fake()
    f.update_session_sensitivity()
    assert objs['session_clear_button'].sensitive is False
    assert objs['session_restore_prev_button'].sensitive is False
    PrefsEditor.on_session_clear_button_clicked(f, None)
    PrefsEditor.on_session_restore_prev_button_clicked(f, None)
    assert calls == [] and len(f.notices) == 2
    # The owner keeps both buttons
    monkeypatch.setattr(SessionManager, 'is_owner', lambda self: True)
    f.update_session_sensitivity()
    assert objs['session_clear_button'].sensitive is True
    _reset_borgs()


# ---- P2-4 / P2-5 excluded windows -------------------------------------------

def test_p2_4_excluded_window_writes_no_cache(sess, app):
    from terminatorlib.scrollback import ScrollbackCache
    w = app(1)
    keep = app(1)
    w._session_excluded = True
    t = w.get_terminals()[0]
    _feed(t, 'M25_EXCLUDED')
    sess.final_saving = True
    assert sess.will_persist(t) is False
    assert sess.will_persist(keep.get_terminals()[0]) is True
    cache = ScrollbackCache()
    cache._flush_uuid(t, str(t.uuid), sync=True)
    assert not os.path.exists(cache.path_for(str(t.uuid)))


def test_p2_5_excluded_window_joins_session_after_split(sess, app, monkeypatch):
    from terminatorlib.terminator import Terminator
    from terminatorlib.session import note_window_grown
    w = app(1)
    w._session_excluded = True
    monkeypatch.setattr(Terminator(), 'doing_layout', True)
    note_window_grown(w)
    assert w._session_excluded            # layout building does not count
    monkeypatch.setattr(Terminator(), 'doing_layout', False)
    t = w.get_terminals()[0]
    w.split_horiz(t)
    _pump(0.1)
    assert not w._session_excluded
    assert len(w.get_terminals()) == 2


# ---- P2-7 close group covering everything -----------------------------------

def test_p2_7_close_group_of_all_terminals_saves_whole_layout(sess, app,
                                                             monkeypatch):
    from terminatorlib import close_confirm
    from terminatorlib.terminator import Terminator
    monkeypatch.setattr(close_confirm, 'confirm_close_terminals',
                        lambda ts, parent_window=None: True)
    w = app(2)
    a, b = w.get_terminals()
    a.group = b.group = 'g'
    closed = []
    for t in (a, b):
        orig = t.close
        t.close = (lambda o=orig, t=t: (closed.append(t), o())[1])
    assert Terminator().closegroupedterms('g')
    _pump(0.1)
    assert len(_session_terms(sess)) == 2
    assert sorted(map(id, closed)) == sorted(map(id, (a, b)))  # once each


# ---- P2-9 teardown on a dying window ------------------------------------------

def test_p2_9_teardown_on_dying_window_skips_focus_and_font(app):
    w = app(2)
    t1 = w.get_terminals()[0]
    assert w.overlay_maximise(t1, animate=False)
    calls = []
    t1.resume_auto_font_scale = lambda *a: calls.append('resume')
    t1.grab_focus = lambda *a: calls.append('focus')
    w._session_destroy_handled = True
    w._overlay.teardown()
    assert not w.is_overlay_maximised()
    assert t1 in w.get_terminals()
    assert calls == []


def test_p2_8_script_comment_is_honest():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(here, 'terminator')).read()
    assert 'display connection loss, a stray' not in src
    assert 'C exit()' in src
