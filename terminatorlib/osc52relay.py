# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""osc52relay.py - put a filtering pump between the child and VTE.

VTE exposes no hook that lets a caller observe the bytes it reads from the
child's PTY, and it has no OSC 52 handler, so a terminal cannot "see" an
OSC 52 sequence any other way.  What we can do is give VTE a PTY we control:

* the child runs on one PTY pair; we hold its master;
* VTE gets the master of a second pair; we hold that pair's slave;
* a GLib-powered pump copies bytes in both directions, filtering the
  child's output through :class:`~terminatorlib.osc52.Osc52Filter`.

Ordering and content are preserved for everything except the sequences the
filter consumes, and the window size VTE sets on its own PTY is forwarded to
the child's, so ``stty size`` and SIGWINCH keep working.
"""

import fcntl
import os
import termios

from gi.repository import GLib

from .osc52 import Osc52Filter
from .util import dbg, err

#: Bytes moved per read.  Big enough that a full-screen redraw needs few
#: iterations, small enough that one read stays cheap.
CHUNK = 8192


def open_pairs():
    """Open the two PTY pairs the relay needs.

    Returns ``(child_master, child_slave, vte_master, vte_slave)``.  The
    child is spawned on *child_slave*; VTE is handed *vte_master*; the relay
    keeps *child_master* and *vte_slave* and moves bytes between them.
    """
    child_master, child_slave = os.openpty()
    vte_master, vte_slave = os.openpty()
    return child_master, child_slave, vte_master, vte_slave


class Osc52Relay:
    """Copies bytes between the child's PTY and VTE's, stripping OSC 52.

    Everything runs on the GTK main loop, so the clipboard callback is
    always invoked from the main thread, as GTK requires.  The relay does
    nothing until :meth:`enable` is called.
    """

    def __init__(self, write_clipboard):
        self.write_clipboard = write_clipboard
        self.filter = Osc52Filter(self._on_sequence)
        self.enabled = False
        #: fd of the child's PTY master: we read the child's output here.
        self.child_master = -1
        #: fd of VTE's PTY master; VTE reads there, we only close it.
        self.vte_master = -1
        #: fd of VTE's PTY slave: we write output to, and read input from,
        #: here.
        self.vte_slave = -1
        self._sources = []

    # -- lifecycle ------------------------------------------------------

    def enable(self, child_master, vte_master, vte_slave):
        """Start pumping between *child_master* and *vte_slave*."""
        self.child_master = child_master
        self.vte_master = vte_master
        self.vte_slave = vte_slave
        self.enabled = True
        for fd in (child_master, vte_slave):
            self._set_nonblocking(fd)
        self._sources.append(GLib.io_add_watch(
            child_master, GLib.IO_IN | GLib.IO_HUP, self._on_child_readable))
        self._sources.append(GLib.io_add_watch(
            vte_slave, GLib.IO_IN | GLib.IO_HUP, self._on_vte_readable))
        # VTE has already sized its own PTY by now; copy that across so the
        # child starts with the right geometry.
        self._forward_window_size()
        dbg('osc52: relay enabled')

    def close(self):
        """Stop pumping and close every fd the relay owns."""
        for source in self._sources:
            GLib.source_remove(source)
        self._sources = []
        self.enabled = False
        for fd in (self.child_master, self.vte_slave, self.vte_master):
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
        self.child_master = -1
        self.vte_slave = -1
        self.vte_master = -1
        dbg('osc52: relay closed')

    # -- pumping --------------------------------------------------------

    def _on_child_readable(self, _fd, condition):
        """Child output: filter it and hand it to VTE."""
        if condition & GLib.IO_HUP:
            return False
        if not self._pump(self.child_master, self.vte_slave, self.filter.feed):
            return False
        self._forward_window_size()
        return True

    def _on_vte_readable(self, _fd, condition):
        """Keyboard input from VTE: pass it through unfiltered."""
        if condition & GLib.IO_HUP:
            return False
        return self._pump(self.vte_slave, self.child_master, lambda data: data)

    @staticmethod
    def _pump(source, sink, transform):
        """Move one chunk from *source* to *sink* through *transform*."""
        try:
            data = os.read(source, CHUNK)
        except BlockingIOError:
            return True
        except OSError as ex:
            err('osc52: read failed: %s' % ex)
            return False
        if not data:
            return False
        rest = transform(data)
        if not rest:
            return True
        try:
            os.write(sink, rest)
        except OSError as ex:
            err('osc52: write failed: %s' % ex)
            return False
        return True

    def _on_sequence(self, selections, text):
        if not self.enabled:
            return
        try:
            self.write_clipboard(selections, text)
        except Exception as ex:  # pragma: no cover - clipboard may be gone
            err('osc52: clipboard write failed: %s' % ex)

    def _forward_window_size(self):
        """Make the child's PTY as large as VTE's, so SIGWINCH still fires."""
        try:
            size = fcntl.ioctl(self.vte_master, termios.TIOCGWINSZ, b'\0' * 8)
            fcntl.ioctl(self.child_master, termios.TIOCSWINSZ, size)
        except OSError:
            pass

    @staticmethod
    def _set_nonblocking(fd):
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
