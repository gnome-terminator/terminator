"""Tmux control mode protocol layer.

Handles subprocess management, protocol parsing, and command queuing.
No GTK dependencies in this module.
"""

import os
import queue
import signal
import subprocess
import threading
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Optional

from terminatorlib.util import dbg


def unescape_tmux_output(data: bytes) -> bytes:
    """Reverse tmux's octal escaping.

    In control mode, tmux escapes characters < 0x20 and backslash itself
    as \\NNN (octal). This function converts them back to raw bytes.
    """
    result = bytearray()
    i = 0
    while i < len(data):
        if data[i:i+1] == b'\\' and i + 3 < len(data):
            # Check for octal escape \NNN
            octal = data[i+1:i+4]
            try:
                val = int(octal, 8)
                result.append(val)
                i += 4
                continue
            except (ValueError, IndexError):
                pass
        result.append(data[i])
        i += 1
    return bytes(result)


@dataclass
class CommandResult:
    """Result of a tmux command."""
    timestamp: str = ''
    command_number: str = ''
    output_lines: list = field(default_factory=list)
    is_error: bool = False


class TmuxSubprocess:
    """Wraps subprocess.Popen for tmux control mode."""

    TMUX_BINARY = 'tmux'

    def __init__(self, arguments: list):
        self._process = None
        self._arguments = arguments
        self._line_queue = queue.Queue()
        self._pipe_thread = None

    def start(self):
        """Start the tmux subprocess."""
        self._process = subprocess.Popen(
            [self.TMUX_BINARY] + self._arguments,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            bufsize=0,
        )
        self._pipe_thread = threading.Thread(
            target=self._pipe_content,
            daemon=True,
        )
        self._pipe_thread.start()

    def _pipe_content(self):
        """Read lines from tmux stdout into a queue."""
        try:
            for line in iter(self._process.stdout.readline, b''):
                self._line_queue.put(line)
        except Exception:
            pass
        finally:
            self._line_queue.put(None)

    def send_raw(self, line: str):
        """Send a raw line to tmux stdin."""
        try:
            self._process.stdin.write('{}\n'.format(line).encode())
            self._process.stdin.flush()
        except (IOError, BrokenPipeError):
            dbg('TmuxSubprocess: failed to send: %s' % line)

    def stop(self):
        """Stop the tmux subprocess."""
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
            except Exception:
                pass

    def is_alive(self) -> bool:
        """Check if the subprocess is running."""
        return self._process is not None and self._process.poll() is None

    def __iter__(self):
        return self

    def __next__(self):
        line = self._line_queue.get(block=True)
        if line is not None:
            return line
        raise StopIteration


class NotificationReader(threading.Thread):
    """Daemon thread that reads tmux stdout and parses control mode protocol.

    Dispatches:
    - %begin/%end/%error blocks -> matched to pending commands
    - %output -> output handler
    - %layout-change -> layout handler
    - %window-add, %window-close, %window-renamed -> window handlers
    - %session-changed, %session-renamed -> session handlers
    - %exit -> exit handler
    """

    def __init__(self, subprocess_iter, handler_map, command_queue):
        super().__init__(daemon=True)
        self._subprocess_iter = subprocess_iter
        self._handler_map = handler_map
        self._command_queue = command_queue
        self._running = True

    def run(self):
        try:
            for raw_line in self._subprocess_iter:
                if not self._running:
                    break
                line = raw_line.rstrip(b'\n')
                if not line.startswith(b'%'):
                    continue

                parts = line[1:].split(b' ', 1)
                marker = parts[0].decode('ascii', errors='replace')
                data = parts[1] if len(parts) > 1 else b''

                if marker == 'begin':
                    self._handle_begin(data, line)
                elif marker == 'output':
                    self._handle_output(data)
                elif marker == 'layout-change':
                    self._handle_layout_change(data)
                elif marker == 'exit':
                    self._dispatch('exit', {'reason': data.decode('utf-8', errors='replace')})
                    break
                elif marker in ('window-add', 'window-close', 'window-renamed',
                                'unlinked-window-add', 'unlinked-window-close',
                                'unlinked-window-renamed',
                                'session-changed', 'session-renamed',
                                'sessions-changed'):
                    self._handle_notification(marker, data)
                else:
                    dbg('NotificationReader: unknown marker: %s' % marker)
        except StopIteration:
            pass
        except Exception as e:
            dbg('NotificationReader: error: %s' % e)
            traceback.print_exc()
        finally:
            self._dispatch('exit', {'reason': 'reader stopped'})

    def stop(self):
        self._running = False

    def _handle_begin(self, data, first_line):
        """Handle %begin/%end/%error command result blocks."""
        output_lines = []
        is_error = False
        for raw_line in self._subprocess_iter:
            line = raw_line.rstrip(b'\n')
            if line.startswith(b'%end') or line.startswith(b'%error'):
                is_error = line.startswith(b'%error')
                break
            output_lines.append(line)

        result = CommandResult(
            output_lines=output_lines,
            is_error=is_error,
        )

        # Match to pending command callback
        try:
            callback = self._command_queue.get_nowait()
        except queue.Empty:
            callback = None

        if callback is not None:
            try:
                callback(result)
            except Exception as e:
                dbg('NotificationReader: callback error: %s' % e)
                traceback.print_exc()

    def _handle_output(self, data: bytes):
        """Handle %output %PANE_ID DATA."""
        parts = data.split(b' ', 1)
        if len(parts) < 2:
            return
        pane_id = parts[0].decode('ascii', errors='replace')
        raw_output = parts[1]
        # Unescape tmux octal encoding
        output_bytes = unescape_tmux_output(raw_output)
        self._dispatch('output', {
            'pane_id': pane_id,
            'data': output_bytes,
        })

    def _handle_layout_change(self, data: bytes):
        """Handle %layout-change @WIN_ID LAYOUT."""
        decoded = data.decode('utf-8', errors='replace')
        parts = decoded.split(' ', 2)
        if len(parts) >= 2:
            self._dispatch('layout-change', {
                'window_id': parts[0],
                'layout_string': parts[1],
            })

    def _handle_notification(self, marker: str, data: bytes):
        """Handle simple notifications."""
        decoded = data.decode('utf-8', errors='replace')
        parts = decoded.split(' ', 1)
        info = {'raw': decoded}
        if marker in ('window-add', 'window-close', 'unlinked-window-add',
                       'unlinked-window-close'):
            info['window_id'] = parts[0] if parts else ''
        elif marker in ('window-renamed', 'unlinked-window-renamed'):
            info['window_id'] = parts[0] if parts else ''
            info['name'] = parts[1] if len(parts) > 1 else ''
        elif marker in ('session-changed', 'session-renamed'):
            info['session_id'] = parts[0] if parts else ''
            info['name'] = parts[1] if len(parts) > 1 else ''
        self._dispatch(marker, info)

    def _dispatch(self, marker: str, info: dict):
        """Call all registered handlers for this marker."""
        handlers = self._handler_map.get(marker, [])
        for handler in handlers:
            try:
                handler(info)
            except Exception as e:
                dbg('NotificationReader: handler error for %s: %s' % (marker, e))
                traceback.print_exc()


class TmuxProtocol:
    """Combines TmuxSubprocess + NotificationReader.

    Provides send_command() with optional callback for responses.
    """

    def __init__(self, session_name: str, new_session: bool = False):
        self.session_name = session_name
        self._handler_map = defaultdict(list)
        self._command_queue = queue.Queue()
        self._reader = None

        if new_session:
            args = ['-2', '-C', 'new-session', '-s', session_name]
        else:
            args = ['-2', '-C', 'attach-session', '-t', session_name]
        self._subprocess = TmuxSubprocess(args)

    def start(self):
        """Start the tmux subprocess and reader thread."""
        self._subprocess.start()
        # tmux sends an initial %begin/%end on connect; queue a dummy callback
        self._command_queue.put(None)
        self._reader = NotificationReader(
            self._subprocess, self._handler_map, self._command_queue
        )
        self._reader.start()

    def stop(self, send_detach=True):
        """Stop the protocol. Sends detach first unless send_detach=False."""
        if send_detach:
            try:
                self._subprocess.send_raw('detach')
            except Exception:
                pass
        if self._reader:
            self._reader.stop()
        self._subprocess.stop()

    def send_command(self, cmd: str, callback: Optional[Callable] = None):
        """Send a command to tmux. Optional callback receives CommandResult."""
        self._command_queue.put(callback)
        self._subprocess.send_raw(cmd)

    def add_handler(self, marker: str, handler: Callable):
        """Register a handler for a notification type."""
        self._handler_map[marker].append(handler)

    def is_alive(self) -> bool:
        return self._subprocess.is_alive()


class PtyTmuxBridge:
    """Wraps an existing PTY fd where tmux -CC is already running.

    Used when the user runs 'tmux -CC' inside a Terminator terminal.
    We take over the PTY fd as the communication channel to tmux.

    PTY raw mode produces lines with \\x00 prefixes and \\r\\n endings.
    This bridge cleans those up before queuing lines.
    """

    def __init__(self, fd: int):
        self._fd = fd
        self._line_queue = queue.Queue()
        self._pipe_thread = None
        self._alive = True
        self._saved_termios = None
        # Disable echo on the PTY so our commands aren't reflected back
        try:
            import termios
            self._saved_termios = termios.tcgetattr(fd)
            attrs = list(self._saved_termios)
            attrs[3] = attrs[3] & ~termios.ECHO  # lflags: disable ECHO
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
        except Exception as e:
            dbg('PtyTmuxBridge: could not disable echo: %s' % e)

    def start(self):
        """Start reading from the PTY fd."""
        self._pipe_thread = threading.Thread(
            target=self._pipe_content,
            daemon=True,
        )
        self._pipe_thread.start()

    def _pipe_content(self):
        """Read from PTY fd, split into lines, clean up PTY artifacts."""
        import select
        buf = b''
        try:
            while self._alive:
                r, _, _ = select.select([self._fd], [], [], 1.0)
                if not r:
                    continue
                try:
                    data = os.read(self._fd, 65536)
                except OSError:
                    break
                if not data:
                    break
                buf += data
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    # Strip PTY artifacts:
                    # - NUL bytes anywhere (PTY inserts these randomly,
                    #   corrupting octal sequences like \033 when a NUL
                    #   lands between digits)
                    # - trailing \r from ONLCR output processing
                    line = line.replace(b'\x00', b'').rstrip(b'\r')
                    self._line_queue.put(line + b'\n')
        except Exception:
            pass
        finally:
            self._line_queue.put(None)

    def send_raw(self, line: str):
        """Send a raw line to tmux via the PTY fd."""
        try:
            os.write(self._fd, '{}\n'.format(line).encode())
        except (IOError, OSError):
            dbg('PtyTmuxBridge: failed to send: %s' % line)

    def restore_termios(self):
        """Restore saved terminal attributes on the fd."""
        if self._saved_termios:
            try:
                import termios
                termios.tcsetattr(self._fd, termios.TCSANOW, self._saved_termios)
            except Exception:
                pass
            self._saved_termios = None

    def stop(self):
        """Stop reading and close the fd."""
        self._alive = False
        try:
            os.close(self._fd)
        except OSError:
            pass

    def is_alive(self) -> bool:
        return self._alive

    def __iter__(self):
        return self

    def __next__(self):
        line = self._line_queue.get(block=True)
        if line is not None:
            return line
        raise StopIteration


class TmuxProtocolFromPty:
    """Like TmuxProtocol but uses an existing PTY fd.

    Used when tmux -CC was started by the user in a terminal.
    """

    def __init__(self, pty_fd: int):
        self._handler_map = defaultdict(list)
        self._command_queue = queue.Queue()
        self._reader = None
        self._bridge = PtyTmuxBridge(pty_fd)
        self.session_name = None

    def start(self):
        """Start reading from the PTY."""
        self._bridge.start()
        # Don't queue a dummy callback — the initial %begin/%end
        # already passed through VTE before we took over
        self._reader = NotificationReader(
            self._bridge, self._handler_map, self._command_queue
        )
        self._reader.start()

    def stop(self, send_detach=True):
        """Stop the protocol. Sends detach first unless send_detach=False."""
        if send_detach:
            try:
                self._bridge.send_raw('detach')
            except Exception:
                pass
        if self._reader:
            self._reader.stop()
        self._bridge.stop()

    def send_command(self, cmd: str, callback: Optional[Callable] = None):
        """Send a command to tmux. Optional callback receives CommandResult."""
        self._command_queue.put(callback)
        self._bridge.send_raw(cmd)

    def add_handler(self, marker: str, handler: Callable):
        """Register a handler for a notification type."""
        self._handler_map[marker].append(handler)

    def is_alive(self) -> bool:
        return self._bridge.is_alive()
