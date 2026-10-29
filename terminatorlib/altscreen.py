# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""altscreen.py - hide a terminal's scrollbar while a fullscreen TUI runs.

Fullscreen programs (vim, less, htop, tmux, mc, ...) switch the terminal to
the *alternate screen* (DECSET 1049/1047/47).  The alternate screen has no
scrollback, so the scrollbar is pure noise there.

Detection
---------
VTE (up to at least 0.80) has no public API, property or signal for the
alternate screen, and the escape sequences never reach us (VTE reads the
PTY itself).  What *is* observable:

1. The vertical adjustment.  While the alternate screen is active VTE pins
   it to ``lower=0, upper=page_size, value=0`` ("collapsed").  On return to
   the normal screen it springs back to the normal screen's history.
   Ambiguity: a normal screen with no history (fresh terminal, or right
   after ``clear`` which sends ``ESC[3J``) looks exactly the same.

2. The PTY's foreground process group (``tcgetpgrp`` on the master fd).
   When the shell itself is in the foreground nothing fullscreen is
   running, so a collapsed adjustment then means "no history", not
   "alternate screen".

3. The PTY's termios (``tcgetattr`` on the master returns the slave's
   settings).  Fullscreen TUIs switch to non-canonical (raw/cbreak) mode;
   line-oriented commands (ping, make, cat, clear) stay canonical.

4. Evidence that the screen has content: the terminal showed scrollback
   at some point since the shell last cleared it, or the cursor row is
   beyond the page (the current ring has scrolled).

Rule: hide when the adjustment is collapsed, a non-shell process owns the
foreground, the PTY is raw (or unknown), and there is evidence of content.
The decision is taken at the start of such an episode (1 s grace) and kept
until the episode ends.  The hidden bar's width goes to the VTE, so the
program reaches the pane edge.  That is one resize when it starts and one
when it exits.  ``hidden_width`` is still recorded so the font tier does
not follow those extra columns.  The bar stays hidden for the whole
episode: showing it again for a redraw would resize the grid under the
program.

Consequences:

* vim/less/htop/tmux/mc after some output              -> hidden
* ``ping``/``make`` in a fresh or just-cleared terminal  -> untouched
  (canonical mode), so no hide/show flap when output starts scrolling
* a TUI in a brand-new terminal with nothing above the prompt -> untouched
  by this detector (there is nothing to scroll).  The terminal itself hides
  the scrollbar whenever the buffer fits the window; see
  ``scrollbar_should_show``
* programs that only enable mouse tracking (no alternate screen) never
  collapse the adjustment and are never affected
* ``procps`` top draws on the normal screen, so it is (correctly) ignored
* known false positive: a raw-mode, non-alt-screen program (ssh, a REPL)
  right after ``clear`` hides the scrollbar until its output scrolls.
  Accepted: the adjustment is collapsed, so there is nothing to scroll and
  the hidden scrollbar loses nothing.  Filtering by process name (e.g.
  ignoring ``ssh``) would break the main remote case (vim/tmux over ssh).
* foreground unknown (flatpak's spawn_async gives no pid, /proc missing,
  tcgetpgrp fails) -> untouched; an idle readline prompt is raw too, so
  guessing would hide the scrollbar at the prompt

Evaluation is debounced (``DEBOUNCE_MS``) so short-lived commands such as
``clear`` have exited before we look at the foreground group, and so a
burst of adjustment changes results in at most one show/hide.

VTE also emits ``changed`` once per adjustment field, so a fullscreen
redraw can set ``upper`` before ``page_size`` and look scrollable for
one signal. Showing the bar for that signal changes the column count
and the program's viewport jumps. While a raw non-shell owns the
foreground, that show waits until the adjustment has settled.
"""

import os
import termios
import time

from gi.repository import GLib

from .util import dbg

DEBOUNCE_MS = 150
# Once the decision is latched (TUI detected, or the grace window for this
# collapsed episode has passed) a full-screen redraw cannot change it until
# the foreground process changes; poll that slowly instead of every 150 ms
# of TUI output (UI review P2-6).
LATCHED_POLL_MS = 1000

_KNOWN_SHELLS = {
    'sh', 'bash', 'dash', 'zsh', 'fish', 'ksh', 'mksh', 'pdksh', 'oksh',
    'tcsh', 'csh', 'yash', 'ash', 'busybox', 'nu', 'xonsh', 'elvish',
    'pwsh', 'ion', 'oil', 'osh', 'rc', 'es',
}
_shell_names_cache = None


def shell_names():
    """Basenames of known interactive shells (built-ins + /etc/shells)."""
    global _shell_names_cache
    if _shell_names_cache is None:
        names = set(_KNOWN_SHELLS)
        try:
            with open('/etc/shells') as fh:
                for line in fh:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        names.add(os.path.basename(line))
        except OSError:
            pass
        _shell_names_cache = names
    return _shell_names_cache


def process_name(pid):
    """Return /proc/<pid>/comm or None."""
    try:
        with open('/proc/%d/comm' % pid) as fh:
            return fh.read().strip()
    except (OSError, ValueError, TypeError):
        return None


def is_shell_pid(pid):
    """True/False, or None when /proc/<pid>/comm cannot be read."""
    name = process_name(pid)
    if name is None:
        return None
    return name.lstrip('-') in shell_names()


def adjustment_collapsed(lower, upper, page_size):
    """True when there is nothing to scroll (alt screen or empty history)."""
    if page_size <= 0:
        return False
    return (upper - lower) <= page_size + 0.5


def adjustment_scrollable(lower, upper, page_size):
    """True when the scrollbar can actually move.

    A zero page size means the widget has not been allocated yet, so the
    bar stays hidden instead of flashing a full slider.
    """
    if page_size <= 0:
        return False
    return (upper - lower) > page_size + 0.5


def scrollbar_should_show(position, scrollable, forced=None,
                          alt_auto_hidden=False, user_override=False):
    """Whether the scrollbar widget should be visible.

    ``left`` / ``right`` pack the bar on that side, but it is drawn only
    while the buffer is taller than the window.  ``hidden`` / ``disabled``
    never draw it.  ``forced`` is a manual toggle for this terminal
    (True show, False hide) and sticks until the caller clears it.
    Returns None when a fullscreen-program override owns the widget and
    the caller must leave it alone.  ``alt_auto_hidden`` is that override
    for the whole episode: a TUI redraw that briefly looks scrollable must
    not show the bar, or the pane is resized under the program.
    """
    if user_override:
        return None
    if forced is False:
        return False
    if position in ('disabled', 'hidden') and forced is not True:
        return False
    if alt_auto_hidden:
        return None
    if forced is True or scrollable:
        return True
    return False


def foreground_busy(pty_fd, child_pid, is_shell=is_shell_pid):
    """Is something other than the idle shell in the PTY foreground?

    Returns True/False, or None when it cannot be determined.
    A child that is not a shell at all (custom command such as ``htop``)
    counts as busy even when it owns the foreground.
    """
    if pty_fd is None or pty_fd < 0 or not child_pid or child_pid < 0:
        return None
    try:
        fg = os.tcgetpgrp(pty_fd)
    except OSError:
        return None
    if fg <= 0:
        # 0: foreground group outside our pid namespace / no session
        return None
    if fg != child_pid:
        return True
    shell = is_shell(child_pid)
    if shell is None:
        return None
    return not shell



def tty_raw(pty_fd):
    """True if the PTY is in non-canonical (raw/cbreak) mode.

    tcgetattr() on the master side returns the slave's termios on Linux.
    TUIs (vim, less, htop, tmux, curses) disable ICANON; line-oriented
    commands (ping, make, clear, cat) do not.  None if unknown.
    """
    if pty_fd is None or pty_fd < 0:
        return None
    try:
        lflag = termios.tcgetattr(pty_fd)[3]
    except (termios.error, OSError):
        return None
    return not (lflag & termios.ICANON)


class AltScreenDetector(object):
    """Pure state machine; see module docstring.

    An *episode* is a run of consecutive observations where the adjustment
    is collapsed and something other than the idle shell owns the PTY.
    The hide decision is taken at the start of an episode (with a short
    grace period so a TUI that switches to raw mode a moment after the
    alternate screen is still caught) and then kept until the episode
    ends.  This prevents a mid-session hide (and the SIGWINCH reflow it
    causes) inside a TUI that we initially decided to leave alone.
    """

    GRACE_S = 1.0
    # A TUI redraw can make the adjustment look scrollable for one sample
    # while the same program still owns the foreground. Ending the episode
    # there shows the scrollbar and resizes the grid under the program.
    # A real exit stays uncollapsed, or the shell takes the foreground.
    UNCOLLAPSE_HOLD_S = 0.4

    def __init__(self, clock=None):
        self.active = False
        self.had_history = False
        self.episode_start = None
        self._uncollapse_since = None
        self._clock = clock or time.monotonic

    def reset(self):
        self.active = False
        self.had_history = False
        self.episode_start = None
        self._uncollapse_since = None

    def update(self, collapsed, busy, raw=None, cursor_beyond=False):
        """Feed one observation and return the new ``active`` value.

        collapsed      adjustment has nothing to scroll
        busy           True/False/None (unknown => never hide)
        raw            PTY is in non-canonical mode (True/False/None)
        cursor_beyond  cursor row >= page size, i.e. the current screen's
                       ring has scrolled (evidence of content even when the
                       adjustment never showed it, e.g. ``seq 100; vim``
                       processed in one batch)
        """
        if not collapsed:
            self.had_history = True
            if self.active and busy is True:
                now = self._clock()
                since = self._uncollapse_since
                if since is None:
                    self._uncollapse_since = now
                    return self.active
                if now - since < self.UNCOLLAPSE_HOLD_S:
                    return self.active
            self._uncollapse_since = None
            self.active = False
            self.episode_start = None
        elif busy is False:
            self.had_history = False
            self.active = False
            self.episode_start = None
            self._uncollapse_since = None
        elif busy is None:
            # Foreground unknown (no child pid, e.g. flatpak spawn_async,
            # or tcgetpgrp/proc failed).  An idle readline prompt is also
            # in raw mode, so we cannot tell a TUI from the prompt: never
            # hide on guesswork.  Keep had_history untouched.
            self.active = False
            self.episode_start = None
            self._uncollapse_since = None
        else:
            self._uncollapse_since = None
            now = self._clock()
            if self.episode_start is None:
                self.episode_start = now
                self.active = False
            if not self.active and now - self.episode_start <= self.GRACE_S:
                self.active = bool((self.had_history or cursor_beyond)
                                   and raw is not False)
        return self.active

    def undecided(self):
        """True while this collapsed episode may still become a TUI.

        A TUI can switch the alternate screen a moment before it puts the
        PTY in raw mode. During the grace window ``active`` is still False
        but the decision is not final, so a provisional hide must stay.
        """
        if self.active or self.episode_start is None:
            return False
        try:
            return (self._clock() - self.episode_start) <= self.GRACE_S
        except Exception:
            return False


def should_auto_hide(active, enabled, position):
    """Hide only when the user's config would otherwise show a scrollbar."""
    return bool(active and enabled and position not in ('disabled', 'hidden'))


class AltScreenScrollbar(object):
    """Glue between a Terminal's VTE/scrollbar and AltScreenDetector."""

    def __init__(self, terminal):
        self.terminal = terminal
        self.detector = AltScreenDetector()
        self.auto_hidden = False
        self.hidden_width = 0
        # A bar hidden by Terminal.sync_scrollbar while a non-shell program
        # owns the PTY, before the debounced detector has decided. Keeps
        # the bar from being shown again during that window.
        self.pending_hidden = False
        self.pending_hide_width = 0
        # sync_scrollbar asked while pending_hidden owned the bar. Re-run
        # it once the detector decides this was not a TUI.
        self.sync_deferred = False
        # evaluate() sets this around the settled show, so hold_show
        # does not defer that retry.
        self._allow_show = False
        self.user_override = False
        self._timer = None
        self._handlers = []
        self._adj = None
        self.detached = False

    # -- wiring ---------------------------------------------------------
    def attach(self):
        vte = self.terminal.vte
        adj = vte.get_vadjustment()
        self._adj = adj
        self._handlers.append((adj, adj.connect('changed', self._on_change)))
        self._handlers.append(
            (vte, vte.connect('contents-changed', self._on_contents)))
        self._handlers.append(
            (vte, vte.connect('child-exited', self._on_child_exited)))
        self._handlers.append((vte, vte.connect('destroy', self._on_destroy)))

    def detach(self):
        """Disconnect everything.  Must run before the VTE is dropped:
        the handler closures and (obj, id) pairs form a reference cycle
        through GObject that Python's GC cannot break, which would keep
        the whole VTE (and its scrollback) alive after the pane closes."""
        self._cancel()
        for obj, hid in self._handlers:
            try:
                obj.disconnect(hid)
            except Exception:
                pass
        self._handlers = []
        self._adj = None
        self.detached = True

    # -- config ---------------------------------------------------------
    def _config(self, key, default):
        try:
            return self.terminal.config[key]
        except Exception:
            return default

    def enabled(self):
        return bool(self._config('scrollbar_hide_in_alt_screen', True))

    # -- events ---------------------------------------------------------
    def _on_change(self, adj=None, *_args):
        # Fast path: plain output growing the history on the normal screen
        # fires 'changed' for every line; no timer needed for that.
        if (adj is not None and not self.detector.active
                and not self.auto_hidden):
            try:
                if not adjustment_collapsed(adj.get_lower(), adj.get_upper(),
                                            adj.get_page_size()):
                    if self.pending_hidden or (
                            self.sync_deferred and not self._allow_show):
                        # A TUI redraw (or VTE updating upper and page_size
                        # one after the other) can look scrollable for one
                        # sample. Let evaluate() decide on the settled
                        # adjustment: it keeps the provisional hide for a
                        # TUI and drops it for a canonical command.
                        # Clearing the episode here would also forget a
                        # show that sync_scrollbar is still holding.
                        self.schedule()
                        return
                    self.detector.had_history = True
                    # An inactive collapse ends here. A stale episode_start
                    # would make the next fullscreen miss GRACE_S.
                    self.detector.episode_start = None
                    self.detector._uncollapse_since = None
                    return
            except Exception:
                pass
        self.schedule()

    def _latched(self):
        """True when another evaluate during this collapsed episode can only
        notice the TUI exiting (busy -> False), not a new decision."""
        det = self.detector
        if det.active or self.auto_hidden:
            return True
        start = det.episode_start
        if start is None:
            return False
        try:
            return (det._clock() - start) > det.GRACE_S
        except Exception:
            return False

    def _on_contents(self, *_args):
        # Entering the alternate screen from a screen that is already
        # collapsed (fresh terminal, or output + smcup processed in one
        # batch) changes nothing in the adjustment, so watch the contents
        # too -- but only while collapsed, where a state change is possible.
        if self._latched():
            # TUI redraws: only watch for the exit, at a slow rate. The
            # adjustment 'changed' path still reacts immediately.
            self.schedule(LATCHED_POLL_MS)
            return
        adj = self._adj
        try:
            if adj is not None and not adjustment_collapsed(
                    adj.get_lower(), adj.get_upper(), adj.get_page_size()):
                return
        except Exception:
            pass
        self.schedule()

    def _on_child_exited(self, *_args):
        self._cancel()
        was = self.detector.active
        self.detector.reset()
        self.user_override = False
        self.apply()
        if was:
            self._note_fullscreen_exited()

    def _on_destroy(self, *_args):
        self.detach()

    def schedule(self, delay_ms=None):
        if self.detached:
            return
        delay = DEBOUNCE_MS if delay_ms is None else int(delay_ms)
        if self._timer is not None:
            # A pending slow (latched) poll must not swallow a faster
            # request: the adjustment 'changed' on TUI exit wants the
            # normal debounce, not up to LATCHED_POLL_MS.
            if delay >= getattr(self, '_timer_delay', DEBOUNCE_MS):
                return
            self._cancel()
        self._timer_delay = delay
        self._timer = GLib.timeout_add(delay, self._fire)

    def _cancel(self):
        if self._timer is not None:
            try:
                GLib.source_remove(self._timer)
            except Exception:
                pass
            self._timer = None

    def _fire(self):
        self._timer = None
        if self.detached:
            return False
        try:
            self.evaluate()
        except Exception as ex:
            dbg('altscreen evaluate failed: %s' % ex)
        return False

    # -- logic ----------------------------------------------------------
    def _pty_fd(self):
        try:
            pty = self.terminal.vte.get_pty()
            return pty.get_fd() if pty is not None else None
        except Exception:
            return None

    def evaluate(self):
        adj = self._adj or self.terminal.vte.get_vadjustment()
        page = adj.get_page_size()
        collapsed = adjustment_collapsed(adj.get_lower(), adj.get_upper(),
                                         page)
        busy = raw = None
        beyond = False
        # Probe the foreground on an uncollapsed sample too, once a TUI is
        # active. Otherwise every redraw looks like an exit (busy stays
        # unknown) and the scrollbar is shown, which resizes the grid.
        if collapsed or self.detector.active:
            fd = self._pty_fd()
            busy = foreground_busy(fd, getattr(self.terminal, 'pid', None))
            if busy is not False:
                raw = tty_raw(fd)
                try:
                    row = self.terminal.vte.get_cursor_position()[1]
                    beyond = page > 0 and row >= page
                except Exception:
                    beyond = False
        was = self.detector.active
        now = self.detector.update(collapsed, busy, raw, beyond)
        if was != now:
            dbg('altscreen: %s -> %s (busy=%s raw=%s beyond=%s)'
                % (was, now, busy, raw, beyond))
        if not now:
            self.user_override = False
        self.apply()
        if was and not now:
            self._note_fullscreen_exited()
        elif now and not collapsed:
            # Still the same program, adjustment only just uncollapsed.
            # Look again after the hold instead of resizing on this sample.
            self.schedule(int(self.detector.UNCOLLAPSE_HOLD_S * 1000))
        return now

    def apply(self):
        sb = getattr(self.terminal, 'scrollbar', None)
        if sb is None:
            return
        position = self._config('scrollbar_position', 'right')
        hide = (should_auto_hide(self.detector.active, self.enabled(),
                                 position)
                and not self.user_override)
        scroll = self._scroll_value()
        if hide and not self.auto_hidden:
            width = 0
            if sb.get_visible():
                try:
                    width = max(0, int(sb.get_allocated_width()))
                except Exception:
                    width = 0
            elif self.hidden_width > 0:
                # Terminal.sync_scrollbar or reconfigure() hid it first.
                width = self.hidden_width
            elif self.pending_hidden:
                # sync_scrollbar hid it while the PTY was still canonical.
                width = self.pending_hide_width
            # Record the hide before the bar disappears. A synchronous
            # size-allocate then subtracts hidden_width, and the font
            # tier does not flip just because the VTE grew.
            self.auto_hidden = True
            self.hidden_width = width
            self.pending_hidden = False
            self.pending_hide_width = 0
            self.sync_deferred = False
            if sb.get_visible():
                sb.hide()
            self._hold_slot()
            self._restore_scroll(scroll)
            dbg('altscreen: scrollbar visible=%s' % sb.get_visible())
        elif not hide and self.auto_hidden:
            self._release_slot()
            self.auto_hidden = False
            self.hidden_width = 0
            self.pending_hidden = False
            self.pending_hide_width = 0
            self.sync_deferred = False
            # Terminal.sync_scrollbar shows the bar only when the restored
            # buffer is actually taller than the window.
            if getattr(self.terminal, 'sync_scrollbar', None) is not None:
                self._sync_after_decision()
            elif position not in ('disabled', 'hidden'):
                sb.show()
            self._restore_scroll(scroll)
            dbg('altscreen: scrollbar visible=%s' % sb.get_visible())
        elif not hide:
            # The detector decided this is not a TUI (a canonical command
            # cleared the screen, for example). Drop the provisional hide
            # so the next scrollable sample can show the bar again.
            if self.detector.undecided():
                return
            deferred = self.sync_deferred
            self.pending_hidden = False
            self.pending_hide_width = 0
            self.sync_deferred = False
            if deferred:
                self._sync_after_decision()

    def hold_show(self):
        """Keep a hidden bar hidden through this adjustment signal.

        VTE writes ``upper`` and ``page_size`` as separate ``changed``
        emissions. The first can look scrollable while a raw-mode program
        is redrawing. Showing the bar for that emission resizes the grid
        and the program's viewport jumps. The show is retried from
        ``evaluate`` once this signal has returned. A canonical command
        (``raw`` false) and the idle shell still show immediately.
        """
        if self._allow_show or self.detached or self.user_override:
            return False
        if not self.enabled():
            return False
        if self._config('scrollbar_position', 'right') in ('disabled',
                                                           'hidden'):
            return False
        fd = self._pty_fd()
        pid = getattr(self.terminal, 'pid', None)
        if foreground_busy(fd, pid) is not True:
            return False
        if tty_raw(fd) is False:
            return False
        self.sync_deferred = True
        # After the current emission. upper and page_size in the same
        # VTE update have both been applied by then.
        self.schedule(0)
        return True

    def _sync_after_decision(self):
        """Show the bar now that evaluate() has seen the settled range.

        ``hold_show`` returns immediately while this flag is set, so the
        retry cannot defer itself again.
        """
        sync = getattr(self.terminal, 'sync_scrollbar', None)
        if sync is None:
            return
        self._allow_show = True
        try:
            sync()
        finally:
            self._allow_show = False

    def note_bar_hidden(self, width):
        """Terminal.sync_scrollbar is about to hide a visible bar.

        The adjustment collapses a moment before a TUI switches the PTY to
        raw mode, so the debounced detector has not latched yet. If a
        non-shell program owns the foreground, record the hide now: the
        later apply() would otherwise see an invisible bar with no width
        and a single scrollable-looking redraw could show it again,
        resizing the grid under the program.
        """
        if self.auto_hidden or self.user_override or not self.enabled():
            return False
        if self._config('scrollbar_position', 'right') in ('disabled',
                                                           'hidden'):
            return False
        if foreground_busy(self._pty_fd(),
                           getattr(self.terminal, 'pid', None)) is not True:
            return False
        # Same evidence the detector needs: a TUI in a brand-new terminal
        # with nothing above the prompt is left alone, and a canonical
        # command that merely cleared the screen must not latch.
        if not (self.detector.had_history or self._cursor_beyond()):
            return False
        try:
            width = max(0, int(width))
        except (TypeError, ValueError):
            width = 0
        self.pending_hidden = True
        self.pending_hide_width = width
        self.sync_deferred = False
        return True

    def _cursor_beyond(self):
        """The current screen's ring has scrolled: content was drawn."""
        try:
            adj = self._adj or self.terminal.vte.get_vadjustment()
            page = adj.get_page_size()
            row = self.terminal.vte.get_cursor_position()[1]
            return page > 0 and row >= page
        except Exception:
            return False

    def effective_hidden_width(self):
        """Pixels the VTE gained from a bar that is off screen.

        Includes the provisional hide made by Terminal.sync_scrollbar
        before the detector latched, so the font tier does not flip for
        the 150 ms in between.
        """
        if self.auto_hidden:
            return self.hidden_width
        if self.pending_hidden:
            return self.pending_hide_width
        return 0

    def _scroll_value(self):
        try:
            adj = self.terminal.vte.get_vadjustment()
            return adj, float(adj.get_value())
        except Exception:
            return None, None

    def _restore_scroll(self, pin):
        """Hiding the bar must not move the view. A value change here is
        the vertical jump inside a fullscreen program."""
        adj, value = pin
        if adj is None or value is None:
            return
        try:
            if abs(float(adj.get_value()) - value) > 0.01:
                adj.set_value(value)
        except Exception:
            pass

    def _note_fullscreen_exited(self):
        note = getattr(self.terminal, 'note_fullscreen_exited', None)
        if callable(note):
            note()

    def _hold_slot(self):
        """Give the hidden bar's pixels to the VTE.

        A reserved slot is the empty profile-coloured strip beside a
        fullscreen program. ``hidden_width`` stays set for font and
        overlay math. Drop a leftover slot so that strip cannot remain.
        """
        self._release_slot()

    def _release_slot(self):
        release = getattr(self.terminal, 'release_scrollbar_slot', None)
        if callable(release):
            release()

    def user_toggled(self):
        """The user toggled the scrollbar by hand.

        Stop managing it; if a TUI is running, leave the user's choice
        alone until it exits.
        """
        if self.detector.active:
            self.user_override = True
        self._release_slot()
        self.auto_hidden = False
        self.hidden_width = 0
        self.pending_hidden = False
        self.pending_hide_width = 0
        self.sync_deferred = False

    def reconfigured(self):
        """Terminal.reconfigure() just set visibility from config."""
        width = self.hidden_width
        self._release_slot()
        self.auto_hidden = False
        self.pending_hidden = False
        self.pending_hide_width = 0
        self.sync_deferred = False
        # apply() measures a visible bar.  If it is already hidden, the
        # saved width is what font and overlay math still subtract.
        self.hidden_width = width
        self.apply()
        if not self.auto_hidden:
            self.hidden_width = 0
