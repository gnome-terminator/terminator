"""Tests for closing tabs in a Notebook."""

import os
import sys

import gi
import pytest

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")

from terminatorlib.factory import Factory
from terminatorlib.terminator import Terminator


@pytest.fixture
def notebook():
    """Provide a Notebook with three tabs of idle Terminals."""
    terminator = Terminator()
    saved = terminator.terminals, terminator.windows
    terminator.terminals, terminator.windows = [], []

    maker = Factory()
    window = maker.make("Window")
    window.add(maker.make("Terminal"))
    notebook = maker.make("Notebook", window=window)
    for _ in range(2):
        notebook.newtab(widget=maker.make("Terminal"))
    yield notebook

    if not getattr(window, "isDestroyed", False):
        window.on_destroy_event(window)
    terminator.terminals, terminator.windows = saved


def test_closing_a_terminal_removes_its_tab(notebook):
    """Closing a tab's terminal removes the tab from the notebook."""
    closing = notebook.get_nth_page(1)

    notebook.wrapcloseterm(closing)
    assert notebook.get_n_pages() == 2
    assert closing not in notebook.get_children()
