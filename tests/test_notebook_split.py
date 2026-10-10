"""Real-widget tests: splitting / closing inside tabs (M7)."""
import pytest
from gi.repository import Gtk


def _pump():
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)


@pytest.fixture
def win(monkeypatch):
    from terminatorlib.window import Window
    from terminatorlib.terminal import Terminal
    from terminatorlib.terminator import Terminator
    from terminatorlib.factory import Factory
    monkeypatch.setattr(Terminal, 'spawn_child', lambda self, *a, **k: True)
    # Isolate from half-built Terminals other tests leave registered
    monkeypatch.setattr(Terminator(), 'terminals', [])
    monkeypatch.setattr(Terminator(), 'windows', [])
    w = Factory().make('Window')
    t = Factory().make('Terminal')
    w.add(t)
    w.show_all()
    _pump()
    yield w
    for term in list(Terminator().terminals):
        if term.get_toplevel() is w:
            Terminator().deregister_terminal(term)
    w.destroy()
    _pump()


def _nb(w):
    from terminatorlib.notebook import Notebook
    c = w.get_child()
    while c is not None and not isinstance(c, Notebook):
        c = c.get_child() if hasattr(c, 'get_child') else None
    return c


def test_split_inside_tab_creates_paned(win):
    from terminatorlib.paned import Paned
    from terminatorlib.terminal import Terminal
    term = win.get_visible_terminals()
    first = list(term)[0]
    win.tab_new(first)
    _pump()
    nb = _nb(win)
    assert nb is not None and nb.get_n_pages() == 2
    t2 = nb.get_nth_page(1)
    assert isinstance(t2, Terminal)
    nb.split_axis(t2, vertical=False)
    _pump()
    assert nb.get_n_pages() == 2
    page = nb.get_nth_page(1)
    assert isinstance(page, Paned)
    assert t2 in page.get_children()
    assert nb.get_current_page() == 1


def test_notebook_remove_returns_true_and_drops_page(win):
    first = list(win.get_visible_terminals())[0]
    win.tab_new(first)
    _pump()
    nb = _nb(win)
    t2 = nb.get_nth_page(1)
    assert nb.remove(t2) is True
    assert nb.get_n_pages() == 1


def test_closing_last_term_of_tab_collapses_notebook_in_layout(win):
    from terminatorlib.terminator import Terminator
    from terminatorlib.notebook import Notebook
    first = list(win.get_visible_terminals())[0]
    win.tab_new(first)
    _pump()
    nb = _nb(win)
    t2 = nb.get_nth_page(1)
    nb.wrapcloseterm(t2)
    _pump()
    assert not isinstance(win.get_child(), Notebook)
    layout = Terminator().describe_layout(save_cwd=True)
    mine = [v for v in layout.values() if v['type'] == 'Notebook']
    assert mine == [], layout


def test_closing_second_to_last_terminal_does_not_finalize(monkeypatch):
    from terminatorlib import session as sess_mod
    from terminatorlib.terminal import Terminal
    calls = []
    monkeypatch.setattr(sess_mod.SessionManager, 'finalize',
                        lambda self: calls.append(1))

    class FakeT:
        pass
    me = Terminal.__new__(Terminal)
    other = FakeT()

    class Term:
        terminals = [other]          # we were already deregistered
    me.__dict__['terminator'] = Term()

    class Stop(Exception):
        pass

    def boom(*a, **k):
        raise Stop()
    from terminatorlib import terminal as term_mod
    monkeypatch.setattr(term_mod, 'ScrollbackCache', boom)
    try:
        me.close()
    except Exception:
        pass
    assert calls == []
    Term.terminals = []
    try:
        me.close()
    except Exception:
        pass
    assert calls == [1]
