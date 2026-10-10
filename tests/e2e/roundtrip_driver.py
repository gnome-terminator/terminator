"""Drive the real ./terminator entry point for the m21 restore round-trip.

Usage: roundtrip_driver.py PHASE OUT_JSON [terminator args...]
PHASE=setup  : build splits+tabs, cd, titles, overlay-max, coloured output,
               then SIGTERM self (normal finalize path).
PHASE=verify : after restore, dump observed state to OUT_JSON and quit.
PHASE=idle   : just start, dump state, quit (robustness cases).
Scenario parameters come from env RT_DIR_A / RT_DIR_B.
"""
import json
import os
import signal
import sys
import runpy

PHASE = OUT = None
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, REPO)

import gi  # noqa: E402
gi.require_version('Gtk', '3.0')
from gi.repository import GLib  # noqa: E402

DIR_A = os.environ.get('RT_DIR_A', '/tmp')
DIR_B = os.environ.get('RT_DIR_B', '/tmp')
MARK = 'RTMARK'


def T():
    from terminatorlib.terminator import Terminator
    return Terminator()


def wait_until(pred, then, timeout_ms=15000, step=100):
    state = {'t': 0}

    def tick():
        try:
            ok = pred()
        except Exception:
            ok = False
        if ok or state['t'] >= timeout_ms:
            then(ok)
            return False
        state['t'] += step
        return True
    GLib.timeout_add(step, tick)


def fail(msg):
    with open(OUT, 'w') as fh:
        json.dump({'error': msg}, fh)
    os._exit(3)


def type_in(term, text):
    term.vte.feed_child(text.encode('utf-8'))


def vte_text(term):
    from terminatorlib import scrollback
    try:
        return scrollback.read_last_n_lines(term.vte, 2000, color=False) or ''
    except Exception as ex:
        return 'ERR %s' % ex


def vte_sgr(term):
    """Last lines with colours as SGR escapes (m14 exporter)."""
    from terminatorlib import scrollback
    try:
        return scrollback.read_last_n_lines(term.vte, 2000, color=True) or ''
    except Exception as ex:
        return 'ERR %s' % ex


def describe():
    t = T()
    wins = list(t.windows)
    out = {'windows': [], 'terminals': []}
    from terminatorlib.notebook import Notebook
    for w in wins:
        child = w.get_child()
        nb = None
        stack = [child]
        while stack:
            c = stack.pop()
            if isinstance(c, Notebook):
                nb = c
                break
            if hasattr(c, 'get_children'):
                stack.extend(c.get_children())
        out['windows'].append({
            'tabs': nb.get_n_pages() if nb else 1,
            'forced_title': getattr(w.title, 'text', None) if getattr(w.title, 'forced', False) else None,
            'overlay': bool(getattr(w, 'is_overlay_maximised', lambda: False)()),
            'overlay_uuid': None,
        })
        if out['windows'][-1]['overlay']:
            for term in t.terminals:
                if term.get_toplevel() is w and w.is_maximised_pane(term):
                    out['windows'][-1]['overlay_uuid'] = str(term.uuid)
    for term in t.terminals:
        out['terminals'].append({
            'uuid': str(term.uuid),
            'cwd': term.get_cwd(),
            'title': term.titlebar.get_custom_string(),
            'text': vte_text(term),
            'sgr': vte_sgr(term),
        })
    return out


def setup_phase():
    t = T()
    if len(t.terminals) != 1:
        fail('expected 1 terminal at start, got %d' % len(t.terminals))
    t1 = t.terminals[0]
    win = t1.get_toplevel()
    t1.key_split_vert()
    def after_split(ok):
        if not ok:
            fail('split failed')
        t2 = [x for x in t.terminals if x is not t1][0]
        win.tab_new(t2)
        wait_until(lambda: len(t.terminals) == 3, lambda ok: after_tab(ok, t1, t2))
    wait_until(lambda: len(t.terminals) == 2, after_split)


def after_tab(ok, t1, t2):
    if not ok:
        fail('tab_new failed')
    t = T()
    t3 = [x for x in t.terminals if x not in (t1, t2)][0]
    win = t1.get_toplevel()
    type_in(t1, 'cd %s && printf "\\033[31m%s_RED_%%s\\033[0m\\n" T1\n' % (DIR_A, MARK))
    type_in(t2, 'cd %s && echo %s_PLAIN_T2\n' % (DIR_B, MARK))
    type_in(t3, 'echo %s_PLAIN_T3\n' % MARK)
    t2.titlebar.set_custom_string('MyManualTitle')
    win.title.force_title('FixedWinTitle')
    def ready():
        return (t1.get_cwd() == DIR_A and t2.get_cwd() == DIR_B
                and ('%s_RED_T1' % MARK) in vte_text(t1)
                and ('%s_PLAIN_T3' % MARK) in vte_text(t3))
    def go(ok):
        if not ok:
            fail('commands did not take effect: cwd1=%r cwd2=%r' % (t1.get_cwd(), t2.get_cwd()))
        # Floating maximise the split-pane terminal on tab 1.
        nb = t1.get_parent()
        while nb is not None and type(nb).__name__ != 'Notebook':
            nb = nb.get_parent()
        if nb is not None:
            nb.set_current_page(nb.page_num(nb.get_nth_page(0)))
        def do_max():
            win.overlay_maximise(t1, animate=False)
            return False
        GLib.timeout_add(500, do_max)
        def flush_and_quit():
            pre = describe()
            with open(OUT, 'w') as fh:
                json.dump(pre, fh)
            os.kill(os.getpid(), signal.SIGTERM)
            return False
        GLib.timeout_add(2500, flush_and_quit)
    wait_until(ready, go)


def dump_and_quit():
    def go():
        with open(OUT, 'w') as fh:
            json.dump(describe(), fh)
        os.kill(os.getpid(), signal.SIGTERM)
        return False
    GLib.timeout_add(int(os.environ.get('RT_SETTLE_MS', '3000')), go)
    return False


def start():
    if PHASE == 'setup':
        setup_phase()
    else:
        dump_and_quit()
    return False


def main():
    global PHASE, OUT
    PHASE, OUT = sys.argv[1], sys.argv[2]
    GLib.timeout_add(int(os.environ.get('RT_START_MS', '2500')), start)
    GLib.timeout_add(60000, lambda: fail('watchdog timeout'))
    sys.argv = [os.path.join(REPO, 'terminator')] + sys.argv[3:]
    os.chdir(os.environ.get('RT_ORIG_CWD', REPO))
    runpy.run_path(os.path.join(REPO, 'terminator'), run_name='__main__')


if __name__ == '__main__':
    main()
