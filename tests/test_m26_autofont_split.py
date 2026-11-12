"""m26 P1-3: default-size window + one split (either direction) → 100%;
2x2 / 3-way narrow panes still step down (real GTK/VTE, no shells)."""
import pytest

from tests.test_m25_round2_fixes import _pump


@pytest.fixture
def mkwin(monkeypatch):
    from gi.repository import Gtk
    from terminatorlib.terminal import Terminal
    from terminatorlib.terminator import Terminator
    from terminatorlib.factory import Factory
    from terminatorlib.config import Config
    monkeypatch.setattr(Terminal, 'spawn_child', lambda self, *a, **k: True)
    monkeypatch.setattr(Terminator(), 'terminals', [])
    monkeypatch.setattr(Terminator(), 'windows', [])
    cfg = Config()
    old = {k: cfg[k] for k in ('auto_font_scale', 'reading_measure_min_cols',
                               'auto_font_scale_min_rows')}
    cfg['auto_font_scale'] = True
    made = []

    def make(size, splits):
        w = Factory().make('Window')
        t = Factory().make('Terminal')
        targets = []
        w.add(t)
        w.resize(*size)
        w.show_all()
        _pump(0.1)
        for target, vertical in splits:
            # target: index into the terminals as they were BEFORE this
            # call's splits started (stable identities, not tree order)
            term = targets[target] if targets else w.get_terminals()[target]
            term.get_parent().split_axis(term, vertical)
            _pump(0.1)
        w.resize(*size)
        _pump(0.3)
        for term in w.get_terminals():
            term._auto_font_last_change_ms = 0
            term.update_auto_font_scale(force=True)
        made.append(w)
        return w
    yield make
    for k, v in old.items():
        cfg[k] = v
    for w in made:
        w._session_destroy_handled = True
        Gtk.Window.destroy(w)
    _pump()


# split_axis(vertical=True) → VPaned (stacked); False → side by side
@pytest.mark.parametrize('size', [(578, 390), (658, 438), (818, 486)])
@pytest.mark.parametrize('vertical', [True, False])
def test_two_pane_split_stays_full_size(mkwin, size, vertical):
    w = mkwin(size, [(0, vertical)])
    terms = w.get_terminals()
    assert len(terms) == 2
    for t in terms:
        assert t._font_tier == 0, (size, vertical, t.get_allocation().width,
                                   t.get_allocation().height)
        assert t.compute_tier_for_size(t.get_allocated_width(),
                                       t.get_allocated_height()) == 1.0


def _split(term, vertical):
    new = term.get_parent().split_axis(term, vertical)
    _pump(0.1)
    return new


def _settle(w, size):
    w.resize(*size)
    _pump(0.3)
    for term in w.get_terminals():
        term._auto_font_last_change_ms = 0
        term.update_auto_font_scale(force=True)


def test_equal_panes_share_one_tier(mkwin):
    """Hysteresis must not leave equal panes on different font sizes."""
    w = mkwin((658, 438), [])
    a = w.get_terminals()[0]
    _split(a, False)
    a, b = w.get_terminals()
    _split(a, False)
    _split(b, False)
    _settle(w, (658, 438))
    terms = w.get_terminals()
    assert len(terms) == 4
    terms[0]._font_tier = 0
    terms[0].vte.set_font_scale(1.0)
    terms[1]._font_tier = 2
    terms[1].vte.set_font_scale(0.8)
    for t in terms:
        t._auto_font_last_change_ms = 0
        t.update_auto_font_scale(force=True)
    tiers = [t._font_tier for t in terms]
    assert len(set(tiers)) == 1, [(t._font_tier, t.get_allocated_width())
                                  for t in terms]
    assert tiers[0] > 0


def test_four_way_side_by_side_steps_down(mkwin):
    w = mkwin((658, 438), [])
    a = w.get_terminals()[0]
    _split(a, False)
    a, b = w.get_terminals()
    _split(a, False)
    _split(b, False)
    _settle(w, (658, 438))
    terms = w.get_terminals()
    assert len(terms) == 4
    info = [(t._font_tier, t.get_allocated_width()) for t in terms]
    assert all(t._font_tier > 0 for t in terms), info


def test_2x2_grid_steps_down_on_default_window(mkwin):
    w = mkwin((578, 390), [])
    _split(w.get_terminals()[0], False)
    left, right = w.get_terminals()
    _split(left, True)
    _split(right, True)
    _settle(w, (578, 390))
    terms = w.get_terminals()
    assert len(terms) == 4
    for t in terms:
        assert not t._auto_font_keeps_full_size(t.get_allocated_width(),
                                                t.get_allocated_height())
    info = [(t._font_tier, t.get_allocated_width()) for t in terms]
    assert all(t._font_tier > 0 for t in terms), info


def test_tui_font_follows_current_pane_size(mkwin):
    """A fullscreen program used to keep the font from before the resize,
    so a narrow pane stayed at 100% and clipped the TUI."""
    w = mkwin((818, 486), [(0, False)])
    terms = w.get_terminals()
    assert len(terms) == 2
    for t in terms:
        # Stuck at the small tier, as a TUI used to freeze it there.
        t._font_tier = 2
        t.vte.set_font_scale(0.8)
        t._auto_font_last_change_ms = 0
        t.update_auto_font_scale(force=True)
    for t in terms:
        assert t._font_tier == 0, (t._font_tier, t.get_allocation().width,
                                   t.get_allocation().height)
        assert abs(t.vte.get_font_scale() - 1.0) < 1e-6


def test_three_pane_big_pane_keeps_small_panes_step(mkwin):
    """Left half + right half split in two: the half stays 100%, the
    quarters follow the reading measure."""
    w = mkwin((578, 390), [])
    _split(w.get_terminals()[0], False)
    left, right = w.get_terminals()
    _split(right, True)
    _settle(w, (578, 390))
    assert left._font_tier == 0
    for t in w.get_terminals():
        if t is not left:
            assert not t._auto_font_keeps_full_size(
                t.get_allocated_width(), t.get_allocated_height())
