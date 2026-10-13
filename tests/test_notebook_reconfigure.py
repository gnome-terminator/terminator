"""Tests for reconfiguring a Notebook."""

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
    """Provide a Notebook with two tabs of idle Terminals."""
    terminator = Terminator()
    saved = terminator.terminals, terminator.windows
    terminator.terminals, terminator.windows = [], []

    maker = Factory()
    window = maker.make("Window")
    window.add(maker.make("Terminal"))
    notebook = maker.make("Notebook", window=window)
    notebook.newtab(widget=maker.make("Terminal"))
    yield notebook

    if not getattr(window, "isDestroyed", False):
        window.on_destroy_event(window)
    terminator.terminals, terminator.windows = saved


def test_layout_can_be_saved_after_configure(notebook):
    """Applying preferences keeps what describe_layout needs for each tab."""
    notebook.configure()
    layout = Terminator().describe_layout()
    assert [obj["type"] for obj in layout.values()].count("Terminal") == 2
