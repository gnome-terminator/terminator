# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""backends.conpty.screen - terminal emulation via pyte.

On Linux, VTE performs VT/xterm emulation in C. On Windows we drive a
ConPTY (which gives us a process with a real PTY) but we still need to turn
the byte stream it produces into a renderable grid of cells. This module
wraps :mod:`pyte` (a pure-Python VT100/xterm terminal emulator) to do that
decoding, and adds the two pieces Terminator needs on top of the raw grid:

* a uniform :class:`Cell` value object (char + attributes + colour) so the
  renderer does not depend on pyte's internal representation;
* URL detection over the visible buffer, replacing VTE's
  ``match_add_regex`` / ``match_check_event`` (the same regexes from
  ``regex.py``, ported from PCRE2 to the :mod:`re` module).

This module is pure Python and has no Windows or GTK dependency, so it can
be unit-tested on Linux -- which is exactly how M5 validates the emulator
without a Windows box.
"""

from __future__ import print_function

import re
import unicodedata

try:
    import pyte
except ImportError:  # pragma: no cover - pyte is a Windows-only dep, absent on Linux CI
    pyte = None


# ANSI colour palette indices (matches pyte's defaults / xterm).
_DEFAULT_FG = None
_DEFAULT_BG = None


class Cell(object):
    """A single screen cell, normalised for the renderer.

    Attributes:
      char: the glyph (may be empty for a cleared cell).
      fg, bg: colour spec. Either ``None`` (use theme default), an integer
        0-15 (palette index), or an ``(r, g, b)`` tuple (true colour).
      bold, italic, underline, strike, reverse: style flags.
    """

    __slots__ = ('char', 'fg', 'bg', 'bold', 'italic', 'underline',
                 'strike', 'reverse', 'width')

    def __init__(self, char=' ', fg=None, bg=None, bold=False, italic=False,
                 underline=False, strike=False, reverse=False, width=1):
        self.char = char or ' '
        self.fg = fg
        self.bg = bg
        self.bold = bold
        self.italic = italic
        self.underline = underline
        self.strike = strike
        self.reverse = reverse
        # Display width in terminal columns: 1 for a normal glyph, 2 for an
        # East-Asian wide glyph, 0 for a continuation/placeholder cell (the
        # second column of a wide char, which pyte leaves as an empty char).
        self.width = width

    def clone(self):
        return Cell(self.char, self.fg, self.bg, self.bold, self.italic,
                    self.underline, self.strike, self.reverse, self.width)


def _display_width(ch):
    """Terminal display width (columns) of a single character.

    East-Asian wide/fullwidth glyphs occupy 2 columns; everything else 1.
    Zero-width combinators are rare in raw terminal output and treated as 1
    (they would be drawn onto the previous cell by a real terminal).
    """
    if not ch:
        return 0
    eaw = unicodedata.east_asian_width(ch)
    if eaw in ('W', 'F', 'A'):
        return 2
    return 1


def _colour(spec):
    """Decode a pyte colour spec into a Cell colour.

    pyte uses strings: ``'default'`` (theme default), a decimal palette index
    like ``'4'``, or ``'rgb:rrrr/gggg/bbbb'`` (1-4 hex digits per channel,
    XParseColor style). Returns ``None`` for the default, an int palette
    index, or an (r, g, b) tuple (0-255 each).
    """
    if spec is None or spec == 'default':
        return None
    if isinstance(spec, str) and spec.startswith('rgb:'):
        parts = spec[4:].split('/')
        if len(parts) == 3:
            out = []
            for p in parts:
                v = int(p, 16)
                # Normalise 1/2/4-digit channels to 0-255.
                scale = 255 // ((1 << (4 * len(p))) - 1)
                out.append(min(255, v * scale))
            return tuple(out)
    if isinstance(spec, str) and len(spec) == 6:
        # pyte encodes 24-bit colour as a bare 6-hex-digit string ('ff0000').
        try:
            return (int(spec[0:2], 16), int(spec[2:4], 16), int(spec[4:6], 16))
        except ValueError:
            pass
    try:
        idx = int(spec)
        if 0 <= idx <= 255:
            return idx
    except (TypeError, ValueError):
        pass
    return None


class Screen(object):
    """A renderable terminal screen backed by pyte.

    Feed bytes from the ConPTY output stream via :meth:`feed`; query the grid
    via :meth:`cells`; match URLs via :meth:`match_urls`.
    """

    def __init__(self, columns=80, rows=24):
        self.columns = columns
        self.rows = rows
        if pyte is None:
            # Fallback: a no-op screen so the module imports on Linux for
            # testing of the non-emulation pieces. Real emulation requires
            # pyte (installed on Windows via setup.py markers).
            self._screen = None
            self._stream = None
            self._buffer = []
        else:
            self._screen = pyte.Screen(columns, rows)
            # ConPTY yields bytes; ByteStream is the bytes-friendly entrypoint
            # (pyte.Stream expects str and would raise on bytes input).
            self._stream = pyte.ByteStream(self._screen)
        self.title = ''

    def resize(self, columns, rows):
        self.columns = columns
        self.rows = rows
        if self._screen is not None:
            try:
                # pyte's Screen() takes (columns, lines) at construction but
                # resize() takes (lines, columns); use keywords to be safe.
                self._screen.resize(lines=rows, columns=columns)
            except Exception:
                pass

    def feed(self, data):
        """Consume bytes/str emitted by the PTY and update the grid."""
        if self._stream is None:
            if isinstance(data, bytes):
                data = data.decode('utf-8', 'replace')
            self._buffer.append(data)
            return
        if isinstance(data, str):
            data = data.encode('utf-8')
        try:
            self._stream.feed(data)
        except Exception:
            # pyte is strict; never let an emulation bug kill the terminal.
            pass
        # Track window title from the OSC 0/2 sequences pyte exposes.
        title = getattr(self._screen, 'title', None)
        if title:
            self.title = title

    @property
    def cursor(self):
        """(row, col) of the cursor, clamped to the grid."""
        if self._screen is None:
            return (0, 0)
        try:
            return (self._screen.cursor.y, self._screen.cursor.x)
        except Exception:
            return (0, 0)

    def cells(self):
        """Return the grid as a list of rows, each a list of :class:`Cell`.

        Without pyte this yields the raw accumulated text split into rows of
        ``columns`` width, which is enough to smoke-test the renderer.
        """
        if self._screen is None:
            text = ''.join(self._buffer)
            rows = []
            for r in range(self.rows):
                start = r * self.columns
                line = text[start:start + self.columns]
                rows.append([Cell(c) for c in line.ljust(self.columns)])
            return rows

        grid = []
        # pyte's buffer is a dict-of-dict of Char objects keyed [y][x]. The
        # 'display' list is a rendered-string convenience but carries no
        # attributes, so we read the buffer for char + style together.
        buf = self._screen.buffer
        for y in range(self.rows):
            row = []
            row_buf = buf.get(y, {})
            for x in range(self.columns):
                src = row_buf.get(x)
                if src is None:
                    row.append(Cell())
                    continue
                raw = getattr(src, 'data', '')
                if raw == '':
                    # pyte leaves an empty char for the second column of a
                    # wide glyph; mark it as a continuation (width 0) so the
                    # renderer can skip it and let the wide glyph span both.
                    row.append(Cell(char=' ', width=0))
                    continue
                fg = _colour(getattr(src, 'fg', None))
                bg = _colour(getattr(src, 'bg', None))
                if getattr(src, 'reverse', False):
                    fg, bg = bg, fg
                row.append(Cell(
                    char=raw,
                    fg=fg, bg=bg,
                    bold=bool(getattr(src, 'bold', False)),
                    italic=bool(getattr(src, 'italics', False)),
                    underline=bool(getattr(src, 'underscore', False)),
                    strike=bool(getattr(src, 'strikethrough', False)),
                    reverse=False,  # already applied to fg/bg above
                    width=_display_width(raw),
                ))
            grid.append(row)
        return grid

    def text(self):
        """The visible screen as plain text (for clipboard/selection)."""
        if self._screen is None:
            return ''.join(self._buffer)
        try:
            return '\n'.join(self._screen.display)
        except Exception:
            return ''

    # -- URL matching (replaces Vte match_add_regex / match_check_event) --

    # Ported from terminatorlib/regex.py (PCRE2 patterns) to the re module.
    _URL_RE = re.compile(
        r'''(?:                  # one of:
            (?:https?|ftp)://    #   scheme://
            | (?:www\.|ftp\.)    #   or bare www./ftp.
            | \w+@[\w.\-]+\.\w+  #   or user@host (email-ish)
        )
        (?:                       # host/path/fragment/query
            [^\s<>"']+
        )?
        ''', re.VERBOSE | re.IGNORECASE)

    def match_urls(self):
        """Return a list of (start_offset, url) for URLs on the visible screen.

        Offsets are character offsets into :meth:`text` output; the renderer
        maps these to cell coordinates for hit-testing (the equivalent of
        VTE's ``match_check_event``).
        """
        text = self.text()
        return [(m.start(), m.group(0)) for m in self._URL_RE.finditer(text)]
