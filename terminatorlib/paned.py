#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""paned.py - a base Paned container class and the vertical/horizontal
variants"""

import gobject
import gtk

from newterminator import Terminator
from container import Container

# pylint: disable-msg=R0921
class Paned(Container):
    """Base class for Paned Containers"""
    cnxids = None

    def __init__(self):
        """Class initialiser"""
        self.terminator = Terminator()
        self.cnxids = {}

        Container.__init__(self)
        gobject.type_register(HPaned)
        self.register_signals(HPaned)

    def split_axis(self, widget, vertical=True):
        """Default axis splitter. This should be implemented by subclasses"""
        raise NotImplementedError('split_axis')

    def add(self, widget):
        """Add a widget to the container"""
        if len(self.children) == 0:
            self.pack1(widget, True, True)
            self.children.append(widget)
        elif len(self.children) == 1:
            self.pack2(widget, True, True)
            self.children.append(widget)
        else:
            raise ValueError('already have two children')

        self.cnxids[widget] = []
        self.cnxids[widget].append(widget.connect('close-term',
                                   self.wrapcloseterm))
        # FIXME: somehow propagate the title-change signal to the Window
        self.cnxids[widget].append(widget.connect('split-horiz',
                                                  self.split_horiz))
        self.cnxids[widget].append(widget.connect('split-vert',
                                                  self.split_vert))

    def remove(self, widget):
        """Remove a widget from the container"""
        gtk.Paned.remove(self, widget)
        for cnxid in self.cnxids[widget]:
            widget.disconnect(cnxid)
        del(self.cnxids[widget])
        self.children.remove(widget)
        return(True)

    def wrapcloseterm(self, widget):
        """A child terminal has closed, so this container must die"""
        if self.closeterm(widget):
            parent = self.get_parent()
            parent.remove(self)

            # At this point we only have one child, which is the surviving term
            sibling = self.children[0]
            self.remove(sibling)
            parent.add(sibling)
            del(self)
        else:
            print "self.closeterm failed"

    def resizeterm(self, widget, keyname):
        """Handle a keyboard event requesting a terminal resize"""
        raise NotImplementedError('resizeterm')

class HPaned(Paned, gtk.HPaned):
    """Merge gtk.HPaned into our base Paned Container"""
    def __init__(self):
        """Class initialiser"""
        Paned.__init__(self)
        gtk.HPaned.__init__(self)

class VPaned(Paned, gtk.VPaned):
    """Merge gtk.VPaned into our base Paned Container"""
    def __init__(self):
        """Class initialiser"""
        Paned.__init__(self)
        gtk.VPaned.__init__(self)

gobject.type_register(HPaned)
gobject.type_register(VPaned)
# vim: set expandtab ts=4 sw=4:
