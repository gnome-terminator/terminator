# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""terminal_backend.py - pluggable terminal backend abstraction

Terminator historically instantiated ``Vte.Terminal`` directly and treated it
both as a terminal emulator *and* as a packed GTK widget (it is a
``Gtk.Widget`` subclass). That coupling to libvte -- which does PTY management,
VT emulation and glyph rendering all in one C library with no Windows port --
is the root reason Terminator cannot run on Windows.

This module introduces the switch point without disturbing Linux behaviour:

* A concrete backend IS-A GTK widget. On Linux that is ``VteBackend``, a thin
  subclass of ``Vte.Terminal`` (so every ``self.vte.*`` call site in
  ``terminal.py`` keeps working unchanged). On Windows it is
  ``ConPtyTerminal`` (a ``Gtk.DrawingArea`` subclass backed by ConPTY + pyte,
  implemented in M2).
* ``make_terminal_widget()`` returns the right one per platform.

The most platform-specific operation -- spawning the child process over a
PTY -- is centralised behind :meth:`TerminalBackend.spawn` so each backend
implements it natively (``Vte.spawn_sync`` on Linux, ``CreatePseudoConsole`` +
``CreateProcess`` on Windows).
"""

from __future__ import print_function

import sys

from . import platform


class TerminalBackend(object):
    """Contract for terminal backends.

    A concrete backend is itself the GTK widget that ``Terminal`` packs into
    its box (so callers can use it for ``connect``, ``grab_focus``,
    ``get_allocation``, style context, etc.). It additionally provides the
    terminal-specific surface below.

    Linux: ``VteBackend(Vte.Terminal)`` inherits the entire surface from VTE.
    Windows: ``ConPtyTerminal(Gtk.DrawingArea)`` re-implements it.

    The methods listed here are the ones ``terminal.py`` relies on; the Linux
    backend gets them for free from VTE, the Windows backend must implement
    them (M2).
    """

    # -- lifecycle --------------------------------------------------------
    def spawn(self, args, envv, cwd, flatpak=False):
        """Spawn the child process. Returns the child PID (or -1)."""
        raise NotImplementedError

    def feed(self, text):
        """Write text onto the terminal screen (process -> terminal)."""
        raise NotImplementedError

    def feed_child(self, text):
        """Send text to the child process' input (terminal -> process)."""
        raise NotImplementedError

    # -- geometry ---------------------------------------------------------
    # set_size, get_char_width, get_char_height, get_column_count,
    # get_row_count, get_cursor_position, get_vadjustment, get_allocation
    # are ordinary widget/emulator methods; provided by VTE on Linux.

    # -- appearance -------------------------------------------------------
    # set_colors, set_font, get_font, set_cursor_shape, set_backspace_binding,
    # set_scrollback_lines, set_audible_bell, ... likewise from VTE on Linux.

    # -- selection / clipboard -------------------------------------------
    # copy_clipboard, paste_primary, get_has_selection, unselect_all,
    # match_add_regex, match_check_event, hyperlink_check_event: from VTE.


def make_terminal_widget(config=None):
    """Return the platform-appropriate terminal backend widget.

    On Linux/macOS this is a ``VteBackend`` (a ``Vte.Terminal`` subclass, so
    behaviour is identical to the historical direct instantiation). On
    Windows it is a ``ConPtyTerminal`` (M2). The import of the concrete
    backend is deferred so that platforms without the alternate backend's
    native deps (VTE on Windows, pywin32 on Linux) never try to load it.
    """
    if platform.IS_WINDOWS:
        from .backends.conpty_backend import ConPtyTerminal
        return ConPtyTerminal(config=config)
    from .backends.vte_backend import VteBackend
    return VteBackend(config=config)
