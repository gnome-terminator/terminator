#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""container.py - classes necessary to contain Terminal widgets"""

import gobject
import gtk

from util import debug, err

class Container():
    """Base class for Terminator Containers"""

    immutable = None
    children = None
    config = None
    state_zoomed = None

    states_zoom = { 'none' : 0,
                    'zoomed' : 1,
                    'maximised' : 2 }

    signals = [ {'name': 'group-hoover-needed',
                 'flags': gobject.SIGNAL_RUN_LAST,
                 'return_type': gobject.TYPE_BOOLEAN,
                 'param_types': ()
                 }
              ]

    def __init__(self, configobject):
        """Class initialiser"""
        self.children = []
        self.config = configobject

    def register_signals(self, object):
        """Register gobject signals in a way that avoids multiple inheritance"""
        for signal in self.signals:
            gobject.signal_new(signal['name'],
                               object,
                               signal['flags'],
                               signal['return_type'],
                               signal['param_types'])

    def get_offspring(self):
        """Return a list of child widgets, if any"""
        return(self.children)

    def split_horiz(self, widget):
        """Split this container horizontally"""
        return(self.split_axis(widget, True))

    def split_vert(self, widget):
        """Split this container vertically"""
        return(self.split_axis(widget, False))

    def split_axis(self, widget, vertical=True):
        """Default axis splitter. This should be implemented by subclasses"""
        err('split_axis called from base class. This is a bug')
        return(False)

    def unsplit(self, widget, keep=False):
        """Default unsplitter. This should be implemented by subclasses"""
        err('unsplit called from base class. This is a bug')
        return(False)

    def remove(self, widget):
        """Remove a widget from the container"""
        err('remove called from base class. This is a bug')

    def closeterm(self, widget):
        """Handle the closure of a terminal"""
        if self.state_zoomed != self.states_zoom['normal']:
            self.unzoom(widget)

        if not self.remove(widget):
            return(False)

        self.emit('need_group_hoover')
        return(True)

    def closegroupterms(self, widget):
        """Handle the closure of a group of terminals"""
        if self.state_zoomed != self.states_zoom['normal']:
            self.unzoom(widget)

        all_closed = True
        for term in self.term_list[:]:
            if term._group == widget._group and not self.remove(term):
                all_closed = False

        self.emit('need_group_hoover')
        return(all_closed)

    def resizeterm(self, widget, keyname):
        """Handle a keyboard event requesting a terminal resize"""
        err('resizeterm called from base class. This is a bug')

    def toggle_zoom(self, widget, fontscale = False):
        """Toggle the existing zoom state"""
        if self.state_zoomed != self.states_zoom['normal']:
            self.unzoom(widget)
        else:
            self.zoom(widget, fontscale)

    def zoom(self, widget, fontscale = False):
        """Zoom a terminal"""
        err('zoom called from base class. This is a bug')

    def unzoom(self, widget):
        """Unzoom a terminal"""
        err('unzoom called from base class. This is a bug')

# vim: set expandtab ts=4 sw=4:
