#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""titlebar.py - classes necessary to provide a terminal title bar"""

import gtk
import gobject

# pylint: disable-msg=R0904
class Titlebar(gtk.EventBox):
    """Class implementing the Titlebar widget"""

    def __init__(self):
        """Class initialiser"""
        gtk.EventBox.__init__(self)
        self.__gobject_init__()

        self.show()

    def connect_icon(self, func):
        """Connect the supplied function to clicking on the group icon"""
        pass

    def update(self):
        """Update our contents"""
        pass

    def update_terminal_size(self, width, height):
        """Update the displayed terminal size"""
        pass

gobject.type_register(Titlebar)
