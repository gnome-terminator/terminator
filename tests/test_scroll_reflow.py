# 回归：回滚顶满后列数变少，视口保持离最新一行的距离。
"""A full scrollback must not jump to the oldest line when the grid narrows.

VTE 0.68 reflows a ring that is already at its cap onto the top row. The
history is still there. The terminal puts back the same distance from the
bottom. A scroll the user asked for still goes to the top.
"""

from gi.repository import GLib, Gtk

from terminatorlib.altscreen import scroll_value_after_reflow
from terminatorlib.terminal import Terminal


def test_reflow_to_top_keeps_distance_from_bottom():
    # Cap-full ring, mid viewport, columns changed, value lands on the top.
    assert scroll_value_after_reflow(
        60, 0, 500, 24, 0, 0, 500, 24, True) == 60


def test_reflow_keeps_the_gap_when_the_page_grows():
    # 10 rows above the bottom, then the page grows by 6.
    assert scroll_value_after_reflow(
        466, 0, 500, 24, 0, 0, 500, 30, True) == 460


def test_reflow_from_the_bottom_stays_at_the_bottom():
    assert scroll_value_after_reflow(
        476, 0, 500, 24, 0, 0, 500, 24, True) == 476


def test_user_scroll_to_the_top_is_not_rewritten():
    assert scroll_value_after_reflow(
        60, 0, 500, 24, 0, 0, 500, 24, False) is None


def test_reflow_that_kept_an_offset_is_not_rewritten():
    # Ring not at the cap: VTE moves 60 to 100 and that value stays.
    assert scroll_value_after_reflow(
        60, 0, 163, 24, 100, 0, 180, 24, True) is None


def test_already_at_the_top_stays_there():
    assert scroll_value_after_reflow(
        0, 0, 500, 24, 0, 0, 500, 24, True) is None


def test_collapsed_range_is_not_rewritten():
    # Alternate screen, or ESC[3J, pulls the range down to one page.
    assert scroll_value_after_reflow(
        200, 0, 500, 24, 0, 0, 24, 24, True) is None


def test_cleared_history_is_not_rewritten():
    assert scroll_value_after_reflow(
        60, 0, 500, 24, 0, 0, 80, 24, True) is None


def test_top_follows_a_nonzero_lower():
    # Dropped lines move the ring's origin. The top is `lower`, not 0.
    assert scroll_value_after_reflow(
        10060, 10000, 10500, 24, 10000, 10000, 10500, 24, True) == 10060


def _pump(ms):
    end = GLib.get_monotonic_time() + ms * 1000
    while GLib.get_monotonic_time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        GLib.usleep(2000)


def _gap(adj):
    return (adj.get_upper() - adj.get_page_size()) - adj.get_value()


def test_full_scrollback_keeps_its_place_when_the_pane_narrows():
    term = Terminal()
    term._auto_font_disabled = True
    term._cancel_auto_font_timer()
    term.vte.set_scrollback_lines(500)
    win = Gtk.Window()
    win.set_default_size(1200, 640)
    win.set_focus_on_map(False)
    paned = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
    paned.pack1(term, True, False)
    paned.pack2(Gtk.Box(), True, False)
    win.add(paned)
    try:
        win.show_all()
        _pump(80)
        paned.set_position(980)
        _pump(80)
        # Long lines wrap, and a narrower grid wraps them again. Enough of
        # them fill the default 500-line ring.
        term.vte.feed((('word ' * 36) + '\n').encode() * 400)
        _pump(250)
        adj = term.vte.get_vadjustment()
        assert adj.get_upper() >= 400, adj.get_upper()
        adj.set_value(60)
        _pump(80)
        assert abs(adj.get_value() - 60) < 1
        gap = _gap(adj)
        cols = term.vte.get_column_count()
        paned.set_position(420)
        _pump(250)
        assert term.vte.get_column_count() != cols
        assert adj.get_upper() >= 400
        assert adj.get_value() > adj.get_lower() + 1
        assert abs(_gap(adj) - gap) < 1.5
        # The column count has settled. A scroll to the top stays there.
        adj.set_value(adj.get_lower())
        _pump(80)
        assert adj.get_value() <= adj.get_lower() + 0.5
    finally:
        for attr in ('_scroll_restore_idle', '_scroll_settle_timer',
                     '_auto_font_timer'):
            sid = getattr(term, attr, None)
            if sid:
                GLib.source_remove(sid)
                setattr(term, attr, None)
        win.destroy()
        try:
            term.terminator.deregister_terminal(term)
        except ValueError:
            pass
        _pump(30)
