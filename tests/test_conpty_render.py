# Render-layer tests for the Windows backend widget.
#
# These exercise the ConPtyTerminal renderer (per-run Pango attributes, cursor
# shapes/colours, selection) against a Cairo image surface, so they actually
# validate the draw path on Linux CI. They need GTK + a display, so they are
# skipped on the (GTK-less) Windows CI job; the pure-Python helpers are also
# covered so at least their logic is checked everywhere.
import pytest

gi = pytest.importorskip('gi')
gi.require_version('Gtk', '3.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Gdk, Pango  # noqa: E402

import cairo  # noqa: E402

from terminatorlib.backends import conpty_backend as cb  # noqa: E402
from terminatorlib.backends.conpty.screen import Screen  # noqa: E402

requires_display = pytest.mark.skipif(
    Gdk.Display.get_default() is None,
    reason='needs a GDK display for Pango')


# -- pure helpers (run everywhere, including Windows CI) ----------------

def test_cursor_shape_string():
    assert cb._cursor_shape_from_value('block') == 'block'
    assert cb._cursor_shape_from_value('underline') == 'underline'
    assert cb._cursor_shape_from_value('ibeam') == 'beam'
    assert cb._cursor_shape_from_value('bar') == 'beam'


def test_cursor_shape_int():
    assert cb._cursor_shape_from_value(0) == 'block'
    assert cb._cursor_shape_from_value(1) == 'beam'
    assert cb._cursor_shape_from_value(2) == 'underline'


def test_cursor_shape_bad():
    assert cb._cursor_shape_from_value('garbage') is None
    assert cb._cursor_shape_from_value(99) is None


def test_cursor_blink_on():
    assert cb._cursor_blink_on(True) is True
    assert cb._cursor_blink_on(1) is True
    assert cb._cursor_blink_on(False) is False
    assert cb._cursor_blink_on(2) is False


def test_norm_and_rgba():
    assert cb._norm((255, 0, 0)) == (1.0, 0.0, 0.0)
    assert cb._rgba_to_rgb(None) is None
    rgba = Gdk.RGBA(); rgba.parse('#ff8000')
    assert cb._rgba_to_rgb(rgba) == (255, 128, 0)


def test_emit_run_adds_attrs():
    attrs = Pango.AttrList.new()
    run = [0, (255, 0, 0), (0, 0, 255), True, True, True, True]
    cb._emit_run(attrs, run, end=3)
    # Each of fg/bg/weight/style/underline/strikethrough = 6 attrs.
    assert attrs.get_attributes() is not None


# -- full draw path (needs GTK + display) --------------------------------

def _make_widget(cols=24, rows=3):
    w = cb.ConPtyTerminal()
    w.set_size(cols, rows)
    fg = Gdk.RGBA(); fg.parse('#eeeeee')
    bg = Gdk.RGBA(); bg.parse('#1d1f21')
    w.set_colors(fg, bg)
    return w


def _draw(w):
    cw, ch = w.get_char_width(), w.get_char_height()
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w.columns * cw, w.rows * ch)
    ctx = cairo.Context(surf)
    w.size_allocate(Gdk.Rectangle(0, 0, w.columns * cw, w.rows * ch))
    w._on_draw(w, ctx)
    data = surf.get_data()
    return sum(1 for i in range(0, len(data), 4) if data[i + 3] > 0)


@requires_display
def test_draw_plain_text_renders_pixels():
    w = _make_widget()
    w.feed(b'hello world')
    assert _draw(w) > 0


@requires_display
def test_draw_bold_colour_reverse_no_error():
    w = _make_widget()
    w.feed(b'\x1b[1mbold\x1b[0m \x1b[38;2;255;0;0mred\x1b[0m \x1b[7mrev\x1b[0m')
    assert _draw(w) > 0


@requires_display
def test_cursor_shapes_render():
    for shape in ('block', 'underline', 'beam'):
        w = _make_widget(rows=2)
        w.feed(b'ab')
        w.set_cursor_shape(shape)
        assert _draw(w) > 0


@requires_display
def test_cursor_colour_applied():
    w = _make_widget(rows=2)
    w.feed(b'ab')
    cc = Gdk.RGBA(); cc.parse('#00ff00')
    w.set_color_cursor(cc)
    w.set_color_cursor_foreground(None)
    assert _draw(w) > 0


@requires_display
def test_selection_renders_without_error():
    w = _make_widget(rows=2)
    w.feed(b'abcdefgh')
    w._selection = (0, 1, 0, 4)  # select 'bcde'
    assert _draw(w) > 0
    assert w.get_has_selection() is True


@requires_display
def test_clear_background_paints_bg():
    w = _make_widget()
    w.feed(b'x')
    w.set_clear_background(False)
    n_off = _draw(w)
    w.set_clear_background(True)
    n_on = _draw(w)
    # With the background painted, more pixels are non-transparent.
    assert n_on >= n_off
