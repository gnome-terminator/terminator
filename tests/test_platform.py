# Tests for the platform abstraction layer (terminatorlib/platform.py).
#
# These run on Linux but also exercise the Windows branches by patching
# IS_WINDOWS, so the Windows code paths get coverage on Linux CI.
import os
import importlib

import terminatorlib.platform as platform


def test_path_lookup_finds_known_binary():
    # `ls` is present on every CI runner we target.
    assert platform.path_lookup('ls') is not None


def test_path_lookup_missing_returns_none():
    assert platform.path_lookup('definitely-not-a-real-binary-xyz') is None


def test_shell_lookup_returns_a_string_on_linux():
    sh = platform.shell_lookup()
    assert isinstance(sh, str) and sh


def test_display_manager_linux_default():
    assert platform.display_manager() in ('X11', 'WAYLAND')


def test_supports_dbus_true_on_linux():
    assert platform.supports_dbus() is True


def test_windows_config_dir(monkeypatch):
    monkeypatch.setattr(platform, 'IS_WINDOWS', True)
    monkeypatch.setenv('APPDATA', r'C:\Users\test\AppData\Roaming')
    d = platform.get_config_dir()
    # os.path.join uses the host separator; normalise before asserting so
    # the test is meaningful on a Linux runner exercising the Windows branch.
    assert d.replace('/', '\\').lower() == r'c:\users\test\appdata\roaming\terminator'


def test_windows_display_manager(monkeypatch):
    monkeypatch.setattr(platform, 'IS_WINDOWS', True)
    assert platform.display_manager() == 'WIN32'


def test_windows_supports_dbus_false(monkeypatch):
    monkeypatch.setattr(platform, 'IS_WINDOWS', True)
    assert platform.supports_dbus() is False


def test_windows_open_url_uses_startfile(monkeypatch):
    monkeypatch.setattr(platform, 'IS_WINDOWS', True)
    opened = {}
    # os.startfile only exists on Windows; install a stub so the Windows
    # branch can be exercised on a Linux runner.
    monkeypatch.setattr(platform.os, 'startfile',
                        lambda url: opened.setdefault('url', url),
                        raising=False)
    assert platform.open_url('https://example.com') is True
    assert opened['url'] == 'https://example.com'


def test_set_window_dark_mode_noop_on_linux():
    # Must not raise on non-Windows and returns False.
    assert platform.set_window_dark_mode(0, dark=True) is False
