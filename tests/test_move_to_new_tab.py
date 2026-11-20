"""Tests for 'Move to new tab' functionality."""

import os
import sys
import gi

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
gi.require_version("Gtk", "3.0")

import pytest
from gi.repository import Gtk
from terminatorlib.factory import Factory
from terminatorlib.terminator import Terminator


@pytest.fixture(autouse=True)
def clean_terminator():
    """Ensure a clean singleton state for each test."""
    t = Terminator()
    t.terminals = []
    t.windows = []
    yield
    t.terminals = []
    t.windows = []


def test_can_move_to_new_tab_single_terminal():
    """A terminal that is not split cannot be moved to a new tab."""
    Terminator()
    maker = Factory()

    # Case 1: single terminal in a window
    win = maker.make("Window")
    term = maker.make("Terminal")
    win.add(term)

    assert not term.can_move_to_new_tab()
    assert not term.move_to_new_tab()


def test_can_move_to_new_tab_split_terminals():
    """Terminals in a horizontal or vertical split can be moved to a new tab."""
    Terminator()
    maker = Factory()

    win = maker.make("Window")
    term1 = maker.make("Terminal")
    win.add(term1)

    win.split_axis(term1, True)  # Split horizontally
    paned = term1.get_parent()
    term2 = [c for c in paned.get_children() if c != term1][0]

    assert term1.can_move_to_new_tab()
    assert term2.can_move_to_new_tab()


def test_move_to_new_tab_without_existing_notebook():
    """Moving a split terminal creates a Notebook with two tabs."""
    Terminator()
    maker = Factory()

    win = maker.make("Window")
    term1 = maker.make("Terminal")
    win.add(term1)

    # Split horizontally into term1 and term2
    win.split_axis(term1, True)
    paned = term1.get_parent()
    term2 = [c for c in paned.get_children() if c != term1][0]

    assert not win.is_child_notebook()

    # Move term2 to a new tab
    result = term2.move_to_new_tab()
    assert result is True

    # Window now contains a Notebook with 2 tabs
    assert win.is_child_notebook()
    notebook = win.get_child()
    assert notebook.get_n_pages() == 2

    # Tab 0 holds term1 alone (full screen in tab 0)
    assert notebook.get_nth_page(0) == term1
    assert maker.isinstance(term1.get_parent(), "Notebook")

    # Tab 1 holds term2 alone (full screen in tab 1)
    assert notebook.get_nth_page(1) == term2
    assert maker.isinstance(term2.get_parent(), "Notebook")

    # Current page is Tab 1 (term2)
    assert notebook.get_current_page() == 1


def test_move_to_new_tab_with_existing_notebook():
    """Moving a split terminal in a tabbed window adds a tab to the existing Notebook."""
    Terminator()
    maker = Factory()

    win = maker.make("Window")
    term1 = maker.make("Terminal")
    win.add(term1)

    # Add a tab (now 2 tabs)
    win.tab_new()
    notebook = win.get_child()
    assert notebook.get_n_pages() == 2

    # Split term1 in tab 0
    notebook.split_axis(term1, False)  # Split vertically
    paned = term1.get_parent()
    term1_sibling = [c for c in paned.get_children() if c != term1][0]

    # Move term1_sibling to a new tab
    result = term1_sibling.move_to_new_tab()
    assert result is True

    # Now there are 3 tabs
    assert notebook.get_n_pages() == 3

    # Tab 0 has term1 restored to full size
    assert notebook.get_nth_page(0) == term1

    # New tab has term1_sibling alone
    assert notebook.get_nth_page(2) == term1_sibling
    assert notebook.get_current_page() == 2


def test_move_to_new_tab_nested_paneds():
    """Moving one terminal out of nested splits collapses only the affected split."""
    Terminator()
    maker = Factory()

    win = maker.make("Window")
    term1 = maker.make("Terminal")
    win.add(term1)

    # Split 1: horiz
    win.split_axis(term1, True)
    paned1 = term1.get_parent()
    term2 = [c for c in paned1.get_children() if c != term1][0]

    # Split 2: vert on term2
    paned1.split_axis(term2, False)
    paned2 = term2.get_parent()
    term3 = [c for c in paned2.get_children() if c != term2][0]

    # Move term2 to new tab
    result = term2.move_to_new_tab()
    assert result is True

    notebook = win.get_child()
    assert notebook.get_n_pages() == 2

    # Tab 0 still contains paned1 with term1 and term3
    tab0_child = notebook.get_nth_page(0)
    assert maker.isinstance(tab0_child, "Paned")
    assert set(tab0_child.get_children()) == {term1, term3}

    # Tab 1 contains term2 alone
    assert notebook.get_nth_page(1) == term2
