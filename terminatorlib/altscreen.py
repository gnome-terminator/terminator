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
until the episode ends, so a TUI is never reflowed mid-session.

Consequences:

* vim/less/htop/tmux/mc after some output              -> hidden
* ``ping``/``make`` in a fresh or just-cleared terminal  -> untouched
  (canonical mode), so no hide/show flap when output starts scrolling
* a TUI in a brand-new terminal with nothing above the prompt -> untouched
  (the scrollbar shows a full slider; there is nothing to scroll)
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
"""

import os
import termios
import time

from gi.repository import GLib

from .util import dbg

DEBOUNCE_MS = 150

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

    def __init__(self, clock=None):
        self.active = False
        self.had_history = False
        self.episode_start = None
        self._clock = clock or time.monotonic

    def reset(self):
        self.active = False
        self.had_history = False
        self.episode_start = None

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
            self.active = False
            self.episode_start = None
        elif busy is False:
            self.had_history = False
            self.active = False
            self.episode_start = None
        elif busy is None:
            # Foreground unknown (no child pid, e.g. flatpak spawn_async,
            # or tcgetpgrp/proc failed).  An idle readline prompt is also
            # in raw mode, so we cannot tell a TUI from the prompt: never
            # hide on guesswork.  Keep had_history untouched.
            self.active = False
            self.episode_start = None
        else:
            now = self._clock()
            if self.episode_start is None:
                self.episode_start = now
                self.active = False
            if not self.active and now - self.episode_start <= self.GRACE_S:
                self.active = bool((self.had_history or cursor_beyond)
                                   and raw is not False)
        return self.active


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
                    self.detector.had_history = True
                    return
            except Exception:
                pass
        self.schedule()

    def _on_contents(self, *_args):
        # Entering the alternate screen from a screen that is already
        # collapsed (fresh terminal, or output + smcup processed in one
        # batch) changes nothing in the adjustment, so watch the contents
        # too -- but only while collapsed, where a state change is possible.
        if self.detector.active or self.auto_hidden:
            self.schedule()
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
        self.detector.reset()
        self.user_override = False
        self.apply()

    def _on_destroy(self, *_args):
        self.detach()

    def schedule(self):
        if self._timer is not None or self.detached:
            return
        self._timer = GLib.timeout_add(DEBOUNCE_MS, self._fire)

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
        if collapsed:
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
        return now

    def apply(self):
        sb = getattr(self.terminal, 'scrollbar', None)
        if sb is None:
            return
        position = self._config('scrollbar_position', 'right')
        hide = (should_auto_hide(self.detector.active, self.enabled(),
                                 position)
                and not self.user_override)
        if hide and not self.auto_hidden:
            if not sb.get_visible():
                return  # user (or config) already hid it; nothing to undo
            try:
                self.hidden_width = max(0, sb.get_allocated_width())
            except Exception:
                self.hidden_width = 0
            self.auto_hidden = True
            sb.hide()
            dbg('altscreen: scrollbar visible=%s' % sb.get_visible())
        elif not hide and self.auto_hidden:
            self.auto_hidden = False
            self.hidden_width = 0
            if position not in ('disabled', 'hidden'):
                sb.show()
            dbg('altscreen: scrollbar visible=%s' % sb.get_visible())

    def user_toggled(self):
        """The user toggled the scrollbar by hand.

        Stop managing it; if a TUI is running, leave the user's choice
        alone until it exits.
        """
        if self.detector.active:
            self.user_override = True
        self.auto_hidden = False
        self.hidden_width = 0

    def reconfigured(self):
        """Terminal.reconfigure() just set visibility from config."""
        self.auto_hidden = False
        self.hidden_width = 0
        self.apply()
