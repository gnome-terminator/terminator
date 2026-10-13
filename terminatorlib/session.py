# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""session.py - Restore the previous session on startup (issue #1020)

When the 'restore_session' option is on, every shell runs behind a small
in-process relay: VTE talks to one pty, the shell to another, and we copy
bytes between them. Everything the shell prints is also appended to a
size-capped log. On the next start the saved layout is recreated and each
terminal's log is fed back into VTE, so the scrollback comes back exactly as
it was (colours, links, wrapping), followed by a fresh shell.

Session also keeps the last few panes, tabs and windows the user closed so
they can be reopened, and implements Quit (close every window at once, which
is what gets restored next time).

VTE has no API to export its buffer faithfully (the HTML export drops and
shifts attributes), so recording the raw stream is the only lossless way.
"""

import fcntl
import os
import signal
import termios
import time
import tty
from pathlib import Path

from gi.repository import GLib, Gtk, Vte
from configobj import ConfigObj

from .borg import Borg
from .terminator import Terminator
from .translation import _
from .util import dbg, err

# Put the terminal back into a sane state after replaying output from a
# process that no longer exists: attributes, cursor, mouse reporting,
# bracketed paste.
EPILOGUE = (b'\x1b[0m\x1b[?25h\x1b[?1000l\x1b[?1002l'
            b'\x1b[?1003l\x1b[?1006l\x1b[?2004l\r\n')
ALT_ON, ALT_OFF = b'\x1b[?1049h', b'\x1b[?1049l'
LOG_CAP = 4 << 20  # bytes of output kept per terminal
MAX_CLOSED = 10  # how many closed panes/tabs/windows can be reopened


def session_dir():
    """Where the saved layout and output logs live"""
    base = os.environ.get('XDG_STATE_HOME') or \
        os.path.join(os.path.expanduser('~'), '.local', 'state')
    return os.path.join(base, 'terminator', 'session')


def terminal_uuids(layout):
    """UUIDs (as strings) of the terminals in a flat layout dict"""
    return {str(obj['uuid']) for obj in layout.values()
            if obj.get('type') == 'Terminal' and obj.get('uuid')}


def as_saved(layout):
    """Round-trip a live describe_layout() through ConfigObj, so it has the
    same (string) values as a layout loaded from disk"""
    lines = ConfigObj(layout, encoding='utf-8').write()
    return ConfigObj(lines, encoding='utf-8').dict()


def tree(layout, name):
    """Turn a flat layout into the nested form the create_layout() methods of
    Window, Notebook, Paned and Terminal expect, starting at 'name'"""
    node = dict(layout[name])
    node['children'] = {key: tree(layout, key) for key, obj in layout.items()
                        if obj.get('parent') == name}
    return node


class Log:
    """Append-only output log for one terminal. Once it passes half the cap
    it becomes <uuid>.log.old and a new one starts, so the pair never uses
    more than the cap."""

    def __init__(self, key):
        self.path = os.path.join(session_dir(), key + '.log')
        self.fd = None
        self.open()

    def open(self):
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        self.size = os.fstat(fd).st_size
        self.fd = os.fdopen(fd, 'ab', buffering=64 * 1024)

    def write(self, data):
        if not self.fd:
            return
        self.fd.write(data)
        self.size += len(data)
        if self.size > LOG_CAP // 2:
            self.fd.close()
            os.replace(self.path, self.path + '.old')
            self.open()

    def flush(self):
        if self.fd:
            self.fd.flush()

    def close(self):
        if self.fd:
            self.fd.close()
            self.fd = None

    def read(self):
        """Saved output, oldest first. A rotated log may start in the middle
        of a line or an escape sequence, so it starts at the next full line."""
        old = self.path + '.old'
        data = b''.join(Path(p).read_bytes() for p in (old, self.path)
                        if os.path.exists(p))
        return data[data.find(b'\n') + 1:] if os.path.exists(old) else data


class Pipe:
    """Copy bytes from one fd to another without ever blocking the UI. While
    the destination is full we stop reading the source, so the kernel makes
    the writer (the shell, or VTE) wait, instead of us buffering forever."""

    def __init__(self, src, dst, filt, done):
        self.src, self.dst, self.filt, self.done = src, dst, filt, done
        self.buf = b''
        self.wait_for(src, GLib.IO_IN)

    def wait_for(self, fd, cond):
        self.watch = GLib.io_add_watch(fd, GLib.PRIORITY_DEFAULT,
                                       cond | GLib.IO_HUP | GLib.IO_ERR,
                                       self.pump)

    def pump(self, fd, _cond):
        try:
            if fd == self.src:
                data = os.read(self.src, 65536)
                if not data:
                    raise EOFError
                self.buf = self.filt(data)
            written = os.write(self.dst, self.buf) if self.buf else 0
        except BlockingIOError:
            written = 0
        except (OSError, EOFError):
            # EIO/EOF: the other side has gone away
            self.watch = None
            self.done()
            return False
        self.buf = self.buf[written:]
        if bool(self.buf) == (fd == self.dst):
            return True  # still draining, or still reading
        if self.buf:
            self.wait_for(self.dst, GLib.IO_OUT)
        else:
            self.wait_for(self.src, GLib.IO_IN)
        return False

    def stop(self):
        if self.watch:
            GLib.source_remove(self.watch)
            self.watch = None


class Relay:
    """Run a terminal's shell on our own pty and copy its output to VTE and
    to the terminal's log."""

    def __init__(self, terminal, args, envv, log):
        self.terminal = terminal
        self.log = log
        self.vte = vte = terminal.vte

        master, self.tty = os.openpty()
        vte.set_pty(Vte.Pty.new_foreign_sync(master))
        os.set_blocking(self.tty, False)
        tty.setraw(self.tty)

        self.inner = Vte.Pty.new_sync(Vte.PtyFlags.DEFAULT)
        self.master = self.inner.get_fd()
        os.set_blocking(self.master, False)
        self.resize()
        self.resize_id = vte.connect_after('size-allocate', self.resize)

        self.pipes = [Pipe(self.master, self.tty, self.output, self.close),
                      Pipe(self.tty, self.master, bytes, self.close)]
        self.inner.spawn_async(terminal.cwd, args, envv,
                               GLib.SpawnFlags.FILE_AND_ARGV_ZERO, None, None,
                               -1, None, self.spawned)

    def spawned(self, pty, result):
        try:
            _ok, pid = pty.spawn_finish(result)
        except GLib.Error as ex:
            err('Relay: unable to start shell: %s' % ex)
            self.vte.feed(str(ex).encode())
            self.close()
            return
        self.terminal.pid = pid
        self.vte.watch_child(pid)

    def output(self, data):
        # Vte.Pty uses packet mode: a zero byte, then the data. Non-zero
        # headers are flow-control notices with no data.
        if data[0]:
            return b''
        data = data[1:]
        self.log.write(data)
        return data

    def resize(self, *_args):
        """Give the shell's pty the size VTE just gave its own"""
        size = fcntl.ioctl(self.tty, termios.TIOCGWINSZ, b'\0' * 8)
        fcntl.ioctl(self.master, termios.TIOCSWINSZ, size)

    def close(self):
        if self.inner is None:
            return
        for pipe in self.pipes:
            pipe.stop()
        if self.vte.handler_is_connected(self.resize_id):
            self.vte.disconnect(self.resize_id)
        os.close(self.tty)
        self.inner = None  # dropping the Vte.Pty closes the shell's pty


class Session(Borg):
    """Records the session while Terminator runs and hands it back at
    startup"""
    active = None
    frozen = None
    logs = None
    restore = None
    saved = None
    closed_units = None

    def __init__(self):
        Borg.__init__(self, self.__class__.__name__)
        self.prepare_attributes()

    def prepare_attributes(self):
        if self.logs is None:
            self.active = False
            self.frozen = False
            self.logs = {}
            self.restore = set()
            self.saved = None
            self.closed_units = []

    def start(self):
        """Start recording. Returns the previous session's layout, if any."""
        os.makedirs(session_dir(), mode=0o700, exist_ok=True)
        self.active = True
        GLib.timeout_add_seconds(5, self.tick)
        for signum in (signal.SIGTERM, signal.SIGHUP):
            GLib.unix_signal_add(GLib.PRIORITY_HIGH, signum, self.on_signal)

        path = os.path.join(session_dir(), 'layout')
        try:
            layout = ConfigObj(path, encoding='utf-8').dict()
        except Exception as ex:
            err('Session: unable to read %s: %s' % (path, ex))
            return None
        self.restore = terminal_uuids(layout)
        # A window with no terminals left means the user closed them all
        return layout if self.restore else None

    def spawn(self, terminal, args, envv):
        """Start a terminal's shell behind a relay, replaying its saved
        output first if we are restoring it"""
        key = str(terminal.uuid)
        log = self.logs.get(key)
        if log is None:
            log = self.logs[key] = Log(key)
        if key in self.restore:
            self.restore.discard(key)
            # ponytail: replays at VTE's size before the window is allocated;
            # output drawn with cursor movement at another width may look
            # off. Defer to the first size-allocate if that matters.
            data = log.read()
            if data:
                # Leave the alternate screen (vim, less...) only if we are
                # in it: ALT_OFF also restores the saved cursor position.
                # ponytail: only mode 1049, the one current apps use
                in_alt = data.rfind(ALT_ON) > data.rfind(ALT_OFF)
                stamp = (ALT_OFF if in_alt else b'') + EPILOGUE + \
                    ('\x1b[2m--- restored %s ---\x1b[0m\r\n' %
                     time.strftime('%c')).encode()
                terminal.vte.feed(data + stamp)
                log.write(stamp)
        terminal.relay = Relay(terminal, args, envv, log)

    def tick(self):
        if self.frozen:
            return False
        self.save()
        return True

    def save(self):
        """Flush the logs, write the layout if it changed, and delete the logs
        of terminals that were closed"""
        for log in self.logs.values():
            log.flush()
        terminator = Terminator()
        if terminator.doing_layout:
            return
        try:
            layout = terminator.describe_layout(save_cwd=True)
        except Exception as ex:  # a layout bug must not stop saving or Quit
            err('Session: unable to describe the layout: %s' % ex)
            return
        text = b'\n'.join(ConfigObj(layout, encoding='utf-8').write())
        if text != self.saved:
            path = os.path.join(session_dir(), 'layout')
            fd = os.open(path + '.tmp', os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                         0o600)
            with os.fdopen(fd, 'wb') as layoutfile:
                layoutfile.write(text)
            os.replace(path + '.tmp', path)
            self.saved = text

        live = terminal_uuids(layout)
        for unit in self.closed_units:
            live |= terminal_uuids(unit)
        for name in os.listdir(session_dir()):
            key = name.split('.')[0]
            if name.endswith(('.log', '.log.old')) and key not in live:
                dbg('Session: forgetting terminal %s' % key)
                if key in self.logs:
                    self.logs.pop(key).close()
                os.remove(os.path.join(session_dir(), name))

    def freeze(self):
        """Terminator is going away: save everything and stop recording, so
        closing the remaining terminals doesn't erase them from the session"""
        if self.frozen:
            return
        if self.active:
            self.save()
            for log in self.logs.values():
                log.close()
        self.frozen = True

    def on_signal(self):
        """Logout or shutdown"""
        dbg('Session: caught SIGTERM/SIGHUP, saving session')
        self.freeze()
        Gtk.main_quit()
        return False

    def quit(self, parent):
        """Close every window at once. With restore_session on, all of them
        come back on the next start (closing them one by one only brings
        back the last)."""
        terminator = Terminator()
        ask = terminator.config['ask_before_closing']
        if ask == 'always' or (ask == 'multiple_terminals' and
                               len(terminator.terminals) > 1):
            dialog = Gtk.MessageDialog(
                transient_for=parent, modal=True,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.OK_CANCEL,
                text=_('Quit Terminator?'))
            dialog.format_secondary_text(
                _('All windows will be reopened next time you start '
                  'Terminator.') if self.active else
                _('This closes all windows and terminals.'))
            answer = dialog.run()
            dialog.destroy()
            if answer != Gtk.ResponseType.OK:
                return
        self.freeze()
        for window in terminator.windows[:]:
            window.destroy()  # runs on_destroy_event exactly once

    def closed(self, widget, tab_label=None):
        """Remember a pane, tab or window the user is closing, so that
        reopen() can bring it back. Call before it is torn down."""
        if self.frozen:
            return  # quitting, not closing
        layout = {}
        try:
            widget.describe_layout(0, '', layout, 0, save_cwd=True)
        except Exception as ex:  # never block the close itself
            err('Session: unable to remember %s: %s' % (widget, ex))
            return
        uuids = terminal_uuids(layout)
        if not uuids:
            return
        for unit in self.closed_units:
            if uuids <= terminal_uuids(unit):
                return  # part of a tab or window already remembered
        layout = as_saved(layout)
        if tab_label:
            root = [key for key, obj in layout.items() if not obj['parent']]
            layout[root[0]]['tab_label'] = tab_label
        self.closed_units.append(layout)
        del self.closed_units[:-MAX_CLOSED]

    def reopen(self, terminal):
        """Bring back the most recently closed pane or tab (as a new tab in
        terminal's window) or window, with its output if we recorded it"""
        if not self.closed_units:
            return
        layout = self.closed_units.pop()
        uuids = terminal_uuids(layout)
        self.restore |= uuids
        root = [key for key, obj in layout.items() if not obj['parent']][0]
        kind = layout[root]['type']
        terminator = Terminator()
        if kind == 'Window':
            terminator.config.base.layouts['__reopen__'] = layout
            terminator.create_layout('__reopen__')
            del terminator.config.base.layouts['__reopen__']
        else:
            # ponytail: comes back as the last tab, not at its old place
            terminator.doing_layout = True
            window = terminal.get_toplevel()
            window.tab_new()
            notebook = window.get_child()
            page = notebook.get_nth_page(notebook.get_current_page())
            if kind != 'Terminal':
                notebook.split_axis(page, kind == 'VPaned')
                page = notebook.get_nth_page(notebook.get_current_page())
            page.create_layout(tree(layout, root))
            if layout[root].get('tab_label'):
                notebook.get_tab_label(page).set_custom_label(
                    layout[root]['tab_label'])
        terminator.doing_layout = False
        for term in terminator.terminals:
            if str(term.uuid) in uuids:
                term.spawn_child()
