"""End-to-end GUI harness for the Terminator fork.

Launches the REAL ``terminator`` script under Xvfb (+ xfwm4 when present),
drives it with xdotool and inspects it from the outside: WM titles (xprop),
screenshots (ffmpeg x11grab + Pillow), session.json / scrollback cache
files and /proc (psutil).

This module is import-safe (no side effects) because the unit lane runs
pytest with --doctest-modules over the whole tree.  It is NOT a pytest
module; run it through tests/e2e/run_e2e.sh.
"""
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SHOT_DIR = os.environ.get('E2E_SHOTS', '/workspace/smoke/e2e')
# Same location tests/run_tests.sh and run_e2e.sh compile the stub schema to.
# m34: run_e2e.sh keys the directory by the stub's content (E2E_SCHEMA_DIR).
# Under tests/run_tests.sh (m30 opt-in) its fresh stub dir is reused.
_RUNNER_SCHEMAS = os.environ.get('GSETTINGS_SCHEMA_DIR', '')
if 'terminator-test-schemas' not in _RUNNER_SCHEMAS:
    _RUNNER_SCHEMAS = ''
SCHEMA_DIR = (os.environ.get('E2E_SCHEMA_DIR') or _RUNNER_SCHEMAS or
              os.path.join(os.environ.get('TMPDIR') or '/tmp',
                           'terminator-test-schemas-%d' % os.getuid()))
# Every process launched for a scenario inherits this env var (terminator ->
# VTE -> shells -> anything the shells start, incl. double-forked loops that
# escape the terminator process group and the pty hangup).  cleanup() sweeps
# /proc for it so nothing outlives the scenario.
MARK_ENV = 'TERMINATOR_E2E_ROOT'


def _isolated_env(home, root):
    """os.environ with HOME/XDG/DBus pointed away from the real user."""
    env = dict(os.environ)
    for k in list(env):
        # DBUS_*: never reach the real user's session bus (dconf/xfconf/a11y);
        # an autolaunched bus inherits MARK_ENV and is swept in cleanup.
        if k.startswith(('XDG_', 'DBUS_', 'GSETTINGS_')):
            del env[k]
    env.update({
        'HOME': home,
        'XDG_CONFIG_HOME': os.path.join(home, '.config'),
        'XDG_STATE_HOME': os.path.join(home, '.local', 'state'),
        'XDG_CACHE_HOME': os.path.join(home, '.cache'),
        'XDG_DATA_HOME': os.path.join(home, '.local', 'share'),
        'XDG_RUNTIME_DIR': os.path.join(root, 'run'),
        'NO_AT_BRIDGE': '1',
        MARK_ENV: root,
    })
    os.makedirs(env['XDG_RUNTIME_DIR'], mode=0o700, exist_ok=True)
    if os.path.isfile(os.path.join(SCHEMA_DIR, 'gschemas.compiled')):
        env['GSETTINGS_SCHEMA_DIR'] = SCHEMA_DIR
    # memory backend always: never write the real user's dconf database
    env['GSETTINGS_BACKEND'] = 'memory'
    return env


def kill_marked(root, sig=signal.SIGKILL):
    """Kill every process whose environment carries MARK_ENV=root.
    Returns the number of processes signalled."""
    import psutil
    want = '%s=%s' % (MARK_ENV, root)
    n = 0
    me = os.getpid()
    for p in psutil.process_iter(['pid']):
        if p.info['pid'] == me:
            continue
        try:
            with open('/proc/%d/environ' % p.info['pid'], 'rb') as fh:
                envb = fh.read().split(b'\0')
        except OSError:
            continue
        if want.encode() in envb:
            try:
                p.send_signal(sig)
                n += 1
            except psutil.Error:
                pass
    return n

BASHRC = r'''
PS1='$ '
unset PROMPT_COMMAND
HISTFILE=/dev/null
'''

LIGHT_PROFILE = '''[global_config]
[profiles]
  [[default]]
    use_theme_colors = False
    background_color = "#ffffff"
    foreground_color = "#000000"
'''


class E2EFailure(AssertionError):
    pass


class E2ESkip(Exception):
    """Scenario cannot run here (missing optional tool); reported SKIP."""


def check(cond, msg):
    if not cond:
        raise E2EFailure(msg)


def run(cmd, timeout=10, check_rc=False, env=None):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=timeout, env=env, universal_newlines=True)
    if check_rc and p.returncode != 0:
        raise E2EFailure('%s failed: %s' % (cmd, p.stderr.strip()))
    return p.stdout


def wait_for(pred, timeout=10.0, interval=0.2, what='condition'):
    """Poll pred() until truthy; return its value or raise E2EFailure."""
    end = time.monotonic() + timeout
    last_exc = None
    while time.monotonic() < end:
        try:
            v = pred()
            if v:
                return v
        except Exception as ex:  # pylint: disable=broad-except
            last_exc = ex
        time.sleep(interval)
    raise E2EFailure('timeout (%.1fs) waiting for %s%s' % (
        timeout, what, (' (last error: %s)' % last_exc) if last_exc else ''))


# --------------------------------------------------------------------------
# X display
# --------------------------------------------------------------------------
class XDisplay(object):
    """Private Xvfb (+ light WM).  One per suite run."""

    def __init__(self, width=1600, height=1000, wm=None):
        self.width, self.height = width, height
        self.wm = wm if wm is not None else os.environ.get('E2E_WM', 'xfwm4')
        self.procs = []
        self.display = None
        self.wm_root = None

    def start(self):
        """Start Xvfb (display number picked by Xvfb itself via -displayfd,
        so we never attach to somebody else's server) and the WM.  On any
        failure everything already started is stopped again."""
        try:
            self._start()
        except BaseException:
            self.stop()
            raise
        return self

    def _start(self):
        rfd, wfd = os.pipe()
        try:
            self.procs.append(subprocess.Popen(
                ['Xvfb', '-displayfd', str(wfd), '-screen', '0',
                 '%dx%dx24' % (self.width, self.height), '-nolisten', 'tcp'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                pass_fds=(wfd,), start_new_session=True))
            os.close(wfd)
            wfd = None
            num = b''
            end = time.monotonic() + 15
            import select
            while not num.endswith(b'\n'):
                left = end - time.monotonic()
                if left <= 0 or self.procs[0].poll() is not None:
                    raise E2EFailure('Xvfb did not start')
                if select.select([rfd], [], [], left)[0]:
                    chunk = os.read(rfd, 16)
                    if not chunk:
                        raise E2EFailure('Xvfb closed -displayfd without a number')
                    num += chunk
        finally:
            os.close(rfd)
            if wfd is not None:
                os.close(wfd)
        self.display = ':%d' % int(num)
        os.environ['DISPLAY'] = self.display
        wait_for(lambda: self.procs[0].poll() is None and subprocess.call(
            ['xprop', '-root', '-display', self.display],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0,
                 10, what='Xvfb')
        if self.wm and self.wm != 'none' and shutil.which(self.wm):
            args = [self.wm]
            if self.wm == 'xfwm4':
                args += ['--compositor=off']
            self.wm_root = tempfile.mkdtemp(prefix='e2e-wm-')
            home = os.path.join(self.wm_root, 'home')
            os.makedirs(home)
            self.procs.append(subprocess.Popen(
                args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=_isolated_env(home, self.wm_root), start_new_session=True))
            # poll for the EWMH supporting-WM-check instead of a fixed sleep
            wait_for(lambda: self.procs[-1].poll() is None and '_NET_SUPPORTING_WM_CHECK(WINDOW)'
                     in run(['xprop', '-root', '_NET_SUPPORTING_WM_CHECK']),
                     10, what='window manager %s' % self.wm)
            time.sleep(0.3)
        else:
            self.wm = 'none'

    def stop(self):
        for p in reversed(self.procs):
            try:
                p.terminate()
                p.wait(5)
            except Exception:  # pylint: disable=broad-except
                p.kill()
                try:
                    p.wait(5)
                except Exception:  # pylint: disable=broad-except
                    pass
        self.procs = []
        if self.wm_root:
            kill_marked(self.wm_root)
            shutil.rmtree(self.wm_root, ignore_errors=True)
            self.wm_root = None


# --------------------------------------------------------------------------
# One isolated Terminator "user"
# --------------------------------------------------------------------------
class App(object):
    """Isolated HOME/XDG tree plus helpers to launch and drive terminator."""

    def __init__(self, name, python, light=False, keep=False):
        self.name = name
        self.python = python
        self.root = tempfile.mkdtemp(prefix='e2e-%s-' % name)
        self.home = os.path.join(self.root, 'home')
        self.work = os.path.join(self.root, 'work')   # dirs to cd into
        self.mark = os.path.join(self.root, 'mark')   # marker files from panes
        for d in (self.home, self.work, self.mark):
            os.makedirs(d)
        with open(os.path.join(self.home, '.bashrc'), 'w') as fh:
            fh.write(BASHRC)
        self.env = _isolated_env(self.home, self.root)
        self.env.update({
            'SHELL': '/bin/bash',
            'PYTHONPATH': REPO,
            'LANG': 'C.UTF-8',
            'LC_ALL': 'C.UTF-8',
        })
        if light:
            self.write_config(LIGHT_PROFILE)
        self.proc = None
        self.launches = 0
        self.keep = keep
        self.notes = []

    # ---- files ---------------------------------------------------------
    def write_config(self, text):
        d = os.path.join(self.env['XDG_CONFIG_HOME'], 'terminator')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'config'), 'w') as fh:
            fh.write(text)

    @property
    def state_dir(self):
        return os.path.join(self.env['XDG_STATE_HOME'], 'terminator')

    @property
    def session_path(self):
        return os.path.join(self.state_dir, 'session.json')

    @property
    def scrollback_dir(self):
        return os.path.join(self.env['XDG_CACHE_HOME'], 'terminator',
                            'scrollback')

    def session(self):
        with open(self.session_path) as fh:
            return json.load(fh)

    def mkdir(self, name):
        p = os.path.join(self.work, name)
        os.makedirs(p, exist_ok=True)
        return p

    def marker(self, name):
        return os.path.join(self.mark, name)

    def read_marker(self, name, timeout=8.0):
        p = self.marker(name)
        return wait_for(lambda: os.path.exists(p) and open(p).read().strip(),
                        timeout, what='marker %s' % name)

    def scrollback_text(self):
        """{filename: text} for every scrollback cache file."""
        out = {}
        if os.path.isdir(self.scrollback_dir):
            for f in sorted(os.listdir(self.scrollback_dir)):
                p = os.path.join(self.scrollback_dir, f)
                if os.path.isfile(p):
                    with open(p, errors='replace') as fh:
                        out[f] = fh.read()
        return out

    # ---- process -------------------------------------------------------
    def launch(self, *args, wait_windows=1):
        self.launches += 1
        self.log_path = os.path.join(self.root, 'terminator-%d.log' % self.launches)
        log = open(self.log_path, 'w')
        cmd = [self.python, os.path.join(REPO, 'terminator'), '-u', '-d'] + list(args)
        self.proc = subprocess.Popen(cmd, cwd=self.home, env=self.env,
                                     stdout=log, stderr=subprocess.STDOUT,
                                     start_new_session=True)
        if wait_windows:
            wait_for(lambda: len(self.main_windows()) >= wait_windows, 20,
                     what='%d terminator window(s)' % wait_windows)
            time.sleep(1.0)
            self.activate(self.main_windows()[0])
        return self.proc

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def signal(self, sig):
        self.proc.send_signal(sig)

    def wait_exit(self, timeout=15):
        try:
            return self.proc.wait(timeout)
        except subprocess.TimeoutExpired:
            raise E2EFailure('terminator did not exit within %ss' % timeout)

    def kill(self):
        if self.proc is None:
            return
        try:
            os.killpg(self.proc.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            self.proc.wait(5)
        except Exception:  # pylint: disable=broad-except
            pass

    def shells(self):
        """Live interactive bash children of the terminator process."""
        import psutil
        try:
            kids = psutil.Process(self.proc.pid).children(recursive=False)
        except psutil.Error:
            return []
        return [k for k in kids if k.name() == 'bash' and k.status() != 'zombie']

    def wait_shells(self, n, timeout=10):
        """Poll until exactly n live shells (instead of fixed sleeps)."""
        wait_for(lambda: len(self.shells()) == n, timeout,
                 what='%d live shells' % n)

    def shell_cwds(self):
        out = []
        for s in self.shells():
            try:
                out.append(s.cwd())
            except Exception:  # pylint: disable=broad-except
                pass
        return sorted(out)

    def log(self):
        try:
            with open(self.log_path, errors='replace') as fh:
                return fh.read()
        except OSError:
            return ''

    def cleanup(self):
        self.kill()
        # shells live in their own sessions (VTE setsid), and background
        # loops started from them survive the pty hangup: sweep by env mark.
        for _ in range(3):
            if not kill_marked(self.root):
                break
            time.sleep(0.2)
        if not self.keep:
            shutil.rmtree(self.root, ignore_errors=True)

    # ---- X helpers -----------------------------------------------------
    def _pid_windows(self):
        out = run(['xdotool', 'search', '--onlyvisible', '--class', 'terminator'])
        return [int(w) for w in out.split()]

    def window_type(self, wid):
        out = run(['xprop', '-id', str(wid), '_NET_WM_WINDOW_TYPE'])
        if 'DIALOG' in out:
            return 'dialog'
        return 'normal'

    def main_windows(self):
        return [w for w in self._pid_windows() if self.window_type(w) == 'normal']

    def dialogs(self):
        return [w for w in self._pid_windows() if self.window_type(w) == 'dialog']

    def title(self, wid):
        out = run(['xprop', '-id', str(wid), '_NET_WM_NAME'])
        if '=' not in out:
            return None
        v = out.split('=', 1)[1].strip()
        if v.startswith('"') and v.endswith('"'):
            v = v[1:-1]
        return v

    def geometry(self, wid):
        """Absolute client-area (x, y, w, h).  xwininfo, not xdotool: xdotool
        getwindowgeometry is off by the WM frame offset for reparented windows."""
        out = run(['xwininfo', '-id', str(wid)])
        g = {}
        for line in out.splitlines():
            k, _, v = line.strip().partition(':')
            g[k] = v.strip()
        return (int(g['Absolute upper-left X']), int(g['Absolute upper-left Y']),
                int(g['Width']), int(g['Height']))

    def activate(self, wid):
        run(['xdotool', 'windowactivate', '--sync', str(wid)], timeout=10)
        time.sleep(0.3)

    def resize(self, wid, w, h):
        run(['xdotool', 'windowsize', '--sync', str(wid), str(w), str(h)], timeout=10)
        time.sleep(0.8)

    def key(self, *combos, delay=0.5):
        for c in combos:
            run(['xdotool', 'key', '--clearmodifiers', c])
            time.sleep(delay)

    def type(self, text, enter=True, delay=0.3):
        run(['xdotool', 'type', '--delay', '6', text], timeout=60)
        if enter:
            run(['xdotool', 'key', 'Return'])
        time.sleep(delay)

    def click(self, x, y):
        run(['xdotool', 'mousemove', '--sync', str(x), str(y), 'click', '1'])

    def screenshot(self, label):
        os.makedirs(SHOT_DIR, exist_ok=True)
        path = os.path.join(SHOT_DIR, '%s-%s.png' % (self.name, label))
        disp = os.environ['DISPLAY']
        w, h = run(['xdpyinfo']).split('dimensions:')[1].split()[0].split('x') \
            if shutil.which('xdpyinfo') else ('1600', '1000')
        subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
                        '-f', 'x11grab', '-video_size', '%sx%s' % (w, h),
                        '-i', disp + '.0', '-frames:v', '1', '-update', '1', path],
                       timeout=20, check=True)
        return path


# --------------------------------------------------------------------------
# pixel helpers
# --------------------------------------------------------------------------
def region_mean(png, box):
    """Mean luminance (0-255) of box=(x0, y0, x1, y1) in png."""
    from PIL import Image, ImageStat
    im = Image.open(png).convert('L').crop(box)
    return ImageStat.Stat(im).mean[0]


def region_diff(png_a, png_b, box):
    """Mean abs per-pixel luminance diff of the same box in two screenshots."""
    from PIL import Image, ImageChops, ImageStat
    a = Image.open(png_a).convert('L').crop(box)
    b = Image.open(png_b).convert('L').crop(box)
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0]


# --------------------------------------------------------------------------
# session.json helpers
# --------------------------------------------------------------------------
def layout_nodes(sess, typ=None):
    lay = sess.get('layout', {}) if isinstance(sess, dict) else {}
    nodes = [dict(v, _name=k) for k, v in lay.items() if isinstance(v, dict)]
    if typ:
        nodes = [n for n in nodes if n.get('type') == typ]
    return nodes


def terminal_dirs(sess):
    return sorted(n.get('directory', '') for n in layout_nodes(sess, 'Terminal'))
