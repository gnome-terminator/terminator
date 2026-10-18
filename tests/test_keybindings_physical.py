import os

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk


CTRL = Gdk.ModifierType.CONTROL_MASK
SHIFT = Gdk.ModifierType.SHIFT_MASK


class FakeKeyEvent:
    """Minimal stand-in for a Gdk.EventKey used by Keybindings.lookup()."""

    def __init__(self, hardware_keycode, state, group=0):
        self.hardware_keycode = hardware_keycode
        self._state = state
        self.group = group
        self.type = Gdk.EventType.KEY_PRESS

    def get_state(self):
        return self._state


class _Entry:
    def __init__(self, keycode, group, level):
        self.keycode = keycode
        self.group = group
        self.level = level


class FakeKeymap:
    """Hand-built stand-in for Gdk.Keymap.

    ``entries`` maps a keyval to the ``(keycode, group, level)`` tuples that
    produce it, as reported by ``get_entries_for_keyval()``. ``presses`` maps
    a ``(keycode, group)`` to the ``(keyval, level, consumed)`` triple that
    ``translate_keyboard_state()`` returns for a key press. Using a fake
    keymap lets the tests describe non-Latin layouts deterministically, which
    is not possible with the real keymap of the test machine.
    """

    def __init__(self, entries, presses):
        self._entries = entries
        self._presses = presses

    def get_entries_for_keyval(self, keyval):
        entries = self._entries.get(keyval, [])
        return (bool(entries), [_Entry(*entry) for entry in entries])

    def translate_keyboard_state(self, keycode, state, group):
        keyval, level, consumed = self._presses[(keycode, group)]
        return (True, keyval, group, level, consumed)


def keybindings_with(entries, presses):
    """Return a Keybindings instance backed by the given fake keymap."""
    from terminatorlib.keybindings import Keybindings

    keybindings = Keybindings()
    keybindings.keymap = FakeKeymap(entries, presses)
    return keybindings


def test_physical_keybindings_default_is_disabled():
    """The physical keybinding lookup must be opt-in."""
    from terminatorlib import config

    assert config.DEFAULTS["global_config"]["physical_keybindings"] is False


def test_lookup_physical_resolves_by_keycode():
    """
    With physical lookup enabled, a binding is matched by the hardware
    keycode even when the active layout reports a different keyval, which is
    what happens with non-Latin layouts such as Cyrillic.
    """
    keybindings = keybindings_with(
        # The Latin 'C' keyval comes from the US group, the Cyrillic one from
        # the active Bulgarian group; both share physical keycode 54.
        entries={Gdk.KEY_C: [(54, 0, 1)]},
        presses={(54, 1): (Gdk.KEY_Cyrillic_ES, 1, SHIFT)},
    )
    keybindings.configure({"copy": "<Shift><Control>c"}, physical=True)

    event = FakeKeyEvent(54, CTRL | SHIFT, group=1)
    assert keybindings.lookup(event) == "copy"


def test_physical_does_not_hijack_unshifted_keys():
    """
    A shifted binding must not be triggered by the unshifted physical key.

    Otherwise Ctrl+C and Ctrl+D (which the terminal needs for SIGINT and
    EOF) would fire the Ctrl+Shift+C 'copy' and Ctrl+Shift+D 'detach_tab'
    bindings.
    """
    keybindings = keybindings_with(
        entries={Gdk.KEY_C: [(54, 0, 1)], Gdk.KEY_D: [(40, 0, 1)]},
        presses={
            (54, 0): (Gdk.KEY_c, 0, 0),
            (40, 0): (Gdk.KEY_d, 0, 0),
            (54, 1): (Gdk.KEY_Cyrillic_ES, 1, SHIFT),
            (40, 1): (Gdk.KEY_Cyrillic_DE, 1, SHIFT),
        },
    )
    keybindings.configure(
        {"copy": "<Shift><Control>c", "detach_tab": "<Shift><Control>d"},
        physical=True,
    )

    # Unshifted Ctrl+C / Ctrl+D on a Latin layout must not resolve.
    assert keybindings.lookup(FakeKeyEvent(54, CTRL, group=0)) is None
    assert keybindings.lookup(FakeKeyEvent(40, CTRL, group=0)) is None

    # The shifted variants still work on a non-Latin layout.
    assert keybindings.lookup(FakeKeyEvent(54, CTRL | SHIFT, group=1)) == "copy"
    assert (
        keybindings.lookup(FakeKeyEvent(40, CTRL | SHIFT, group=1)) == "detach_tab"
    )


def test_physical_does_not_hijack_other_latin_layout():
    """
    A shortcut configured for one Latin layout must not steal a key that the
    active Latin layout maps to a different character.

    Regression test for us+de: physical keycode 61 is '/' on US and '-' on
    German, so with zoom_out = <Control>minus on the US layout, Ctrl+/ must
    still reach the program instead of firing zoom_out.
    """
    keybindings = keybindings_with(
        entries={Gdk.KEY_minus: [(61, 1, 0)]},
        presses={(61, 0): (Gdk.KEY_slash, 0, 0)},
    )
    keybindings.configure({"zoom_out": "<Control>minus"}, physical=True)

    # The physical table does map the key ...
    assert keybindings._lookup_physical(CTRL, 61, 0) == "zoom_out"
    # ... but the Latin '/' must not be hijacked by it.
    assert keybindings.lookup(FakeKeyEvent(61, CTRL, group=0)) is None


def test_preferences_exposes_physical_keybindings_option():
    """The Global preferences tab must expose the opt-in checkbox."""
    glade = os.path.join(
        os.path.dirname(__file__), "..", "terminatorlib", "preferences.glade"
    )
    builder = Gtk.Builder()
    builder.add_from_file(os.path.abspath(glade))

    widget = builder.get_object("physical_keybindings")
    assert widget is not None
    assert "Physical keybindings" in widget.get_label()


def test_lookup_physical_disabled_falls_through():
    """
    With physical lookup disabled (the default), no physical keycode map is
    built and the physical fallback never resolves an action.
    """
    keybindings = keybindings_with(
        entries={Gdk.KEY_C: [(54, 0, 1)]},
        presses={(54, 1): (Gdk.KEY_Cyrillic_ES, 1, SHIFT)},
    )
    keybindings.configure({"copy": "<Shift><Control>c"}, physical=False)

    assert keybindings._physical_lookup == {}
    assert keybindings.lookup(FakeKeyEvent(54, CTRL | SHIFT, group=1)) is None


def test_keys_changed_rebuilds_physical_lookup():
    """
    Adding or reordering layouts at runtime changes the keycodes a keyval
    resolves to, so the table must be rebuilt on Gdk.Keymap::keys-changed.
    """
    entries = {}
    keybindings = keybindings_with(entries, {})
    keybindings.configure({"copy": "<Shift><Control>c"}, physical=True)
    assert keybindings._physical_lookup == {}

    # A layout containing the Latin 'C' key shows up at runtime.
    entries[Gdk.KEY_C] = [(54, 0, 1)]
    keybindings._on_keys_changed(keybindings.keymap)
    assert keybindings._physical_lookup[CTRL][(54, 1)] == "copy"

    # With the option off nothing is rebuilt.
    keybindings.physical = False
    keybindings._physical_lookup = {}
    keybindings._on_keys_changed(keybindings.keymap)
    assert keybindings._physical_lookup == {}
