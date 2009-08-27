#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""container.py - classes necessary to contain Terminal widgets"""

import gobject

from config import Config
from util import dbg

# pylint: disable-msg=R0921
class Container(object):
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

    def __init__(self):
        """Class initialiser"""
        self.children = []
        self.config = Config()
        self.state_zoomed = self.states_zoom['none']

    def register_signals(self, widget):
        """Register gobject signals in a way that avoids multiple inheritance"""
        for signal in self.signals:
            gobject.signal_new(signal['name'],
                               widget,
                               signal['flags'],
                               signal['return_type'],
                               signal['param_types'])

    def emit(self, signal):
        """Emit a gobject signal"""
        raise NotImplementedError('emit')

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
        raise NotImplementedError('split_axis')

    def unsplit(self, widget, keep=False):
        """Default unsplitter. This should be implemented by subclasses"""
        raise NotImplementedError('unsplit')

    def add(self, widget):
        """Add a widget to the container"""
        raise NotImplementedError('add')

    def remove(self, widget):
        """Remove a widget from the container"""
        raise NotImplementedError('remove')

    def closeterm(self, widget):
        """Handle the closure of a terminal"""
        if self.state_zoomed != self.states_zoom['none']:
            dbg('closeterm: current zoomed state is: %s' % self.state_zoomed)
            self.unzoom(widget)

        if not self.remove(widget):
            return(False)

        self.emit('need_group_hoover')
        return(True)

    def resizeterm(self, widget, keyname):
        """Handle a keyboard event requesting a terminal resize"""
        raise NotImplementedError('resizeterm')

    def toggle_zoom(self, widget, fontscale = False):
        """Toggle the existing zoom state"""
        if self.state_zoomed != self.states_zoom['none']:
            self.unzoom(widget)
        else:
            self.zoom(widget, fontscale)

    def zoom(self, widget, fontscale = False):
        """Zoom a terminal"""
        raise NotImplementedError('zoom')

    def unzoom(self, widget):
        """Unzoom a terminal"""
        raise NotImplementedError('unzoom')

# vim: set expandtab ts=4 sw=4:
