# Terminator ConPTY backend package.
#
# screen.py is pure-Python (no Windows/GTK deps) and is unit-tested on Linux.
# pty.py wraps the Windows ConPTY API and only imports pywin32/ctypes at
# runtime on win32.
