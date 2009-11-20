#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""container.py - classes necessary to contain Terminal widgets"""

import gobject

from config import Config
from util import dbg, err

# pylint: disable-msg=R0921
class Container(object):
    """Base class for Terminator Containers"""

    terminator = None
    immutable = None
    children = None
    config = None
    signals = None
    cnxids = None

    def __init__(self):
        """Class initialiser"""
        self.children = []
        self.signals = []
        self.cnxids = {}
        self.config = Config()

    def register_signals(self, widget):
        """Register gobject signals in a way that avoids multiple inheritance"""
        existing = gobject.signal_list_names(widget)
        for signal in self.signals:
            if signal['name'] in existing:
                dbg('Container:: skipping signal %s for %s, already exists' % (
                        signal['name'], widget))
            else:
                dbg('Container:: registering signal for %s on %s' % (signal['name'], widget))
                try:
                    gobject.signal_new(signal['name'],
                                       widget,
                                       signal['flags'],
                                       signal['return_type'],
                                        signal['param_types'])
                except RuntimeError:
                    err('Container:: registering signal for %s on %s failed' %
                            (signal['name'], widget))

    def connect_child(self, widget, signal, handler, data=None):
        """Register the requested signal and record its connection ID"""
        if not self.cnxids.has_key(widget):
            self.cnxids[widget] = []

        if data is not None:
            self.cnxids[widget].append(widget.connect(signal, handler, data))
            dbg('Container::connect_child: registering %s(%s) to handle %s::%s' %
                (handler.__name__, data, widget.__class__.__name__, signal))
        else:
            self.cnxids[widget].append(widget.connect(signal, handler))
            dbg('Container::connect_child: registering %s to handle %s::%s' %
                (handler.__name__, widget.__class__.__name__, signal))

    def disconnect_child(self, widget):
        """De-register the signals for a child"""
        if self.cnxids.has_key(widget):
            for cnxid in self.cnxids[widget]:
                # FIXME: Look up the IDs to print a useful debugging message
                widget.disconnect(cnxid)
            del(self.cnxids[widget])

    def get_offspring(self):
        """Return a list of child widgets, if any"""
        return(self.children)

    def get_top_window(self, startpoint):
        """Return the Window instance this container belongs to"""
        widget = startpoint
        parent = widget.get_parent()
        while parent:
            widget = parent
            parent = widget.get_parent()
        return(widget)

    def split_horiz(self, widget):
        """Split this container horizontally"""
        return(self.split_axis(widget, True))

    def split_vert(self, widget):
        """Split this container vertically"""
        return(self.split_axis(widget, False))

    def split_axis(self, widget, vertical=True, sibling=None):
        """Default axis splitter. This should be implemented by subclasses"""
        raise NotImplementedError('split_axis')

    def add(self, widget):
        """Add a widget to the container"""
        raise NotImplementedError('add')

    def remove(self, widget):
        """Remove a widget from the container"""
        raise NotImplementedError('remove')

    def closeterm(self, widget):
        """Handle the closure of a terminal"""
        try:
            if self.get_property('term_zoomed'):
                # We're zoomed, so unzoom and then start closing again
                dbg('Container::closeterm: terminal zoomed, unzooming')
                self.unzoom(widget)
                widget.close()
                return(True)
        except TypeError:
            pass

        if not self.remove(widget):
            return(False)

        self.terminator.deregister_terminal(widget)
        self.terminator.group_hoover()
        return(True)

    def resizeterm(self, widget, keyname):
        """Handle a keyboard event requesting a terminal resize"""
        raise NotImplementedError('resizeterm')

    def toggle_zoom(self, widget, fontscale = False):
        """Toggle the existing zoom state"""
        try:
            if self.get_property('term_zoomed'):
                self.unzoom(widget)
            else:
                self.zoom(widget, fontscale)
        except TypeError:
            err('Container::toggle_zoom: %s is unable to handle zooming, for \
            %s' % (self, widget))

    def zoom(self, widget, fontscale = False):
        """Zoom a terminal"""
        raise NotImplementedError('zoom')

    def unzoom(self, widget):
        """Unzoom a terminal"""
        raise NotImplementedError('unzoom')

# vim: set expandtab ts=4 sw=4:
