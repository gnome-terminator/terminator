"""Tests for the always_show_tabbar option."""

import os
import sys
import uuid

import gi
import pytest

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")

from gi.repository import Gtk

from terminatorlib.config import Config
from terminatorlib.factory import Factory
from terminatorlib.terminator import Terminator


@pytest.fixture
def config():
    """Provide the config, restoring the option these tests change."""
    config = Config()
    saved = config["always_show_tabbar"]
    yield config
    config["always_show_tabbar"] = saved


@pytest.fixture
def terminator():
    """Isolate the Terminator singleton from objects left by other tests."""
    terminator = Terminator()
    saved = terminator.terminals, terminator.windows
    terminator.terminals, terminator.windows = [], []
    yield terminator
    terminator.terminals, terminator.windows = saved


@pytest.fixture
def window(terminator):
    """Provide a Window holding a single Terminal that has no child process."""
    maker = Factory()
    window = maker.make("Window")
    window.add(maker.make("Terminal"))
    yield window
    if not getattr(window, "isDestroyed", False):
        window.on_destroy_event(window)


def is_notebook(widget):
    """Return True if widget is a Notebook."""
    return Factory().isinstance(widget, "Notebook")


def test_single_terminal_is_wrapped_when_always_showing_tabbar(config, window):
    """A window with one terminal gets a tab bar when the option is set."""
    config["always_show_tabbar"] = True
    window.apply_always_show_tabbar()
    assert is_notebook(window.get_child())
    assert window.get_child().get_n_pages() == 1


def test_single_terminal_is_not_wrapped_by_default(config, window):
    """A window with one terminal has no tab bar by default."""
    config["always_show_tabbar"] = False
    window.apply_always_show_tabbar()
    assert not is_notebook(window.get_child())


def test_single_tab_is_unwrapped_when_option_is_turned_off(config, window):
    """Turning the option off removes the tab bar from single tab windows."""
    config["always_show_tabbar"] = True
    window.apply_always_show_tabbar()
    terminal = window.get_child().get_nth_page(0)

    config["always_show_tabbar"] = False
    window.apply_always_show_tabbar()
    assert window.get_child() is terminal


def test_closing_last_tab_closes_window(config, window):
    """Closing the last tab closes its window but not other windows."""
    config["always_show_tabbar"] = True
    window.apply_always_show_tabbar()
    notebook = window.get_child()
    maker = Factory()
    other_window = maker.make("Window")
    other_window.add(maker.make("Terminal"))

    notebook.wrapcloseterm(notebook.get_nth_page(0))
    assert window.isDestroyed
    assert other_window in Terminator().windows
    other_window.on_destroy_event(other_window)


def test_closing_only_terminal_closes_window(config, window):
    """Closing the only terminal left closes its window."""
    config["always_show_tabbar"] = True
    window.apply_always_show_tabbar()
    notebook = window.get_child()

    notebook.wrapcloseterm(notebook.get_nth_page(0))
    assert window not in Terminator().windows


def test_only_tab_is_not_detached(config, window):
    """The only tab in a window cannot be detached into a new window."""
    config["always_show_tabbar"] = True
    window.apply_always_show_tabbar()
    notebook = window.get_child()

    assert notebook.detach_tab_to_new_window(notebook.get_nth_page(0)) is False
    assert notebook.get_n_pages() == 1



def test_single_tab_layout_is_restored(config, window, monkeypatch):
    """A saved layout with a single tab loads back as one tab."""
    config["always_show_tabbar"] = True
    monkeypatch.setattr("terminatorlib.terminal.Terminal.spawn_child",
                        lambda *args, **kwargs: None)
    layout = {"children": {"child1": {
        "type": "Notebook",
        "labels": ["~/src"],
        "children": {"terminal2": {"type": "Terminal", "order": 0,
                                   "title": "build"}},
    }}}

    window.create_layout(layout)
    notebook = window.get_child()
    assert is_notebook(notebook)
    assert notebook.get_n_pages() == 1
    terminal = notebook.get_nth_page(0)
    assert notebook.get_tab_label(terminal).get_custom_label() == "~/src"
    assert terminal.titlebar.get_custom_string() == "build"


@pytest.fixture
def split_window(config, window, monkeypatch):
    """Provide a shown window whose terminal is split into two panes."""
    monkeypatch.setattr("terminatorlib.terminal.Terminal.spawn_child",
                        lambda *args, **kwargs: None)
    window.split_axis(window.get_child(), False)
    window.show_all()
    return window


def test_toggling_option_keeps_focused_pane(config, split_window):
    """Adding or removing the tab bar doesn't move the focus."""
    first = split_window.get_child().get_child1()
    first.grab_focus()

    for enabled in (True, False):
        config["always_show_tabbar"] = enabled
        split_window.apply_always_show_tabbar()
        assert split_window.get_focussed_terminal() is first


def test_option_change_while_zoomed_applies_on_unzoom(config, split_window):
    """Turning the option on while zoomed adds the tab bar on unzoom."""
    terminal = split_window.get_child().get_child1()
    split_window.zoom(terminal)
    config["always_show_tabbar"] = True
    split_window.apply_always_show_tabbar()
    assert split_window.get_child() is terminal

    split_window.unzoom()
    assert is_notebook(split_window.get_child())


def test_zooming_only_terminal_does_nothing(config, window):
    """Zooming a window's only terminal is a no-op, as without a tab bar."""
    config["always_show_tabbar"] = True
    window.apply_always_show_tabbar()
    notebook = window.get_child()

    window.zoom(notebook.get_nth_page(0))
    assert not window.is_zoomed()
    assert window.get_child() is notebook


@pytest.mark.parametrize("enabled", [True, False])
def test_single_tab_layout_restores_focused_pane(config, terminator, enabled,
                                                 monkeypatch):
    """Loading a one tab layout focuses the pane that was saved as active."""
    config["always_show_tabbar"] = enabled
    monkeypatch.setattr("terminatorlib.terminal.Terminal.spawn_child",
                        lambda *args, **kwargs: None)
    first, second = str(uuid.uuid4()), str(uuid.uuid4())
    layout = {"children": {"child1": {
        "type": "Notebook",
        "last_active_term": [first],
        "children": {"child2": {
            "type": "HPaned", "order": 0, "children": {
                "terminal3": {"type": "Terminal", "order": 0, "uuid": first},
                "terminal4": {"type": "Terminal", "order": 1, "uuid": second},
            }}},
    }}}
    terminator.doing_layout = True
    terminator.prelayout_windows = terminator.windows[:]
    window, _terminal = terminator.new_window()

    window.create_layout(layout)
    terminator.layout_done()
    while Gtk.events_pending():
        Gtk.main_iteration()
    focused = window.get_focussed_terminal()
    assert focused is terminator.find_terminal_by_uuid("urn:uuid:" + first)
    window.on_destroy_event(window)


class AskedToConfirm(Exception):
    """Raised instead of showing the close confirmation dialog."""


@pytest.fixture
def confirm_dialog(config, monkeypatch):
    """Ask before closing multiple terminals, and fail if the dialog opens."""
    saved = config["ask_before_closing"]
    config["ask_before_closing"] = "multiple_terminals"

    def dialog(*args, **kwargs):
        raise AskedToConfirm()

    monkeypatch.setattr("terminatorlib.container.Gtk.Dialog", dialog)
    yield
    config["ask_before_closing"] = saved


def test_closing_single_terminal_window_does_not_ask(config, window,
                                                     confirm_dialog):
    """A window with one terminal in one tab closes without asking."""
    config["always_show_tabbar"] = True
    window.apply_always_show_tabbar()

    assert not window.on_delete_event(window, None)


def test_closing_window_with_split_tab_asks(config, split_window,
                                           confirm_dialog):
    """A window with a split in its only tab still asks before closing."""
    config["always_show_tabbar"] = True
    split_window.apply_always_show_tabbar()

    with pytest.raises(AskedToConfirm):
        split_window.on_delete_event(split_window, None)
