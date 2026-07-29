# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""backends.conpty.pty - Windows ConPTY pseudoconsole wrapper.

This is the Windows equivalent of VTE's PTY layer (fork + openpty on POSIX).
Windows 10 1809+ exposes the ``CreatePseudoConsole`` / ``ResizePseudoConsole``
/ ``ClosePseudoConsole`` API ("ConPTY"), which gives us a real PTY around a
spawned console process. This module binds that API (plus the supporting
``CreatePipe`` / ``CreateProcess`` / attribute-list plumbing) via ``ctypes``
so we avoid a hard compile-time dependency on the Windows SDK.

Everything here is Windows-only; :class:`ConPty` raises ``ImportError`` if
constructed on a non-Windows platform, and the renderer never imports this
module on Linux.
"""

from __future__ import print_function

import sys
import ctypes
from ctypes import wintypes

if sys.platform == 'win32':  # pragma: no cover - exercised on Windows CI only
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)  # pylint: disable=no-member
else:
    kernel32 = None

# ---------------------------------------------------------------------------
# Structures and constants
# ---------------------------------------------------------------------------

# PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE and the extended-startupinfo flag. These
# are what bind a child process to our pseudoconsole handle.
PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE = 0x00020016
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
CREATE_UNICODE_ENVIRONMENT = 0x00000400
CREATE_NO_WINDOW = 0x08000000
INFINITE = 0xFFFFFFFF
WAIT_TIMEOUT = 0x102
STILL_ACTIVE = 259


class COORD(ctypes.Structure):
    _fields_ = (('X', ctypes.c_short), ('Y', ctypes.c_short))


class STARTUPINFOEX(ctypes.Structure):
    class _STARTUPINFO(ctypes.Structure):
        _fields_ = (
            ('cb', wintypes.DWORD),
            ('lpReserved', wintypes.LPWSTR),
            ('lpDesktop', wintypes.LPWSTR),
            ('lpTitle', wintypes.LPWSTR),
            ('dwX', wintypes.DWORD),
            ('dwY', wintypes.DWORD),
            ('dwXSize', wintypes.DWORD),
            ('dwYSize', wintypes.DWORD),
            ('dwXCountChars', wintypes.DWORD),
            ('dwYCountChars', wintypes.DWORD),
            ('dwFillAttribute', wintypes.DWORD),
            ('dwFlags', wintypes.DWORD),
            ('wShowWindow', ctypes.c_ushort),
            ('cbReserved2', ctypes.c_ushort),
            ('lpReserved2', ctypes.POINTER(ctypes.c_byte)),
            ('hStdInput', wintypes.HANDLE),
            ('hStdOutput', wintypes.HANDLE),
            ('hStdError', wintypes.HANDLE),
        )
    _fields_ = (
        ('StartupInfo', _STARTUPINFO),
        ('lpAttributeList', ctypes.c_void_p),
    )


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = (
        ('hProcess', wintypes.HANDLE),
        ('hThread', wintypes.HANDLE),
        ('dwProcessId', wintypes.DWORD),
        ('dwThreadId', wintypes.DWORD),
    )


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = (
        ('nLength', wintypes.DWORD),
        ('lpSecurityDescriptor', wintypes.LPVOID),
        ('bInheritHandle', wintypes.BOOL),
    )


# HPCON is an opaque pointer; model it as void*.
_HPCON = ctypes.c_void_p

if kernel32 is not None:  # pragma: no cover
    kernel32.CreatePseudoConsole.restype = ctypes.c_long  # HRESULT
    kernel32.CreatePseudoConsole.argtypes = [
        COORD, wintypes.HANDLE, wintypes.HANDLE, wintypes.DWORD,
        ctypes.POINTER(_HPCON)]
    kernel32.ResizePseudoConsole.restype = ctypes.c_long
    kernel32.ResizePseudoConsole.argtypes = [_HPCON, COORD]
    kernel32.ClosePseudoConsole.restype = None
    kernel32.ClosePseudoConsole.argtypes = [_HPCON]

    kernel32.CreatePipe.restype = wintypes.BOOL
    kernel32.CreatePipe.argtypes = [
        ctypes.POINTER(wintypes.HANDLE), ctypes.POINTER(wintypes.HANDLE),
        ctypes.POINTER(SECURITY_ATTRIBUTES), wintypes.DWORD]
    kernel32.PeekNamedPipe.restype = wintypes.BOOL
    kernel32.PeekNamedPipe.argtypes = [
        wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD)]
    kernel32.ReadFile.restype = wintypes.BOOL
    kernel32.ReadFile.argtypes = [
        wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
    kernel32.WriteFile.restype = wintypes.BOOL
    kernel32.WriteFile.argtypes = [
        wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    kernel32.InitializeProcThreadAttributeList.restype = wintypes.BOOL
    kernel32.DeleteProcThreadAttributeList.restype = None
    kernel32.UpdateProcThreadAttribute.restype = wintypes.BOOL

    kernel32.CreateProcessW.restype = wintypes.BOOL
    kernel32.CreateProcessW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.POINTER(SECURITY_ATTRIBUTES),
        ctypes.POINTER(SECURITY_ATTRIBUTES), wintypes.BOOL, wintypes.DWORD,
        wintypes.LPVOID, wintypes.LPCWSTR, ctypes.POINTER(STARTUPINFOEX),
        ctypes.POINTER(PROCESS_INFORMATION)]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]


class ConPtyError(RuntimeError):
    """Raised when a ConPTY syscall fails (carries GetLastError())."""


class ConPty(object):
    """A single ConPTY pseudoconsole plus its child process.

    Typical use::

        pty = ConPty()
        pty.open(80, 24)
        pid = pty.spawn(['powershell.exe'], ['TERM=xterm-256color'], r'C:\\')
        pty.write(b'echo hi\r')
        chunk = pty.read()      # non-blocking; b'' if nothing buffered
        pty.resize(120, 30)
        pty.close()
    """

    def __init__(self):
        if kernel32 is None:
            raise ImportError('ConPTY is only available on Windows')
        self._hpc = None
        self._proc_info = None
        self._input_write = None   # we write child input here (-> pty reads)
        self._output_read = None   # we read child output here (pty writes)
        self._closed = False

    # -- lifecycle --------------------------------------------------------

    def open(self, columns, rows):
        """Create the pseudoconsole and the two pipe ends we own."""
        sa = SECURITY_ATTRIBUTES()
        sa.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
        sa.bInheritHandle = True  # so the child can inherit (we still own our ends)

        input_read = wintypes.HANDLE()   # pty reads child input from here
        input_write = wintypes.HANDLE()  # we write here
        output_read = wintypes.HANDLE()  # we read here
        output_write = wintypes.HANDLE()  # pty writes child output here

        if not kernel32.CreatePipe(
                ctypes.byref(input_read), ctypes.byref(input_write),
                ctypes.byref(sa), 0):
            raise ConPtyError('CreatePipe(input) failed: %d' %
                              ctypes.get_last_error())
        if not kernel32.CreatePipe(
                ctypes.byref(output_read), ctypes.byref(output_write),
                ctypes.byref(sa), 0):
            raise ConPtyError('CreatePipe(output) failed: %d' %
                              ctypes.get_last_error())

        size = COORD(columns, rows)
        hpc = _HPCON()
        # PSEUDOCONSOLE_INHERIT_CURSOR is 0x1; we do not inherit, so flags=0.
        hr = kernel32.CreatePseudoConsole(
            size, input_read, output_write, 0, ctypes.byref(hpc))
        if hr != 0:
            raise ConPtyError('CreatePseudoConsole failed: 0x%08x' % (hr & 0xffffffff))

        # The pty now owns the read end of the input pipe and the write end of
        # the output pipe; we keep the complementary ends.
        kernel32.CloseHandle(input_read)
        kernel32.CloseHandle(output_write)

        self._hpc = hpc
        self._input_write = input_write
        self._output_read = output_read

    def spawn(self, argv, envv, cwd):
        """Start ``argv`` (a list) under this pseudoconsole.

        ``envv`` is a list of ``KEY=VALUE`` strings (UTF-8, like VTE's). We
        build a UTF-16 environment block. Returns the child PID.
        """
        startup = STARTUPINFOEX()
        startup.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEX)

        # Build the attribute list carrying the pseudoconsole handle.
        size = wintypes.DWORD(0)
        kernel32.InitializeProcThreadAttributeList(None, 1, 0,
                                                    ctypes.byref(size))
        buf = (ctypes.c_byte * size.value)()
        startup.lpAttributeList = ctypes.cast(buf, ctypes.c_void_p)
        if not kernel32.InitializeProcThreadAttributeList(
                ctypes.cast(startup.lpAttributeList,
                            ctypes.POINTER(ctypes.c_void)),
                1, 0, ctypes.byref(size)):
            raise ConPtyError('InitializeProcThreadAttributeList failed: %d' %
                             ctypes.get_last_error())
        try:
            if not kernel32.UpdateProcThreadAttribute(
                    ctypes.cast(startup.lpAttributeList,
                                ctypes.POINTER(ctypes.c_void)),
                    0, PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE,
                    self._hpc, ctypes.sizeof(_HPCON), None, None):
                raise ConPtyError('UpdateProcThreadAttribute failed: %d' %
                                 ctypes.get_last_error())

            # Environment block: UTF-16, NUL-separated, double-NUL terminated.
            env_block = '\0'.join(envv or []) + '\0\0'
            env_bytes = env_block.encode('utf-16-le')

            cmdline = ' '.join(_quote(a) for a in argv)
            proc = PROCESS_INFORMATION()
            creation = EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT
            ok = kernel32.CreateProcessW(
                None, ctypes.create_unicode_buffer(cmdline), None, None,
                False, creation, env_bytes,
                cwd or None,
                ctypes.byref(startup), ctypes.byref(proc))
            if not ok:
                raise ConPtyError('CreateProcessW failed: %d' %
                                 ctypes.get_last_error())

            self._proc_info = proc
            kernel32.CloseHandle(proc.hThread)
            return proc.dwProcessId
        finally:
            kernel32.DeleteProcThreadAttributeList(
                ctypes.cast(startup.lpAttributeList,
                            ctypes.POINTER(ctypes.c_void)))

    # -- I/O --------------------------------------------------------------

    def write(self, data):
        """Send bytes to the child's input."""
        if self._input_write is None or not data:
            return 0
        written = wintypes.DWORD(0)
        ok = kernel32.WriteFile(self._input_write, data, len(data),
                                ctypes.byref(written), None)
        return written.value if ok else 0

    def read(self, max_bytes=65536):
        """Non-blocking read of available output bytes.

        Uses PeekNamedPipe first so we never block the GTK main loop.
        """
        if self._output_read is None:
            return b''
        available = wintypes.DWORD(0)
        if not kernel32.PeekNamedPipe(self._output_read, None, 0, None,
                                     ctypes.byref(available), None):
            return b''
        if available.value == 0:
            return b''
        n = min(available.value, max_bytes)
        buf = (ctypes.c_char * n)()
        read = wintypes.DWORD(0)
        if not kernel32.ReadFile(self._output_read, buf, n,
                                 ctypes.byref(read), None):
            return b''
        return bytes(buf[:read.value])

    def resize(self, columns, rows):
        if self._hpc is None:
            return
        kernel32.ResizePseudoConsole(self._hpc, COORD(columns, rows))

    def poll_exit(self):
        """Return True if the child has exited (non-blocking)."""
        if self._proc_info is None:
            return True
        result = kernel32.WaitForSingleObject(
            self._proc_info.hProcess, 0)
        if result == WAIT_TIMEOUT:
            return False
        return True

    def exit_code(self):
        if self._proc_info is None:
            return None
        code = wintypes.DWORD(0)
        kernel32.GetExitCodeProcess(self._proc_info.hProcess,
                                    ctypes.byref(code))
        return code.value

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._hpc is not None:
            kernel32.ClosePseudoConsole(self._hpc)
            self._hpc = None
        for attr in ('_input_write', '_output_read'):
            h = getattr(self, attr, None)
            if h is not None:
                kernel32.CloseHandle(h)
                setattr(self, attr, None)
        if self._proc_info is not None and self._proc_info.hProcess:
            kernel32.CloseHandle(self._proc_info.hProcess)
            self._proc_info = None


def _quote(arg):
    """Minimal Windows command-line quoting."""
    if arg and ' ' not in arg and '"' not in arg:
        return arg
    return '"%s"' % arg.replace('"', '\\"')
