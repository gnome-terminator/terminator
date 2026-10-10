"""m30: hook the real-GUI e2e suite (tests/e2e) into the single
tests/run_tests.sh channel.

Opt-in because it launches the real terminator ~11 times (~2.5 min):

    TERMINATOR_E2E=1 tests/run_tests.sh tests/test_m30_e2e_gui.py

Skipped when not requested or when Xvfb/xdotool/x11-utils/ffmpeg/Pillow
are missing.  Runs the runner module directly (not run_e2e.sh, which waits
for run_tests.sh and would deadlock); the runner starts its own private
Xvfb via -displayfd and cleans every spawned process up."""
import fcntl
import os
import shutil
import signal
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = ('Xvfb', 'xdotool', 'xprop', 'xwininfo', 'xdpyinfo', 'ffmpeg')


def _missing():
    miss = [t for t in TOOLS if not shutil.which(t)]
    try:
        import PIL  # noqa: F401  pylint: disable=unused-import,import-outside-toplevel
        import psutil  # noqa: F401  pylint: disable=unused-import,import-outside-toplevel
    except ImportError as ex:
        miss.append(str(ex))
    return miss


@pytest.mark.skipif(os.environ.get('TERMINATOR_E2E') != '1',
                    reason='GUI e2e is opt-in: set TERMINATOR_E2E=1')
def test_e2e_gui_suite():
    miss = _missing()
    if miss:
        pytest.skip('e2e deps missing: %s' % ', '.join(miss))
    env = dict(os.environ, PYTHONPATH=ROOT)
    env.pop('DISPLAY', None)
    args = [sys.executable, '-m', 'tests.e2e.run_e2e', '--python', sys.executable]
    for k in filter(None, os.environ.get('TERMINATOR_E2E_K', '').split(',')):
        args += ['-k', k]
    # same single e2e lane as run_e2e.sh (it holds this lock too); we are
    # inside run_tests.sh so its "wait for run_tests.sh" loop is skipped.
    lock = open(os.path.join(os.environ.get('TMPDIR', '/tmp'),
                             'terminator-e2e-%d.lock' % os.getuid()), 'w')
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        # own session so a timeout can SIGTERM the runner (its handler unwinds
        # the finally blocks: app, shells, Xvfb/WM) and then reap the group.
        p = subprocess.Popen(args, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, universal_newlines=True,
                             start_new_session=True)
        try:
            out, _ = p.communicate(timeout=1800)
        except subprocess.TimeoutExpired:
            p.send_signal(signal.SIGTERM)
            try:
                out, _ = p.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                out = ''
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
            p.wait()
            pytest.fail('e2e suite timed out after 1800s\n' + (out or '')[-4000:])
    finally:
        lock.close()
    print(out)
    assert p.returncode == 0, out[-4000:]
