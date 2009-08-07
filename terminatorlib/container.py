#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""container.py - classes necessary to contain Terminal widgets"""

from util import debug, dbg, err

class Container:
    """Base class for Terminator Containers"""

    immutable = None
    children = None
    config = None

    def __init__(self, configobject):
        """Class initialiser"""
        self.children = []
        self.config = configobject

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
        dbg('split_axis called from base class. This is a bug')
        return(False)

