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


def _pump(Gtk, until=None, timeout=3.0):
    """VTE parses fed data asynchronously; spin until `until()` holds."""
    import time
    end = time.monotonic() + timeout
    while True:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        if until is None or until() or time.monotonic() > end:
            return
        time.sleep(0.01)


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
    cfg['scrollback_cache_color'] = False
    fed[:] = []
    c.restore_into(T())
    assert b''.join(fed).decode('utf-8').startswith('red')
