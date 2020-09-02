import pytest
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

CONTROL_SHIFT_MOD = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
CONTROL_ALT_MOD = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK
CONTROL_ALT_SHIFT_MOD = (
    Gdk.ModifierType.CONTROL_MASK
    | Gdk.ModifierType.MOD1_MASK
    | Gdk.ModifierType.SHIFT_MASK
)


class MessageDialogToken:
    def __init__(self):
        self.has_appeared = False


def detect_close_message_dialog(prefs_editor, message_dialog_token):
    # type: (terminatorlib.prefseditor.PrefsEditor, MessageDialogToken) -> bool
    """
    Checks whether a message dialog is displayed over the Preferences
    window and if so, closes it. This function is intended to be used with
    `GLib.timeout_add_seconds` or a similar function.
    """
    if prefs_editor.active_message_dialog is not None:
        message_dialog_token.has_appeared = True
        prefs_editor.active_message_dialog.hide()
        return False
    return True


def reset_config_keybindings():
    """
    Resets key bindings to the default.

    Key bindings are stored in `terminatorlib.config.ConfigBase`,
    which is implemented using the Borg design pattern - this means
    that simply recreating a `ConfigBase` instance won't reset the key
    bindings to the default.
    """
    from terminatorlib import config

    conf_base = config.ConfigBase()
    conf_base.keybindings = None
    conf_base.prepare_attributes()


def test_non_empty_default_keybinding_accels_are_distinct():
    """
    Tests that all non-empty key binding accelerators defined in
    the default config are distinct.
    """
    from terminatorlib import config

    all_default_accelerators = [
        Gtk.accelerator_parse(accel)
        for accel in config.DEFAULTS["keybindings"].values()
        if accel != ""  # ignore empty key bindings
    ]

    assert len(all_default_accelerators) == len(set(all_default_accelerators))


@pytest.mark.parametrize(
    "accel_params,expected",
    [
        # 1) 'edit_tab_title' Ctrl+Alt+A
        (("9", 97, CONTROL_ALT_MOD, 38), False,),
        # 2) 'edit_terminal_title' Ctrl+Alt+A
        (("10", 97, CONTROL_ALT_MOD, 38), True,),
        # 3) 'edit_window_title' F11
        (("11", 65480, Gdk.ModifierType(0), 95), True,),
        # 4) 'zoom_in' Shift+Ctrl+Z
        (("70", 122, CONTROL_SHIFT_MOD, 52), True,),
        # 5) 'close_terminal' Ctrl+Alt+{
        (("3", 123, CONTROL_ALT_SHIFT_MOD, 34), False,),
        # 6) 'zoom_in' Shift+Ctrl+B
        (("70", 98, CONTROL_SHIFT_MOD, 56), False,),
    ],
)
def test_message_dialog_is_shown_on_duplicate_accel_assignment(
    accel_params, expected
):
    """
    Tests that a message dialog appears every time a duplicate key binding accelerator
    is attempted to be assigned to a different action in `Preferences > Keybindings`,
    and doesn't appear if a key binding accelerator is not a duplicate.
    """
    from terminatorlib import terminal
    from terminatorlib import prefseditor

    path, key, mods, code = accel_params

    term = terminal.Terminal()
    prefs_editor = prefseditor.PrefsEditor(term=term)
    message_dialog = MessageDialogToken()
    # Check for an active message dialog every second
    GLib.timeout_add_seconds(
        1, detect_close_message_dialog, prefs_editor, message_dialog
    )

    widget = prefs_editor.builder.get_object("keybindingtreeview")
    liststore = widget.get_model()

    # Replace default accelerator with a test one
    prefs_editor.on_cellrenderer_accel_edited(
        liststore=liststore, path=path, key=key, mods=mods, _code=code
    )

    assert message_dialog.has_appeared == expected

    reset_config_keybindings()


@pytest.mark.parametrize(
    "accel_params",
    [
        # 1) 'edit_tab_title' Ctrl+Alt+A
        ("9", 97, CONTROL_ALT_MOD, 38),
        # 2) 'edit_terminal_title' Ctrl+Alt+A
        ("10", 97, CONTROL_ALT_MOD, 38),
        # 3) 'edit_window_title' F11
        ("11", 65480, Gdk.ModifierType(0), 95),
        # 4) 'zoom_in' Shift+Ctrl+Z
        ("70", 122, CONTROL_SHIFT_MOD, 52),
    ],
)
def test_duplicate_accels_not_possible_to_set(accel_params):
    """
    Tests that a duplicate key binding accelerator, that is a key binding accelerator
    which is already defined in the config cannot be used to refer to more than
    one action.
    """
    from terminatorlib import config
    from terminatorlib import terminal
    from terminatorlib import prefseditor

    path, key, mods, code = accel_params

    term = terminal.Terminal()
    prefs_editor = prefseditor.PrefsEditor(term=term)
    message_dialog = MessageDialogToken()

    # Check for an active message dialog every second
    GLib.timeout_add_seconds(
        1, detect_close_message_dialog, prefs_editor, message_dialog
    )

    widget = prefs_editor.builder.get_object("keybindingtreeview")
    liststore = widget.get_model()
    binding = liststore.get_value(liststore.get_iter(path), 0)

    all_default_accelerators = {
        Gtk.accelerator_parse(accel)
        for accel in config.DEFAULTS["keybindings"].values()
        if accel != ""  # ignore empty key bindings
    }
    # Check that a test accelerator is indeed a duplicate
    assert (key, mods) in all_default_accelerators

    default_accelerator = Gtk.accelerator_parse(
        config.DEFAULTS["keybindings"][binding]
    )

    # Replace default accelerator with a test one
    prefs_editor.on_cellrenderer_accel_edited(
        liststore=liststore, path=path, key=key, mods=mods, _code=code
    )

    new_accelerator = Gtk.accelerator_parse(
        prefs_editor.config["keybindings"][binding]
    )

    # Key binding accelerator value shouldn't have changed
    assert default_accelerator == new_accelerator

    reset_config_keybindings()
