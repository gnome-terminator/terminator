#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""terminator.py - class for the master Terminator singleton"""

from borg import Borg
from terminal import Terminal

class Terminator(Borg):
    """master object for the application"""

    window = None
    windowtitle = None
    terminals = None
    groups = None
    config = None

    def __init__(self):
        """Class initialiser"""

        Borg.__init__(self)
        self.prepare_attributes()

    def prepare_attributes(self):
        """Initialise anything that isn't already"""

        if not self.terminals:
            self.terminals = []
        if not self.groups:
            self.groups = []

    def new_terminal(self):
        """Create and register a new terminal widget"""

        terminal = Terminal()
        self.terminals.append(terminal)

    def reconfigure_terminals(self):
        """Tell all terminals to update their configuration"""

        for terminal in self.terminals:
            terminal.reconfigure()

    def group_hoover(self):
        """Clean out unused groups"""

        if self.config['autoclean_groups']:
            todestroy = []
            for group in self.groups:
                for terminal in self.terminals:
                    save = False
                    if terminal.group == group:
                        save = True
                        break

                    if not save:
                        todestroy.append(group)

            for group in todestroy:
                self.groups.remove(group)

# vim: set expandtab ts=4 sw=4:
