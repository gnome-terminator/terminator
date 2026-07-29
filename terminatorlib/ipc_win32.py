# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""ipc_win32.py - Windows single-instance IPC over a named pipe.

On Linux, Terminator uses a DBus session service (``ipc.py``) both to enforce
single-instance behaviour and to forward command-line requests ("new window",
"new tab", "reload", ...) to the already-running master. Native Windows has no
session bus, so this module provides the equivalent transport using a named
pipe.

Design:
  * The master process creates a pipe server on
    ``\\\\.\\pipe\\terminator-<user>`` and serves requests as JSON lines.
  * A second instance tries to connect as a client; if it succeeds, a master
    is already running, so it forwards its options and exits. If the connect
    fails, the instance becomes the master.
  * The pipe name embeds the user name (the DBus implementation embeds the X11
    DISPLAY name) to keep sessions per-user.

This is the transport layer. Wiring it into the entry script's option
forwarding (mirroring ``ipc.new_window_cmdline`` etc.) is done in M3. The
method surface here mirrors the DBus service so the call sites stay
identical.
"""

from __future__ import print_function

import os
import sys
import json
import hashlib
import threading

from .util import dbg, err

PIPE_PREFIX = r'\\.\pipe\terminator'


def pipe_name():
    """Per-user pipe name (the Windows analogue of the per-Display DBus name)."""
    try:
        user = os.getlogin()
    except OSError:
        user = os.environ.get('USERNAME') or os.environ.get('USER') or 'default'
    digest = hashlib.md5(user.encode('utf-8')).hexdigest()[:8]
    return '%s-%s' % (PIPE_PREFIX, digest)


class PipeService(object):
    """Server-side single-instance + command dispatch.

    The owning process instantiates this and calls :meth:`start`. Incoming
    requests are JSON dicts with a ``method`` key plus an ``options`` dict; the
    matching handler on ``self.terminator`` (set by the entry point) is
    invoked. This mirrors the ``@dbus.service.method`` handlers in
    ``ipc.py``.
    """

    def __init__(self, terminator=None):
        self.terminator = terminator
        self._running = False
        self._server = None

    def start(self):
        """Start serving in a background thread. Returns True on success."""
        if sys.platform != 'win32':
            return False
        try:
            import win32pipe
            import win32file
        except ImportError:
            err('pywin32 not available; single-instance IPC disabled')
            return False
        self._win32pipe = win32pipe
        self._win32file = win32file
        self._running = True
        thread = threading.Thread(target=self._serve, daemon=True)
        thread.start()
        dbg('PipeService started on %s' % pipe_name())
        return True

    def _serve(self):
        name = pipe_name()
        PIPE_ACCESS = self._win32pipe.PIPE_ACCESS_DUPLEX
        PIPE_TYPE = self._win32pipe.PIPE_TYPE_MESSAGE | \
            self._win32pipe.PIPE_READMODE_MESSAGE
        while self._running:
            try:
                pipe = self._win32pipe.CreateNamedPipe(
                    name, PIPE_ACCESS, PIPE_TYPE,
                    self._win32pipe.PIPE_UNLIMITED_INSTANCES,
                    65536, 65536, 0, None)
            except Exception as e:
                err('CreateNamedPipe failed: %s' % e)
                break
            try:
                self._win32pipe.ConnectNamedPipe(pipe, None)
                threading.Thread(
                    target=self._handle, args=(pipe,), daemon=True).start()
            except Exception as e:
                err('ConnectNamedPipe failed: %s' % e)
                try:
                    self._win32pipe.DisconnectNamedPipe(pipe)
                except Exception:
                    pass

    def _handle(self, pipe):
        try:
            data = b''
            while True:
                result, chunk = self._win32file.ReadFile(pipe, 65536)
                data += chunk
                if result == 0:
                    break
            try:
                msg = json.loads(data.decode('utf-8'))
            except ValueError:
                msg = {}
            response = self._dispatch(msg)
            self._win32file.WriteFile(
                pipe, json.dumps(response).encode('utf-8'))
        except Exception as e:
            err('PipeService handler error: %s' % e)
        finally:
            try:
                self._win32pipe.DisconnectNamedPipe(pipe)
            except Exception:
                pass

    def _dispatch(self, msg):
        method = msg.get('method')
        options = msg.get('options', {})
        handler = getattr(self, 'cmd_%s' % method, None) \
            if method else None
        if handler is None:
            return {'ok': False, 'error': 'unknown method %r' % method}
        try:
            handler(options)
            return {'ok': True}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    # -- command surface (mirrors ipc.DBusService @method entries) -------

    def cmd_new_window(self, options):
        self.terminator.config.options_set(_options_obj(options))
        self.terminator.create_layout(options.get('layout'))
        self.terminator.layout_done()

    def cmd_new_tab(self, options):
        window = self.terminator.get_windows()[0]
        window.tab_new()

    def cmd_reload_configuration(self, options):
        self.terminator.config.base.reload()
        self.terminator.reconfigure()

    def cmd_toggle_visibility(self, options):
        for window in self.terminator.get_windows():
            window.on_hide_window()

    def cmd_unhide(self, options):
        for window in self.terminator.get_windows():
            if not window.get_property('visible'):
                window.on_hide_window()


def _options_obj(options):
    """Reconstitute an options namespace from a dict (mirrors DBus path)."""
    from argparse import Namespace
    return Namespace(**(options or {}))


def send_command(method, options):
    """Client: forward a single command to the running master.

    Returns the parsed response dict, or ``None`` if no master is running
    (in which case the caller should become the master).
    """
    if sys.platform != 'win32':
        return None
    try:
        import win32pipe
        import win32file
    except ImportError:
        return None
    msg = json.dumps({'method': method, 'options': options or {}}).encode('utf-8')
    try:
        pipe = win32file.CreateFile(
            pipe_name(),
            win32file.GENERIC_READ | win32file.GENERIC_WRITE,
            0, None, win32file.OPEN_EXISTING, 0, None)
    except Exception:
        return None  # no master
    try:
        win32file.WriteFile(pipe, msg)
        win32file.FlushFileBuffers(pipe)
        result, data = win32file.ReadFile(pipe, 65536)
        return json.loads(data.decode('utf-8'))
    except Exception as e:
        dbg('send_command failed: %s' % e)
        return None
    finally:
        try:
            win32file.CloseHandle(pipe)
        except Exception:
            pass
