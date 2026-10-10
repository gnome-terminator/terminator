"""m37: measure pane-maximise animation frame timings under Xvfb.

Not a test (never collected): launches the real terminator with
TERMINATOR_ANIM_PROFILE set, builds a 2x2 (or 3x3 with --panes 9) grid of
panes full of text, toggles maximise/restore --rounds times and prints the
per-animation frame stats written by terminatorlib/animprofile.py.

    tests/e2e/profile_maximise.py [--panes 4|9] [--rounds 6] [--tui]
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                                                '..', '..')))


def main(argv=None):
    from tests.e2e.harness import XDisplay, App
    from tests.e2e.scenarios import KEYS
    ap = argparse.ArgumentParser()
    ap.add_argument('--panes', type=int, default=4, choices=(4, 9))
    ap.add_argument('--rounds', type=int, default=6)
    ap.add_argument('--tui', action='store_true',
                    help='run top in the maximised pane (live redraws)')
    ap.add_argument('--python', default=sys.executable)
    ap.add_argument('--out', default=None)
    ap.add_argument('--debug', action='store_true', help='launch with -d')
    ap.add_argument('--screen', default='1600x1000',
                    help='Xvfb size WxH (window is screen minus 100px)')
    a = ap.parse_args(argv)
    sw, sh = (int(v) for v in a.screen.split('x'))
    disp = XDisplay(sw, sh).start()
    app = App('profile', a.python)
    out = a.out or os.path.join(app.root, 'anim.jsonl')
    app.env['TERMINATOR_ANIM_PROFILE'] = out
    if not a.debug:
        # -d makes every dbg() walk inspect.stack(): ~100ms of noise per
        # focus change that real users never see. Launch like a user.
        import subprocess
        from tests.e2e import harness
        def _launch(*args, **_kw):
            app.launches += 1
            log = open(os.path.join(app.root, 'terminator.log'), 'w')
            app.proc = subprocess.Popen(
                [app.python, os.path.join(harness.REPO, 'terminator'), '-u'],
                cwd=app.home, env=app.env, stdout=log,
                stderr=subprocess.STDOUT, start_new_session=True)
            harness.wait_for(lambda: len(app.main_windows()) >= 1, 20,
                             what='terminator window')
            time.sleep(1.0)
            app.activate(app.main_windows()[0])
        app.launch = _launch
    try:
        app.launch()
        win = app.main_windows()[0]
        app.resize(win, sw - 100, sh - 60)
        fill = 'for i in $(seq 1 400); do echo "line $i $(printf %0.sX {1..90})"; done'
        if a.panes == 4:
            app.key(KEYS['split_vert'], delay=0.8)
            app.key(KEYS['split_horiz'], delay=0.8)
            app.key('alt+Left', delay=0.4)
            app.key(KEYS['split_horiz'], delay=0.8)
        else:
            app.key(KEYS['split_vert'], delay=0.8)
            app.key(KEYS['split_vert'], delay=0.8)
            for _ in range(3):
                app.key(KEYS['split_horiz'], delay=0.6)
                app.key(KEYS['split_horiz'], delay=0.6)
                app.key('alt+Left', delay=0.3)
        app.wait_shells(a.panes, timeout=20)
        for _ in range(a.panes):
            app.type(fill, delay=0.4)
            app.key('alt+Right', delay=0.2)
            app.key('alt+Down', delay=0.2)
        if a.tui:
            app.type('top -d 0.2', delay=1.0)
        time.sleep(1.5)
        for _ in range(a.rounds):
            app.key(KEYS['maximise'], delay=1.0)
            app.key(KEYS['maximise'], delay=1.0)
        # rapid toggles mid-animation
        for _ in range(3):
            app.key(KEYS['maximise'], delay=0.08)
        time.sleep(1.5)
        app.key(KEYS['restore_maximised'], delay=1.0)
        time.sleep(0.8)
        if a.tui:
            app.key('q', delay=0.3)
    finally:
        app.keep = True
        app.cleanup()
        disp.stop()
    recs = []
    if os.path.exists(out):
        with open(out) as fh:
            recs = [json.loads(l) for l in fh if l.strip()]
    keys = ('frames', 'first_frame_ms', 'max_gap_ms', 'p95_gap_ms',
            'mean_gap_ms', 'gaps_over_33ms', 'max_paint_ms', 'mean_paint_ms',
            'done_ms', 'done_to_next_frame_ms', 'done_frame_paint_ms')
    print('kind     ' + ' '.join('%s' % k for k in keys))
    for r in recs:
        print('%-8s ' % r['kind'] + ' '.join(str(r.get(k, '-')) for k in keys))
    for kind in ('expand', 'restore'):
        rs = [r for r in recs if r['kind'] == kind and 'max_gap_ms' in r]
        if not rs:
            continue
        def med(k):
            v = sorted(r.get(k, 0) for r in rs)
            return v[len(v) // 2]
        print('MEDIAN %-7s n=%d frames=%s first=%s maxgap=%s p95=%s meangap=%s '
              '>33ms=%s maxpaint=%s meanpaint=%s done->next=%s donepaint=%s' % (
                  kind, len(rs), med('frames'), med('first_frame_ms'),
                  med('max_gap_ms'), med('p95_gap_ms'), med('mean_gap_ms'),
                  med('gaps_over_33ms'), med('max_paint_ms'),
                  med('mean_paint_ms'), med('done_to_next_frame_ms'),
                  med('done_frame_paint_ms')))
    print('raw:', out)


if __name__ == '__main__':
    main()
