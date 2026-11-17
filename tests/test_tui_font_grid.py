# 回归：字号换档后，TUI 的行列数仍等于窗格里的格子。TX-06。
"""A font-tier change must publish the grid the pane is actually drawing.

The tier used to land on a timer, after VTE had already told the program
the previous cell count. The program kept drawing that count, and the
smaller cells left the picture in the corner. The PTY size at the end of
a resize is the grid VTE is painting. A timer does not change the font
while that program is still in the foreground.
"""

import os
import struct
import tempfile

import fcntl
import termios
from gi.repository import GLib, Gtk, Vte

from terminatorlib.config import Config
from terminatorlib.terminal import Terminal


def _pump(ms):
    end = GLib.get_monotonic_time() + ms * 1000
    while GLib.get_monotonic_time() < end:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        GLib.usleep(2000)


def _pty_size(term):
    fd = term.vte.get_pty().get_fd()
    rows, cols, _yp, _xp = struct.unpack(
        'HHHH', fcntl.ioctl(fd, termios.TIOCGWINSZ, b'\0' * 8))
    return rows, cols


def _cleanup(term, win):
    for attr in ('_scroll_restore_idle', '_scroll_settle_timer',
                 '_auto_font_timer', '_pty_grid_assert_idle',
                 '_autofont_toast_timer'):
        sid = getattr(term, attr, None)
        if sid:
            GLib.source_remove(sid)
            setattr(term, attr, None)
    win.destroy()
    try:
        term.terminator.deregister_terminal(term)
    except ValueError:
        pass
    _pump(30)


_CHILD = r"""
import sys, time, struct, fcntl, termios, signal
log = open(sys.argv[1], 'w', buffering=1)
def size():
    rows, cols = struct.unpack('HHHH', fcntl.ioctl(1, termios.TIOCGWINSZ, b'\0'*8))[:2]
    return rows, cols
def note(why):
    rows, cols = size()
    log.write('%s %s %s\n' % (why, rows, cols))
    log.flush()
signal.signal(signal.SIGWINCH, lambda *_a: note('sig'))
if '--raw' in sys.argv:
    attr = termios.tcgetattr(1)
    attr[3] = attr[3] & ~(termios.ICANON | termios.ECHO)
    termios.tcsetattr(1, termios.TCSANOW, attr)
note('start')
time.sleep(float(sys.argv[2]))
note('end')
"""


def _spawn(term, log_path, seconds, raw=False):
    script = tempfile.NamedTemporaryFile(
        'w', suffix='.py', delete=False)
    script.write(_CHILD)
    script.close()
    argv = [sys_executable(), script.name, log_path, str(seconds)]
    if raw:
        argv.append('--raw')
    _result, pid = term.vte.spawn_sync(
        Vte.PtyFlags.DEFAULT, None, argv, None,
        GLib.SpawnFlags.DEFAULT, None, None, None)
    term.pid = pid
    return script.name


def sys_executable():
    import sys
    return sys.executable


def _read_log(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return [line.split() for line in fh if line.strip()]


def test_resize_publishes_the_tier_the_pane_is_drawing():
    cfg = Config()
    saved = cfg['reading_measure_min_cols']
    cfg['reading_measure_min_cols'] = 60
    log_path = tempfile.mktemp(prefix='tui-grid-', suffix='.log')
    script = None
    term = Terminal()
    win = Gtk.Window()
    win.set_default_size(1400, 800)
    win.set_focus_on_map(False)
    paned = Gtk.Paned.new(Gtk.Orientation.HORIZONTAL)
    paned.pack1(term, True, False)
    paned.pack2(Gtk.Box(), True, False)
    win.add(paned)
    try:
        win.show_all()
        _pump(40)
        paned.set_position(480)
        _pump(80)
        script = _spawn(term, log_path, 2.0)
        _pump(400)
        rows, cols = _pty_size(term)
        assert term.vte.get_font_scale() < 0.99
        assert rows == term.vte.get_row_count()
        assert cols == term.vte.get_column_count()
        cell = term.vte.get_char_width()
        alloc = term.vte.get_allocated_width()
        assert abs(cols - int(alloc / cell)) <= 1
        # The 100% cell is wider, so the same pane holds fewer columns.
        base = cell / term.vte.get_font_scale()
        assert cols > int(alloc / base)
        last = _read_log(log_path)[-1]
        assert int(last[1]) == rows and int(last[2]) == cols
    finally:
        cfg['reading_measure_min_cols'] = saved
        _cleanup(term, win)
        if script:
            os.unlink(script)
        if os.path.exists(log_path):
            os.unlink(log_path)


def test_timer_does_not_change_font_under_a_running_tui():
    cfg = Config()
    saved = cfg['reading_measure_min_cols']
    log_path = tempfile.mktemp(prefix='tui-hold-', suffix='.log')
    script = None
    term = Terminal()
    win = Gtk.Window()
    win.set_default_size(1100, 700)
    win.set_focus_on_map(False)
    win.add(term)
    try:
        win.show_all()
        _pump(200)
        assert term.vte.get_font_scale() == 1.0
        scale = term.vte.get_font_scale()
        grid = (term.vte.get_row_count(), term.vte.get_column_count())
        script = _spawn(term, log_path, 0.8, raw=True)
        _pump(150)
        cfg['reading_measure_min_cols'] = 500
        term._auto_font_last_change_ms = 0
        term.update_auto_font_scale()
        _pump(200)
        assert term.vte.get_font_scale() == scale
        assert (term.vte.get_row_count(), term.vte.get_column_count()) == grid
        assert _pty_size(term) == grid
        kinds = [row[0] for row in _read_log(log_path)]
        assert 'sig' not in kinds
    finally:
        cfg['reading_measure_min_cols'] = saved
        _cleanup(term, win)
        if script:
            os.unlink(script)
        if os.path.exists(log_path):
            os.unlink(log_path)
