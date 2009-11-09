#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""terminator.py - class for the master Terminator singleton"""

from borg import Borg
from config import Config
from keybindings import Keybindings

class Terminator(Borg):
    """master object for the application"""

    window = None
    windowtitle = None
    terminals = None
    groups = None
    config = None
    keybindings = None

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
        if not self.config:
            self.config = Config()
        if not self.keybindings:
            self.keybindings = Keybindings()
            self.keybindings.configure(self.config['keybindings'])

    def register_terminal(self, terminal):
        """Register a new terminal widget"""
        self.terminals.append(terminal)
        terminal.connect('ungroup-all', self.ungroup_all)
        terminal.connect('navigate', self.navigate_terminal)

    def deregister_terminal(self, terminal):
        """De-register a terminal widget"""

        self.terminals.remove(terminal)

    def reconfigure_terminals(self):
        """Tell all terminals to update their configuration"""

        for terminal in self.terminals:
            terminal.reconfigure()

    def navigate_terminal(self, terminal, direction):
        """Nagivate around the terminals"""
        current = self.terminals.index(terminal)
        length = len(self.terminals)
        next = None

        if length <= 1:
            return

        print "Current term: %d" % current
        print "Number of terms: %d" % length

        if direction == 'next':
            next = current + 1
            if next >= length:
                next = 0
        elif direction == 'prev':
            next = current - 1
            if next < 0:
                next = length - 1
        else:
            raise NotImplementedError
            # FIXME: Do the directional navigation
        
        if next is not None:
            print "sending focus to term %d" % next
            self.terminals[next].grab_focus()

    def create_group(self, name):
        """Create a new group"""
        if name not in self.groups:
            self.groups.append(name)

    def ungroup_all(self, widget):
        """Remove all groups"""
        for terminal in self.terminals:
            terminal.set_group(None, None)
        self.groups = []

    def closegroupedterms(self, group):
        """Close all terminals in a group"""
        for terminal in self.terminals:
            if terminal.group == group:
                terminal.close()

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

    def do_enumerate(self, widget, pad):
        """Insert the number of each terminal in a group, into that terminal"""
        if pad:
            numstr = '%0'+str(len(str(len(self.terminals))))+'d'
        else:
            numstr = '%d'

        for term in self.get_target_terms(widget):
            idx = self.terminals.index(term)
            term.feed(numstr % (idx + 1))

    def get_target_terms(self, widget):
        """Get the terminals we should currently be broadcasting to"""
        if self.groupsend == self.groupsend_type['all']:
            return(self.terminals)
        elif self.groupsend == self.groupsend_type['group']:
            termset = []
            for term in self.terminals:
                if term == widget or (term.group != None and term.group ==
                        widget.group):
                    termset.append(term)
            return(termset)
        else:
            return([widget])

    def group_tab(self, widget):
        """Group all the terminals in a tab"""
        pass

    def ungroup_tab(self, widget):
        """Ungroup all the terminals in a tab"""
        pass

    def focus_changed(self, widget):
        """We just moved focus to a new terminal"""
        for terminal in self.terminals:
            terminal.titlebar.update()
        return
# vim: set expandtab ts=4 sw=4:
