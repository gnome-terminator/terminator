import os
import signal
import sys

# Fix imports when testing this file directly
if __name__ == '__main__':
  sys.path.append( os.path.join(os.path.dirname(__file__), "../.."))

from gi.repository import GLib

from terminatorlib.config import Config
import terminatorlib.plugin as plugin
from terminatorlib.util import dbg
from terminatorlib.terminator import Terminator
from terminatorlib import util


# AVAILABLE must contain a list of all the classes that you want exposed
AVAILABLE = ['SaveLastSessionLayout']


class SaveLastSessionLayout(plugin.Plugin):
    """Plugin to automatically save the current session layout on close.

    This plugin saves the terminal layout (tabs, splits, working directories)
    when Terminator closes, allowing restoration via the Layouts menu.

    The implementation uses event-driven signal connections:
    - Connects to each terminal's 'pre-close-term' signal to trigger saves
    - Connects to each Notebook's 'page-added' signal to catch new tabs
    - Uses deferred setup via GLib.idle_add to avoid blocking the UI
    """
    capabilities = ['session']

    def __init__(self):
        self.connected_terminals = set()
        self.connected_notebooks = set()
        self.save_triggered = False
        dbg("SaveLastSessionLayout: init")
        # Defer all setup to avoid blocking the preferences UI
        GLib.idle_add(self.deferred_connect)

    def connect_to_terminal(self, terminal):
        """Connect to a terminal's pre-close-term signal if not already connected."""
        if terminal not in self.connected_terminals:
            dbg("SaveLastSessionLayout: connecting to terminal %s" % id(terminal))
            terminal.connect('pre-close-term', self.on_close, None)
            self.connected_terminals.add(terminal)

    def connect_to_notebooks(self):
        """Scan all windows and connect to any new notebooks."""
        terminator = Terminator()
        for window in terminator.windows:
            child = window.get_child()
            # Only connect to Notebook widgets (they have 'append_page' method)
            if child is not None and hasattr(child, 'append_page'):
                if child not in self.connected_notebooks:
                    dbg("SaveLastSessionLayout: connecting to notebook %s" % id(child))
                    child.connect('page-added', self.on_page_added)
                    self.connected_notebooks.add(child)

    def on_page_added(self, notebook, child, page_num):
        """Handle new page added to notebook - connect to any new terminals."""
        dbg("SaveLastSessionLayout: page added to notebook")
        # New tabs are usually single terminals - connect directly if possible
        if hasattr(child, 'connect') and child not in self.connected_terminals:
            try:
                child.connect('pre-close-term', self.on_close, None)
                self.connected_terminals.add(child)
            except TypeError:
                # Not a terminal widget, ignore
                pass

    def deferred_connect(self):
        """Deferred setup - runs once after startup completes via idle_add."""
        dbg("SaveLastSessionLayout: deferred connect running")

        # OS signal handlers for shutdown scenarios
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGHUP, self.signal_handler)

        terminator = Terminator()

        # Connect to all existing terminals
        for terminal in terminator.terminals:
            self.connect_to_terminal(terminal)

        # Connect to all existing notebooks for new tab detection
        self.connect_to_notebooks()

        return False  # Don't repeat - run only once

    # Not used, but capability can be used to load automatically
    def load_session_layout(self, debugtab=False, widget=None, cwd=None, metadata=None, profile=None):
        """Load the saved session layout in a new Terminator instance."""
        dbg("SaveLastSessionLayout: load layout")
        terminator = Terminator()
        util.spawn_new_terminator(terminator.origcwd, ['-u', '-l', 'SaveLastSessionLayout'])

    def save_session_layout(self):
        """Save the current layout to config."""
        config = Config()
        terminator = Terminator()
        current_layout = terminator.describe_layout(save_cwd=True)
        dbg("SaveLastSessionLayout: save layout(%s)" % current_layout)
        res = config.replace_layout("SaveLastSessionLayout", current_layout)
        if not res:
            config.add_layout("SaveLastSessionLayout", current_layout)
        config.save()
        return True

    def signal_handler(self, signum, frame):
        """Handle OS signals (SIGTERM, SIGHUP)."""
        signame = signal.Signals(signum).name
        dbg('SaveLastSessionLayout: signal handler called: %s (%s)' % (signame, signum))
        self.save_session_layout()

    def on_close(self, terminal, event, arg1=None):
        """Handle terminal pre-close-term signal."""
        if not self.save_triggered:
            self.save_triggered = True
            dbg("SaveLastSessionLayout: terminal closing, saving layout")
            self.save_session_layout()
