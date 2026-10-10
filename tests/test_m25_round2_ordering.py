"""m25 round-2 x merged zoom guard / followups: close/destroy ordering.

Checks that round-2's unzoom-on-destroy, the m25 zoom-save guard
(save_now defers while legacy-zoomed), the followups' final-save refusal
and deregister_window's mark_dirty compose: exactly one final save, of the
whole (re-attached) tree, and no later timer write.
"""
from terminatorlib.session import SessionManager
from tests.test_m25_round2_fixes import (  # noqa: F401  (fixtures)
    _pump, _session_terms, app, sess)


def _fast_timer(monkeypatch):
    monkeypatch.setattr(SessionManager, '_delay_ms', lambda self: 100)


def _count_saves(monkeypatch):
    calls = []
    orig = SessionManager.save_now

    def wrapped(self, final=False):
        res = orig(self, final=final)
        calls.append((final, res, self._any_legacy_zoom()))
        return res
    monkeypatch.setattr(SessionManager, 'save_now', wrapped)
    return calls


def test_destroy_last_zoomed_window_with_pending_timer(sess, app, monkeypatch):
    from terminatorlib.terminator import Terminator
    _fast_timer(monkeypatch)
    w = app(3)
    uuids = sorted(str(t.uuid) for t in w.get_terminals())
    w.zoom(w.get_terminals()[0], font_scale=True)
    _pump(0.05)
    assert w.is_zoomed() and len(w.get_terminals()) == 1
    sess._timer = None
    sess.mark_dirty('test')            # deferred while zoomed (guard)
    assert sess._timer is None and sess._pending_after_zoom
    calls = _count_saves(monkeypatch)
    w.destroy()
    _pump(0.1)
    finals = [c for c in calls if c[0]]
    assert len(finals) == 1                       # no double final save
    assert finals[0][1] is True and finals[0][2] is False  # saved unzoomed
    assert sorted(t['uuid'] for t in _session_terms(sess)) == uuids
    assert sess._timer is None
    assert Terminator().windows == [] and Terminator().terminals == []
    with open(sess.session_path(), 'rb') as f:
        before = f.read()
    _pump(0.4)                                    # past any debounce
    assert [c for c in calls if not c[0] and c[1]] == []
    with open(sess.session_path(), 'rb') as f:
        assert f.read() == before


def test_closegroup_all_then_destroy_single_final_save(sess, app, monkeypatch):
    from terminatorlib import close_confirm
    from terminatorlib.terminator import Terminator
    monkeypatch.setattr(close_confirm, 'confirm_close_terminals',
                        lambda ts, parent_window=None: True)
    w = app(2)
    a, b = w.get_terminals()
    a.group = b.group = 'g'
    w.zoom(a, font_scale=True)                    # b hidden by legacy zoom
    _pump(0.05)
    calls = _count_saves(monkeypatch)
    assert Terminator().closegroupedterms('g')
    _pump(0.2)
    finals = [c for c in calls if c[0]]
    assert len(finals) == 1 and finals[0][1] is True
    assert len(_session_terms(sess)) == 2


def test_last_window_deregister_with_pending_timer_leaves_file(sess, app,
                                                               monkeypatch):
    from terminatorlib.terminator import Terminator
    _fast_timer(monkeypatch)
    w = app(2)
    assert sess.save_now(final=False)
    with open(sess.session_path(), 'rb') as f:
        good = f.read()
    sess._timer = None
    sess._last_change_hash = None                 # force a real describe
    sess.mark_dirty('pending')
    assert sess._timer is not None
    # Window goes away without the destroy/finalize path (e.g. torn down
    # externally): terminals and window deregistered, timer still armed.
    # (Bypass deregister_terminal: its last-terminal branch destroys the
    # window and runs finalize, which is the covered path above.)
    del Terminator().terminals[:]
    Terminator().deregister_window(w)             # followups: mark_dirty
    assert Terminator().windows == []
    _pump(0.4)
    assert sess._timer is None                    # fired
    with open(sess.session_path(), 'rb') as f:
        assert f.read() == good                   # 0 terminals: not written
