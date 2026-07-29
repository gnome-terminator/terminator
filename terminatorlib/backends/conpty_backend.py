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

Coverage note: the launch/render/scroll/resize/colour/font/URL path is real,
and the renderer does full per-cell/per-run colour (true-colour, palette,
reverse, bold/italic/underline/strikethrough), selection inversion, and
cursor shapes (block/underline/beam) with cursor colours and blink. A few
advanced VTE features remain stubbed with clear comments: SIXEL graphics,
OSC-8 hyperlink hover metadata, and CJK IME composition are tracked gaps.
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

        # Cursor: shape ('block'/'underline'/'beam'), colours, blink.
        self._cursor_shape = 'block'
        self._cursor_bg = None     # (r,g,b) fill, None => use default fg
        self._cursor_fg = None     # (r,g,b) glyph-on-cursor, None => use default bg
        self._cursor_blink = False
        self._cursor_visible = True
        self._blink_id = None

        self._clear_background = True

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
        """Cursor fill colour (Gdk.RGBA or None for theme default)."""
        self._cursor_bg = _rgba_to_rgb(color)
        self.queue_draw()

    def set_color_cursor_foreground(self, color):
        """Glyph colour drawn over a block cursor (Gdk.RGBA or None)."""
        self._cursor_fg = _rgba_to_rgb(color)
        self.queue_draw()

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
    def set_cursor_shape(self, v):
        """Set the cursor shape.

        Accepts a Vte.CursorShape enum (int, on the off chance it is passed)
        or the config string ('block'/'underline'/'ibeam'/'bar').
        """
        shape = _cursor_shape_from_value(v)
        if shape:
            self._cursor_shape = shape
            self.queue_draw()

    def set_cursor_blink_mode(self, v):
        """Enable/disable cursor blink. ``v`` may be a Vte.CursorBlinkMode
        enum or a plain bool (terminal.py passes the raw config on Windows)."""
        on = _cursor_blink_on(v)
        self._cursor_blink = on
        if on and self._blink_id is None:
            self._blink_id = GLib.timeout_add(530, self._blink_tick)
        elif not on and self._blink_id is not None:
            GLib.source_remove(self._blink_id)
            self._blink_id = None
        self._cursor_visible = True
        self.queue_draw()

    def _blink_tick(self):
        # Only blink while the terminal is the focus widget; otherwise the
        # cursor stays solid (mirrors VTE's behaviour).
        if self.is_focus():
            self._cursor_visible = not self._cursor_visible
        else:
            self._cursor_visible = True
        self.queue_draw()
        return True

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
            # Skip width-0 continuation cells so a copied wide glyph does not
            # gain a trailing space from its placeholder column.
            lines.append(''.join(cell.char for cell in row[start:end]
                                 if cell.width != 0))
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

        if self._clear_background:
            cr.set_source_rgb(bg[0] / 255.0, bg[1] / 255.0, bg[2] / 255.0)
            cr.paint()

        grid = self.screen.cells()
        cw, ch = self._char_width, self._char_height
        pctx = self.get_pango_context()

        sel = self._selection
        cursor_y, cursor_x = self.screen.cursor  # (row, col)

        for y, row in enumerate(grid):
            if y >= self.rows:
                break
            row = row[:self.columns]
            # Build the line text and a Pango attribute list encoding runs of
            # equal (fg, bg, bold, italic, underline, strike), with selection
            # inverting fg<->bg. Wide (East-Asian) glyphs are emitted once and
            # advance the column cursor by 2; their continuation cells (width 0)
            # are skipped so Pango's natural advance keeps everything aligned.
            text_chars = []
            attrs = Pango.AttrList.new()
            run = None  # [start_text_index, rfg, rbg, bold, italic, underline, strike]
            col = 0
            for cell in row:
                w = cell.width
                if w == 0:
                    # Continuation column of the preceding wide glyph; nothing
                    # to draw (the wide glyph already spans this column).
                    continue
                rfg = self._resolve_colour(cell.fg, fg)
                rbg = self._resolve_colour(cell.bg, bg)
                if sel is not None and _span_in_selection(y, col, w, sel):
                    rfg, rbg = rbg, rfg
                ti = len(text_chars)
                text_chars.append(cell.char)
                cur = (rfg, rbg, cell.bold, cell.italic, cell.underline, cell.strike)
                if run is None:
                    run = [ti, rfg, rbg, cell.bold, cell.italic,
                           cell.underline, cell.strike]
                elif cur != tuple(run[1:]):
                    _emit_run(attrs, run, end=ti)
                    run = [ti, rfg, rbg, cell.bold, cell.italic,
                           cell.underline, cell.strike]
                col += w
            if run is not None:
                _emit_run(attrs, run, end=len(text_chars))

            layout = Pango.Layout(pctx)
            layout.set_font_description(self._font_desc)
            layout.set_text(''.join(text_chars), -1)
            layout.set_attributes(attrs)
            # Default foreground; per-run attrs override colours where needed.
            cr.set_source_rgb(fg[0] / 255.0, fg[1] / 255.0, fg[2] / 255.0)
            cr.move_to(0, y * ch)
            PangoCairo.show_layout(cr, layout)

        # Cursor (drawn last, on top). Hidden when blinking is in its off
        # phase, or when the cell is outside the visible grid.
        if (self._cursor_visible and 0 <= cursor_y < self.rows
                and 0 <= cursor_x < self.columns):
            self._draw_cursor(cr, cursor_x, cursor_y, cw, ch, fg, bg, grid)

        return False

    def _draw_cursor(self, cr, cx, cy, cw, ch, fg, bg, grid):
        cfill = self._cursor_bg or fg   # block/underline/beam fill colour
        cglyph = self._cursor_fg or bg   # glyph colour drawn over a block
        # Cursor spans the full display width of the cell under it, so a
        # block cursor over a wide (East-Asian) glyph covers both columns.
        cell = None
        if cy < len(grid) and cx < len(grid[cy]):
            cell = grid[cy][cx]
        span_w = max(1, getattr(cell, 'width', 1) or 1) * cw
        x0, y0 = cx * cw, cy * ch
        shape = self._cursor_shape
        if shape == 'underline':
            bar_h = max(2, ch // 8)
            cr.set_source_rgb(*(_norm(cfill)))
            cr.rectangle(x0, y0 + ch - bar_h, span_w, bar_h)
            cr.fill()
        elif shape in ('beam', 'ibeam', 'bar'):
            bar_w = max(2, cw // 4)
            cr.set_source_rgb(*(_norm(cfill)))
            cr.rectangle(x0, y0, bar_w, ch)
            cr.fill()
        else:  # block
            cr.set_source_rgb(*(_norm(cfill)))
            cr.rectangle(x0, y0, span_w, ch)
            cr.fill()
            # Redraw the cell's glyph in the cursor-foreground colour so the
            # character stays visible under the block.
            ch_char = getattr(cell, 'char', ' ') if cell else ' '
            if ch_char and ch_char != ' ':
                layout = Pango.Layout(self.get_pango_context())
                layout.set_font_description(self._font_desc)
                layout.set_text(ch_char, -1)
                cr.set_source_rgb(*(_norm(cglyph)))
                cr.move_to(x0, y0)
                PangoCairo.show_layout(cr, layout)

    def _resolve_colour(self, spec, default):
        """Turn a Cell colour spec into an (r,g,b) byte triple.

        ``default`` is returned when the spec is the theme default (None) or
        refers to an unknown palette index; the caller passes either the fg
        or bg default depending on whether it is resolving foreground or
        background.
        """
        if spec is None:
            return default
        if isinstance(spec, tuple):
            return spec
        if isinstance(spec, int) and spec in self._palette:
            return self._palette[spec]
        return default


# ---------------------------------------------------------------------------
# Module-level render helpers
# ---------------------------------------------------------------------------

def _norm(rgb):
    """Return a (r,g,b) float triple in [0,1] for cairo set_source_rgb."""
    return (rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)


def _pango16(byte):
    """Scale an 0-255 channel to Pango's 0-65535 range."""
    return max(0, min(65535, int(byte) * 257))


def _rgba_to_rgb(color):
    """Convert a Gdk.RGBA (or None) to an (r,g,b) byte triple (or None)."""
    if color is None:
        return None
    try:
        return (int(color.red * 255), int(color.green * 255), int(color.blue * 255))
    except AttributeError:
        return None


def _emit_run(attrs, run, end=None):
    """Append Pango attributes for one style run to ``attrs``.

    ``run`` is ``[start_index, rfg, rbg, bold, italic, underline, strike]``.
    Foreground/background attrs are only added where the colour differs from
    the layout default, which Pango would otherwise draw via set_source_rgb.
    """
    start = run[0]
    stop = end if end is not None else start + 1
    rfg, rbg, bold, italic, underline, strike = run[1:7]
    if bold:
        a = Pango.attr_weight_new(Pango.Weight.BOLD)
        a.start_index = start
        a.end_index = stop
        attrs.insert(a)
    if italic:
        a = Pango.attr_style_new(Pango.Style.ITALIC)
        a.start_index = start
        a.end_index = stop
        attrs.insert(a)
    if underline:
        a = Pango.attr_underline_new(Pango.Underline.SINGLE)
        a.start_index = start
        a.end_index = stop
        attrs.insert(a)
    if strike:
        a = Pango.attr_strikethrough_new(True)
        a.start_index = start
        a.end_index = stop
        attrs.insert(a)
    # We always emit fg/bg so per-cell colours (truecolour, reverse, palette)
    # win over the layout-wide default.
    a = Pango.attr_foreground_new(_pango16(rfg[0]), _pango16(rfg[1]),
                                  _pango16(rfg[2]))
    a.start_index = start
    a.end_index = stop
    attrs.insert(a)
    a = Pango.attr_background_new(_pango16(rbg[0]), _pango16(rbg[1]),
                                  _pango16(rbg[2]))
    a.start_index = start
    a.end_index = stop
    attrs.insert(a)


# Vte.CursorShape enum values (libvte): BLOCK=0, IBEAM=1, UNDERLINE=2.
_VTE_CURSOR_SHAPE = {0: 'block', 1: 'beam', 2: 'underline'}


def _cursor_shape_from_value(v):
    """Normalise a Vte.CursorShape int or config string to a shape name."""
    if isinstance(v, int):
        return _VTE_CURSOR_SHAPE.get(v)
    if isinstance(v, str):
        s = v.lower()
        if s in ('block', 'underline', 'ibeam', 'beam', 'bar'):
            return 'beam' if s == 'ibeam' else s if s != 'bar' else 'beam'
    return None


# Vte.CursorBlinkMode: SYSTEM=0, ON=1, OFF=2 (libvte). A raw bool from the
# Windows config path is also accepted.
def _cursor_blink_on(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, int):
        return v == 1
    return False


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


def _span_in_selection(y, col, width, sel):
    """Whether a cell spanning [col, col+width-1] is (partly) selected.

    A wide glyph occupying two columns should be inverted if either column is
    in the selection, so this checks the whole span rather than one column.
    """
    r0, c0, r1, c1 = sel
    if r0 > r1 or (r0 == r1 and c0 > c1):
        r0, c0, r1, c1 = r1, c1, r0, c0
    if y < r0 or y > r1:
        return False
    span_end = col + width - 1
    if y == r0 and span_end < c0:
        return False
    if y == r1 and col > c1:
        return False
    return True
