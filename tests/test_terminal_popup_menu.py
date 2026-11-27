"""Tests for terminal context menu actions."""

import os
import sys

import gi
import pytest

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")

from gi.repository import Gdk, Gtk

from terminatorlib.terminal_popup_menu import TerminalPopupMenu


class FakeContainer:
    """Container recording confirmation requests."""

    def __init__(self, response, parent=None):
        self.response = response
        self.parent = parent
        self.confirmations = []

    def construct_confirm_close(self, window, child):
        self.confirmations.append((window, child))
        return self.response

    def get_parent(self):
        return self.parent


class FakeParent:
    """Intermediate widget without close confirmation behavior."""

    def __init__(self, parent):
        self.parent = parent

    def get_parent(self):
        return self.parent


class FakeTerminal:
    """Terminal recording close calls."""

    def __init__(self, parent=None, toplevel=None):
        self.parent = parent
        self.toplevel = toplevel
        self.closed = False

    def get_parent(self):
        return self.parent

    def get_toplevel(self):
        return self.toplevel

    def close(self):
        self.closed = True


def popup_for(terminal):
    popup = TerminalPopupMenu.__new__(TerminalPopupMenu)
    popup.terminal = terminal
    return popup


def test_close_terminal_closes_after_confirmation_accepts():
    """Context menu close uses the container confirmation path."""
    window = object()
    container = FakeContainer(Gtk.ResponseType.ACCEPT)
    terminal = FakeTerminal(parent=container, toplevel=window)

    popup_for(terminal).close_terminal()

    assert terminal.closed
    assert container.confirmations == [(window, terminal)]


def test_close_terminal_keeps_terminal_open_when_confirmation_rejects():
    """A rejected confirmation prevents context menu close."""
    container = FakeContainer(Gtk.ResponseType.REJECT)
    terminal = FakeTerminal(parent=container, toplevel=object())

    popup_for(terminal).close_terminal()

    assert not terminal.closed
    assert container.confirmations == [(terminal.get_toplevel(), terminal)]


def test_close_terminal_finds_confirmation_container_above_parent_widget():
    """Intermediate GTK widgets do not bypass close confirmation."""
    container = FakeContainer(Gtk.ResponseType.ACCEPT)
    parent = FakeParent(container)
    terminal = FakeTerminal(parent=parent, toplevel=object())

    popup_for(terminal).close_terminal()

    assert terminal.closed
    assert container.confirmations == [(terminal.get_toplevel(), terminal)]


@pytest.fixture
def popup_with_keybindings():
    """Factory of popups whose config holds only the given keybindings."""
    popups = []

    def make(keybindings):
        class FakeBase:
            def get_item(self, key, profile='default'):
                assert key == 'keybindings'
                return keybindings

        class FakeConfig:
            base = FakeBase()

        popup = TerminalPopupMenu.__new__(TerminalPopupMenu)
        popup.config = FakeConfig()
        popup.accelgrp = Gtk.AccelGroup()
        popup.items = []
        popups.append(popup)
        return popup

    yield make

    # Destroy the items while their accel group is still alive: a menu
    # item's label disconnects from the group when the item goes away.
    for popup in popups:
        for item in popup.items:
            item.destroy()


def menu_item(popup, actstr, menustr):
    """Build a menu item on the popup and keep it alive until teardown."""
    item = popup.menu_item(Gtk.MenuItem, actstr, menustr)
    popup.items.append(item)
    return item


def accelerators(popup):
    """Sorted (keyval, modifiers) of the accelerators shown on the popup."""
    found = []

    def collect(key, closure):
        assert key.accel_flags & Gtk.AccelFlags.VISIBLE
        found.append((key.accel_key, key.accel_mods))
        return False

    popup.accelgrp.find(collect)
    return sorted(found)


def test_zoom_menu_items_show_their_keybindings(popup_with_keybindings):
    """Zoom, maximize and restore items carry the configured shortcuts."""
    popup = popup_with_keybindings({'scaled_zoom': '<Shift><Control>z',
                                    'toggle_zoom': '<Shift><Control>x'})
    mods = Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.CONTROL_MASK

    zoom = menu_item(popup, 'scaled_zoom', '_Zoom terminal')
    maximize = menu_item(popup, 'toggle_zoom', 'Ma_ximize terminal')
    restore = menu_item(popup, 'toggle_zoom', '_Restore all terminals')

    assert zoom.get_name() == 'scaled_zoom'
    assert maximize.get_name() == 'toggle_zoom'
    assert restore.get_name() == 'toggle_zoom'
    assert accelerators(popup) == sorted([
        (Gdk.keyval_from_name('z'), mods),
        (Gdk.keyval_from_name('x'), mods),
        (Gdk.keyval_from_name('x'), mods)])


@pytest.mark.parametrize('keybindings', [{}, {'scaled_zoom': ''},
                                         {'scaled_zoom': None},
                                         {'scaled_zoom': 'None'}])
def test_menu_item_without_keybinding_has_no_accelerator(
        popup_with_keybindings, keybindings):
    """An unbound action still produces a plain menu item."""
    popup = popup_with_keybindings(keybindings)

    item = menu_item(popup, 'scaled_zoom', '_Zoom terminal')

    assert item.get_name() == 'scaled_zoom'
    assert accelerators(popup) == []


def test_menu_item_shows_named_key_bindings(popup_with_keybindings):
    """Bindings on named keys are shown as configured, not as the mnemonic."""
    popup = popup_with_keybindings({'scaled_zoom': '<Control>F5',
                                    'toggle_zoom': '<Super>x'})

    menu_item(popup, 'scaled_zoom', '_Zoom terminal')
    menu_item(popup, 'toggle_zoom', 'Ma_ximize terminal')

    assert accelerators(popup) == sorted([
        (Gdk.KEY_F5, Gdk.ModifierType.CONTROL_MASK),
        (Gdk.keyval_from_name('x'), Gdk.ModifierType.SUPER_MASK)])


def test_menu_item_ignores_unparsable_binding(popup_with_keybindings):
    """A binding GTK cannot parse yields a plain menu item, no crash."""
    popup = popup_with_keybindings({'scaled_zoom': '<Control>NotAKey'})

    item = menu_item(popup, 'scaled_zoom', '_Zoom terminal')

    assert item.get_name() == 'scaled_zoom'
    assert accelerators(popup) == []
