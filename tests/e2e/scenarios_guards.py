"""m31 E2E: session restore guard rails (import-safe, see harness.py).

11-missing-cwd   saved cwd deleted between runs -> that pane restores in ~,
                 the others keep their dirs; layout intact.
12-crash-marker  a stale ``restoring`` marker (previous restore crashed)
                 -> restore skipped, session.json moved to .crashed, marker
                 cleared, and the fresh run writes a new session.
13-lock-held     another instance holds session.lock -> this instance
                 neither restores nor overwrites session.json."""
import fcntl
import os
import signal
import time

from tests.e2e.harness import check, wait_for, layout_nodes, terminal_dirs
from tests.e2e.scenarios import KEYS, _cd, _session_has_dirs


def _seed_session(app, dirs, split=True):
    """First run: cd into dirs (splitting between them), SIGTERM."""
    app.launch()
    _cd(app, dirs[0], 'SEED0')
    for i, d in enumerate(dirs[1:], 1):
        app.key(KEYS['split_horiz'] if split else KEYS['new_tab'], delay=1.0)
        _cd(app, d, 'SEED%d' % i)
    app.wait_shells(len(dirs))
    wait_for(_session_has_dirs(app, dirs), 10, what='seed session.json')
    app.signal(signal.SIGTERM)
    app.wait_exit()
    check(terminal_dirs(app.session()) == sorted(dirs),
          'seed dirs=%s' % terminal_dirs(app.session()))


# ---------------------------------------------------------------- 11
def s11_missing_cwd(app):
    a, b = app.mkdir('mc_A'), app.mkdir('mc_B')
    _seed_session(app, [a, b])
    os.rmdir(b)
    app.launch()
    wait_for(lambda: len(app.shells()) == 2, 10, what='2 restored shells')
    want = sorted([a, os.path.realpath(app.home)])
    wait_for(lambda: sorted(os.path.realpath(c) for c in app.shell_cwds()) == want,
             10, what='cwds %s (got %s)' % (want, app.shell_cwds()))
    check({'HPaned', 'VPaned'} & {n['type'] for n in layout_nodes(app.session())},
          'split lost when restoring with a missing cwd')
    app.signal(signal.SIGTERM)
    app.wait_exit()
    check(b not in terminal_dirs(app.session()),
          'deleted dir still saved: %s' % terminal_dirs(app.session()))


# ---------------------------------------------------------------- 12
def s12_crash_marker(app):
    a = app.mkdir('cm_A')
    _seed_session(app, [a])
    seeded = open(app.session_path).read()
    marker = os.path.join(app.state_dir, 'restoring')
    with open(marker, 'w') as fh:
        fh.write('%d\n' % int(time.time()))
    app.launch()
    wait_for(lambda: len(app.shells()) == 1, 10, what='1 fresh shell')
    time.sleep(1.0)
    cwds = [os.path.realpath(c) for c in app.shell_cwds()]
    check(cwds == [os.path.realpath(app.home)],
          'session restored despite crash marker (cwds=%s)' % cwds)
    crashed = app.session_path + '.crashed'
    check(os.path.isfile(crashed) and open(crashed).read() == seeded,
          'session.json not preserved as .crashed')
    check(not os.path.exists(marker), 'crash marker not cleared')
    b = app.mkdir('cm_B')
    app.type('cd %s' % b)
    wait_for(_session_has_dirs(app, [b]), 10, what='fresh session after crash skip')
    app.signal(signal.SIGTERM)
    app.wait_exit()
    # next launch restores normally (no crash loop)
    app.launch()
    wait_for(lambda: app.shell_cwds() == [b], 10,
             what='normal restore after crash skip (got %s)' % app.shell_cwds())


# ---------------------------------------------------------------- 13
def s13_lock_held(app):
    a = app.mkdir('lk_A')
    _seed_session(app, [a])
    seeded = open(app.session_path, 'rb').read()
    fd = os.open(os.path.join(app.state_dir, 'session.lock'),
                 os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        app.launch()
        wait_for(lambda: len(app.shells()) == 1, 10, what='1 shell')
        time.sleep(1.0)
        cwds = [os.path.realpath(c) for c in app.shell_cwds()]
        check(cwds == [os.path.realpath(app.home)],
              'non-owner instance restored the session (cwds=%s)' % cwds)
        b = app.mkdir('lk_B')
        app.type('cd %s' % b)
        app.key(KEYS['split_horiz'], delay=1.0)
        time.sleep(4.0)   # > debounce
        app.signal(signal.SIGTERM)
        app.wait_exit()
        check(open(app.session_path, 'rb').read() == seeded,
              'non-owner instance overwrote session.json')
    finally:
        os.close(fd)
    app.launch()
    wait_for(lambda: app.shell_cwds() == [a], 10,
             what='owner restore after lock released (got %s)' % app.shell_cwds())


SCENARIOS = [
    ('11-missing-cwd', s11_missing_cwd, {}),
    ('12-crash-marker', s12_crash_marker, {}),
    ('13-lock-held', s13_lock_held, {}),
]
