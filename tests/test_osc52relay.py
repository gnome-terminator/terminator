"""Tests for the OSC 52 relay (PTY pumping layer)."""

import base64
import fcntl
import os
import struct
import sys
import termios

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

from terminatorlib.osc52relay import Osc52Relay, open_pairs  # noqa: E402


def close_quietly(fds):
    for fd in fds:
        try:
            os.close(fd)
        except OSError:
            pass


def drain(fd, count=16):
    """Read up to *count* chunks from *fd*, ignoring empties."""
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    data = b""
    for _ in range(count):
        try:
            chunk = os.read(fd, 8192)
        except (BlockingIOError, OSError):
            break
        if not chunk:
            break
        data += chunk
    return data


def test_open_pairs_returns_two_independent_ptys():
    child_master, child_slave, vte_master, vte_slave = open_pairs()
    try:
        assert os.isatty(child_slave) and os.isatty(vte_slave)
        assert child_master != vte_master
    finally:
        close_quietly((child_master, child_slave, vte_master, vte_slave))


def set_raw(fd):
    """Drop ICANON/ECHO so input is not line-buffered, as VTE would do."""
    attrs = termios.tcgetattr(fd)
    attrs[3] &= ~(termios.ICANON | termios.ECHO)
    termios.tcsetattr(fd, termios.TCSANOW, attrs)


def test_relay_strips_child_output_and_forwards_input():
    child_master, child_slave, vte_master, vte_slave = open_pairs()
    relay_master = os.dup(vte_master)
    try:
        relay = Osc52Relay(lambda selections, text: None)
        relay.enable(child_master, relay_master, vte_slave)
        set_raw(vte_slave)

        os.write(child_slave,
                 b"plain\r\n\x1b]52;c;" + base64.b64encode(b"hi") + b"\x07tail\r\n")
        assert relay._on_child_readable(child_master, 0)
        # ONLCR turns \n into \r\n on the way out of the child's tty.
        assert drain(vte_master) == b"plain\r\r\r\ntail\r\r\r\n"

        # Keyboard input travels the other way, unfiltered: VTE writes it to
        # its PTY master, we read it at the slave and hand it to the child.
        set_raw(child_slave)
        os.write(relay_master, b"\x1b[A")
        assert relay._on_vte_readable(vte_slave, 0)
        assert drain(child_slave) == b"\x1b[A"
    finally:
        relay.close()
        close_quietly((child_master, child_slave, vte_master, vte_slave))


def test_relay_invokes_clipboard_callback():
    child_master, child_slave, vte_master, vte_slave = open_pairs()
    relay_master = os.dup(vte_master)
    seen = []
    try:
        relay = Osc52Relay(lambda selections, text: seen.append((list(selections), text)))
        relay.enable(child_master, relay_master, vte_slave)

        os.write(child_slave, b"\x1b]52;c;" + base64.b64encode(b"hi") + b"\x07")
        relay._on_child_readable(child_master, 0)

        assert seen == [(["CLIPBOARD"], b"hi")]
    finally:
        relay.close()
        close_quietly((child_master, child_slave, vte_master, vte_slave))


def test_relay_forwards_window_size():
    child_master, child_slave, vte_master, vte_slave = open_pairs()
    relay_master = os.dup(vte_master)
    try:
        relay = Osc52Relay(lambda selections, text: None)
        relay.enable(child_master, relay_master, vte_slave)

        fcntl.ioctl(relay_master, termios.TIOCSWINSZ,
                    struct.pack("HHHH", 44, 132, 0, 0))
        os.write(child_slave, b"x")
        relay._on_child_readable(child_master, 0)

        size = fcntl.ioctl(child_master, termios.TIOCGWINSZ, b"\0" * 8)
        rows, cols = struct.unpack("HHHH", size)[:2]
        assert (rows, cols) == (44, 132)
    finally:
        relay.close()
        close_quietly((child_master, child_slave, vte_master, vte_slave))


def test_close_closes_owned_fds():
    child_master, child_slave, vte_master, vte_slave = open_pairs()
    relay_master = os.dup(vte_master)
    relay = Osc52Relay(lambda selections, text: None)
    relay.enable(child_master, relay_master, vte_slave)
    relay.close()
    for fd in (child_master, relay_master, vte_slave):
        try:
            os.fstat(fd)
            closed = False
        except OSError:
            closed = True
        assert closed, "fd %d still open" % fd
    close_quietly((child_slave, vte_master))


def test_relay_ignores_callbacks_after_close():
    child_master, child_slave, vte_master, vte_slave = open_pairs()
    relay_master = os.dup(vte_master)
    seen = []
    relay = Osc52Relay(lambda selections, text: seen.append(text))
    relay.enable(child_master, relay_master, vte_slave)
    relay.close()
    relay.filter.feed(b"\x1b]52;c;" + base64.b64encode(b"hi") + b"\x07")
    assert seen == []
    close_quietly((child_slave, vte_master))
