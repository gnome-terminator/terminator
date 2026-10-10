"""Stand-in fullscreen TUI for tests/smoke/tui_restore_smoke.sh (alt screen)."""
import sys
import time


def main():
    sys.stdout.write('\x1b[?1049h\x1b[2J\x1b[H')
    for i in range(10):
        sys.stdout.write('TUIFRAME_%d\r\n' % i)
    sys.stdout.flush()
    time.sleep(600)


if __name__ == '__main__':
    main()
