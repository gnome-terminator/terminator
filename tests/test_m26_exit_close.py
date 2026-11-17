"""m26 (e2e 2b): a window closed because its last shell exited must be kept
in the session like one closed with Ctrl+Shift+Q (D5 buffer)."""
import pytest

from tests.test_m25_round2_fixes import _pump, app, sess  # noqa: F401 fixtures


def _exit(term):
    # same path as VTE child-exited with exit_action=close
    term._on_child_exited_close(term.vte, 0)
    _pump(0.1)


def _windows(data):
    return [k for k, v in data['layout'].items() if v.get('type') == 'Window']


def _uuids(data):
    return sorted(str(v.get('uuid')) for v in data['layout'].values()
                  if v.get('type') == 'Terminal')


def test_exit_closed_window_is_buffered_then_saved(sess, app):
    w1 = app(1)
    w2 = app(1)
    t1, = w1.get_terminals()
    t2, = w2.get_terminals()
    u1, u2 = str(t1.uuid), str(t2.uuid)
    _exit(t1)
    assert getattr(w1, 'isDestroyed', False)
    buf = sess._closing_buffer
    assert buf and u1 in buf['uuids'], 'exit-closed window not buffered'
    assert sess.will_persist(t1)
    _exit(t2)
    data = sess.load()
    assert len(_windows(data)) == 2
    assert _uuids(data) == sorted([u1, u2])


def test_exit_closed_multi_pane_window_last_pane(sess, app):
    w1 = app(2)
    w2 = app(1)
    a, b = w1.get_terminals()
    _exit(a)
    assert not sess._closing_buffer, 'closing a non-last pane must not buffer'
    _exit(b)
    assert sess._closing_buffer and str(b.uuid) in sess._closing_buffer['uuids']
    (t2,) = w2.get_terminals()
    _exit(t2)
    data = sess.load()
    assert len(_windows(data)) == 2
    assert _uuids(data) == sorted([str(b.uuid), str(t2.uuid)])


def test_ctrl_shift_q_and_exit_paths_agree(sess, app):
    """Window destroyed (Ctrl+Shift+Q / WM) then the other window's shell
    exits: both windows restored, as in the exit-then-exit order."""
    w1 = app(1)
    w2 = app(1)
    (t1,) = w1.get_terminals()
    (t2,) = w2.get_terminals()
    w1.on_destroy_event(w1)
    _pump(0.1)
    _exit(t2)
    data = sess.load()
    assert len(_windows(data)) == 2
    assert _uuids(data) == sorted([str(t1.uuid), str(t2.uuid)])


def test_single_window_exit_finalizes_with_terminal(sess, app):
    w = app(1)
    (t,) = w.get_terminals()
    _exit(t)
    assert sess._finalize_done
    data = sess.load()
    assert _uuids(data) == [str(t.uuid)]
