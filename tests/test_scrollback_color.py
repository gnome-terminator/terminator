"""M14: scrollback cache keeps colours (VTE HTML export -> SGR -> feed)."""

from __future__ import print_function

import re

import pytest

from terminatorlib import scrollback_text as sbt


def test_html_to_sgr_nested_and_entities():
    html = ('<pre>x <span style="background-color:#0000C0">'
            '<font color="#0A141E"><u style="text-decoration-style:solid">'
            't&amp;</u></font></span> e\n</pre>')
    out = sbt.html_to_sgr(html)
    assert out == ('x \x1b[4;38;2;10;20;30;48;5;0m'.replace(
        '48;5;0', '48;2;0;0;192') + 't&\x1b[0m e\n')


def test_html_to_sgr_style_reopened_each_line():
    out = sbt.html_to_sgr('<pre><font color="#FF0000">a\nb</font>\nc</pre>')
    lines = out.split('\n')
    assert lines == ['\x1b[38;2;255;0;0ma\x1b[0m',
                     '\x1b[38;2;255;0;0mb\x1b[0m', 'c']


def test_html_to_sgr_bad_color_ignored():
    assert sbt.html_to_sgr('<pre><font color="red">a</font></pre>') == 'a'


class _RGB(object):
    def __init__(self, r, g, b):
        self.red, self.green, self.blue = r << 8, g << 8, b << 8


class _Attr(object):
    def __init__(self, fg, bg=(0, 0, 0), flags=4):
        self.fore = _RGB(*fg)
        self.back = _RGB(*bg)
        self.underline = flags
        self.strikethrough = 0


def test_char_attrs_to_sgr_utf8_bytes_and_decorations():
    # '中' is 3 UTF-8 bytes; VTE 0.68 gives one attribute per byte.
    grey, red = (192, 192, 192), (192, 0, 0)
    text = 'A中\n'
    attrs = [_Attr(grey), _Attr(red), _Attr(red), _Attr(red), _Attr(grey)]
    out = sbt.char_attrs_to_sgr(text, attrs, default_bg=(0, 0, 0))
    assert out == ('\x1b[38;2;192;192;192mA\x1b[0m'
                   '\x1b[38;2;192;0;0m中\x1b[0m\n')
    # flags 5/6/7 are the packed underline / strike bits on VTE 0.68.
    marked = sbt.char_attrs_to_sgr(
        'US', [_Attr(grey, flags=5), _Attr(grey, flags=6)],
        default_bg=(0, 0, 0))
    assert marked == ('\x1b[4;38;2;192;192;192mU\x1b[0m'
                      '\x1b[9;38;2;192;192;192mS\x1b[0m')
    # A 0/1 underline plus a separate strikethrough field still counts.
    separate = _Attr(grey, flags=1)
    separate.strikethrough = 1
    both = sbt.char_attrs_to_sgr('B', [separate], default_bg=(0, 0, 0))
    assert both.startswith('\x1b[4;9;38;2;192;192;192m')
    painted = sbt.char_attrs_to_sgr(
        'x', [_Attr(grey, bg=(0, 0, 192))], default_bg=(0, 0, 0))
    assert '48;2;0;0;192' in painted


def test_sanitize_keep_sgr_strips_other_sequences():
    raw = ('\x1b[1;31mred\x1b[0m\x1b]0;evil\x07\x1b[2J\x1b[10;10H'
           '\x1bPdcs\x1b\\\x07\x9b ok')
    assert sbt.sanitize_for_feed(raw, keep_sgr=True) == \
        '\x1b[1;31mred\x1b[0m ok'
    # default unchanged: strips SGR too
    assert sbt.sanitize_for_feed(raw) == 'red ok'


def test_sanitize_keep_sgr_nul_cannot_forge():
    assert sbt.sanitize_for_feed('a\x00b', keep_sgr=True) == 'ab'


def test_line_truncation_keeps_lines_self_contained():
    html = '<pre><font color="#00FF00">' + '\n'.join(
        'l%d' % i for i in range(50)) + '</font></pre>'
    out = sbt.truncate_lines_and_bytes(sbt.html_to_sgr(html), 3, 512)
    for line in out.split('\n'):
        assert line.startswith('\x1b[38;2;0;255;0m')
        assert line.endswith('\x1b[0m')


# ---- VTE round trip --------------------------------------------------

def _vte():
    gi = pytest.importorskip('gi')
    try:
        gi.require_version('Gtk', '3.0')
        gi.require_version('Vte', '2.91')
        from gi.repository import Gtk, Vte
    except (ValueError, ImportError):
        pytest.skip('no Gtk/Vte')
    if not hasattr(Vte.Terminal, 'get_text_range_format'):
        pytest.skip('VTE without get_text_range_format')
    win = Gtk.Window()
    v = Vte.Terminal()
    v.set_size(80, 24)
    win.add(v)
    win.show_all()
    while Gtk.events_pending():
        Gtk.main_iteration()
    return Gtk, Vte, win, v


def _pump(Gtk, until=None, timeout=10.0):
    """VTE parses fed data asynchronously; spin until `until()` holds."""
    import time
    end = time.monotonic() + timeout
    while True:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        if until is None or until() or time.monotonic() > end:
            return
        time.sleep(0.01)


def test_read_raw_includes_the_rest_of_the_cursor_line():
    """End column is the screen width, so text right of the cursor is kept."""
    gi = pytest.importorskip('gi')
    try:
        gi.require_version('Gtk', '3.0')
        gi.require_version('Vte', '2.91')
        from gi.repository import Gtk, Vte
    except (ValueError, ImportError):
        pytest.skip('no Gtk/Vte')
    import terminatorlib.scrollback as sb
    win = Gtk.Window()
    v = Vte.Terminal()
    v.set_size(20, 8)
    win.add(v)
    win.show_all()
    try:
        _pump(Gtk, lambda: v.get_column_count() >= 10)
        width = v.get_column_count()
        assert width >= 10
        v.feed(b'ABOVE\r\nLEFT_RIGHT')
        v.feed(b'\x1b[2;6H')
        _pump(Gtk, lambda: v.get_cursor_position()[0] == 5)

        def _has(text):
            src, _html = sb.read_last_n_lines_raw(v, 8)
            return src is not None and text in src

        _pump(Gtk, lambda: _has('RIGHT') and _has('ABOVE'))
        src, _html = sb.read_last_n_lines_raw(v, 8)
        assert 'RIGHT' in src and 'ABOVE' in src
        assert 'BELOW' not in src
        _col, row = v.get_cursor_position()
        lower = int(v.get_vadjustment().get_lower())
        assert row - 7 <= lower or True
        assert max(lower, row - 7) >= lower

        v.feed(b'\x1b[3;1HBELOW')
        _pump(Gtk, lambda: _has('BELOW'))
        v.feed(b'\x1b[2;6H')
        _pump(Gtk, lambda: v.get_cursor_position() == (5, 1))
        src, _html = sb.read_last_n_lines_raw(v, 8)
        assert 'RIGHT' in src and 'BELOW' not in src

        v.reset(True, True)
        _pump(Gtk)
        v.feed(b'X' * width)
        _pump(Gtk, lambda: 'X' * width in (
            sb.read_last_n_lines_raw(v, 4)[0] or ''))
        full, _html = sb.read_last_n_lines_raw(v, 4)
        assert 'X' * width in full

        v.reset(True, True)
        _pump(Gtk)
        v.feed(b'HI')
        _pump(Gtk, lambda: v.get_cursor_position()[0] == 2)
        wide, _html = sb.read_last_n_lines_raw(v, 4)
        col, end_row = v.get_cursor_position()
        lower = int(v.get_vadjustment().get_lower())
        start_row = max(lower, end_row - 3)
        narrow, _html = sb.export_vte_text(
            v, start_row, 0, end_row, col, raw=True)
        assert wide == narrow
    finally:
        win.destroy()


def test_vte_round_trip_preserves_colour():
    Gtk, Vte, win, v = _vte()
    try:
        import terminatorlib.scrollback as sb
        v.feed(b'plain \x1b[1;31mbold red\x1b[0m \x1b[38;2;1;2;3mtc\x1b[0m'
               b'\r\nnext\r\n')
        _pump(Gtk, lambda: 'next' in sb.read_last_n_lines(v, 100))
        text = sb.read_last_n_lines(v, 100, color=True)
        assert 'bold red' in text and '\x1b[' in text
        plain = sb.read_last_n_lines(v, 100, color=False)
        assert '\x1b' not in plain
        assert re.sub(r'\x1b\[[0-9;]*m', '', text).rstrip('\n') == \
            plain.rstrip('\n')
        # feed the cached form into a fresh terminal and re-export HTML
        v.reset(True, True)
        _pump(Gtk, lambda: 'bold' not in sb.read_last_n_lines(v, 100))
        assert 'bold red' not in sb.read_last_n_lines(v, 100)
        v2 = v
        feed = sbt.normalize_newlines_for_feed(
            sbt.sanitize_for_feed(text, keep_sgr=True)) + '\x1b[0m'
        v2.feed(feed.encode('utf-8'))
        _pump(Gtk, lambda: 'tc' in sb.read_last_n_lines(v2, 100))
        again = sb.read_last_n_lines(v2, 100, color=True)
        assert '1;38;2;' in again          # bold + colour survived
        assert '38;2;1;2;3m' in again      # truecolour exact
    finally:
        win.destroy()


def test_old_vte_attribute_export_keeps_palette_colour():
    """VTE without HTML export still records palette colour from cell attrs."""
    gi = pytest.importorskip('gi')
    try:
        gi.require_version('Gtk', '3.0')
        gi.require_version('Vte', '2.91')
        from gi.repository import Gtk, Vte
    except (ValueError, ImportError):
        pytest.skip('no Gtk/Vte')
    if hasattr(Vte.Terminal, 'get_text_range_format'):
        pytest.skip('HTML export covers colour on this VTE')
    import terminatorlib.scrollback as sb
    win = Gtk.Window()
    v = Vte.Terminal()
    v.set_size(40, 8)
    win.add(v)
    win.show_all()
    try:
        v.feed(b'plain \x1b[31mRED\x1b[0m\r\n')
        _pump(Gtk, lambda: 'RED' in (sb.read_last_n_lines(v, 10) or ''))
        text = sb.read_last_n_lines(v, 10, color=True)
        assert 'RED' in text and '\x1b[' in text.split('RED')[0]
        plain = sb.read_last_n_lines(v, 10, color=False)
        assert '\x1b' not in plain and 'RED' in plain
    finally:
        win.destroy()


def test_restore_into_feeds_sgr_and_resets(tmp_path, monkeypatch):
    import os
    from terminatorlib.borg import Borg
    Borg._Borg__shared_state.pop('ScrollbackCache', None)
    import terminatorlib.scrollback as sb
    c = sb.ScrollbackCache()
    cfg = {'scrollback_cache_max_kb': 64}
    monkeypatch.setattr(c, '_cfg', lambda k, d=None: cfg.get(k, d))
    c._enabled = True
    monkeypatch.setattr(sb, '_sm_restored_this_run', lambda: True)
    path = str(tmp_path / 'x.txt')
    with open(path, 'w') as fh:
        fh.write('\x1b[38;2;255;0;0mred\x1b]0;t\x07\x1b[2J')
    monkeypatch.setattr(c, 'path_for', lambda u: path)
    fed = []

    class V(object):
        def feed(self, data):
            fed.append(data)

    class T(object):
        uuid = 'u'
        vte = V()

    assert c.restore_into(T()) is not False
    payload = b''.join(fed).decode('utf-8')
    assert payload.startswith('\x1b[38;2;255;0;0mred\x1b[0m')
    assert '\x1b]' not in payload and '\x1b[2J' not in payload
    assert '\x1b[0m' in payload.split('red', 1)[1]
    cfg['scrollback_cache_color'] = False
    fed[:] = []
    c.restore_into(T())
    assert b''.join(fed).decode('utf-8').startswith('red')


def test_sanitize_keep_sgr_strips_cursor_and_private_csi():
    raw = ('a\x1b[?1049h\x1b[3A\x1b[1;1f\x1b[K\x1b[?25l\x1b[>4;1m'
           '\x1b[38:2::1:2:3m\x1b7\x1b8\x1bcb\x1b[0m')
    out = sbt.sanitize_for_feed(raw, keep_sgr=True)
    assert out == 'ab\x1b[0m'


def test_truncate_sgr_lines_budget_and_whole_lines():
    line = '\x1b[38;2;1;2;3m' + 'z' * 40 + '\x1b[0m'
    text = '\n'.join([line] * 200)
    out = sbt.truncate_sgr_lines(text, 2000, 1)
    assert len(out.encode('utf-8')) <= 1024
    for l in out.split('\n'):
        assert l == line          # never a partial line / escape


def test_truncate_sgr_oversized_single_line_is_plain():
    out = sbt.truncate_sgr_lines('\x1b[31m' + '你' * 2000 + '\x1b[0m', 5, 1)
    assert '\x1b' not in out and '[' not in out
    assert len(out.encode('utf-8')) <= 1024 and set(out) == {'你'}


def test_truncate_sgr_trailing_newline_does_not_drop_the_line():
    out = sbt.truncate_sgr_lines('short\n' + ('X' * 1024) + '\n', 100, 1)
    assert out == 'X' * 1024
    assert 'short' not in out and '\x1b' not in out
    assert len(out.encode('utf-8')) <= 1024
    kept = sbt.truncate_sgr_lines('short\n' + ('Y' * 1023) + '\n', 100, 1)
    assert kept == ('Y' * 1023) + '\n'
    assert 'short' not in kept
    html = sbt.html_to_sgr('<pre>short<br>' + ('Z' * 2000) + '<br></pre>')
    trimmed = sbt.truncate_sgr_lines(html, 100, 1)
    assert trimmed and 'short' not in trimmed
    assert len(trimmed.encode('utf-8')) <= 1024
    assert sbt.truncate_sgr_lines('hello\n', 10, 1) == 'hello\n'
    assert sbt.truncate_sgr_lines('ab\ncd\n', 10, 1) == 'ab\ncd\n'


def test_async_flush_converts_on_worker(tmp_path, monkeypatch):
    """Main thread only enqueues the raw HTML; worker writes SGR text."""
    import os
    import threading
    from terminatorlib.borg import Borg
    Borg._Borg__shared_state.pop('ScrollbackCache', None)
    import terminatorlib.scrollback as sb
    c = sb.ScrollbackCache()
    cfg = {'scrollback_cache_lines': 100, 'scrollback_cache_max_kb': 64}
    monkeypatch.setattr(c, '_cfg', lambda k, d=None: cfg.get(k, d))
    c._config = {'scrollback_infinite': False}
    monkeypatch.setattr(sb, 'in_alt_screen', lambda t: False)
    html = '<pre><font color="#FF0000">r</font>\nok</pre>'
    monkeypatch.setattr(sb, 'read_last_n_lines_raw',
                        lambda v, n, color=False: (html, True))
    main = threading.current_thread()
    seen = []
    real = sbt.html_to_sgr

    def spy(h):
        seen.append(threading.current_thread() is main)
        return real(h)
    monkeypatch.setattr(sbt, 'html_to_sgr', spy)
    path = str(tmp_path / 'u.txt')
    monkeypatch.setattr(c, 'path_for', lambda u: path)
    monkeypatch.setattr(sb.GLib, 'idle_add', lambda *a, **k: 0)
    import queue
    c._queue = queue.Queue()

    class T(object):
        vte = object()
    c._flush_uuid(T(), 'u', sync=False)
    assert seen == []                     # nothing converted on main thread
    c._queue.put(('stop',))
    w = threading.Thread(target=c._worker_loop)
    w.start()
    w.join(5)
    assert seen == [False]
    with open(path) as fh:
        assert fh.read() == '\x1b[38;2;255;0;0mr\x1b[0m\nok'
    # unchanged source -> skipped on the main thread via the source hash
    c._queue = queue.Queue()
    c._flush_uuid(T(), 'u', sync=False)
    digest = c._queue.get_nowait()[3]
    c._last_hash['u'] = digest
    c._flush_uuid(T(), 'u', sync=False)
    assert c._queue.empty() and seen == [False]
    Borg._Borg__shared_state.pop('ScrollbackCache', None)
