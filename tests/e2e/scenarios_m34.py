"""m34 E2E: HiDPI (GDK_SCALE=2 on Xvfb) and a headless Wayland smoke test
(weston --backend=headless, GDK_BACKEND=wayland).  Import-safe.

14-hidpi-scale2     GDK_SCALE=2: cell grid is half the scale-1 column count
                    for the same device-px window; overlay maximise dims the
                    (24 device px) margin and restores; session size is in
                    logical px; no traceback.
15-hidpi-autofont   stepped autofont tiers at GDK_SCALE=2 are the same as at
                    scale 1 (decided in cells, not px): 1 pane / stacked 1.0,
                    2x2 grid 0.8.
16-wayland-smoke    session seeded on X11 (split + cd + maximised pane +
                    window position) -> restored natively on Wayland: shells,
                    cwds, maximised pane; the Wayland save drops the
                    position but keeps size/maximised/layout; no WINDOWID in
                    the shells; clean SIGTERM; second Wayland run restores
                    again, at output scale 2.  SKIP without weston.
"""
import os
import shutil
import signal
import subprocess
import time

from tests.e2e.harness import (E2ESkip, check, wait_for, region_mean,
                               layout_nodes, terminal_dirs)
from tests.e2e.scenarios import (KEYS, _cd, _session_has_dirs, _edge_band,
                                 s5_autofont)


def _no_traceback(app):
    log = app.log()
    check('Traceback' not in log, 'traceback in terminator log:\n%s' %
          log[log.find('Traceback'):][:1500])


def _stty(app, name):
    app.type('stty size > %s' % app.marker(name))
    r, c = map(int, app.read_marker(name).split())
    return r, c


def _window_node(app):
    wins = layout_nodes(app.session(), 'Window')
    check(len(wins) == 1, 'expected 1 window in session, got %d' % len(wins))
    return wins[0]


# ---------------------------------------------------------------- 14
def s14_hidpi_scale2(app):
    # scale 1 reference at a fixed device size
    app.launch()
    win = app.main_windows()[0]
    app.resize(win, 1000, 700)
    time.sleep(0.8)
    r1, c1 = _stty(app, 'ref')
    app.signal(signal.SIGTERM)
    app.wait_exit()
    # same device size at GDK_SCALE=2
    app.env['GDK_SCALE'] = '2'
    app.launch()
    win = app.main_windows()[0]
    app.resize(win, 1000, 700)
    time.sleep(0.8)
    r2, c2 = _stty(app, 'hidpi')
    app.notes.append('scale1 %dx%d, scale2 %dx%d' % (r1, c1, r2, c2))
    check(abs(c2 * 2 - c1) <= max(4, c1 * 0.12),
          'GDK_SCALE=2 cols %d not ~half of %d' % (c2, c1))
    # session size is logical px (~device/2)
    sw, sh = [int(v) for v in wait_for(
        lambda: _window_node(app).get('size'), 8, what='session size')]
    check(400 <= sw <= 560, 'session width %d not logical (~500)' % sw)
    # overlay maximise at scale 2 (12 logical px margin = 24 device px)
    app.key(KEYS['split_vert'], delay=1.0)
    app.wait_shells(2)
    before = app.screenshot('s2-before')
    app.key(KEYS['maximise'], delay=1.5)
    dimmed = app.screenshot('s2-maximised')
    band = _edge_band(app, win)
    m0, m1 = region_mean(before, band), region_mean(dimmed, band)
    check(m1 < m0 * 0.8, 'no dim at scale 2 (edge lum %.1f -> %.1f)' % (m0, m1))
    _, cm = _stty(app, 'max')
    check(cm > c2 * 0.8, 'maximised pane too narrow at scale 2 (%d cols)' % cm)
    app.key(KEYS['restore_maximised'], delay=1.5)
    restored = app.screenshot('s2-restored')
    m2 = region_mean(restored, band)
    check(m2 > m1 * 1.1 or m2 > 200, 'still dimmed at scale 2 (%.1f)' % m2)
    check(app.alive(), 'terminator died at scale 2')
    _no_traceback(app)


# ---------------------------------------------------------------- 15
def s15_hidpi_autofont(app):
    app.env['GDK_SCALE'] = '2'
    s5_autofont(app, size=(1560, 940))
    _no_traceback(app)


# ---------------------------------------------------------------- 16
class _Weston(object):
    def __init__(self, app, scale=1):
        self.app = app
        self.scale = scale
        self.socket = 'e2e-wl-%d' % os.getpid()
        self.proc = None

    def start(self):
        env = dict(self.app.env)
        env.pop('DISPLAY', None)
        log = open(os.path.join(self.app.root, 'weston-%d.log' % self.scale),
                   'w')
        self.proc = subprocess.Popen(
            ['weston', '--backend=headless', '--socket=%s' % self.socket,
             '--width=1600', '--height=1000', '--scale=%d' % self.scale,
             '--idle-time=0', '--no-config'],
            env=env, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True)
        sock = os.path.join(self.app.env['XDG_RUNTIME_DIR'], self.socket)
        wait_for(lambda: os.path.exists(sock) or self.proc.poll() is not None,
                 10, what='weston socket')
        check(self.proc.poll() is None, 'weston exited (rc %s)' %
              self.proc.returncode)
        return self

    def stop(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(5)
        self.proc = None


def _wayland_env(app, wl):
    env = dict(app.env)
    env.pop('DISPLAY', None)          # no X fallback: prove it is Wayland
    env['GDK_BACKEND'] = 'wayland'
    env['WAYLAND_DISPLAY'] = wl.socket
    env['WINDOWID'] = '424242'        # stale value from a launching terminal
    return env


def _shell_env(pid):
    with open('/proc/%d/environ' % pid, 'rb') as fh:
        return dict(kv.split(b'=', 1) for kv in fh.read().split(b'\0')
                    if b'=' in kv)


def _wayland_run(app, wl, dirs, tag):
    x11_env = app.env
    app.env = _wayland_env(app, wl)
    try:
        before = os.stat(app.session_path).st_mtime_ns
        app.launch(wait_windows=0)
    finally:
        app.env = x11_env
    wait_for(lambda: len(app.shells()) == len(dirs), 20,
             what='%d restored shells on Wayland (%s)' % (len(dirs), tag))
    wait_for(lambda: app.shell_cwds() == sorted(dirs), 10,
             what='restored cwds on Wayland (%s)' % tag)
    check('display backend: WAYLAND' in app.log(),
          'terminator did not use the Wayland backend')
    for sh in app.shells():
        check(b'WINDOWID' not in _shell_env(sh.pid),
              'stale WINDOWID leaked into a Wayland shell')
    # wait for a Wayland-side save
    wait_for(lambda: os.stat(app.session_path).st_mtime_ns != before, 15,
             what='session saved on Wayland (%s)' % tag)
    time.sleep(0.5)
    app.signal(signal.SIGTERM)
    rc = app.wait_exit()
    check(rc == 0, 'terminator exit code %s on Wayland (%s)' % (rc, tag))
    _no_traceback(app)
    sess = app.session()
    w = _window_node(app)
    check('position' not in w,
          'Wayland save kept a window position: %r' % w.get('position'))
    check(w.get('size') and int(w['size'][0]) > 100,
          'Wayland save lost the window size: %r' % w.get('size'))
    check(terminal_dirs(sess) == sorted(dirs),
          'Wayland save dirs=%s' % terminal_dirs(sess))
    check(any(n.get('maximised_pane') == 'True'
              for n in layout_nodes(sess, 'Terminal')),
          'maximised pane lost on Wayland (%s)' % tag)
    return sess


def s16_wayland_smoke(app):
    if not shutil.which('weston'):
        raise E2ESkip('weston not installed (apt-get install weston)')
    a, b = app.mkdir('wl_A'), app.mkdir('wl_B')
    # 1) seed on X11: split, cd, maximise one pane, a real position
    app.launch()
    win = app.main_windows()[0]
    _cd(app, a, 'WLSEED0')
    app.key(KEYS['split_horiz'], delay=1.0)
    _cd(app, b, 'WLSEED1')
    app.wait_shells(2)
    app.key(KEYS['maximise'], delay=1.5)
    wait_for(_session_has_dirs(app, [a, b]), 10, what='seed session')
    wait_for(lambda: any(n.get('maximised_pane') == 'True' for n in
                         layout_nodes(app.session(), 'Terminal')), 10,
             what='maximised pane in seed session')
    app.signal(signal.SIGTERM)
    app.wait_exit()
    check('position' in _window_node(app), 'X11 seed has no position')
    # 2) restore on Wayland (scale 1), 3) again at output scale 2
    for scale in (1, 2):
        wl = _Weston(app, scale).start()
        try:
            _wayland_run(app, wl, [a, b], 'scale %d' % scale)
        finally:
            wl.stop()
    app.notes.append('weston headless: restored 2 panes + maximised pane '
                     'at scale 1 and 2; positions dropped, sizes kept')


SCENARIOS = [
    ('14-hidpi-scale2', s14_hidpi_scale2, {}),
    ('15-hidpi-autofont', s15_hidpi_autofont, {}),
    ('16-wayland-smoke', s16_wayland_smoke, {}),
]
