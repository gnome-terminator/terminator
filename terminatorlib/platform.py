# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""platform.py - cross-platform abstractions

This module is the single source of truth for platform-specific behaviour.
It is intentionally written to depend only on the Python standard library so
that it can be imported and unit-tested on any platform without GTK, VTE or
dbus being present.

The historical codebase was hard-wired to POSIX/Linux (``pwd``, ``os.getuid``,
X11 ``WINDOWID``, ``xdg-open``, DBus, XDG dirs, ``/etc/xdg``). The functions
here collect those concerns behind platform-aware implementations that keep
Linux behaviour byte-for-byte identical while providing Windows equivalents.
"""

from __future__ import print_function

import os
import sys

# ---------------------------------------------------------------------------
# Platform flags
# ---------------------------------------------------------------------------

IS_WINDOWS = sys.platform == 'win32'
IS_MACOS = sys.platform == 'darwin'
IS_LINUX = sys.platform.startswith('linux')
IS_BSD = sys.platform in ('freebsd', 'openbsd', 'netbsd') or \
    'bsd' in sys.platform


def is_windows():
    """Whether we are running on native Windows (not WSL)."""
    return IS_WINDOWS


def is_flatpak():
    """Whether we are running inside a Flatpak sandbox.

    Only meaningful on Linux; always False elsewhere.
    """
    return os.path.exists("/.flatpak-info")


def display_manager():
    """Try to detect which display manager we run under.

    Returns ``'WAYLAND'``, ``'X11'`` or ``'WIN32'``. Callers that need an X
    server (GdkX11, raw libX11 ctypes, Keybinder) use this to short-circuit
    on non-X11 platforms -- which is exactly how we keep them off Windows.
    """
    if IS_WINDOWS:
        return 'WIN32'
    if os.environ.get('WAYLAND_DISPLAY'):
        return 'WAYLAND'
    # Fallback assumption of X11
    return 'X11'


def supports_dbus():
    """Whether the DBus-based single-instance IPC is available.

    Native Windows has no session bus, so the Windows port uses a named-pipe
    IPC implementation instead (see ``ipc_win32.py``). This flag lets the
    entry point and ``ipc`` module pick the right transport.
    """
    if IS_WINDOWS:
        return False
    try:
        import dbus  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Path / shell discovery
# ---------------------------------------------------------------------------

def path_separator():
    """The OS path list separator (``:`` on POSIX, ``;`` on Windows)."""
    return os.pathsep


def default_path_fallback():
    """Paths used when ``$PATH`` is not set in the environment."""
    if IS_WINDOWS:
        # Common Windows executable directories.  The installer may also
        # ship its own runtime; this is just a sane last resort.
        return [
            os.environ.get('SystemRoot', r'C:\Windows') + r'\System32',
            os.environ.get('SystemRoot', r'C:\Windows'),
            os.environ.get('SystemRoot', r'C:\Windows') + r'\System32\Wbem',
        ]
    return ['/usr/local/bin', '/usr/bin', '/bin']


def path_lookup(command):
    """Find a command in our path.

    On Windows the ``PATHEXT`` mechanism is honoured so that a bare
    ``powershell`` resolves to ``powershell.exe``.
    """
    if os.path.isabs(command):
        if os.path.isfile(command):
            return command
        # On Windows, allow ``powershell`` to match ``powershell.exe`` even
        # when given an absolute bare name without extension.
        if IS_WINDOWS:
            for ext in _pathext():
                candidate = command + ext
                if os.path.isfile(candidate):
                    return candidate
        return None
    elif command[:2] == './' and os.path.isfile(command):
        return command

    try:
        paths = os.environ['PATH'].split(path_separator())
        if len(paths[0]) == 0:
            raise ValueError
    except (ValueError, KeyError):
        paths = default_path_fallback()

    for path in paths:
        target = os.path.join(path, command)
        if os.path.isfile(target):
            return target
        if IS_WINDOWS:
            for ext in _pathext():
                candidate = target + ext
                if os.path.isfile(candidate):
                    return candidate

    return None


def _pathext():
    """The list of executable extensions to try on Windows."""
    if not IS_WINDOWS:
        return ['']
    patext = os.environ.get('PATHEXT', '.COM;.EXE;.BAT;.CMD')
    return [e for e in patext.split(os.pathsep) if e]


def default_windows_shell():
    """Discover the preferred shell on native Windows.

    Order of preference: PowerShell (pwsh/powershell), then cmd.exe.
    Returns the resolved absolute path or ``None``.
    """
    # pwsh (PowerShell Core) is preferable to the inbox Windows PowerShell.
    for name in ('pwsh.exe', 'powershell.exe', 'cmd.exe'):
        found = path_lookup(name)
        if found:
            return found
    # Last resort: COMSPEC (cmd.exe) is essentially always set on Windows.
    comspec = os.environ.get('COMSPEC')
    if comspec and os.path.isfile(comspec):
        return comspec
    return None


def shell_lookup():
    """Find an appropriate shell for the user.

    Linux path is unchanged from the historical implementation (Flatpak-aware,
    ``pwd.getpwuid`` for the login shell, then a fallback chain). Windows path
    resolves PowerShell/cmd via ``path_lookup``.
    """
    import subprocess

    if IS_WINDOWS:
        return default_windows_shell()

    if is_flatpak():
        import pwd
        getent = subprocess.check_output([
            'flatpak-spawn', '--host', 'getent', 'passwd',
            pwd.getpwuid(os.getuid())[0]
        ]).decode(encoding='UTF-8').rstrip('\n')
        shell = getent.split(':')[6]
        return shell

    try:
        import pwd
        usershell = pwd.getpwuid(os.getuid())[6]
    except (KeyError, ImportError):
        usershell = None
    shells = [usershell, 'bash', 'zsh', 'tcsh', 'ksh', 'csh', 'sh']

    for shell in shells:
        if shell is None:
            continue
        elif os.path.isfile(shell):
            return shell
        else:
            rshell = path_lookup(shell)
            if rshell is not None:
                return rshell
    return None


# ---------------------------------------------------------------------------
# URL opening
# ---------------------------------------------------------------------------

def open_url(url):
    """Open ``url`` in the user's preferred handler.

    Returns the launched process/Popen on success (so callers can manage it)
    or ``None`` on failure. On Linux this replaces the ``xdg-open`` fallback;
    on Windows it delegates to ``os.startfile``.
    """
    import subprocess

    if IS_WINDOWS:
        try:
            os.startfile(url)  # pylint: disable=no-member
            return True
        except OSError:
            # WindowsError is a subclass of OSError, so this covers both.
            return None

    try:
        return subprocess.Popen(["xdg-open", url])
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Window identification
# ---------------------------------------------------------------------------

def get_window_id_env(widget):
    """Return the ``WINDOWID`` environment value for a child process, or None.

    On X11 this is the GdkWindow's XID (so shells/tools that query ``$WINDOWID``
    keep working). On Wayland and Windows there is no such concept, so we
    return ``None`` and callers skip setting it.
    """
    if display_manager() != 'X11':
        return None
    try:
        xid = widget.get_parent_window().xid
    except AttributeError:
        return None
    return '%s' % xid


# ---------------------------------------------------------------------------
# Config directories
# ---------------------------------------------------------------------------

def get_config_dir():
    """Locate the per-user Terminator config directory.

    Linux: ``$XDG_CONFIG_HOME/terminator`` (default ``~/.config/terminator``).
    Windows: ``%APPDATA%\\terminator`` (Roaming profile, survives reboot).
    """
    if IS_WINDOWS:
        base = os.environ.get('APPDATA') or os.path.expanduser('~')
        return os.path.join(base, 'terminator')

    try:
        configdir = os.environ['XDG_CONFIG_HOME']
    except KeyError:
        configdir = os.path.join(os.path.expanduser('~'), '.config')
    return os.path.join(configdir, 'terminator')


def get_system_config_dir():
    """Locate the system-wide Terminator config directory.

    Linux: first existing entry of ``$XDG_CONFIG_DIRS`` then ``/etc/xdg``.
    Windows: there is no conventional system config dir, so we return the
    install data directory under ``%ProgramData%`` (or empty if unavailable).
    """
    if IS_WINDOWS:
        base = os.environ.get('ProgramData') or r'C:\ProgramData'
        return os.path.join(base, 'terminator')

    system_config_dir = '/etc/xdg'
    if 'XDG_CONFIG_DIRS' in os.environ.keys():
        for sysconfdir in os.environ['XDG_CONFIG_DIRS'].split(":"):
            if os.path.isdir(sysconfdir):
                system_config_dir = sysconfdir
                break
    return os.path.join(system_config_dir, 'terminator')


# ---------------------------------------------------------------------------
# Window decoration (Dark/Light/Auto) -- Windows DWM bridge
# ---------------------------------------------------------------------------

def set_window_dark_mode(window_handle, dark=True):
    """Toggle immersive dark mode for a HWND via DWM.

    This is the Windows equivalent of the X11 ``_GTK_THEME_VARIANT`` property
    set via raw libX11 ctypes in ``window.py``. It is a no-op on non-Windows
    platforms so callers can invoke it unconditionally.

    ``window_handle`` is a Win32 HWND (int). On Windows we lazily bind
    ``dwmapi``.
    """
    if not IS_WINDOWS:
        return False
    try:
        import ctypes
        from ctypes import wintypes
        DWMAPI = ctypes.WinDLL('dwmapi')  # pylint: disable=no-member
        DWMWA_USE_IMMERSIVE_DARK_MODE = getattr(
            DWMAPI, 'DWMWA_USE_IMMERSIVE_DARK_MODE', 20)
        if isinstance(DWMWA_USE_IMMERSIVE_DARK_MODE, int):
            attr = DWMWA_USE_IMMERSIVE_DARK_MODE
        else:
            attr = 20
        value = ctypes.c_int(1 if dark else 0)
        DWMAPI.DwmSetWindowAttribute(
            wintypes.HWND(window_handle), ctypes.c_int(attr),
            ctypes.byref(value), ctypes.sizeof(value))
        return True
    except Exception:
        return False
