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
    res, (a, b, c), calls = _term(monkeypatch, None, False)
    assert res and calls == [] and a.closed and b.closed
