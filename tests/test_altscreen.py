"""M8: auto-hide scrollbar while a fullscreen TUI uses the alternate screen."""

import os
import time

import pytest

from terminatorlib import altscreen
from terminatorlib.altscreen import (AltScreenDetector, AltScreenScrollbar,
                                     adjustment_collapsed, adjustment_scrollable,
                                     foreground_busy, scrollbar_should_show,
                                     should_auto_hide)


# --- pure helpers --------------------------------------------------------

def test_adjustment_collapsed():
    assert adjustment_collapsed(0, 24, 24)
    assert not adjustment_collapsed(0, 51, 24)
    assert not adjustment_collapsed(0, 0, 0)  # unrealised widget


def test_adjustment_scrollable():
    assert not adjustment_scrollable(0, 24, 24)   # full slider, nothing to move
    assert adjustment_scrollable(0, 51, 24)
    assert not adjustment_scrollable(0, 24, 0)    # not allocated yet
    assert not adjustment_scrollable(0, 24.4, 24) # within the 0.5 slop


def test_scrollbar_should_show_only_when_scrollable():
    assert scrollbar_should_show('right', False) is False
    assert scrollbar_should_show('left', False) is False
    assert scrollbar_should_show('right', True) is True
    assert scrollbar_should_show('left', True) is True
    assert scrollbar_should_show('hidden', True) is False
    assert scrollbar_should_show('disabled', True) is False
    # A manual toggle sticks until reconfigure clears `forced`.
    assert scrollbar_should_show('right', False, forced=True) is True
    assert scrollbar_should_show('right', True, forced=False) is False
    assert scrollbar_should_show('hidden', False, forced=True) is True
    # While the fullscreen latch owns the bar, a redraw that looks
    # scrollable must not show it. The controller shows it again on exit.
    assert scrollbar_should_show('right', False, alt_auto_hidden=True) is None
    assert scrollbar_should_show('right', True, alt_auto_hidden=True) is None
    assert scrollbar_should_show('right', True, user_override=True) is None


def test_should_auto_hide_respects_config():
    assert should_auto_hide(True, True, 'right')
    assert should_auto_hide(True, True, 'left')
    assert not should_auto_hide(True, True, 'hidden')
    assert not should_auto_hide(True, True, 'disabled')
    assert not should_auto_hide(True, False, 'right')
    assert not should_auto_hide(False, True, 'right')


class Clock(object):
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def test_detector_alt_screen_after_history():
    d = AltScreenDetector()
    assert d.update(collapsed=False, busy=None) is False   # history
    assert d.update(True, True, raw=True) is True          # vim
    assert d.update(True, True, raw=True) is True          # stays
    assert d.update(False, None) is False                  # :q


def test_detector_fresh_terminal_never_flaps():
    d = AltScreenDetector()
    # fresh terminal, `ping` running (canonical), nothing scrolled yet
    assert d.update(True, True, raw=False) is False
    # even a raw-mode program with no content above is left alone
    assert d.update(True, True, raw=True) is False


def test_detector_batch_output_then_smcup_uses_cursor_evidence():
    # `seq 100; vim` processed in one batch: adjustment never showed history
    d = AltScreenDetector()
    assert d.update(True, True, raw=True, cursor_beyond=True) is True


def test_detector_canonical_program_not_hidden():
    d = AltScreenDetector()
    d.update(False, None)
    # `clear` (ESC[3J) while still in foreground, canonical mode
    assert d.update(True, True, raw=False, cursor_beyond=True) is False


def test_detector_clear_then_command_does_not_hide():
    d = AltScreenDetector()
    d.update(False, None)
    # `clear` finished, shell back in foreground
    assert d.update(True, False) is False
    assert d.had_history is False
    # `ping` starts afterwards on the cleared screen
    assert d.update(True, True, raw=False, cursor_beyond=True) is False


def test_detector_unknown_foreground_never_hides():
    # flatpak (no pid) / no /proc: an idle readline prompt is raw too, so
    # an unknown foreground must not hide the scrollbar after `clear`.
    d = AltScreenDetector()
    d.update(False, None)
    assert d.update(True, None, raw=True, cursor_beyond=True) is False
    assert d.had_history is True


def test_detector_unknown_termios_with_known_tui_hides():
    d = AltScreenDetector()
    d.update(False, None)
    assert d.update(True, True, raw=None) is True


def test_foreground_busy_unknown_shell_name_or_pgrp(monkeypatch):
    monkeypatch.setattr(os, 'tcgetpgrp', lambda fd: 100)
    assert foreground_busy(5, 100, is_shell=lambda pid: None) is None
    monkeypatch.setattr(os, 'tcgetpgrp', lambda fd: 0)
    assert foreground_busy(5, 100, is_shell=lambda pid: True) is None
    assert altscreen.is_shell_pid(2 ** 22 + 12345) is None


def test_detector_redraw_does_not_end_episode():
    """One uncollapsed sample while the TUI still owns the pty is a redraw.
    A stable uncollapse, or the shell coming back, ends the episode."""
    clock = Clock()
    d = AltScreenDetector(clock=clock)
    d.update(False, None)
    assert d.update(True, True, raw=True) is True
    assert d.update(False, True, raw=True) is True
    clock.t += 0.2
    assert d.update(False, True, raw=True) is True
    clock.t += 0.3
    assert d.update(False, True, raw=True) is False
    d2 = AltScreenDetector(clock=clock)
    d2.update(False, None)
    assert d2.update(True, True, raw=True) is True
    assert d2.update(False, False) is False


def test_detector_shell_in_foreground_means_no_tui():
    d = AltScreenDetector()
    d.update(False, None)
    d.update(True, True, raw=True)
    # TUI died without leaving alt screen; shell prompt is back
    assert d.update(True, False) is False


def test_detector_grace_then_latch():
    clock = Clock()
    d = AltScreenDetector(clock=clock)
    d.update(False, None)
    # TUI switched screen but not yet raw
    assert d.update(True, True, raw=False) is False
    clock.t += 0.3
    assert d.update(True, True, raw=True) is True      # within grace
    d2 = AltScreenDetector(clock=clock)
    assert d2.update(True, True, raw=True) is False    # fresh: no evidence
    clock.t += 5
    # alt ring scrolled much later: no mid-session hide/reflow
    assert d2.update(True, True, raw=True, cursor_beyond=True) is False
    # episode ends, next TUI decides afresh
    assert d2.update(False, None) is False
    assert d2.update(True, True, raw=True) is True


def test_tty_raw_on_real_pty():
    import pty
    import termios
    import tty
    master, slave = pty.openpty()
    try:
        attrs = termios.tcgetattr(slave)
        attrs[3] |= termios.ICANON
        termios.tcsetattr(slave, termios.TCSANOW, attrs)
        assert altscreen.tty_raw(master) is False
        tty.setraw(slave)
        assert altscreen.tty_raw(master) is True
    finally:
        os.close(master)
        os.close(slave)
    assert altscreen.tty_raw(None) is None
    assert altscreen.tty_raw(-1) is None


def test_foreground_busy(monkeypatch):
    monkeypatch.setattr(os, 'tcgetpgrp', lambda fd: 100)
    assert foreground_busy(5, 100, is_shell=lambda pid: True) is False
    assert foreground_busy(5, 100, is_shell=lambda pid: False) is True
    assert foreground_busy(5, 42, is_shell=lambda pid: True) is True
    assert foreground_busy(None, 100) is None
    assert foreground_busy(5, -1) is None

    def boom(fd):
        raise OSError('nope')
    monkeypatch.setattr(os, 'tcgetpgrp', boom)
    assert foreground_busy(5, 100) is None


def test_is_shell_pid_for_own_process_is_false():
    # pytest runs under python, not a shell
    assert altscreen.is_shell_pid(os.getpid()) is False
    assert altscreen.process_name(os.getpid())


# --- controller with fakes -----------------------------------------------

class FakeAdj(object):
    def __init__(self, lower=0, upper=51, page=24):
        self.lower, self.upper, self.page = lower, upper, page

    def get_lower(self):
        return self.lower

    def get_upper(self):
        return self.upper

    def get_page_size(self):
        return self.page


class FakeScrollbar(object):
    def __init__(self, visible=True):
        self.visible = visible
        self.calls = []

    def get_visible(self):
        return self.visible

    def get_allocated_width(self):
        return 14

    def show(self):
        self.visible = True
        self.calls.append('show')

    def hide(self):
        self.visible = False
        self.calls.append('hide')


class FakeVte(object):
    def __init__(self, adj):
        self.adj = adj
        self.row = 30

    def get_vadjustment(self):
        return self.adj

    def get_pty(self):
        return None

    def get_cursor_position(self):
        return (0, self.row)


class FakeTerminal(object):
    def __init__(self, position='right', enabled=True, visible=True):
        self.adj = FakeAdj()
        self.vte = FakeVte(self.adj)
        self.scrollbar = FakeScrollbar(visible)
        self.pid = 1234
        self.config = {'scrollbar_position': position,
                       'scrollbar_hide_in_alt_screen': enabled}


def _ctl(monkeypatch, busy=True, **kw):
    term = FakeTerminal(**kw)
    ctl = AltScreenScrollbar(term)
    ctl._adj = term.adj
    state = {'busy': busy, 'raw': True}
    monkeypatch.setattr(altscreen, 'foreground_busy',
                        lambda fd, pid: state['busy'])
    monkeypatch.setattr(altscreen, 'tty_raw', lambda fd: state['raw'])
    return term, ctl, state


def test_restore_asks_terminal_when_it_syncs(monkeypatch):
    term, ctl, state = _ctl(monkeypatch)
    calls = []
    term.sync_scrollbar = lambda *a: calls.append('sync')
    ctl.evaluate()
    term.adj.upper = 24
    ctl.evaluate()
    assert not term.scrollbar.visible and calls == []
    state['busy'] = False                 # shell is back; not a redraw
    term.adj.upper = 51
    ctl.evaluate()
    assert calls == ['sync']
    assert 'show' not in term.scrollbar.calls


def test_hide_does_not_move_the_view(monkeypatch):
    """Hiding the bar must put the scroll position back. That shift is the
    vertical jump inside a fullscreen program."""
    term, ctl, _ = _ctl(monkeypatch)
    term.adj.value = 12.0

    def get_value():
        return term.adj.value

    def set_value(value):
        term.adj.value = value

    term.adj.get_value = get_value
    term.adj.set_value = set_value
    real_hide = term.scrollbar.hide

    def hide():
        real_hide()
        term.adj.value = 0.0

    term.scrollbar.hide = hide
    ctl.evaluate()
    term.adj.upper = 24
    ctl.evaluate()
    assert term.adj.value == 12.0


def test_leaving_fullscreen_notifies_terminal(monkeypatch):
    term, ctl, state = _ctl(monkeypatch)
    notes = []
    term.note_fullscreen_exited = lambda: notes.append('exit')
    ctl.evaluate()
    term.adj.upper = 24
    ctl.evaluate()
    assert notes == []
    state['busy'] = False
    term.adj.upper = 51
    ctl.evaluate()
    assert notes == ['exit']


def test_hide_gives_scrollbar_width_to_vte(monkeypatch):
    """Hiding the bar leaves no empty strip. The VTE takes that width."""
    term, ctl, state = _ctl(monkeypatch)
    held = []
    term.hold_scrollbar_slot = lambda width: held.append(width)
    term.release_scrollbar_slot = lambda: held.append('release')
    ctl.evaluate()
    term.adj.upper = 24
    ctl.evaluate()
    assert held == ['release']
    assert ctl.auto_hidden and ctl.hidden_width == 14
    state['busy'] = False
    term.adj.upper = 51
    ctl.evaluate()
    assert held == ['release', 'release']
    assert not ctl.auto_hidden
    assert ctl.hidden_width == 0


def test_reconfigure_keeps_width_without_a_slot(monkeypatch):
    term, ctl, _ = _ctl(monkeypatch)
    held = []
    term.hold_scrollbar_slot = lambda width: held.append(width)
    term.release_scrollbar_slot = lambda: held.append('release')
    ctl.evaluate()
    term.adj.upper = 24
    ctl.evaluate()
    ctl.reconfigured()
    assert held == ['release', 'release', 'release']
    assert 14 not in held
    assert ctl.auto_hidden and ctl.hidden_width == 14


def test_controller_hides_and_restores(monkeypatch):
    term, ctl, state = _ctl(monkeypatch)
    ctl.evaluate()                       # history
    assert term.scrollbar.visible and not ctl.auto_hidden
    term.adj.upper = 24                  # enter alt screen
    ctl.evaluate()
    assert not term.scrollbar.visible and ctl.auto_hidden
    assert ctl.hidden_width == 14
    ctl.evaluate()                       # no repeated hide
    assert term.scrollbar.calls == ['hide']
    state['busy'] = False                # leave alt screen
    term.adj.upper = 51
    ctl.evaluate()
    assert term.scrollbar.visible and not ctl.auto_hidden
    assert term.scrollbar.calls == ['hide', 'show']


@pytest.mark.parametrize('position', ['hidden', 'disabled'])
def test_controller_never_shows_configured_hidden(monkeypatch, position):
    term, ctl, _ = _ctl(monkeypatch, position=position, visible=False)
    ctl.evaluate()
    term.adj.upper = 24
    ctl.evaluate()
    term.adj.upper = 51
    ctl.evaluate()
    assert term.scrollbar.calls == []


def test_controller_option_off(monkeypatch):
    term, ctl, _ = _ctl(monkeypatch, enabled=False)
    ctl.evaluate()
    term.adj.upper = 24
    ctl.evaluate()
    assert term.scrollbar.calls == []


def test_controller_user_hidden_scrollbar_left_alone(monkeypatch):
    # user pressed Ctrl+Shift+S before starting vim
    term, ctl, _ = _ctl(monkeypatch, visible=False)
    ctl.evaluate()
    term.adj.upper = 24
    ctl.evaluate()
    term.adj.upper = 51
    ctl.evaluate()
    assert term.scrollbar.calls == []


def test_controller_user_toggle_inside_tui_is_respected(monkeypatch):
    term, ctl, state = _ctl(monkeypatch)
    ctl.evaluate()
    term.adj.upper = 24
    ctl.evaluate()
    assert not term.scrollbar.visible
    ctl.user_toggled()                   # Terminal.do_scrollbar_toggle
    term.scrollbar.show()
    ctl.evaluate()
    assert term.scrollbar.visible        # not re-hidden while in vim
    state['busy'] = False
    term.adj.upper = 51
    ctl.evaluate()                       # vim exits: override cleared
    state['busy'] = True
    term.adj.upper = 24
    ctl.evaluate()                       # next TUI hides again
    assert not term.scrollbar.visible


def test_tui_redraw_does_not_show_scrollbar(monkeypatch):
    """A scrollable-looking sample while the TUI is still in front must not
    show the bar. Showing it would resize the grid under the program."""
    term, ctl, state = _ctl(monkeypatch)
    held = []
    term.hold_scrollbar_slot = lambda width: held.append(width)
    term.release_scrollbar_slot = lambda: held.append('release')
    ctl.evaluate()
    term.adj.upper = 24
    ctl.evaluate()
    assert ctl.auto_hidden and ctl.hidden_width == 14
    assert held == ['release']
    term.adj.upper = 51                  # redraw blip
    ctl.evaluate()
    assert ctl.auto_hidden and ctl.detector.active
    assert held == ['release']
    assert term.scrollbar.calls == ['hide']
    state['busy'] = False
    ctl.evaluate()
    assert not ctl.auto_hidden
    assert held == ['release', 'release']
    ctl._cancel()


def test_controller_reconfigure_reapplies(monkeypatch):
    term, ctl, _ = _ctl(monkeypatch)
    ctl.evaluate()
    term.adj.upper = 24
    ctl.evaluate()
    term.scrollbar.show()                # Terminal.reconfigure() shows it
    ctl.reconfigured()
    assert not term.scrollbar.visible and ctl.auto_hidden
    term.config['scrollbar_hide_in_alt_screen'] = False
    term.scrollbar.show()
    ctl.reconfigured()
    assert term.scrollbar.visible and not ctl.auto_hidden


def test_hide_latches_when_bar_was_already_hidden(monkeypatch):
    """A fresh terminal, a cleared screen or a manual hide leaves the bar
    invisible before vim starts. The episode must still latch, or one
    scrollable-looking redraw shows the bar and resizes the grid."""
    term, ctl, state = _ctl(monkeypatch, visible=False)
    ctl.evaluate()
    term.adj.upper = 24                  # enter alt screen
    ctl.evaluate()
    assert ctl.auto_hidden and ctl.hidden_width == 0
    assert term.scrollbar.calls == []
    term.adj.upper = 51                  # redraw blip
    ctl.evaluate()
    assert ctl.auto_hidden and ctl.detector.active
    assert term.scrollbar.calls == []
    state['busy'] = False                # vim exits
    term.adj.upper = 51
    ctl.evaluate()
    assert not ctl.auto_hidden
    ctl._cancel()


def test_note_bar_hidden_keeps_width_for_the_latch(monkeypatch):
    """sync_scrollbar hides the bar before raw mode is on. apply() must
    inherit that width instead of losing it."""
    term, ctl, _ = _ctl(monkeypatch)
    assert ctl.note_bar_hidden(14)
    assert ctl.pending_hidden and ctl.pending_hide_width == 14
    assert ctl.effective_hidden_width() == 14
    term.adj.upper = 24
    ctl.evaluate()
    assert ctl.auto_hidden and ctl.hidden_width == 14
    assert not ctl.pending_hidden
    assert ctl.effective_hidden_width() == 14


def test_note_bar_hidden_ignores_shell_foreground(monkeypatch):
    term, ctl, state = _ctl(monkeypatch)
    state['busy'] = False                 # idle prompt: `clear`, not a TUI
    assert not ctl.note_bar_hidden(14)
    assert not ctl.pending_hidden


def test_note_bar_hidden_needs_content_evidence(monkeypatch):
    """A brand-new terminal has nothing to scroll, so hiding early would
    only resize the grid for a program that never had a bar."""
    term, ctl, _ = _ctl(monkeypatch)
    term.vte.row = 0                      # cursor inside the first page
    assert not ctl.detector.had_history
    assert not ctl.note_bar_hidden(14)
    assert not ctl.pending_hidden
    ctl.detector.had_history = True
    assert ctl.note_bar_hidden(14)


def test_pending_hide_survives_grace_then_clears(monkeypatch):
    """A provisional hide must not be dropped while the TUI may still be
    switching to raw mode, but a canonical command must release it."""
    term, ctl, state = _ctl(monkeypatch)
    clock = Clock()
    ctl.detector._clock = clock
    assert ctl.note_bar_hidden(14)
    state['raw'] = False
    term.adj.upper = 24
    ctl.evaluate()                        # inside grace: undecided
    assert ctl.pending_hidden
    clock.t += ctl.detector.GRACE_S + 1
    ctl.evaluate()                        # canonical: not a TUI
    assert not ctl.pending_hidden and not ctl.auto_hidden
    assert ctl.effective_hidden_width() == 0


def test_sync_scrollbar_records_the_hide(monkeypatch):
    from terminatorlib.terminal import Terminal

    class Stub(object):
        pass

    term, ctl, _ = _ctl(monkeypatch)
    stub = Stub()
    stub.config = term.config
    stub.scrollbar = term.scrollbar
    stub.altscreen = ctl
    stub._scrollbar_forced = None
    stub._adjustment_scrollable = lambda: False
    stub._fullscreen_app_may_hide = lambda: False
    stub._place_scrollbar = lambda: None
    Terminal._sync_scrollbar(stub, stub.scrollbar)
    assert not stub.scrollbar.visible
    assert ctl.pending_hidden and ctl.pending_hide_width == 14


def test_pending_hide_suppresses_a_redraw_show(monkeypatch):
    from terminatorlib.terminal import Terminal

    class Stub(object):
        pass

    term, ctl, _ = _ctl(monkeypatch)
    ctl.pending_hidden = True
    ctl.pending_hide_width = 14
    stub = Stub()
    stub.config = term.config
    stub.scrollbar = term.scrollbar
    stub.altscreen = ctl
    stub._scrollbar_forced = None
    stub._adjustment_scrollable = lambda: True
    stub._fullscreen_app_may_hide = lambda: True
    stub._place_scrollbar = lambda: None
    term.scrollbar.visible = False
    Terminal._sync_scrollbar(stub, stub.scrollbar)
    assert not stub.scrollbar.visible
    assert ctl.sync_deferred


def test_pending_hide_survives_a_scrollable_sample(monkeypatch):
    """VTE sets upper and page_size separately, so a TUI redraw can look
    scrollable for one sample. The provisional hide must wait for the
    debounced decision instead of being dropped by the fast path."""
    term, ctl, state = _ctl(monkeypatch)
    scheduled = []
    monkeypatch.setattr(ctl, 'schedule', lambda: scheduled.append(1))
    assert ctl.note_bar_hidden(14)
    term.adj.upper = 51
    ctl._on_change(term.adj)
    assert scheduled == [1]
    assert ctl.pending_hidden and ctl.pending_hide_width == 14


def test_pending_hide_released_when_a_command_scrolls(monkeypatch):
    term, ctl, state = _ctl(monkeypatch)
    assert ctl.note_bar_hidden(14)
    state['raw'] = False
    state['busy'] = True
    term.adj.upper = 51                  # canonical command output
    ctl.evaluate()
    assert not ctl.pending_hidden
    assert ctl.effective_hidden_width() == 0


def test_controller_child_exit_restores(monkeypatch):
    term, ctl, _ = _ctl(monkeypatch)
    ctl.evaluate()
    term.adj.upper = 24
    ctl.evaluate()
    ctl._on_child_exited()
    assert term.scrollbar.visible and not ctl.detector.active


def test_controller_canonical_command_untouched(monkeypatch):
    term, ctl, state = _ctl(monkeypatch)
    state['raw'] = False
    ctl.evaluate()
    term.adj.upper = 24
    ctl.evaluate()
    assert term.scrollbar.calls == []


def test_on_contents_only_schedules_when_collapsed(monkeypatch):
    term, ctl, _ = _ctl(monkeypatch)
    scheduled = []
    monkeypatch.setattr(ctl, 'schedule', lambda: scheduled.append(1))
    ctl._on_contents()
    assert scheduled == []
    term.adj.upper = 24
    ctl._on_contents()
    assert scheduled == [1]


def test_on_change_fast_path_skips_timer(monkeypatch):
    term, ctl, _ = _ctl(monkeypatch)
    scheduled = []
    monkeypatch.setattr(ctl, 'schedule', lambda: scheduled.append(1))
    ctl._on_change(term.adj)
    assert scheduled == [] and ctl.detector.had_history
    term.adj.upper = 24
    ctl._on_change(term.adj)
    assert scheduled == [1]


def test_on_change_fast_path_ends_inactive_episode(monkeypatch):
    term, ctl, _ = _ctl(monkeypatch)
    clock = Clock()
    ctl.detector._clock = clock
    scheduled = []
    monkeypatch.setattr(ctl, 'schedule', lambda: scheduled.append(1))
    ctl.detector.update(True, True, raw=False)
    assert ctl.detector.episode_start is not None
    assert ctl.detector.active is False
    assert ctl.detector.had_history is False
    term.adj.upper = 51
    ctl._on_change(term.adj)
    assert ctl.detector.episode_start is None
    assert ctl.detector._uncollapse_since is None
    assert ctl.detector.active is False
    assert ctl.detector.had_history is True
    assert scheduled == []
    clock.t += ctl.detector.GRACE_S + 1
    assert ctl.detector.update(True, True, raw=True) is True


def test_terminal_wires_controller():
    import inspect
    from terminatorlib import terminal
    src = inspect.getsource(terminal.Terminal)
    assert 'AltScreenScrollbar(self)' in src
    assert 'user_toggled()' in src
    assert 'self.altscreen.reconfigured()' in src
    assert 'self.sync_scrollbar' in src


def test_config_default_on():
    from terminatorlib.config import DEFAULTS
    assert DEFAULTS['profiles']['default']['scrollbar_hide_in_alt_screen'] \
        is True


def test_prefs_glade_has_checkbox():
    path = os.path.join(os.path.dirname(altscreen.__file__),
                        'preferences.glade')
    with open(path) as fh:
        text = fh.read()
    assert 'scrollbar_hide_in_alt_screen_checkbutton' in text
    from terminatorlib import prefseditor
    assert hasattr(prefseditor.PrefsEditor,
                   'on_scrollbar_hide_in_alt_screen_checkbutton_toggled')


# --- real VTE --------------------------------------------------------------

def _run_real_vte(script, duration_ms=3600):
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('Vte', '2.91')
    from gi.repository import Gtk, Vte, GLib

    class RealTerm(object):
        def __init__(self):
            self.config = {'scrollbar_position': 'right',
                           'scrollbar_hide_in_alt_screen': True}
            self.vte = Vte.Terminal()
            self.vte.set_size(80, 24)
            self.vte.set_scrollback_lines(1000)
            self.scrollbar = Gtk.Scrollbar.new(
                Gtk.Orientation.VERTICAL, self.vte.get_vadjustment())
            self.scrollbar.set_no_show_all(True)
            box = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
            box.pack_start(self.vte, True, True, 0)
            box.pack_start(self.scrollbar, False, True, 0)
            self.scrollbar.show()
            self.win = Gtk.Window()
            self.win.add(box)
            self.win.show_all()
            self.pid = None

    term = RealTerm()
    ctl = AltScreenScrollbar(term)
    ctl.attach()
    ok, term.pid = term.vte.spawn_sync(
        Vte.PtyFlags.DEFAULT, None, ['/bin/bash', '--norc', '-c', script],
        None, GLib.SpawnFlags.DEFAULT, None, None, None)
    samples = []
    t0 = time.monotonic()

    def sample():
        samples.append((round(time.monotonic() - t0, 2),
                        term.scrollbar.get_visible()))
        return True

    GLib.timeout_add(100, sample)
    loop = GLib.MainLoop()
    GLib.timeout_add(duration_ms, loop.quit)
    loop.run()
    ctl.detach()
    term.win.destroy()
    return samples


# `set -m`: job control like an interactive shell (own fg pgrp per job).
# The TUI stand-in switches the pty to raw mode like a real TUI.
_TUI = ('sh -c \'stty raw -echo; printf "\\033[?1049h"; sleep 1.2; '
        'printf "\\033[?1049l"; stty sane; sleep 0.2\'')

needs_display = pytest.mark.skipif(not os.environ.get('DISPLAY'),
                                   reason='needs X display')


def _changes(vis):
    return sum(1 for a, b in zip(vis, vis[1:]) if a != b)


@needs_display
def test_real_vte_alt_screen_roundtrip():
    samples = _run_real_vte('set -m; seq 60; sleep 0.8; %s; sleep 1.2' % _TUI)
    vis = [v for _, v in samples]
    assert False in vis, samples              # hidden while in alt screen
    assert vis[0] is True and vis[-1] is True, samples
    assert _changes(vis) == 2, samples        # one cycle, no flapping


@needs_display
def test_real_vte_output_and_smcup_in_one_batch():
    samples = _run_real_vte('set -m; sleep 0.5; seq 100; %s; sleep 1.2' % _TUI)
    vis = [v for _, v in samples]
    assert False in vis, samples
    assert vis[-1] is True and _changes(vis) == 2, samples


@needs_display
def test_real_vte_clear_and_canonical_command_never_hide():
    # history, then `clear` (ESC[3J) followed by a line-oriented command
    samples = _run_real_vte(
        'set -m; seq 60; sleep 0.5; sh -c \'printf "\\033[H\\033[2J\\033[3J"\'; '
        'sh -c \'sleep 1.5; echo done\'; sleep 0.5', duration_ms=3000)
    vis = [v for _, v in samples]
    assert all(vis), samples


def test_detach_stops_timers_and_handlers(monkeypatch):
    term, ctl, _ = _ctl(monkeypatch)
    added = []
    removed = []
    monkeypatch.setattr(altscreen.GLib, 'timeout_add',
                        lambda ms, cb: added.append(cb) or 77)
    monkeypatch.setattr(altscreen.GLib, 'source_remove',
                        lambda sid: removed.append(sid))

    class Obj(object):
        def __init__(self):
            self.gone = []

        def disconnect(self, hid):
            self.gone.append(hid)
    obj = Obj()
    ctl._handlers = [(obj, 1), (obj, 2)]
    ctl.schedule()
    ctl.detach()
    assert removed == [77] and obj.gone == [1, 2]
    assert ctl._handlers == [] and ctl._adj is None
    ctl.schedule()                       # no new timer after detach
    assert len(added) == 1
    assert added[0]() is False           # stale callback is a no-op


def test_terminal_close_detaches_altscreen():
    import inspect
    from terminatorlib.terminal import Terminal
    src = inspect.getsource(Terminal.close)
    assert 'altscreen' in src and 'detach()' in src
    assert src.index('detach()') < src.index('del(self.vte)')
