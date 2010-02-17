#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""terminator.py - class for the master Terminator singleton"""

import gtk

from borg import Borg
from config import Config
from keybindings import Keybindings
from util import dbg, err
from factory import Factory

class Terminator(Borg):
    """master object for the application"""

    windows = None
    windowtitle = None
    terminals = None
    groups = None
    config = None
    keybindings = None

    origcwd = None

    groupsend = None
    groupsend_type = {'all':0, 'group':1, 'off':2}

    def __init__(self):
        """Class initialiser"""

        Borg.__init__(self, self.__class__.__name__)
        self.prepare_attributes()

    def prepare_attributes(self):
        """Initialise anything that isn't already"""

        if not self.windows:
            self.windows = []
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

    def register_window(self, window):
        """Register a new window widget"""
        if window not in self.windows:
            dbg('Terminator::register_window: registering %s:%s' % (id(window),
                type(window)))
            self.windows.append(window)

    def deregister_window(self, window):
        """de-register a window widget"""
        dbg('Terminator::deregister_window: de-registering %s:%s' %
                (id(window), type(window)))
        if window in self.windows:
            self.windows.remove(window)
        else:
            err('%s is not in registered window list' % window)

        if len(self.windows) == 0:
            # We have no windows left, we should exit
            dbg('no windows remain, quitting')
            gtk.main_quit()

    def register_terminal(self, terminal):
        """Register a new terminal widget"""
        if terminal not in self.terminals:
            dbg('Terminator::register_terminal: registering %s:%s' %
                    (id(terminal), type(terminal)))
            self.terminals.append(terminal)
            terminal.connect('ungroup-all', self.ungroup_all)

    def deregister_terminal(self, terminal):
        """De-register a terminal widget"""
        dbg('Terminator::deregister_terminal: de-registering %s:%s' %
                (id(terminal), type(terminal)))
        self.terminals.remove(terminal)

        if len(self.terminals) == 0:
            dbg('no terminals remain, destroying all windows')
            for window in self.windows:
                window.destroy()
        else:
            dbg('Terminator::deregister_terminal: %d terminals remain' %
                    len(self.terminals))

    def new_window(self):
        """Create a window with a Terminal in it"""
        maker = Factory()
        window = maker.make('Window')
        terminal = maker.make('Terminal')
        window.add(terminal)
        window.show()
        terminal.spawn_child()

        return(window, terminal)

    def create_layout(self, layoutname):
        """Create all the parts necessary to satisfy the specified layout"""
        layout = None
        objects = {}

        layout = self.config.layout_get_config(layoutname)
        if not layout:
            # User specified a non-existent layout. default to one Terminal
            err('layout %s not defined' % layout)
            raise(KeyError)

        # Wind the flat objects into a hierarchy
        hierarchy = {}
        count = 0
        # Loop over the layout until we have consumed it, or hit 1000 loops.
        # This is a stupid artificial limit, but it's safe.
        while len(layout) > 0 and count < 1000:
            count = count + 1
            if count == 1000:
                err('hit maximum loop boundary. THIS IS VERY LIKELY A BUG')
            for obj in layout.keys():
                if layout[obj]['type'].lower() == 'window':
                    hierarchy[obj] = {}
                    hierarchy[obj]['type'] = 'Window'
                    hierarchy[obj]['children'] = {}
                    objects[obj] = hierarchy[obj]
                    del(layout[obj])
                else:
                    # Now examine children to see if their parents exist yet
                    if not layout[obj].has_key('parent'):
                        err('Invalid object: %s' % obj)
                        del(layout[obj])
                        continue
                    if objects.has_key(layout[obj]['parent']):
                        # Our parent has been created, add ourselves
                        childobj = {}
                        childobj['type'] = layout[obj]['type']
                        childobj['children'] = {}

                        # Copy over any additional object keys
                        for objkey in layout[obj].keys():
                            if not childobj.has_key(objkey):
                                childobj[objkey] = layout[obj][objkey]

                        objects[layout[obj]['parent']]['children'][obj] = childobj
                        objects[obj] = childobj
                        del(layout[obj])

        layout = hierarchy

        for windef in layout:
            if layout[windef]['type'] != 'Window':
                err('invalid layout format. %s' % layout)
                raise(ValueError)
            window, terminal = self.new_window()
            window.create_layout(layout[windef])

    def reconfigure(self):
        """Update configuration for the whole application"""

        if self.config['handle_size'] in xrange(0, 6):
            gtk.rc_parse_string("""style "terminator-paned-style" {
                GtkPaned::handle_size = %s }
                class "GtkPaned" style "terminator-paned-style" """ %
                self.config['handle_size'])
            gtk.rc_reset_styles(gtk.settings_get_default())

        # Cause all the terminals to reconfigure
        for terminal in self.terminals:
            terminal.reconfigure()

        # Reparse our keybindings
        self.keybindings.configure(self.config['keybindings'])

    def create_group(self, name):
        """Create a new group"""
        if name not in self.groups:
            dbg('Terminator::create_group: registering group %s' % name)
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
            inuse = []
            todestroy = []

            for terminal in self.terminals:
                if terminal.group:
                    if not terminal.group in inuse:
                        inuse.append(terminal.group)

            for group in self.groups:
                if not group in inuse:
                    todestroy.append(group)

            dbg('Terminator::group_hoover: %d groups, hoovering %d' %
                    (len(self.groups), len(todestroy)))
            for group in todestroy:
                self.groups.remove(group)

    def group_emit(self, terminal, group, type, event):
        """Emit to each terminal in a group"""
        dbg('Terminator::group_emit: emitting a keystroke for group %s' %
                group)
        for term in self.terminals:
            if term != terminal and term.group == group:
                term.vte.emit(type, event)

    def all_emit(self, terminal, type, event):
        """Emit to all terminals"""
        for term in self.terminals:
            if term != terminal:
                term.vte.emit(type, event)

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
        # FIXME: Implement or drop
        pass

    def ungroup_tab(self, widget):
        """Ungroup all the terminals in a tab"""
        # FIXME: Implement or drop
        pass

    def focus_changed(self, widget):
        """We just moved focus to a new terminal"""
        for terminal in self.terminals:
            terminal.titlebar.update(widget)
        return

    def describe_layout(self):
        """Describe our current layout"""
        layout = {}
        count = 0
        for window in self.windows:
            parent = ''
            count = window.describe_layout(count, parent, layout)

        return(layout)

# vim: set expandtab ts=4 sw=4:
