"""E2E scenarios.  Each function gets a fresh harness.App and raises
E2EFailure (or any exception) on failure.  Import-safe (see harness.py).

SCENARIOS entries are (name, fn, opts).  opts go to harness.App except
'xfail': a reason string marking a KNOWN real-app bug.  Such a scenario is
reported XFAIL when it fails (does not fail the run) and XPASS when it
passes, which DOES fail the run so the marker gets removed once fixed."""
import json
import os
import re
import signal
import time

from tests.e2e.harness import (App, E2EFailure, check, wait_for, region_mean,
                               region_diff, layout_nodes, terminal_dirs)

KEYS = {
    'split_horiz': 'ctrl+shift+o', 'split_vert': 'ctrl+shift+e',
    'new_tab': 'ctrl+shift+t', 'new_window': 'ctrl+shift+i',
    'close_term': 'ctrl+shift+w', 'close_window': 'ctrl+shift+q',
    'maximise': 'ctrl+shift+Return', 'restore_maximised': 'shift+Escape',
}
TIERS = (1.0, 0.9, 0.8)


def _cd(app, d, tag=None):
    """cd into d in the focused pane and print a scrollback marker."""
    cmd = 'cd %s' % d
    if tag:
        cmd += '; for i in 1 2 3; do echo SB_%s_$i; done' % tag
    app.type(cmd)


def _session_has_dirs(app, dirs):
    def pred():
        s = app.session()
        got = terminal_dirs(s)
        return all(d in got for d in dirs) and s
    return pred


# ---------------------------------------------------------------- 1
def s1_session_roundtrip(app):
    """Unlocked tabs stay in the live snapshot and are dropped on a normal exit.

    A crash (see s9) still restores them. A window with no tab list, such
    as the fresh window after this exit, is kept by the next final save.
    """
    dirs = {t: app.mkdir('dir_' + t) for t in ('A', 'B', 'C', 'D')}
    app.launch()
    _cd(app, dirs['A'], 'ALPHA')
    app.key(KEYS['split_horiz'], delay=1.0)
    _cd(app, dirs['B'], 'BRAVO')
    app.key(KEYS['split_vert'], delay=1.0)
    _cd(app, dirs['C'], 'CHARLIE')
    app.key(KEYS['new_tab'], delay=1.0)
    _cd(app, dirs['D'], 'DELTA')
    app.wait_shells(4)
    sess = wait_for(_session_has_dirs(app, dirs.values()), 10,
                    what='debounced session.json with 4 cwds')
    types = [n['type'] for n in layout_nodes(sess)]
    check(types.count('Terminal') == 4, 'session terminals: %s' % types)
    check('Notebook' in types, 'no Notebook in session: %s' % types)
    check(any(t in types for t in ('HPaned', 'VPaned')), 'no Paned: %s' % types)
    check(sess.get('exit') == 'live', 'debounced save exit=%r' % sess.get('exit'))
    app.screenshot('1-before-sigterm')

    # SIGTERM is a normal exit: unlocked tabs are forgotten.
    app.signal(signal.SIGTERM)
    app.wait_exit()
    sess = app.session()
    check(sess.get('exit') == 'clean', 'final save exit=%r' % sess.get('exit'))
    check(not (set(dirs.values()) & set(terminal_dirs(sess))),
          'unlocked tabs survived SIGTERM: %s' % terminal_dirs(sess))

    # relaunch starts empty, then a split (no tab list) survives SIGINT.
    app.launch()
    wait_for(lambda: len(app.shells()) == 1, 10, what='fresh shell, no tabs')
    app.screenshot('2-fresh')
    app.key(KEYS['split_horiz'], delay=1.0)
    app.wait_shells(2)
    e = app.mkdir('dir_E')
    app.type('cd %s' % e, delay=0.4)
    app.signal(signal.SIGINT)
    app.wait_exit()
    sess = app.session()
    check(e in terminal_dirs(sess),
          'SIGINT did not run the final save (dirs=%s)' % terminal_dirs(sess))
    check(sess.get('exit') == 'clean', 'SIGINT exit=%r' % sess.get('exit'))


# ---------------------------------------------------------------- 2
def s2_multiwindow_close_order(app, how='close_window'):
    a, b = app.mkdir('win_A'), app.mkdir('win_B')
    app.launch()
    w1 = app.main_windows()[0]
    _cd(app, a, 'WINA')
    app.key(KEYS['new_window'], delay=1.5)
    wins = wait_for(lambda: len(app.main_windows()) == 2 and app.main_windows(), 10,
                    what='second window')
    w2 = [w for w in wins if w != w1][0]
    app.activate(w2)
    _cd(app, b, 'WINB')
    wait_for(_session_has_dirs(app, [a, b]), 10, what='session with both windows')
    app.screenshot('1-two-windows')
    # close FIRST window, then LAST window, within 10s (D5 buffer)
    def close(w):
        app.activate(w)
        if how == 'exit':
            app.type('exit')            # last shell of the window exits
        else:
            app.key(KEYS['close_window'])   # Ctrl+Shift+Q (same path as WM close)
    close(w1)
    wait_for(lambda: len(app.main_windows()) == 1, 8, what='first window closed')
    time.sleep(1.0)
    close(app.main_windows()[0])
    app.wait_exit(15)
    sess = app.session()
    wins = layout_nodes(sess, 'Window')
    check(len(wins) == 2, 'session has %d windows after close-first-then-last: %s'
          % (len(wins), json.dumps(sess.get('layout'))[:400]))
    check(terminal_dirs(sess) == sorted([a, b]), 'dirs=%s' % terminal_dirs(sess))
    app.launch(wait_windows=2)
    check(len(app.main_windows()) == 2, 'restored %d windows' % len(app.main_windows()))
    wait_for(lambda: app.shell_cwds() == sorted([a, b]), 10,
             what='restored cwds (got %s)' % app.shell_cwds())
    app.screenshot('2-restored')


# ---------------------------------------------------------------- 3
def s3_close_confirm(app):
    app.launch()
    win = app.main_windows()[0]
    # shell-only pane closes without prompt
    app.key(KEYS['split_horiz'], delay=0.5)
    app.wait_shells(2)
    app.key(KEYS['close_term'], delay=0.2)
    wait_for(lambda: len(app.shells()) == 1, 5, what='idle pane closed')
    check(not app.dialogs(), 'prompt shown for idle shell pane')
    # running process -> dialog
    app.type('sleep 1000', delay=0.2)
    wait_for(lambda: any(c.name() == 'sleep' for s in app.shells() for c in s.children()),
             5, what='sleep 1000 running')
    app.key(KEYS['close_term'], delay=0.2)
    dlg = wait_for(lambda: app.dialogs(), 6, what='confirm dialog (close_term)')[0]
    app.screenshot('1-dialog')
    app.activate(dlg)
    app.key('Escape', delay=1.0)        # cancel
    wait_for(lambda: not app.dialogs(), 5, what='dialog dismissed by Escape')
    check(app.alive() and len(app.shells()) == 1, 'cancel did not keep the pane')
    sleeps = [c for s in app.shells() for c in s.children() if c.name() == 'sleep']
    check(sleeps, 'sleep killed by cancel')
    # close_window with running process -> dialog -> accept
    app.activate(win)
    app.key(KEYS['close_window'], delay=0.2)
    dlg = wait_for(lambda: app.dialogs(), 6, what='confirm dialog (close_window)')[0]
    app.activate(dlg)
    # Click "Close" (right half of the action area).  Mnemonic Alt+C is not
    # delivered by xdotool to GtkMessageDialog buttons here.
    x, y, w, h = app.geometry(dlg)
    app.click(x + w * 3 // 4, y + h - 18)
    app.wait_exit(10)
    time.sleep(0.5)
    check(not any(p.is_running() and p.status() != 'zombie' for p in sleeps),
          'accepted close left the running sleep alive')
    app.screenshot('2-closed')


# ---------------------------------------------------------------- 4
def _edge_band(app, win):
    x, y, w, h = app.geometry(win)
    # left margin band (inside the 12px overlay margin), middle height
    return (x + 3, y + h // 3, x + 9, y + 2 * h // 3)


def s4_overlay_maximise(app):
    app.launch()
    win = app.main_windows()[0]
    app.resize(win, 1000, 700)
    app.key(KEYS['split_vert'], delay=1.0)          # left | right
    app.type('echo $$ > %s; sleep 5; exit' % app.marker('sib'))  # right pane exits later
    app.key('alt+Left', delay=0.5)                  # back to left pane
    app.key(KEYS['split_horiz'], delay=0.5)         # left: top/bottom
    app.wait_shells(3)
    app.type('stty size > %s' % app.marker('size0'))
    before = app.screenshot('1-before')
    app.key(KEYS['maximise'], delay=1.2)
    dimmed = app.screenshot('2-maximised')
    band = _edge_band(app, win)
    m0, m1 = region_mean(before, band), region_mean(dimmed, band)
    check(m1 < m0 * 0.8, 'no dim around maximised pane (edge lum %.1f -> %.1f)' % (m0, m1))
    app.type('stty size > %s' % app.marker('size1'))
    r1, c1 = map(int, app.read_marker('size1').split())
    # shrink window: the maximised terminal must follow (not be cropped)
    app.resize(win, 700, 500)
    time.sleep(1.0)
    app.type('stty size > %s' % app.marker('size2'))
    r2, c2 = map(int, app.read_marker('size2').split())
    check(c2 < c1 and r2 < r1, 'maximised pane did not shrink (%dx%d -> %dx%d)'
          % (r1, c1, r2, c2))
    app.screenshot('3-shrunk')
    # sibling (right pane) exits while maximised -> no lost terminals
    app.read_marker('sib')
    wait_for(lambda: len(app.shells()) == 2, 10, what='sibling shell exit')
    time.sleep(2.5)
    check(app.alive(), 'terminator died after sibling exit')
    sess = wait_for(lambda: len(layout_nodes(app.session(), 'Terminal')) == 2
                    and app.session(), 8, what='session with 2 terminals')
    app.screenshot('4-after-sibling-exit')
    app.key(KEYS['restore_maximised'], delay=1.2)
    restored = app.screenshot('5-restored')
    band = _edge_band(app, win)
    m2 = region_mean(restored, band)
    check(m2 > region_mean(dimmed, band) * 1.1 or m2 > 200,
          'still dimmed after Shift+Esc (lum %.1f)' % m2)
    # closing a pane afterwards must not crash
    app.key(KEYS['close_term'], delay=1.5)
    check(app.alive() and len(app.shells()) == 1,
          'close after restore: alive=%s shells=%d' % (app.alive(), len(app.shells())))


# ---------------------------------------------------------------- 5
def _tier(cols, px, cell1):
    est = (px / float(cols)) / cell1
    return min(TIERS, key=lambda t: abs(t - est)), est


def s5_autofont(app, size=(800, 600)):
    app.launch()
    win = app.main_windows()[0]
    app.resize(win, *size)
    x, y, W, H = app.geometry(win)
    app.type('stty size > %s' % app.marker('one'))
    r1, c1 = map(int, app.read_marker('one').split())
    cell1 = W / float(c1)          # includes chrome; good to ~3%
    res = {'single': (1.0, 1.0)}
    app.key(KEYS['split_horiz'], delay=0.5)          # stacked (top/bottom)
    app.wait_shells(2)
    time.sleep(1.5)                                  # autofont tier settle
    app.type('stty size > %s' % app.marker('bottom'))
    app.key('alt+Up', delay=0.5)
    app.type('stty size > %s' % app.marker('top'))
    for m in ('top', 'bottom'):
        r, c = map(int, app.read_marker(m).split())
        res['stacked-' + m] = _tier(c, W, cell1)
    app.key(KEYS['split_vert'], delay=0.8)           # top-right
    app.key('alt+Down', delay=0.5)
    app.key(KEYS['split_vert'], delay=2.5)           # bottom-right
    app.type('stty size > %s' % app.marker('g_br'))
    app.key('alt+Left', delay=0.4)
    app.type('stty size > %s' % app.marker('g_bl'))
    app.key('alt+Up', delay=0.4)
    app.type('stty size > %s' % app.marker('g_tl'))
    app.key('alt+Right', delay=0.4)
    app.type('stty size > %s' % app.marker('g_tr'))
    for m in ('g_tl', 'g_tr', 'g_bl', 'g_br'):
        r, c = map(int, app.read_marker(m).split())
        res['grid-' + m] = _tier(c, W / 2.0, cell1)
    app.screenshot('grid')
    app.notes.append('tiers: ' + ', '.join('%s=%.1f(est %.2f)' % (k, v[0], v[1])
                                          for k, v in sorted(res.items())))
    for k, (t, est) in res.items():
        want = 0.8 if k.startswith('grid') else 1.0
        check(t == want, 'autofont %s: tier %.1f (est %.2f), want %.1f' % (k, t, est, want))


# ---------------------------------------------------------------- 6
def s6_window_title(app):
    app.launch()
    win = app.main_windows()[0]
    loop = ("( while :; do printf '\\033]0;TITLE_%s_%%s\\007' $RANDOM; "
            "sleep 0.05; done & ) ; clear")
    app.type(loop % 'A', delay=0.5)
    app.key(KEYS['split_vert'], delay=1.0)
    app.type(loop % 'B', delay=0.5)
    app.key(KEYS['split_horiz'], delay=1.0)
    app.type(loop % 'C', delay=0.5)

    def sample(expect, n=30):
        time.sleep(1.0)
        got = [app.title(win) or '' for _ in range(n) if time.sleep(0.1) is None]
        bad = [t for t in got if not t.startswith('TITLE_%s_' % expect)]
        distinct = len(set(got))
        return bad, distinct

    for pane, keys in (('C', []), ('B', ['alt+Up']), ('A', ['alt+Left'])):
        app.key(*keys)
        bad, distinct = sample(pane)
        check(not bad, 'focus=%s but WM title was %s' % (pane, sorted(set(bad))[:5]))
        check(distinct > 3, 'title not following focused pane %s updates' % pane)
    app.screenshot('titles')


# ---------------------------------------------------------------- 7
def _sb_strip(app, win):
    x, y, w, h = app.geometry(win)
    return (x + w - 14, y + h // 3, x + w - 3, y + 2 * h // 3)


def s7_altscreen(app):
    import shutil
    app.launch()
    win = app.main_windows()[0]
    app.resize(win, 800, 500)
    app.type('seq 1 300; echo PRE_TUI_MARK', delay=1.5)
    s0 = app.screenshot('1-normal')
    strip = _sb_strip(app, win)
    app.type("tput smcup; for i in $(seq 1 15); do echo TUI''SCREEN_$i; done; "
             "sleep 5; tput rmcup", delay=2.5)
    s1 = app.screenshot('2-in-tui')
    d_tui = region_diff(s0, s1, strip)
    wait_for(lambda: len(app.shells()[0].children()) == 0, 10, what='TUI exit')
    time.sleep(2.0)
    s2 = app.screenshot('3-after-tui')
    d_after = region_diff(s0, s2, strip)
    app.notes.append('scrollbar strip diff: tui=%.1f after=%.1f' % (d_tui, d_after))
    check(d_tui > 15, 'scrollbar not hidden in alt screen (strip diff %.1f)' % d_tui)
    check(d_after < 5, 'scrollbar not restored after rmcup (strip diff %.1f)' % d_after)
    if shutil.which('tmux'):
        app.type("tmux -L e2e%d -f /dev/null new \"echo TMUX''SCREEN; sleep 4\""
                 % os.getpid(), delay=2.5)
        s3 = app.screenshot('4-in-tmux')
        d_tmux = region_diff(s0, s3, strip)
        wait_for(lambda: len(app.shells()[0].children()) == 0, 10, what='tmux exit')
        time.sleep(2.0)
        s4 = app.screenshot('5-after-tmux')
        d_tmux_after = region_diff(s0, s4, strip)
        app.notes.append('tmux strip diff: in=%.1f after=%.1f' % (d_tmux, d_tmux_after))
        check(d_tmux > 15, 'scrollbar not hidden in tmux (%.1f)' % d_tmux)
        check(d_tmux_after < 5, 'scrollbar not restored after tmux (%.1f)' % d_tmux_after)
    # quit while a TUI is on screen: cache keeps shell history, not TUI frame
    app.type("tput smcup; echo TUI''SCREEN_LIVE; sleep 60", delay=2.0)
    app.signal(signal.SIGTERM)
    app.wait_exit()
    sb = '\n'.join(app.scrollback_text().values())
    check('PRE_TUI_MARK' in sb, 'scrollback cache lost shell history')
    check('TUISCREEN_' not in sb and 'TMUXSCREEN' not in sb,
          'scrollback cache contains the alt-screen (TUI) frame')


# ---------------------------------------------------------------- 8
def s8_corrupt_session(app):
    os.makedirs(app.state_dir, exist_ok=True)
    with open(app.session_path, 'w') as fh:
        fh.write('[1,2]')
    app.launch()
    corrupt = app.session_path + '.corrupt'
    wait_for(lambda: not app.alive() or os.path.exists(corrupt), 8,
             what='session.json.corrupt (state dir: %s)' % app.state_dir)
    check(app.alive(), 'terminator exited with corrupt session.json')
    check(open(corrupt).read().strip() == '[1,2]', 'corrupt file content changed')
    app.type('cd /tmp')
    s = wait_for(lambda: isinstance(app.session(), dict) and app.session(), 10,
                 what='fresh valid session.json')
    check(layout_nodes(s, 'Terminal'), 'new session.json has no terminals')


# ---------------------------------------------------------------- 9
def s9_sigkill_recovery(app):
    """Hard crash (SIGKILL, no final save) restores the last debounced
    session. A second SIGKILL while the restoring marker is still present
    quarantines that named session as *.crashed; the third start uses
    load_crash_fallback (layout and cwd, no scrollback replay)."""
    app.write_config('[global_config]\n  scrollback_cache_interval_s = 5\n')
    dirs = {t: app.mkdir('k9_' + t) for t in ('A', 'B', 'C')}
    app.launch()
    _cd(app, dirs['A'], 'KILOA')
    app.key(KEYS['split_vert'], delay=1.0)
    _cd(app, dirs['B'], 'KILOB')
    app.key(KEYS['new_tab'], delay=1.0)
    _cd(app, dirs['C'], 'KILOC')
    app.wait_shells(3)
    wait_for(_session_has_dirs(app, dirs.values()), 10,
             what='debounced session.json with 3 cwds')
    def _cached():
        sb = '\n'.join(app.scrollback_text().values())
        return all('SB_KILO%s_3' % t in sb for t in 'ABC')
    wait_for(_cached, 15, what='interval scrollback flush (5s)')
    app.kill()   # SIGKILL the whole process group: no final save
    check(terminal_dirs(app.session()) == sorted(dirs.values()),
          'session after SIGKILL: %s' % terminal_dirs(app.session()))

    t_relaunch = time.monotonic()
    app.launch()
    wait_for(lambda: len(app.shells()) == 3, 10, what='3 restored shells')
    wait_for(lambda: app.shell_cwds() == sorted(dirs.values()), 10,
             what='restored cwds (got %s)' % app.shell_cwds())
    types = [n['type'] for n in layout_nodes(app.session())]
    check('Notebook' in types and any(t in types for t in ('HPaned', 'VPaned')),
          'restored layout lost tab/split: %s' % types)
    restoring = os.path.join(app.state_dir, 'restoring')
    check(os.path.isfile(restoring), 'restoring marker missing before 2nd SIGKILL')
    with open(restoring, encoding='utf-8') as fh:
        marker_lines = fh.read().splitlines()
    check(len(marker_lines) > 1, 'restoring marker has no source line')
    named = os.path.basename(marker_lines[1].strip())
    check(named in ('session.json', 'session.json.prev', 'session.json.prev2'),
          'restoring source %r' % named)
    with open(os.path.join(app.state_dir, named), 'rb') as fh:
        blob = fh.read()
    named_dirs = terminal_dirs(json.loads(blob.decode('utf-8')))
    check(named_dirs == sorted(dirs.values()),
          'named session dirs %s' % named_dirs)
    elapsed = time.monotonic() - t_relaunch
    app.notes.append('2nd SIGKILL %.1fs after relaunch (restoring still present)'
                     % elapsed)
    app.kill()
    app.launch()
    check(app.alive(), 'third launch after crash-during-restore died')

    def _quarantined():
        if not os.path.isdir(app.state_dir):
            return False
        for fn in os.listdir(app.state_dir):
            if not (fn.startswith('session.json') and '.crashed' in fn):
                continue
            path = os.path.join(app.state_dir, fn)
            if os.path.isfile(path):
                with open(path, 'rb') as fh:
                    if fh.read() == blob:
                        return True
        return False

    check(_quarantined(), 'named session was not quarantined byte-for-byte')
    wait_for(lambda: len(app.shells()) == 3, 10, what='3 shells after crash fallback')
    wait_for(lambda: app.shell_cwds() == sorted(dirs.values()), 10,
             what='fallback cwds (got %s)' % app.shell_cwds())
    types = [n['type'] for n in layout_nodes(app.session())]
    check('Notebook' in types and any(t in types for t in ('HPaned', 'VPaned')),
          'fallback layout lost tab/split: %s' % types)
    app.signal(signal.SIGTERM)
    app.wait_exit()
    sess = app.session()
    check(isinstance(sess, dict) and isinstance(sess.get('layout'), dict),
          'no valid session after 3rd launch')
    app.notes.append('3rd launch restored %d terminal(s) from %s' % (
        len(layout_nodes(app.session(), 'Terminal')),
        sorted(f for f in os.listdir(app.state_dir) if 'session' in f)))


def s9b_sigkill_scrollback(app):
    """First relaunch after SIGKILL feeds each pane its own scrollback,
    including the previous-session separator. No second SIGKILL."""
    app.write_config('[global_config]\n  scrollback_cache_interval_s = 5\n')
    dirs = {t: app.mkdir('k9_' + t) for t in ('A', 'B', 'C')}
    app.launch()
    _cd(app, dirs['A'], 'KILOA')
    app.key(KEYS['split_vert'], delay=1.0)
    _cd(app, dirs['B'], 'KILOB')
    app.key(KEYS['new_tab'], delay=1.0)
    _cd(app, dirs['C'], 'KILOC')
    app.wait_shells(3)
    wait_for(_session_has_dirs(app, dirs.values()), 10,
             what='debounced session.json with 3 cwds')

    def _cached():
        sb = '\n'.join(app.scrollback_text().values())
        return all('SB_KILO%s_3' % t in sb for t in 'ABC')

    wait_for(_cached, 15, what='interval scrollback flush (5s)')
    app.kill()
    check(terminal_dirs(app.session()) == sorted(dirs.values()),
          'session after SIGKILL: %s' % terminal_dirs(app.session()))
    app.launch()
    wait_for(lambda: len(app.shells()) == 3, 10, what='3 restored shells')
    wait_for(lambda: app.shell_cwds() == sorted(dirs.values()), 10,
             what='restored cwds (got %s)' % app.shell_cwds())
    types = [n['type'] for n in layout_nodes(app.session())]
    check('Notebook' in types and any(t in types for t in ('HPaned', 'VPaned')),
          'restored layout lost tab/split: %s' % types)
    tags = {'A': 'SB_KILOA_3', 'B': 'SB_KILOB_3', 'C': 'SB_KILOC_3'}
    separator = 'Output above is from the previous session'

    def _per_pane():
        nodes = layout_nodes(app.session(), 'Terminal')
        by_dir = {}
        for node in nodes:
            by_dir.setdefault(node.get('directory'), []).append(node.get('uuid'))
        if sorted(by_dir) != sorted(dirs.values()):
            return False
        for letter, directory in dirs.items():
            uuids = by_dir.get(directory) or []
            if len(uuids) != 1 or not uuids[0]:
                return False
            path = os.path.join(app.scrollback_dir, str(uuids[0]) + '.txt')
            if not os.path.isfile(path):
                return False
            with open(path, errors='replace') as fh:
                text = fh.read()
            others = [tags[k] for k in tags if k != letter]
            if tags[letter] not in text or any(other in text for other in others):
                return False
            if separator not in re.sub(r'\s+', ' ', text):
                return False
        return True

    wait_for(_per_pane, 15, what='per-pane scrollback replay')
    app.signal(signal.SIGTERM)
    app.wait_exit()


# ---------------------------------------------------------------- 10
def s10_quit_relaunch(app):
    """m30: normal quit via Ctrl+Shift+Q (single window, idle shells) then
    relaunch restores split + cwds + scrollback."""
    a, b = app.mkdir('q_A'), app.mkdir('q_B')
    app.launch()
    _cd(app, a, 'QUITA')
    app.key(KEYS['split_horiz'], delay=1.0)
    _cd(app, b, 'QUITB')
    app.wait_shells(2)
    wait_for(_session_has_dirs(app, [a, b]), 10, what='session with 2 cwds')
    app.key(KEYS['close_window'], delay=0.5)
    # upstream "Close multiple terminals?" prompt -> click Close Terminals
    dlg = wait_for(lambda: app.dialogs(), 6, what='close-window prompt')[0]
    app.activate(dlg)
    x, y, w, h = app.geometry(dlg)
    app.click(x + w * 7 // 8, y + h - 18)   # 3/4 lands on Cancel here
    app.wait_exit()
    check(terminal_dirs(app.session()) == sorted([a, b]),
          'after quit dirs=%s' % terminal_dirs(app.session()))
    app.launch()
    wait_for(lambda: app.shell_cwds() == sorted([a, b]), 10,
             what='restored cwds (got %s)' % app.shell_cwds())
    check({'HPaned', 'VPaned'} & {n['type'] for n in layout_nodes(app.session())},
          'split lost after quit/relaunch')
    app.signal(signal.SIGTERM)
    app.wait_exit()
    sb = '\n'.join(app.scrollback_text().values())
    for t in ('QUITA', 'QUITB'):
        check('SB_%s_3' % t in sb, 'scrollback %s lost after quit/relaunch' % t)


SCENARIOS = [
    ('1-session-roundtrip', s1_session_roundtrip, {}),
    ('2-multiwindow', s2_multiwindow_close_order, {}),
    # m26: windows closed by their last shell exiting are buffered (D5)
    # like Ctrl+Shift+Q-closed ones (Container._session_before_last_close).
    ('2b-multiwindow-exit', lambda app: s2_multiwindow_close_order(app, 'exit'), {}),
    ('3-close-confirm', s3_close_confirm, {}),
    ('4-overlay-maximise', s4_overlay_maximise, {'light': True}),
    ('5-autofont', s5_autofont, {}),
    ('6-window-title', s6_window_title, {}),
    ('7-altscreen', s7_altscreen, {}),
    ('8-corrupt-session', s8_corrupt_session, {}),
    ('9-sigkill-recovery', s9_sigkill_recovery, {}),
    ('9b-sigkill-scrollback', s9b_sigkill_scrollback, {}),
    ('10-quit-relaunch', s10_quit_relaunch, {}),
]
