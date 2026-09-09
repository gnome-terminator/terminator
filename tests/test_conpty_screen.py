# Tests for the Windows terminal backend's pure-Python emulation layer.
#
# These run on Linux because backends/conpty/screen.py depends only on the
# standard library + pyte (no GTK, no Windows). They lock in the behaviour
# the ConPTY renderer relies on: feed -> grid, attributes, cursor, titles,
# URL matching. pyte must be installed (it is in setup.py's Windows extra;
# on Linux CI install it via `pip install pyte`).
import pytest

pyte = pytest.importorskip('pyte')

from terminatorlib.backends.conpty.screen import Screen, Cell, _colour


def test_feed_renders_to_grid():
    s = Screen(20, 2)
    s.feed(b'hi\r\nyo')
    rows = s.cells()
    assert ''.join(c.char for c in rows[0]).startswith('hi')
    assert ''.join(c.char for c in rows[1]).startswith('yo')


def test_bold_attribute_decoded():
    s = Screen(20, 1)
    s.feed(b'a\x1b[1mb\x1b[0mc')
    row = s.cells()[0]
    assert row[0].bold is False
    assert row[1].bold is True
    assert row[2].bold is False


def test_truecolour_decoded():
    s = Screen(20, 1)
    s.feed(b'\x1b[38;2;255;0;0mR')
    assert s.cells()[0][0].fg == (255, 0, 0)


def test_cursor_position():
    s = Screen(20, 2)
    s.feed(b'abc')
    assert s.cursor == (0, 3)  # (row, col)


def test_resize_updates_dims():
    s = Screen(10, 1)
    s.feed(b'0123456789')
    s.resize(5, 2)
    assert s.columns == 5
    assert s.rows == 2


def test_url_matching():
    # Wide enough that the whole line stays on a single visible row
    # (pyte wraps and scrolls narrow screens).
    s = Screen(120, 2)
    s.feed(b'see https://example.com/a?x=1 and ftp://h/files and www.site.io')
    urls = [u for _, u in s.match_urls()]
    assert any(u.startswith('https://example.com') for u in urls)
    assert any(u.startswith('ftp://h/files') for u in urls)
    assert any(u.startswith('www.site.io') for u in urls)


def test_colour_default_is_none():
    assert _colour(None) is None
    assert _colour('default') is None


def test_colour_palette_index():
    assert _colour('4') == 4


def test_colour_bare_hex():
    assert _colour('ff0000') == (255, 0, 0)


def test_text_for_clipboard():
    s = Screen(10, 2)
    s.feed(b'line1\r\nline2')
    assert 'line1' in s.text() and 'line2' in s.text()


def test_cell_clone_independent():
    a = Cell('x', bold=True)
    b = a.clone()
    b.bold = False
    assert a.bold is True


def test_display_width_wide():
    from terminatorlib.backends.conpty.screen import _display_width
    assert _display_width('A') == 1
    assert _display_width('中') == 2
    assert _display_width('。') == 2
    assert _display_width('') == 0


def test_wide_glyph_marked_width_two():
    s = Screen(20, 1)
    s.feed('AB中CD'.encode())
    row = s.cells()[0]
    assert row[2].char == '中' and row[2].width == 2


def test_wide_glyph_continuation_is_width_zero():
    s = Screen(20, 1)
    s.feed('AB中CD'.encode())
    row = s.cells()[0]
    # The column after a wide glyph is pyte's empty continuation cell.
    assert row[3].width == 0


def test_resize_keeps_buffer_correct():
    # Regression guard: pyte's resize() takes (lines, columns), the opposite
    # order of __init__. A swapped call used to scramble the grid (1-col wide).
    s = Screen(10, 1)
    s.feed('0123456789'.encode())
    s.resize(5, 2)
    assert s.columns == 5 and s.rows == 2
    # After resize to 5x2 the first row still holds the start of the text.
    first = ''.join(c.char for c in s.cells()[0][:5] if c.width != 0)
    assert first.startswith('0')


def test_cursor_after_wide_glyph_advances_two():
    s = Screen(20, 1)
    s.feed('AB中CD'.encode())
    # A,B(2 cols) + 中(2 cols) + C,D(2 cols) -> cursor at column 6.
    assert s.cursor == (0, 6)
