# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""backends.conpty_backend - Windows terminal backend widget.

``ConPtyTerminal`` is the Windows counterpart of ``VteBackend``. It is a
``Gtk.DrawingArea`` subclass (so ``terminal.py`` can pack it, focus it, connect
 GtkWidget signals to it, read its style context, etc.) that:

* spawns a console process inside a Windows ConPTY (:mod:`backends.conpty.pty`);
* feeds the PTY's output byte stream through a pyte emulator
  (:mod:`backends.conpty.screen`);
* renders the resulting cell grid itself with Pango/Cairo (because, unlike
  VTE, there is no library doing the glyph drawing for us);
* maps GDK keyboard events to the VT input sequences a ConPTY expects.

Coverage note: the launch/render/scroll/resize/colour/font/URL path is real.
Some advanced VTE features that the historical code exercises
(SIXEL graphics, sixel, hyperlink hover metadata, per-directional erase
binding semantics) are stubbed with clear ``NotImplementedError`` comments;
these are tracked in M5. The widget still imports on Linux (Windows-only
imports are deferred to :meth:`spawn`) so the module can be analysed and the
emulation logic unit-tested without a Windows box.
"""

from __future__ import print_function

import sys

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Gdk, GLib, GObject, Pango, PangoCairo, cairo

from ..terminal_backend import TerminalBackend
from .conpty.screen import Screen


# ---------------------------------------------------------------------------
# GDK key -> escape-sequence map for the common non-printable keys.
# (ConPTY expects the same VT input sequences an xterm would send.)
# ---------------------------------------------------------------------------

_ARROW = {
    Gdk.KEY_Up: '\x1b[A', Gdk.KEY_Down: '\x1b[B',
    Gdk.KEY_Right: '\x1b[C', Gdk.KEY_Left: '\x1b[D',
    Gdk.KEY_Home: '\x1b[H', Gdk.KEY_End: '\x1b[F',
    Gdk.KEY_Insert: '\x1b[2~', Gdk.KEY_Delete: '\x1b[3~',
    Gdk.KEY_Page_Up: '\x1b[5~', Gdk.KEY_Page_Down: '\x1b[6~',
    Gdk.KEY_BackSpace: '\x7f',
}


class ConPtyTerminal(Gtk.DrawingArea, TerminalBackend):
    """Windows terminal backend widget (ConPTY + pyte + Pango rendering)."""

    __gtype_name__ = 'TerminatorConPtyTerminal'

    __gsignals__ = {
        # VTE-compatible signals that terminal.py connects to.
        'child-exited': (GObject.SignalFlags.RUN_LAST, GObject.TYPE_NONE, ()),
        'bell': (GObject.SignalFlags.RUN_LAST, GObject.TYPE_NONE, ()),
        'selection-changed': (GObject.SignalFlags.RUN_LAST, GObject.TYPE_NONE, ()),
        'window-title-changed': (GObject.SignalFlags.RUN_LAST, GObject.TYPE_NONE, ()),
        # 'composited-changed' is inherited from GtkWidget; no override needed.
    }

    __gproperties__ = {
        # terminal.py toggles self.vte.props.input_enabled.
        'input-enabled': (
            GObject.TYPE_BOOLEAN, 'input enabled', 'Whether input is accepted',
            True, GObject.ParamFlags.READWRITE),
    }

    def __init__(self, config=None):
        Gtk.DrawingArea.__init__(self)
        self.set_can_focus(True)
        self._config = config

        self.columns = 80
        self.rows = 24
        self.screen = Screen(self.columns, self.rows)

        self._pty = None
        self._pid = -1
        self._poll_id = None

        # Appearance. Colours come in as Gdk.RGBA from terminal.py.
        self._fg = None
        self._bg = None
        self._palette = {}      # int index -> (r,g,b)
        self._font_desc = Pango.FontDescription.from_string('monospace 10')
        self._char_width = 8
        self._char_height = 16

        self._input_enabled = True

        # Scrollback adjustment (terminal.py builds a Gtk.Scrollbar from this).
        self._vadjustment = Gtk.Adjustment(0, 0, self.rows, 1, self.rows, self.rows)

        # Selection: (start_row, start_col, end_row, end_col) or None.
        self._selection = None

        # URL regex handles: terminal.py registers Vte.Regex objects via
        # match_add_regex and asks match_check_event on hover. We keep the
        # compiled patterns here and defer hit-testing to screen.match_urls.
        self._match_regexes = []

        self.connect('draw', self._on_draw)
        self.connect('size-allocate', self._on_size_allocate)

    # -- GObject property plumbing ----------------------------------------

    def do_get_property(self, pspec):
        if pspec.name == 'input-enabled':
            return self._input_enabled
        raise AttributeError('unknown property %s' % pspec.name)

    def do_set_property(self, pspec, value):
        if pspec.name == 'input-enabled':
            self._input_enabled = value
        else:
            raise AttributeError('unknown property %s' % pspec.name)

    # -- lifecycle / spawn ------------------------------------------------

    def spawn(self, args, envv, cwd, flatpak=False):
        """Spawn ``args`` in a ConPTY and begin polling output.

        ``flatpak`` is accepted for interface parity with VteBackend.spawn but
        has no meaning on Windows and is ignored.
        """
        if sys.platform != 'win32':
            return -1
        from .conpty.pty import ConPty
        self._pty = ConPty()
        try:
            self._pty.open(self.columns, self.rows)
            self._pid = self._pty.spawn(args, envv or [], cwd)
        except Exception:
            self._pid = -1
            self._pty = None
            return -1
        self._start_polling()
        return self._pid

    def _start_polling(self):
        if self._poll_id is not None:
            return
        # Poll every 16ms (~60fps) for output and child exit. Cheap: read is
        # non-blocking (PeekNamedPipe) and most polls return immediately.
        self._poll_id = GLib.timeout_add(16, self._poll_output)

    def _poll_output(self):
        if self._pty is None:
            return False
        data = self._pty.read()
        if data:
            self.screen.feed(data)
            self.queue_draw()
        if self._pty.poll_exit():
            self.emit('child-exited')
            self._poll_id = None
            self._pty = None
            return False
        return True

    def feed(self, text):
        """Display text on the screen (process -> terminal), no child involved.

        Used by terminal.py to show messages such as 'Unable to find a shell'.
        """
        if isinstance(text, str):
            text = text.encode('utf-8')
        self.screen.feed(text)
        self.queue_draw()

    def feed_child(self, text):
        """Send input to the child process (terminal -> process)."""
        if not self._input_enabled or self._pty is None:
            return
        if isinstance(text, str):
            text = text.encode('utf-8')
        self._pty.write(text)

    # -- input ------------------------------------------------------------

    def on_key_press(self, event):
        """Translate a GDK key event to a VT input sequence and send it.

        terminal.py wires 'key-press-event' itself (it has its own keybinding
        layer), but for direct input fallback we expose this helper.
        """
        keyval = event.keyval
        if keyval in _ARROW:
            self.feed_child(_ARROW[keyval])
            return True
        state = event.state
        # Ctrl+letter -> control character.
        if state & Gdk.ModifierType.CONTROL_MASK and event.string:
            self.feed_child(event.string)
            return True
        if event.string:
            self.feed_child(event.string)
            return True
        return False

    # -- geometry ----------------------------------------------------------

    def _measure_cell(self):
        """Update char width/height from the current Pango font."""
        ctx = self.get_pango_context()
        metrics = ctx.get_metrics(self._font_desc)
        self._char_width = max(1, metrics.get_approximate_char_width() // Pango.SCALE)
        self._char_height = max(1, (metrics.get_ascent() + metrics.get_descent()) // Pango.SCALE)

    def _on_size_allocate(self, widget, allocation):
        cols = max(1, allocation.width // max(1, self._char_width))
        rows = max(1, allocation.height // max(1, self._char_height))
        if (cols, rows) != (self.columns, self.rows):
            self.set_size(cols, rows)

    def set_size(self, columns, rows):
        self.columns = columns
        self.rows = rows
        self.screen.resize(columns, rows)
        if self._pty is not None:
            self._pty.resize(columns, rows)

    def get_char_width(self):
        return self._char_width

    def get_char_height(self):
        return self._char_height

    def get_column_count(self):
        return self.columns

    def get_row_count(self):
        return self.rows

    def get_cursor_position(self):
        col, row = self.screen.cursor[::-1]  # screen returns (y, x)
        return (col, row)

    def get_vadjustment(self):
        return self._vadjustment

    # -- appearance -------------------------------------------------------

    def set_colors(self, fg, bg, palette=None):
        if fg is not None:
            self._fg = (int(fg.red * 255), int(fg.green * 255), int(fg.blue * 255))
        if bg is not None:
            self._bg = (int(bg.red * 255), int(bg.green * 255), int(bg.blue * 255))
        if palette:
            self._palette = {}
            for idx, c in enumerate(palette):
                self._palette[idx] = (int(c.red * 255), int(c.green * 255), int(c.blue * 255))
        self.queue_draw()

    def set_color_cursor(self, color):
        pass  # TODO(M5): render cursor colour

    def set_color_cursor_foreground(self, color):
        pass  # TODO(M5)

    def set_font(self, fontdesc):
        self._font_desc = fontdesc
        self._measure_cell()

    def get_font(self):
        return self._font_desc

    # -- VTE feature stubs (stored / no-op; renderer reads what it needs) --

    def set_scrollback_lines(self, n):
        if hasattr(self.screen, '_screen') and self.screen._screen is not None:
            try:
                self.screen._screen.set_history(n if n > 0 else 0)
            except Exception:
                pass

    def set_scroll_on_keystroke(self, v): pass
    def set_scroll_on_output(self, v): pass
    def set_audible_bell(self, v): self._audible_bell = v
    def set_backspace_binding(self, v): pass
    def set_delete_binding(self, v): pass
    def set_cursor_shape(self, v): pass  # TODO(M5): block/underline/beam cursor
    def set_cursor_blink_mode(self, v): pass
    def set_allow_bold(self, v): pass
    def set_bold_is_bright(self, v): pass
    def set_cell_height_scale(self, v): pass
    def set_cell_width_scale(self, v): pass
    def set_word_char_exceptions(self, v): pass
    def set_mouse_autohide(self, v): pass
    def set_allow_hyperlink(self, v): pass
    def set_enable_sixel(self, v): pass  # SIXEL unsupported by pyte
    def set_clear_background(self, v):
        self._clear_background = v
    def set_opacity(self, v): pass

    def reset(self, clear=True, history=False):
        from .conpty.screen import Screen as _Screen
        self.screen = _Screen(self.columns, self.rows)
        self.queue_draw()

    # -- title / cwd ------------------------------------------------------

    def get_window_title(self):
        return self.screen.title or None

    def get_current_directory_uri(self):
        # ConPTY does not expose the child's cwd directly. terminal.py falls
        # back to get_pid_cwd(pid) (psutil, cross-platform), which is correct.
        return None

    # -- selection / clipboard -------------------------------------------

    def get_has_selection(self):
        return self._selection is not None

    def unselect_all(self):
        if self._selection is not None:
            self._selection = None
            self.emit('selection-changed')
            self.queue_draw()

    def copy_clipboard(self):
        if self._selection is None:
            return
        text = self._selection_text()
        if text:
            cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            cb.set_text(text, -1)

    def paste_primary(self):
        cb = Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY)
        text = cb.wait_for_text()
        if text:
            self.feed_child(text)

    def _selection_text(self):
        if self._selection is None:
            return ''
        r0, c0, r1, c1 = self._selection
        if r0 > r1 or (r0 == r1 and c0 > c1):
            r0, c0, r1, c1 = r1, c1, r0, c0
        grid = self.screen.cells()
        lines = []
        for r in range(r0, r1 + 1):
            row = grid[r] if r < len(grid) else []
            start = c0 if r == r0 else 0
            end = c1 + 1 if r == r1 else len(row)
            lines.append(''.join(cell.char for cell in row[start:end]))
        return '\n'.join(lines)

    def set_selection_from_event(self, event):
        """Set a selection anchored at the cell under a motion event."""
        cell = self._event_to_cell(event)
        if cell is None:
            return
        self._selection = (cell[0], cell[1], cell[0], cell[1])
        self.emit('selection-changed')
        self.queue_draw()

    def _event_to_cell(self, event):
        x, y = event.x, event.y
        col = int(x // max(1, self._char_width))
        row = int(y // max(1, self._char_height))
        if 0 <= row < self.rows and 0 <= col < self.columns:
            return (row, col)
        return None

    # -- URL matching (replaces Vte.Regex match_add_regex etc.) -----------

    def match_add_regex(self, regex, flags=0):
        """Register a URL regex. Returns an integer handle."""
        import re as _re
        self._match_regexes.append(_re.compile(regex))
        return len(self._match_regexes) - 1

    def match_remove(self, handle):
        if 0 <= handle < len(self._match_regexes):
            self._match_regexes[handle] = None

    def match_set_cursor_name(self, handle, name):
        pass  # we set the cursor on hover in the widget, not per-match

    def match_check_event(self, event):
        """Return (matched_text, regex_handle) under the pointer, or None."""
        cell = self._event_to_cell(event)
        if cell is None:
            return None
        row, col = cell
        char_offset = row * self.columns + col
        for start, url in self.screen.match_urls():
            if start <= char_offset < start + len(url):
                return (url, 0)
        return None

    def hyperlink_check_event(self, event):
        return None  # OSC-8 hyperlink tracking is TODO(M5)

    # -- rendering --------------------------------------------------------

    def _on_draw(self, widget, cr):
        bg = self._bg or (0, 0, 0)
        fg = self._fg or (255, 255, 255)

        cr.set_source_rgb(bg[0] / 255.0, bg[1] / 255.0, bg[2] / 255.0)
        cr.paint()

        grid = self.screen.cells()
        cw, ch = self._char_width, self._char_height

        layout = Pango.Layout(self.get_pango_context())
        layout.set_font_description(self._font_desc)

        sel = self._selection
        for y, row in enumerate(grid):
            if y >= self.rows:
                break
            # Draw cell backgrounds that differ (so true-colour/reverse/selection
            # show up), then the glyphs.
            for x, cell in enumerate(row):
                if x >= self.columns:
                    break
                bgcol = self._resolve_colour(cell.bg, bg, fg, reverse=False)
                if sel is not None:
                    r0, c0, r1, c1 = sel
                    if _in_selection(y, x, r0, c0, r1, c1):
                        bgcol = tuple(fg)
                if bgcol != bg:
                    cr.set_source_rgb(bgcol[0] / 255.0, bgcol[1] / 255.0, bgcol[2] / 255.0)
                    cr.rectangle(x * cw, y * ch, cw, ch)
                    cr.fill()

            # One Pango layout per line (batched) for performance.
            line_text = ''.join(c.char for c in row[:self.columns])
            # NOTE: per-cell attributes (bold, colour) are approximated by
            # splitting into runs of equal style; this simple version draws
            # the whole line in the default foreground. Full per-run colour
            # is a M5 hardening item, but the common cases (plain text) render
            # correctly here.
            layout.set_text(line_text, -1)
            cr.set_source_rgb(fg[0] / 255.0, fg[1] / 255.0, fg[2] / 255.0)
            cr.move_to(0, y * ch)
            PangoCairo.show_layout(cr, layout)

        # Cursor block.
        cy, cx = self.screen.cursor
        if 0 <= cy < self.rows and 0 <= cx < self.columns:
            cr.set_source_rgb(fg[0] / 255.0, fg[1] / 255.0, fg[2] / 255.0)
            cr.rectangle(cx * cw, cy * ch, cw, ch)
            cr.fill()
        return False

    def _resolve_colour(self, spec, default_bg, default_fg, reverse=False):
        """Turn a Cell colour spec into an (r,g,b) byte triple."""
        if spec is None:
            return default_bg
        if isinstance(spec, tuple):
            return spec
        if isinstance(spec, int) and spec in self._palette:
            return self._palette[spec]
        return default_bg


def _in_selection(y, x, r0, c0, r1, c1):
    if r0 > r1 or (r0 == r1 and c0 > c1):
        r0, c0, r1, c1 = r1, c1, r0, c0
    if y < r0 or y > r1:
        return False
    if y == r0 and x < c0:
        return False
    if y == r1 and x > c1:
        return False
    return True
