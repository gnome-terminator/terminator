"""Manual Xvfb smoke (not collected by pytest; run as a script):

    SCENARIO=splits|overlay|zoom|tabs|close PYTHONPATH=. python tests/smoke_window_title.py

Smoke: several panes all emit OSC titles in loops; check the window title
only follows the focused / last-focused pane. PYTHONPATH=<worktree>.
SCENARIO=splits|overlay|tabs|zoom|close"""
import os, sys, time, collections
import gi
gi.require_version('Gtk', '3.0'); gi.require_version('Vte', '2.91')
from gi.repository import Gtk, GLib


def main():
    from terminatorlib.terminator import Terminator
    SC = os.environ.get('SCENARIO', 'splits')
    T = Terminator()
    T.config['restore_last_session'] = False
    win, a = T.new_window()
    win.resize(1000, 700)
    win.split_axis(a, True)
    t1 = [t for t in win.get_terminals() if t is not a][0]
    t1.get_parent().split_axis(t1, False)

    names = {}
    def name_all():
        for t in T.terminals:
            if t not in names:
                names[t] = 'P%d' % len(names)
    name_all()
    def term(n):
        return [t for t, v in names.items() if v == n][0]

    phase = {'v': 'init'}
    log = []
    calls = collections.Counter()
    orig_set = Gtk.Window.set_title
    def rec_set_title(self, title):
        log.append((phase['v'], title))
        return orig_set(self, title)
    win.set_title = rec_set_title.__get__(win)

    def loop(t):
        cmd = ("for i in $(seq 1 100000); do printf '\\033]0;%s %%s\\007' $i; sleep 0.02; done\n" % names[t])
        t.vte.feed_child(cmd.encode())

    started = set()
    def start_loops():
        name_all()
        for t in list(names):
            if t not in started and t.pid:
                started.add(t); loop(t)
        return False

    def walk(w):
        yield w
        if isinstance(w, Gtk.Container):
            for c in w.get_children():
                yield from walk(c)

    def act(label, fn):
        def run():
            phase['v'] = label
            fn()
            return False
        return run

    def focus_btn(n):
        t = term(n); t.grab_focus()
        btns = [w for w in walk(t.titlebar) if isinstance(w, Gtk.Button) and w.get_can_focus() and w.get_mapped()]
        (btns[0].grab_focus() if btns else print('no focusable titlebar button'))

    def tabs_setup():
        win.tab_new(term('P2'))
        GLib.timeout_add(800, lambda: (name_all(), term('P3').get_parent().split_axis(term('P3'), True) if False else None, False)[-1])

    steps = [(1500, act('init-loops', start_loops))]
    if SC == 'splits':
        steps += [(2500, act('focus-P1', lambda: term('P1').grab_focus())),
                  (4500, act('focus-P2', lambda: term('P2').grab_focus())),
                  (6500, act('btn-P0', lambda: focus_btn('P0'))),
                  (8500, act('focus-P1-again', lambda: term('P1').grab_focus()))]
        end = 10500
    elif SC == 'overlay':
        steps += [(2500, act('focus-P1', lambda: term('P1').grab_focus())),
                  (4000, act('ovl-max-P0', lambda: win.overlay_maximise(term('P0'), animate=False))),
                  (6000, act('ovl-btn-P0', lambda: focus_btn('P0'))),
                  (8000, act('ovl-transfer-P2', lambda: win.overlay_transfer(term('P2'), animate=False))),
                  (10000, act('ovl-restore', lambda: win.overlay_restore(animate=False))),
                  (12000, act('focus-P1-after', lambda: term('P1').grab_focus()))]
        end = 14000
    elif SC == 'zoom':
        steps += [(2500, act('focus-P1', lambda: term('P1').grab_focus())),
                  (4000, act('zoom-P0', lambda: win.zoom(term('P0'), True))),
                  (6000, act('unzoom', lambda: win.unzoom(term('P0')))),
                  (8000, act('focus-P2', lambda: term('P2').grab_focus()))]
        end = 10000
    elif SC == 'tabs':
        steps += [(2500, act('focus-P1', lambda: term('P1').grab_focus())),
                  (3000, act('newtab', lambda: win.tab_new(term('P1')))),
                  (4500, act('newtab-loops', start_loops)),
                  (6500, act('tab0', lambda: win.get_children()[0].set_current_page(0))),
                  (8500, act('focus-P2', lambda: term('P2').grab_focus())),
                  (10500, act('tab1', lambda: win.get_children()[0].set_current_page(1)))]
        end = 12500
    elif SC == 'close':
        steps += [(2500, act('focus-P1', lambda: term('P1').grab_focus())),
                  (4500, act('close-P1', lambda: term('P1').close())),
                  (7000, act('focus-P0', lambda: term('P0').grab_focus()))]
        end = 9000
    for ms, fn in steps:
        GLib.timeout_add(ms, fn)
    GLib.timeout_add(end, Gtk.main_quit)
    Gtk.main()

    fw = win.get_focus()
    fwn = [names[t] for t in names if t.vte is fw]
    print('SCENARIO', SC, '| focus widget at end:', fwn or fw)
    print('== applied Gtk window set_title per phase')
    by = collections.OrderedDict()
    for ph, title in log:
        by.setdefault(ph, []).append(title)
    bad = 0
    for ph, titles in by.items():
        prefixes = [str(x).split(' ')[0] for x in titles]
        switches = sum(1 for i in range(1, len(prefixes)) if prefixes[i] != prefixes[i-1])
        print('  %-18s n=%4d prefixes=%s switches=%d last=%r' % (ph, len(titles), dict(collections.Counter(prefixes)), switches, titles[-1]))
    print('FINAL window title:', win.get_title())
    total_sw = 0
    for ph, titles in by.items():
        pf = [str(x).split(' ')[0] for x in titles]
        total_sw += sum(1 for i in range(1, len(pf)) if pf[i] != pf[i-1])
    ok = bool(fwn) and str(win.get_title()).split(' ')[0] == fwn[0] and total_sw == 0
    print('RESULT', 'PASS' if ok else 'FAIL', '(in-phase pane switches=%d)' % total_sw)
    os._exit(0)


if __name__ == '__main__':
    main()
