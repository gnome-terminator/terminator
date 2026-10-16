from gi.repository import Gtk
from terminatorlib import close_confirm


class T:
    def __init__(self, group):
        self.group = group
        self.closed = False

    def close(self):
        self.closed = True

    def emit(self, signal):
        # closegroupedterms closes via the normal close-term path (m25)
        if signal == 'close-term':
            self.close()

    def get_toplevel(self):
        return None


def _term(monkeypatch, response, need):
    from terminatorlib.terminator import Terminator
    calls = []
    monkeypatch.setattr(close_confirm, 'should_confirm_processes',
                        lambda ts: (need, [(1, 'vim')] if need else []))
    monkeypatch.setattr(close_confirm, 'show_process_close_dialog',
                        lambda w, ts, p: calls.append(len(ts)) or response)
    a, b, c = T('g'), T('g'), T('h')
    t = Terminator()
    old = t.terminals
    t.terminals = [a, b, c]
    try:
        res = t.closegroupedterms('g')
    finally:
        t.terminals = old
    return res, (a, b, c), calls


def test_group_close_cancel_keeps_terms(monkeypatch):
    res, (a, b, c), calls = _term(monkeypatch, Gtk.ResponseType.CANCEL, True)
    assert res is False and calls == [2]
    assert not a.closed and not b.closed and not c.closed


def test_group_close_accept(monkeypatch):
    res, (a, b, c), calls = _term(monkeypatch, Gtk.ResponseType.ACCEPT, True)
    assert res and a.closed and b.closed and not c.closed


def test_group_close_idle_no_dialog(monkeypatch):
    # always would open the shell dialog; this case is the no-dialog mode.
    monkeypatch.setattr(close_confirm, '_ask_before_closing',
                        lambda: 'multiple_terminals')
    res, (a, b, c), calls = _term(monkeypatch, None, False)
    assert res and calls == [] and a.closed and b.closed


def _confirm_raises(monkeypatch, gerr):
    """Group is the whole terminal set, so a fall-through would finalize."""
    import terminatorlib.close_confirm as cc
    import terminatorlib.session as session
    import terminatorlib.terminator as tmod
    import terminatorlib.util as util
    import terminatorlib.zoomguard as zg
    from terminatorlib.terminator import Terminator

    fins = []
    zooms = []

    def boom(members):
        raise RuntimeError('dialog failed')

    monkeypatch.setattr(cc, 'confirm_close_terminals', boom)
    monkeypatch.setattr(util, 'gerr', gerr)
    monkeypatch.setattr(session.SessionManager, 'finalize',
                        lambda self: fins.append(1))
    monkeypatch.setattr(zg, 'leave_legacy_zoom_all',
                        lambda *a, **k: zooms.append(1))
    a, b = T('g'), T('g')
    t = Terminator()
    old = t.terminals
    t.terminals = [a, b]
    try:
        res = t.closegroupedterms('g')
    finally:
        t.terminals = old
    return res, a, b, fins, zooms


def test_group_close_confirm_error_returns_false(monkeypatch):
    import terminatorlib.terminator as tmod
    gerr_msgs = []
    monkeypatch.setattr(tmod, 'err', lambda msg: None)
    res, a, b, fins, zooms = _confirm_raises(
        monkeypatch, lambda msg: gerr_msgs.append(msg))
    assert res is False
    assert not a.closed and not b.closed
    assert fins == [] and zooms == []
    assert len(gerr_msgs) == 1
    assert gerr_msgs[0] == 'Could not confirm closing terminals: dialog failed'


def test_group_close_confirm_error_gerr_raises(monkeypatch):
    import terminatorlib.terminator as tmod
    errs = []
    monkeypatch.setattr(tmod, 'err', lambda msg: errs.append(msg))

    def broken(msg):
        raise RuntimeError('gerr failed')

    res, a, b, fins, zooms = _confirm_raises(monkeypatch, broken)
    assert res is False
    assert not a.closed and not b.closed
    assert fins == [] and zooms == []
    assert len(errs) == 1
    assert 'dialog failed' in errs[0]
    assert 'gerr failed' not in errs[0]
