#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""terminator.py - class for the master Terminator singleton"""

from borg import Borg

class Terminator(Borg):
    """master object for the application"""

    window = None
    windowtitle = None
    terminals = None
    groups = None
    config = None

    splittogroup = None
    autocleangroups = None
    groupsend = None
    groupsend_type = {'all':0, 'group':1, 'off':2}

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
        if not self.groupsend:
            self.groupsend = self.groupsend_type['group']
        if not self.splittogroup:
            self.splittogroup = False
        if not self.autocleangroups:
            self.autocleangroups = True

    def register_terminal(self, terminal):
        """Register a new terminal widget"""

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
