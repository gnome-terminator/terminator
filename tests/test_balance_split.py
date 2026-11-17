"""Splits divide panes evenly.

TX-10.1 same-direction splits are even, by the drawn divider width.
TX-10.2 layout building keeps the saved ratios.
TX-10.3 balance_on_split off halves only the split pane.
TX-10.4 balance_panes evens every split in the tab.
"""

import time

import pytest
from gi.repository import Gtk

from terminatorlib.paned import even_sizes


def _pump(seconds=0.0):
    end = time.monotonic() + seconds
    while True:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        if time.monotonic() >= end:
            break
        time.sleep(0.01)


@pytest.fixture
def window(monkeypatch):
    from terminatorlib.config import Config
    from terminatorlib.factory import Factory
    from terminatorlib.terminal import Terminal
    from terminatorlib.terminator import Terminator
    monkeypatch.setattr(Terminal, 'spawn_child', lambda self, *a, **k: True)
    monkeypatch.setattr(Terminator(), 'terminals', [])
    monkeypatch.setattr(Terminator(), 'windows', [])
    monkeypatch.setattr(Terminator(), 'doing_layout', False)
    config = Config()
    previous = config['balance_on_split']
    win = Factory().make('Window')
    win.add(Factory().make('Terminal'))
    win.resize(1000, 700)
    win.show_all()
    _pump(0.1)
    yield win
    config['balance_on_split'] = previous
    for term in list(Terminator().terminals):
        try:
            Terminator().terminals.remove(term)
        except ValueError:
            pass
    win._session_destroy_handled = True
    Gtk.Window.destroy(win)
    _pump()


def _split_side_by_side(win, term):
    """Divider is vertical: the panes sit left and right."""
    from terminatorlib.util import logical_parent
    logical_parent(term).split_vert(term)
    _pump(0.2)
    return win.get_terminals()[-1]


def _widths(terms):
    return [t.get_allocated_width() for t in terms]


def test_even_sizes_spreads_the_remainder():
    assert even_sizes(1000, 3) == [334, 333, 333]
    assert sum(even_sizes(997, 4)) == 997
    assert even_sizes(-4, 2) == [0, 0]


def test_tx_10_1_handle_size_is_the_drawn_divider(window):
    from terminatorlib.util import logical_parent
    first = window.get_terminals()[0]
    second = _split_side_by_side(window, first)
    paned = logical_parent(first)
    gap = (paned.get_length() - first.get_allocated_width() -
           second.get_allocated_width())
    assert paned.get_handlesize() == gap


def test_tx_10_1_two_splits_in_a_row_give_thirds(window):
    first = window.get_terminals()[0]
    second = _split_side_by_side(window, first)
    _split_side_by_side(window, second)
    widths = _widths(window.get_terminals())
    assert len(widths) == 3
    assert max(widths) - min(widths) <= 1, widths


def test_tx_10_1_other_direction_keeps_its_size(window):
    from terminatorlib.util import logical_parent
    left = window.get_terminals()[0]
    right = _split_side_by_side(window, left)
    before = left.get_allocated_width()
    logical_parent(right).split_horiz(right)
    _pump(0.2)
    assert abs(left.get_allocated_width() - before) <= 1
    stacked = [t for t in window.get_terminals() if t is not left]
    heights = [t.get_allocated_height() for t in stacked]
    assert max(heights) - min(heights) <= 1, heights


def test_tx_10_2_layout_building_keeps_the_halving(window, monkeypatch):
    from terminatorlib.terminator import Terminator
    first = window.get_terminals()[0]
    second = _split_side_by_side(window, first)
    monkeypatch.setattr(Terminator(), 'doing_layout', True)
    _split_side_by_side(window, second)
    widths = _widths(window.get_terminals())
    assert widths[0] > widths[1] + 100, widths


def test_tx_10_3_off_halves_only_the_split_pane(window):
    from terminatorlib.config import Config
    Config()['balance_on_split'] = False
    first = window.get_terminals()[0]
    second = _split_side_by_side(window, first)
    _split_side_by_side(window, second)
    widths = _widths(window.get_terminals())
    assert widths[0] > widths[1] + 100, widths
    assert abs(widths[1] - widths[2]) <= 1, widths


def test_tx_10_4_balance_panes_evens_every_split(window):
    from terminatorlib.config import Config
    from terminatorlib.util import logical_parent
    Config()['balance_on_split'] = False
    left = window.get_terminals()[0]
    middle = _split_side_by_side(window, left)
    right = _split_side_by_side(window, middle)
    logical_parent(right).split_horiz(right)
    _pump(0.2)
    lower = window.get_terminals()[-1]
    paned = logical_parent(lower)
    paned.set_position(paned.get_position() // 3)
    _pump(0.2)

    left.key_balance_panes()
    _pump(0.2)

    widths = _widths([left, middle, right])
    assert max(widths) - min(widths) <= 1, widths
    heights = [right.get_allocated_height(), lower.get_allocated_height()]
    assert abs(heights[0] - heights[1]) <= 1, heights


def test_tx_10_4_balance_panes_has_a_default_binding():
    from terminatorlib.config import DEFAULTS
    from terminatorlib.prefseditor import PrefsEditor
    assert DEFAULTS['keybindings']['balance_panes'] == '<Shift><Control>b'
    assert 'balance_panes' in PrefsEditor.keybindingnames
    assert DEFAULTS['global_config']['balance_on_split'] is True
