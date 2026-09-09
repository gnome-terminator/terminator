# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""vte_backend.py - Linux terminal backend backed by libvte.

``VteBackend`` subclasses ``Vte.Terminal`` so that every widget and terminal
method ``terminal.py`` calls (``set_colors``, ``feed``, ``connect``, etc.) is
inherited unchanged. The only behaviour we override is :meth:`spawn`, which
centralises the PTY process spawning that was previously inlined in
``Terminal.spawn_child``. Centralising it means the Windows backend
(``ConPtyTerminal``) can provide its own ``spawn`` via ConPTY without
``terminal.py`` caring which platform it is on.
"""

from __future__ import print_function

import gi
gi.require_version('Vte', '2.91')  # vte-0.38 (gnome-3.14)
from gi.repository import Vte, GLib

from ..terminal_backend import TerminalBackend


class VteBackend(Vte.Terminal, TerminalBackend):
    """A ``Vte.Terminal`` that exposes a portable ``spawn`` surface.

    Being a subclass of ``Vte.Terminal`` means all of terminal.py's existing
    ``self.vte.*`` calls continue to work with zero wrapping overhead.
    """

    def __init__(self, config=None):
        Vte.Terminal.__init__(self)
        # config retained for future backend-shared defaults (e.g. default
        # TERM env). VTE itself reads nothing from it today.
        self._config = config

    def spawn(self, args, envv, cwd, flatpak=False):
        """Spawn the child process via VTE's PTY.

        Mirrors the historical ``Terminal.spawn_child`` spawn path: under
        Flatpak we use ``spawn_async`` with ``NO_CTTY`` (the caller already
        rewrites ``args`` into a ``flatpak-spawn`` invocation); otherwise the
        synchronous spawn with ``FILE_AND_ARGV_ZERO``.

        Returns the child PID, or -1 on failure.
        """
        if flatpak:
            # args already wrapped as ['flatpak-spawn', ...] by the caller.
            pid = self.spawn_async(
                Vte.PtyFlags.NO_CTTY,
                cwd,
                args,
                envv,
                0,
                None,
                None,
                -1,
                None,
                None,
                None,
            )
            return pid
        result, pid = self.spawn_sync(
            Vte.PtyFlags.DEFAULT,
            cwd,
            args,
            envv,
            GLib.SpawnFlags.FILE_AND_ARGV_ZERO,
            None,
            None,
            None,
        )
        return pid
