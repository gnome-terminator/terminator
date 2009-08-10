#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""terminator.py - class for the master Terminator singleton"""

from terminal import Terminal

class _Terminator(object):
    """master object for the application"""

    window = None
    windowtitle = None
    terminals = None
    groups = None
    config = None

    def __init__(self):
        """Class initialiser"""

        self.terminals = []
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

TERMINATOR = _Terminator()
def Terminator():
    """Return the instance"""
    return(TERMINATOR)

# vim: set expandtab ts=4 sw=4:
