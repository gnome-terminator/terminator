"""Stand-in fullscreen TUI for tests/smoke/tui_restore_smoke.sh (alt screen)."""
import sys
import time

try:
    import termios
    import tty
except ImportError:  # pragma: no cover
    tty = None


def main():
    # Real TUIs (vim/htop/less) switch the PTY to raw/cbreak; the M8
    # scrollbar detector relies on that, so mimic it.
    if tty is not None and sys.stdin.isatty():
        tty.setcbreak(sys.stdin.fileno(), termios.TCSANOW)
    sys.stdout.write('\x1b[?1049h\x1b[2J\x1b[H')
    for i in range(10):
        sys.stdout.write('TUIFRAME_%d\r\n' % i)
    sys.stdout.flush()
    time.sleep(600)


if __name__ == '__main__':
    main()
