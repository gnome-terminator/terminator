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
        self.__gobject__init()

        self.show()

gobject.type_register(Titlebar)
