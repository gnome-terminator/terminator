"""M23: UI review fixes (overlay maximise robustness, timers, signal table,
prefs debounce, altscreen throttling, titlebar button colour)."""
import time

import pytest
from gi.repository import Gtk, GLib


def _pump(seconds=0.0):
    end = time.monotonic() + seconds
    while True:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        if time.monotonic() >= end:
            break
        time.sleep(0.01)


@pytest.fixture
def win(monkeypatch):
    from terminatorlib.terminal import Terminal
    from terminatorlib.terminator import Terminator
    from terminatorlib.factory import Factory
    monkeypatch.setattr(Terminal, 'spawn_child', lambda self, *a, **k: True)
    monkeypatch.setattr(Terminator(), 'terminals', [])
    monkeypatch.setattr(Terminator(), 'windows', [])
    w = Factory().make('Window')
    t = Factory().make('Terminal')
    w.add(t)
    w.resize(1000, 700)
    w.show_all()
    _pump(0.2)
    yield w
    for term in list(Terminator().terminals):
        if term.get_toplevel() is w:
            Terminator().deregister_terminal(term)
    if not getattr(w, 'isDestroyed', False):
        w.destroy()
    _pump()


def _three_panes(win):
    """[a | [t1 / t2]] like rev-ui-exp/exp1.py."""
    a = list(win.get_terminals())[0]
    win.split_axis(a, True)
    _pump(0.1)
    t1 = [t for t in win.get_terminals() if t is not a][0]
    t1.get_parent().split_axis(t1, False)
    _pump(0.2)
    t2 = [t for t in win.get_terminals() if t not in (a, t1)][0]
    return a, t1, t2


def _close(term):
    term.emit('close-term')
    _pump(0.1)


def _layout_terms(win):
    from terminatorlib.terminator import Terminator
    lay = Terminator().describe_layout(save_cwd=False)
    return sum(1 for v in lay.values() if v.get('type') == 'Terminal')


def _assert_plain_tree(win, expected):
    from terminatorlib.factory import Factory
    child = Gtk.Window.get_child(win)
    assert not isinstance(child, Gtk.Overlay)
    terms = win.get_terminals()
    assert len(terms) == expected
    for t in terms:
        assert t.get_toplevel() is win
        assert Factory().isinstance(t.get_parent(), 'Container') or \
            t.get_parent() is win


# ---- P0-1 ----------------------------------------------------------------

def test_p0_sibling_exit_three_panes_keeps_terminals(win):
    a, t1, t2 = _three_panes(win)
    assert win.overlay_maximise(t1, animate=False)
    _close(a)
    _assert_plain_tree(win, 2)
    assert t1 in win.get_terminals() and t2 in win.get_terminals()
    assert _layout_terms(win) == 2
    # closing more must not crash (was: 'HPaned' has no is_child_notebook)
    _close(t2)
    _assert_plain_tree(win, 1)


def test_p0_sibling_exit_two_panes(win):
    a = list(win.get_terminals())[0]
    win.split_axis(a, True)
    _pump(0.2)
    t1 = [t for t in win.get_terminals() if t is not a][0]
    assert win.overlay_maximise(t1, animate=False)
    _close(a)
    _assert_plain_tree(win, 1)
    assert Gtk.Window.get_child(win) is t1
    assert _layout_terms(win) == 1


def test_p0_root_replaced_under_overlay_without_guard(win, monkeypatch):
    """Fallback (a): even if the structural change happens under the
    Overlay, data['main'] follows Window.add/remove and restore uses the
    Overlay's real child."""
    from terminatorlib import paned
    monkeypatch.setattr(paned, '_restore_overlay_before_collapse',
                        lambda *a: False)
    a, t1, t2 = _three_panes(win)
    assert win.overlay_maximise(t1, animate=False)
    _close(a)
    assert win.is_overlay_maximised()
    assert len(win.get_terminals()) == 2
    assert _layout_terms(win) == 2
    root = win.get_child()
    assert root is Gtk.Bin.get_child(win._overlay.data['overlay'])
    assert win._overlay.data['main'] is root
    win.overlay_restore(animate=False)
    _assert_plain_tree(win, 2)
    assert Gtk.Window.get_child(win) is root
    assert t1.get_mapped()


def test_p0_two_panes_without_guard_placeholder_root(win, monkeypatch):
    from terminatorlib import paned
    monkeypatch.setattr(paned, '_restore_overlay_before_collapse',
                        lambda *a: False)
    a = list(win.get_terminals())[0]
    win.split_axis(a, True)
    _pump(0.2)
    t1 = [t for t in win.get_terminals() if t is not a][0]
    assert win.overlay_maximise(t1, animate=False)
    _close(a)
    assert win.get_terminals() == [t1]
    win.overlay_restore(animate=False)
    _assert_plain_tree(win, 1)
    assert Gtk.Window.get_child(win) is t1


def test_p0_unrelated_paned_collapse_keeps_maximise(win):
    """[[a / b] | t1]: closing b collapses a non-ancestor Paned only."""
    a = list(win.get_terminals())[0]
    win.split_axis(a, False)
    _pump(0.1)
    t1 = [t for t in win.get_terminals() if t is not a][0]
    a.get_parent().split_axis(a, True)
    _pump(0.2)
    b = [t for t in win.get_terminals() if t not in (a, t1)][0]
    assert win.overlay_maximise(t1, animate=False)
    _close(b)
    assert win.is_overlay_maximised() and win.is_maximised_pane(t1)
    assert len(win.get_terminals()) == 2
    win.overlay_restore(animate=False)
    _assert_plain_tree(win, 2)


def test_p0_notebook_collapse_under_overlay(win):
    """Last other tab closes → Notebook.hoover → Window.replace while
    maximised."""
    from terminatorlib.notebook import Notebook
    first = list(win.get_terminals())[0]
    win.tab_new(first)
    _pump(0.2)
    nb = win.get_child()
    assert isinstance(nb, Notebook)
    t2 = nb.get_nth_page(1)
    nb.set_current_page(0)
    _pump(0.1)
    nb.split_axis(first, True)
    _pump(0.2)
    nb.set_current_page(0)
    _pump(0.1)
    sib = [t for t in win.get_visible_terminals() if t is not first][0]
    assert win.overlay_maximise(first, animate=False)
    nb.wrapcloseterm(t2)
    _pump(0.2)
    assert not isinstance(win.get_child(), Notebook)
    assert set(win.get_terminals()) == {first, sib}
    if win.is_overlay_maximised():
        win.overlay_restore(animate=False)
    _assert_plain_tree(win, 2)


# ---- P1-1 / P1-2 ---------------------------------------------------------

def test_p1_frame_shrinks_with_window(win):
    a = list(win.get_terminals())[0]
    win.split_axis(a, True)
    _pump(0.2)
    t1 = [t for t in win.get_terminals() if t is not a][0]
    assert win.overlay_maximise(t1, animate=False)
    _pump(0.2)
    win.resize(500, 400)
    _pump(0.5)
    w, h = win.get_size()
    frame = win._overlay.data['frame']
    alloc = frame.get_allocation()
    m = win._overlay.MARGIN
    assert alloc.width <= w - 2 * m + 1, (alloc.width, w)
    assert alloc.height <= h - 2 * m + 1, (alloc.height, h)
    assert frame.get_size_request() == (-1, -1)
    assert (frame.get_margin_start(), frame.get_margin_end(),
            frame.get_margin_top(), frame.get_margin_bottom()) == (m, m, m, m)
    dst = win._overlay.data['dst_rect']
    assert abs(dst[2] - (alloc.width)) <= 2


def test_p1_maximise_when_ready_waits_for_allocation(monkeypatch):
    from terminatorlib.terminal import Terminal
    from terminatorlib.terminator import Terminator
    from terminatorlib.factory import Factory
    monkeypatch.setattr(Terminal, 'spawn_child', lambda self, *a, **k: True)
    monkeypatch.setattr(Terminator(), 'terminals', [])
    monkeypatch.setattr(Terminator(), 'windows', [])
    w = Factory().make('Window')
    a = Factory().make('Terminal')
    w.add(a)
    w.split_axis(a, True)
    t1 = [t for t in w.get_terminals() if t is not a][0]
    w.resize(900, 600)
    w._ensure_overlay().maximise_when_ready(t1)
    _pump(0.1)
    assert not w.is_overlay_maximised()      # not mapped yet: deferred
    w.show_all()
    _pump(0.5)
    try:
        assert w.is_maximised_pane(t1)
        frame = w._overlay.data['frame']
        m = w._overlay.MARGIN
        assert (frame.get_margin_start(), frame.get_margin_end(),
                frame.get_margin_top(), frame.get_margin_bottom()) == \
            (m, m, m, m)
    finally:
        w.overlay_restore(animate=False)
        for term in list(Terminator().terminals):
            Terminator().deregister_terminal(term)
        w.destroy()
        _pump()


def test_p1_maximise_when_ready_skips_background_tab(win):
    from terminatorlib.notebook import Notebook
    first = list(win.get_terminals())[0]
    win.tab_new(first)
    _pump(0.2)
    nb = win.get_child()
    assert isinstance(nb, Notebook)
    t2 = nb.get_nth_page(1)
    nb.split_axis(t2, True)
    _pump(0.2)
    nb.set_current_page(0)
    _pump(0.2)
    win._ensure_overlay().maximise_when_ready(t2)
    _pump(0.3)
    assert not win.is_overlay_maximised()


# ---- P2 ------------------------------------------------------------------

def test_p2_destroy_during_animation_cancels_tick(win, monkeypatch):
    from terminatorlib import paneoverlay
    a = list(win.get_terminals())[0]
    win.split_axis(a, True)
    _pump(0.3)
    t1 = [t for t in win.get_terminals() if t is not a][0]
    monkeypatch.setattr(paneoverlay, 'should_reduce_motion', lambda c=None: True)
    assert win.overlay_maximise(t1, animate=True)
    anim = win._overlay._animator
    assert anim is not None and anim.running
    emitted = []
    win.connect('pane-maximise-changed', lambda *a: emitted.append(a))
    win.emit('destroy')
    assert not anim.running and anim._source is None
    assert win._overlay.data is None


def test_p2_terminal_close_cancels_autofont_sources(monkeypatch):
    from terminatorlib import terminal as term_mod
    from terminatorlib.terminal import Terminal
    removed = []
    monkeypatch.setattr(term_mod.GLib, 'source_remove',
                        lambda sid: removed.append(sid))
    t = Terminal.__new__(Terminal)
    t.__dict__.update({'_cwd_probe_timer': 1, '_auto_font_timer': 2,
                       '_autofont_toast_timer': 3,
                       '_base_cell_probe_idle': 4})

    class Term:
        terminals = [object()]
    t.__dict__['terminator'] = Term()

    class Stop(Exception):
        pass

    def boom(*a, **k):
        raise Stop()
    monkeypatch.setattr(term_mod, 'ScrollbackCache', boom)
    try:
        t.close()
    except Exception:
        pass
    assert sorted(removed) == [1, 2, 3, 4]
    assert t._auto_font_timer is None and t._autofont_toast_timer is None
    assert t._base_cell_probe_idle is None and t._cwd_probe_timer is None


def test_p2_signal_tables_share_helper(win):
    import inspect
    from terminatorlib import paned, notebook, window
    from terminatorlib.container import window_terminal_signals
    for mod in (paned, notebook, window):
        src = inspect.getsource(mod)
        assert "'group-all-toggle': top_window" not in src
        assert "'group-all-toggle': self.group_all_toggle" not in src
    t = list(win.get_terminals())[0]
    base = set(window_terminal_signals(win, t))
    root = win.terminal_signals(t, overlay=False)
    ov = win.terminal_signals(t, overlay=True)
    assert 'zoom' not in root and 'maximise' not in root
    assert 'zoom' in ov and 'maximise' in ov
    assert base - {'zoom', 'maximise'} <= set(root)


def test_p2_overlay_maximise_signal_restores(win):
    a = list(win.get_terminals())[0]
    win.split_axis(a, True)
    _pump(0.2)
    t1 = [t for t in win.get_terminals() if t is not a][0]
    assert win.overlay_maximise(t1, animate=False)
    t1.emit('maximise')            # was silently dropped while maximised
    _pump(0.4)
    assert not win.is_overlay_maximised()
    _assert_plain_tree(win, 2)


def test_p2_paned_new_size_marks_dirty_only_on_change(win, monkeypatch):
    from terminatorlib import session
    marks = []
    monkeypatch.setattr(session, 'try_mark_dirty',
                        lambda reason='': marks.append(reason))
    a = list(win.get_terminals())[0]
    win.split_axis(a, True)
    _pump(0.3)
    p = a.get_parent()
    del marks[:]
    p.new_size(a, a.get_allocation())
    p.new_size(a, a.get_allocation())
    p.new_size(a, a.get_allocation())
    assert marks.count('paned.new_size') <= 1
    del marks[:]
    p.set_position(p.get_position() - 40)
    p.new_size(a, a.get_allocation())
    assert marks.count('paned.new_size') == 1


def test_p2_altscreen_latched_polls_slowly(monkeypatch):
    from terminatorlib import altscreen
    added = []
    monkeypatch.setattr(altscreen.GLib, 'timeout_add',
                        lambda ms, cb: added.append(ms) or len(added))
    ctl = altscreen.AltScreenScrollbar.__new__(altscreen.AltScreenScrollbar)
    ctl.detector = altscreen.AltScreenDetector(clock=lambda: 10.0)
    ctl.auto_hidden = False
    ctl._timer = None
    ctl.detached = False
    ctl._adj = None
    ctl.detector.active = True
    ctl._on_contents()
    assert added == [altscreen.LATCHED_POLL_MS]
    ctl._timer = None
    ctl.detector.active = False
    ctl.detector.episode_start = 8.0      # grace (1 s) long gone
    ctl._on_contents()
    assert added[-1] == altscreen.LATCHED_POLL_MS
    ctl._timer = None
    ctl.detector.episode_start = 9.5      # still inside grace: fast
    ctl._on_contents()
    assert added[-1] == altscreen.DEBOUNCE_MS


def test_p2_autofont_toast_only_focused(monkeypatch):
    from terminatorlib.terminal import Terminal
    shown = []

    class V(object):
        def __init__(self, focus):
            self.focus = focus

        def has_focus(self):
            return self.focus

        def set_font_scale(self, s):
            pass

    def mk(focus, last=None):
        t = Terminal.__new__(Terminal)
        t.__dict__.update({'vte': V(focus), 'config': {
            'auto_font_scale_show_badge': True}, '_font_tier': 0,
            '_auto_font_last_change_ms': 0})

        class TT(object):
            last_focused_term = None
        t.__dict__['terminator'] = TT()
        t.__dict__['_auto_font_load_params'] = lambda: (
            [1.0, 0.9, 0.8], 60, 10, 2, 80)
        t.__dict__['refresh_badge'] = lambda: None
        t.__dict__['show_center_toast'] = lambda txt: shown.append(t)
        return t
    focused, other = mk(True), mk(False)
    focused.apply_tier(1, reason='update', toast=True)
    other.apply_tier(1, reason='update', toast=True)
    assert shown == [focused]
    other.terminator.last_focused_term = other   # window unfocused
    other.apply_tier(2, reason='update', toast=True)
    assert shown == [focused, other]


def test_p2_toast_css_provider_singleton():
    from terminatorlib import terminal as term_mod
    assert term_mod._autofont_toast_css() is term_mod._autofont_toast_css()


def test_p2_titlebar_buttons_follow_fg(win):
    from terminatorlib.titlebar import _BTN_FG_PROVIDERS
    t = list(win.get_terminals())[0]
    tb = t.titlebar
    tb._set_button_fg('#101010')
    ctx = tb.btn_close.get_style_context()
    color = ctx.get_color(Gtk.StateFlags.NORMAL)
    assert (round(color.red * 255), round(color.green * 255),
            round(color.blue * 255)) == (16, 16, 16)
    tb._set_button_fg('#e6edf3')
    color = ctx.get_color(Gtk.StateFlags.NORMAL)
    assert round(color.red * 255) == 0xe6
    assert '#101010' in _BTN_FG_PROVIDERS


def test_p2_prefs_spin_debounced(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    from terminatorlib import terminal, prefseditor
    from terminatorlib.config import Config
    term = terminal.Terminal()
    pe = prefseditor.PrefsEditor(term=term)
    cfg = Config()
    old = {k: cfg[k] for k in ('reading_measure_min_cols',
                                'pane_animation_expand_ms')}
    try:
        _prefs_spin_body(pe, cfg, prefseditor, monkeypatch)
    finally:
        for k, v in old.items():
            cfg[k] = v


def _prefs_spin_body(pe, cfg, prefseditor, monkeypatch):
    saves = []
    monkeypatch.setattr(type(cfg), 'save', lambda self: saves.append(1))
    notified = []
    monkeypatch.setattr(prefseditor.PrefsEditor, '_notify_auto_font_terminals',
                        staticmethod(lambda: notified.append(1)))
    spin = pe.builder.get_object('reading_measure_spinbutton')
    for v in range(61, 71):
        spin.set_value(v)
    assert cfg['reading_measure_min_cols'] == 70
    assert saves == [] and notified == []
    _pump(0.5)
    assert saves == [1] and notified == [1]
    pe.builder.get_object('pane_anim_expand_spinbutton').set_value(321)
    assert saves == [1]
    pe.window.destroy()                   # closing flushes the pending save
    _pump()
    assert saves == [1, 1] and cfg['pane_animation_expand_ms'] == 321


def test_p2_dim_click_guard_uses_monotonic():
    import inspect
    from terminatorlib import paneoverlay
    src = inspect.getsource(paneoverlay.OverlayController)
    assert 'time.time()' not in src


def test_p2_tier_rect_subtracts_chrome():
    from terminatorlib.paneoverlay import vte_size_for_rect

    class W(object):
        def __init__(self, w, h):
            self.w, self.h = w, h

        def get_allocated_width(self):
            return self.w

        def get_allocated_height(self):
            return self.h

    class T(W):
        altscreen = None
    t = T(500, 400)
    t.vte = W(485, 376)          # 15 px scrollbar, 24 px titlebar
    assert vte_size_for_rect(t, (0, 0, 1000, 700)) == (985, 676)
    assert vte_size_for_rect(t, (0, 0, 1000, 700), 8) == (977, 668)
