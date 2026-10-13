"""Tests for the new tab button on the tab bar."""

import os
import sys

import gi
import pytest

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")

from terminatorlib.config import Config
from terminatorlib.factory import Factory
from terminatorlib.terminator import Terminator


@pytest.fixture
def config():
    """Provide the config, restoring the option these tests change."""
    config = Config()
    saved = config["new_tab_button"]
    yield config
    config["new_tab_button"] = saved


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


@pytest.mark.parametrize("enabled", [True, False])
def test_new_tab_button_follows_option(config, notebook, enabled):
    """The new tab button is shown only when new_tab_button is set."""
    config["new_tab_button"] = enabled
    notebook.configure()
    notebook.show_all()
    assert notebook.new_tab_button.get_visible() is enabled

    config["new_tab_button"] = not enabled
    notebook.configure()
    assert notebook.new_tab_button.get_visible() is not enabled


def test_new_tab_button_opens_tab_from_focused_terminal(notebook, monkeypatch):
    """Clicking the button opens a tab based on the focused terminal."""
    focused = notebook.get_nth_page(1)
    calls = []
    window = notebook.window
    monkeypatch.setattr(window, "get_focussed_terminal", lambda: focused)
    monkeypatch.setattr(window, "tab_new", calls.append)

    notebook.new_tab_button.clicked()
    assert calls == [focused]


def test_new_tab_button_uses_last_terminal_without_focus(notebook, monkeypatch):
    """Without a focused terminal, the tab's last active terminal is used."""
    current = notebook.get_nth_page(notebook.get_current_page())
    notebook.set_last_active_term(current.uuid)
    calls = []
    window = notebook.window
    monkeypatch.setattr(window, "get_focussed_terminal", lambda: None)
    monkeypatch.setattr(window, "tab_new", calls.append)

    notebook.new_tab_button.clicked()
    assert calls == [current]
