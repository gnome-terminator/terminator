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


def test_left_tab_list_fills_the_window_height(win):
    """The list is a sibling of the notebook, so it gets the full height."""
    from gi.repository import Gtk
    from terminatorlib.notebook import Notebook
    first = list(win.get_visible_terminals())[0]
    win.resize(900, 700)
    win.tab_new(first)
    _pump()
    nb = win.get_child()
    assert isinstance(nb, Notebook)
    assert Gtk.Window.get_child(win) is not nb
    assert nb.get_parent() is Gtk.Window.get_child(win)
    assert not nb.get_show_tabs()
    side = nb._tab_sidebar
    assert side.get_visible()
    assert side.get_allocated_height() >= nb.get_allocated_height() - 2
    assert nb._tab_tree_scroll.get_allocated_height() > nb.get_allocated_height() * 0.7


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
                        lambda self, closing=None: calls.append(1))

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


def _three_page_notebook(win):
    first = list(win.get_visible_terminals())[0]
    win.tab_new(first)
    _pump()
    win.tab_new(first)
    _pump()
    nb = _nb(win)
    assert nb is not None and nb.get_n_pages() == 3
    return nb, first


def _split_without_draining_idle(nb, original):
    """split_axis queues focus on idle. Leave that source unrun."""
    page = nb.page_num(original)
    assert page >= 0
    nb.split_axis(original, vertical=True)
    paned = nb.get_nth_page(page)
    survivor = [child for child in paned.get_children()
                if child is not None and child is not original][0]
    return survivor


def test_promote_original_pane_closes_without_focus_in(win, monkeypatch):
    from terminatorlib.terminal import Terminal
    monkeypatch.setattr(Terminal, 'on_vte_focus_in', lambda *a, **k: None)
    old_ask = win.config['ask_before_closing']
    win.config['ask_before_closing'] = 'never'
    try:
        nb, original = _three_page_notebook(win)
        survivor = _split_without_draining_idle(nb, original)
        assert nb._promote_terminal(nb, original, 0) is True
        assert nb.page_num(survivor) >= 0
        assert nb.last_active_term[survivor] is survivor.uuid
        before = nb.get_n_pages()
        label = nb.get_tab_label(survivor)
        nb.closetab(label, label)
        assert nb.get_n_pages() == before - 1
        assert all(nb.get_nth_page(i) is not survivor
                   for i in range(nb.get_n_pages()))
    finally:
        win.config['ask_before_closing'] = old_ask


def test_promote_original_pane_close_after_focus_in(win):
    old_ask = win.config['ask_before_closing']
    win.config['ask_before_closing'] = 'never'
    try:
        nb, original = _three_page_notebook(win)
        survivor = _split_without_draining_idle(nb, original)
        assert nb._promote_terminal(nb, original, 0) is True
        survivor.on_vte_focus_in(None, None)
        assert nb.page_num(survivor) >= 0
        before = nb.get_n_pages()
        label = nb.get_tab_label(survivor)
        nb.closetab(label, label)
        assert nb.get_n_pages() == before - 1
        assert survivor not in nb.last_active_term
    finally:
        win.config['ask_before_closing'] = old_ask


def _scroll(nb, direction, dx=0.0, dy=0.0):
    from gi.repository import Gdk
    event = Gdk.Event.new(Gdk.EventType.SCROLL)
    event.direction = direction
    event.delta_x = dx
    event.delta_y = dy
    return nb.on_scroll_event(nb, event)


def test_tab_strip_window_selects_smooth_scroll(win):
    from gi.repository import Gdk
    first = list(win.get_visible_terminals())[0]
    win.tab_new(first)
    _pump()
    nb = _nb(win)
    previous = nb.config['tab_position']
    nb.config['tab_position'] = 'top'
    try:
        nb.configure()
        win.resize(800, 600)
        _pump()
        mask = nb.get_window().get_events()
        assert mask & Gdk.EventMask.SCROLL_MASK
        assert mask & Gdk.EventMask.SMOOTH_SCROLL_MASK
    finally:
        nb.config['tab_position'] = previous


def test_smooth_scroll_vertical_on_top_switches_one_page(win, monkeypatch):
    from gi.repository import Gdk
    nb, _original = _three_page_notebook(win)
    monkeypatch.setattr(Gtk, 'get_event_widget', lambda _event: nb)
    for pos in (Gtk.PositionType.TOP, Gtk.PositionType.BOTTOM):
        nb.set_tab_pos(pos)
        nb.set_current_page(1)
        nb._scroll_acc = 0.0
        assert _scroll(nb, Gdk.ScrollDirection.SMOOTH, 0.0, 1.0) is True
        assert nb.get_current_page() == 2
        assert _scroll(nb, Gdk.ScrollDirection.SMOOTH, 0.0, -1.0) is True
        assert nb.get_current_page() == 1


def test_smooth_scroll_accumulates_on_the_right(win, monkeypatch):
    from gi.repository import Gdk
    nb, _original = _three_page_notebook(win)
    monkeypatch.setattr(Gtk, 'get_event_widget', lambda _event: nb)
    nb.set_tab_pos(Gtk.PositionType.RIGHT)
    nb.set_current_page(0)
    nb._scroll_acc = 0.0
    assert _scroll(nb, Gdk.ScrollDirection.SMOOTH, 0.0, 0.4) is True
    assert _scroll(nb, Gdk.ScrollDirection.SMOOTH, 0.0, 0.4) is True
    assert nb.get_current_page() == 0
    assert _scroll(nb, Gdk.ScrollDirection.SMOOTH, 0.0, 0.4) is True
    assert nb.get_current_page() == 1
    assert _scroll(nb, Gdk.ScrollDirection.SMOOTH, 0.0, -0.4) is True
    assert nb.get_current_page() == 1


def test_discrete_down_is_next_on_every_edge(win, monkeypatch):
    from gi.repository import Gdk
    nb, _original = _three_page_notebook(win)
    monkeypatch.setattr(Gtk, 'get_event_widget', lambda _event: nb)
    for pos in (Gtk.PositionType.TOP, Gtk.PositionType.BOTTOM,
                Gtk.PositionType.LEFT, Gtk.PositionType.RIGHT):
        nb.set_tab_pos(pos)
        nb.set_current_page(0)
        assert _scroll(nb, Gdk.ScrollDirection.DOWN) is True
        assert nb.get_current_page() == 1


def test_collapse_inner_first_slot_keeps_outer_order(win):
    first = win.get_child()
    win.split_axis(first, vertical=False)
    outer = win.get_child()
    outer.split_axis(outer.get_child1(), vertical=True)
    inner = outer.get_child1()
    saved_second = outer.get_child2()
    survivor = inner.get_child2()
    inner.wrapcloseterm(inner.get_child1())
    assert outer.get_child1() is survivor
    assert outer.get_child2() is saved_second
    assert list(outer.children) == [outer.get_child1(), outer.get_child2()]


def test_collapse_inner_second_slot_keeps_outer_order(win):
    first = win.get_child()
    win.split_axis(first, vertical=False)
    outer = win.get_child()
    outer.split_axis(outer.get_child2(), vertical=True)
    inner = outer.get_child2()
    saved_first = outer.get_child1()
    survivor = inner.get_child2()
    inner.wrapcloseterm(inner.get_child1())
    assert outer.get_child1() is saved_first
    assert outer.get_child2() is survivor
    assert list(outer.children) == [saved_first, survivor]
