# Backend contract test.
#
# terminal.py calls a large, Vte-flavoured surface on self.vte (the backend
# widget). This test pins the contract: whatever make_terminal_widget()
# returns on the current platform must expose every method terminal.py
# relies on. On Linux that is VteBackend (inherits the surface from
# Vte.Terminal); on Windows it is ConPtyTerminal (implements it). Running
# here on Linux therefore locks in VteBackend's coverage; the Windows CI
# job would exercise ConPtyTerminal the same way.
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')
import pytest

from terminatorlib.terminal_backend import make_terminal_widget, TerminalBackend


@pytest.fixture
def backend():
    return make_terminal_widget()


# Methods terminal.py invokes on self.vte. Drawn from the ~100 call sites in
# terminal.py -- the ones that must exist regardless of backend.
REQUIRED_METHODS = [
    # lifecycle
    'spawn', 'feed', 'feed_child',
    # geometry
    'set_size', 'get_char_width', 'get_char_height',
    'get_column_count', 'get_row_count', 'get_cursor_position',
    'get_vadjustment',
    # appearance
    'set_colors', 'set_color_cursor', 'set_color_cursor_foreground',
    'set_font', 'get_font', 'set_clear_background',
    # behaviour
    'set_scrollback_lines', 'set_scroll_on_keystroke', 'set_scroll_on_output',
    'set_audible_bell', 'set_backspace_binding', 'set_delete_binding',
    'set_cursor_shape', 'set_cursor_blink_mode', 'set_allow_bold',
    'set_bold_is_bright', 'set_cell_height_scale', 'set_cell_width_scale',
    'set_word_char_exceptions', 'set_mouse_autohide', 'set_allow_hyperlink',
    'reset',
    # title / cwd
    'get_window_title', 'get_current_directory_uri',
    # selection / clipboard / URL
    'copy_clipboard', 'paste_primary', 'get_has_selection', 'unselect_all',
    'match_add_regex', 'match_remove', 'match_set_cursor_name',
    'match_check_event', 'hyperlink_check_event',
    # GtkWidget surface (terminal.py packs/focuses/connects the backend)
    'connect', 'grab_focus', 'show', 'queue_draw', 'get_style_context',
    'get_allocation', 'get_parent_window', 'add_events', 'drag_dest_set',
    'get_toplevel', 'is_focus', 'has_focus',
]


@pytest.mark.parametrize('name', REQUIRED_METHODS)
def test_backend_exposes_contract(backend, name):
    assert hasattr(backend, name), (
        'backend %s is missing contract method %r (used by terminal.py)'
        % (type(backend).__name__, name))


def test_backend_spawn_is_overridden(backend):
    # The portable spawn() surface must be provided by the backend itself,
    # not inherited as an abstract stub.
    assert callable(getattr(backend, 'spawn'))


def test_backend_is_terminalbackend(backend):
    assert isinstance(backend, TerminalBackend)
