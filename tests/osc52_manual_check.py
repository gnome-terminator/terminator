"""OSC 52 end-to-end smoke test: child PTY -> relay -> VTE PTY -> clipboard.

Not collected by pytest (no ``test_`` prefix): it needs Xvfb, VTE and a GTK
main loop, and it spawns real children.

    xvfb-run -a python3 tests/osc52_manual_check.py
"""

import base64
import os
import signal
import sys
import tempfile

import gi

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Vte", "2.91")

from gi.repository import Gdk, GLib, Gtk, Vte  # noqa: E402

from terminatorlib.terminal import Terminal  # noqa: E402
from terminatorlib.osc52relay import Osc52Relay, open_pairs  # noqa: E402

TEXT_SENT = b"clipboard-set-by-osc52"
SEEN = []
SENT_TO_VTE = bytearray()


def write_clipboard(selections, text):
    for name in selections:
        atom = Gdk.SELECTION_CLIPBOARD if name == "CLIPBOARD" else Gdk.SELECTION_PRIMARY
        Gtk.Clipboard.get(atom).set_text(text.decode("utf-8", "replace"), -1)
    SEEN.append((list(selections), text))


def main():
    size_file = tempfile.NamedTemporaryFile(prefix="osc52_size_", delete=False)
    size_file.close()

    child_master, child_slave, vte_master, vte_slave = open_pairs()
    relay_master = os.dup(vte_master)

    vte = Vte.Terminal()
    vte.set_pty(Vte.Pty.new_foreign_sync(vte_master))
    vte.set_size(100, 30)
    window = Gtk.Window()
    window.add(vte)
    window.show_all()
    window.resize(900, 500)

    payload = base64.b64encode(TEXT_SENT).decode()
    cmd = ('echo plain;'
           ' printf "\\033]52;c;%s\\007" %s;'
           ' echo after; stty size | tee %s; sleep 30'
           % (payload, payload, size_file.name))

    pid = GLib.spawn_async(
        ["/bin/bash", "/bin/bash", "-c", cmd],
        working_directory="/tmp",
        envp=["TERM=xterm"],
        child_setup=lambda: Terminal._osc52_child_setup(child_slave),
        flags=GLib.SpawnFlags.FILE_AND_ARGV_ZERO | GLib.SpawnFlags.DO_NOT_REAP_CHILD,
    )[0]
    os.close(child_slave)
    vte.watch_child(pid)

    relay = Osc52Relay(write_clipboard)
    relay.enable(child_master, relay_master, vte_slave)

    # Record what the relay hands to VTE, i.e. what the user would see.
    inner_feed = relay.filter.feed

    def recording_feed(data):
        rest = inner_feed(data)
        SENT_TO_VTE.extend(rest)
        return rest

    relay.filter.feed = recording_feed

    checks = []

    def report():
        with open(size_file.name) as handle:
            reported_size = handle.read().strip()
        os.unlink(size_file.name)
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text()
        results = [
            ("sequence captured", [s[0] for s in SEEN] == [["CLIPBOARD"]]
             and SEEN[0][1] == TEXT_SENT),
            ("sequence not displayed", b"\x1b]52" not in SENT_TO_VTE),
            ("other output displayed", b"plain" in SENT_TO_VTE
             and b"after" in SENT_TO_VTE),
            ("window size forwarded", reported_size == "30 100"),
            ("clipboard written", clipboard == TEXT_SENT.decode()),
        ]
        for name, ok in results:
            print("%-24s %s" % (name, "PASS" if ok else "FAIL"))
            checks.append(ok)
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        window.destroy()
        Gtk.main_quit()
        return False

    GLib.timeout_add(3000, report)
    Gtk.main()
    return 0 if all(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
