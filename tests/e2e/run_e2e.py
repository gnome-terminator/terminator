"""Runner: python -m tests.e2e.run_e2e [-k substr] [--keep] [--timeout S]"""
import argparse
import os
import signal
import sys
import time
import traceback


class _Timeout(Exception):
    pass


def _alarm(signum, frame):
    raise _Timeout('scenario timeout')


def main(argv=None):
    from tests.e2e.harness import XDisplay, App
    from tests.e2e.scenarios import SCENARIOS
    ap = argparse.ArgumentParser()
    ap.add_argument('-k', action='append', default=[])
    ap.add_argument('--keep', action='store_true')
    ap.add_argument('--timeout', type=int, default=150)
    ap.add_argument('--python', default=sys.executable)
    a = ap.parse_args(argv)
    disp = XDisplay().start()
    print('>> display %s wm=%s' % (disp.display, disp.wm), flush=True)
    results = []
    signal.signal(signal.SIGALRM, _alarm)
    try:
        for name, fn, kw in SCENARIOS:
            if a.k and not any(k in name for k in a.k):
                continue
            app = App(name, a.python, keep=a.keep, **kw)
            t0 = time.monotonic()
            status, detail = 'PASS', ''
            signal.alarm(a.timeout)
            try:
                fn(app)
            except Exception as ex:  # pylint: disable=broad-except
                status = 'FAIL'
                detail = '%s: %s' % (type(ex).__name__, ex)
                if not isinstance(ex, AssertionError):
                    detail += '\n' + traceback.format_exc()
                try:
                    app.screenshot('FAIL')
                except Exception:  # pylint: disable=broad-except
                    pass
                app.keep = True
            finally:
                signal.alarm(0)
                app.cleanup()
            dt = time.monotonic() - t0
            results.append((name, status, dt, detail, app.notes, app.root))
            print('%-22s %s (%.1fs) %s' % (name, status, dt, detail), flush=True)
            for n in app.notes:
                print('    note: %s' % n, flush=True)
            if status == 'FAIL':
                print('    kept: %s' % app.root, flush=True)
    finally:
        disp.stop()
    print('\n== summary ==')
    for name, status, dt, _d, _n, _r in results:
        print('%-22s %s' % (name, status))
    return 0 if all(r[1] == 'PASS' for r in results) else 1


if __name__ == '__main__':
    sys.exit(main())
