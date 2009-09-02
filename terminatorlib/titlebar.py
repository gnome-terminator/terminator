#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""titlebar.py - classes necessary to provide a terminal title bar"""

import gtk
import gobject

from editablelabel import EditableLabel

# pylint: disable-msg=R0904
class Titlebar(gtk.EventBox):
    """Class implementing the Titlebar widget"""

    oldtitle = None
    termtext = None
    sizetext = None
    label = None
    hbox = None
    ebox = None
    grouphbox = None
    groupicon = None
    grouplabel = None

    def __init__(self):
        """Class initialiser"""
        gtk.EventBox.__init__(self)
        self.__gobject_init__()

        self.label = EditableLabel()
        self.ebox = gtk.EventBox()
        self.grouphbox = gtk.HBox()
        self.grouplabel = gtk.Label()
        self.groupicon = gtk.Image()

        # FIXME: How do we decide which icon to use?

        self.grouphbox.pack_start(self.groupicon, False, True, 2)
        self.grouphbox.pack_start(self.grouplabel, False, True, 2)
        self.ebox.add(self.grouphbox)
        self.ebox.show_all()

        self.hbox = gtk.HBox()
        self.hbox.pack_start(self.ebox, False, True, 0)
        self.hbox.pack_start(gtk.VSeparator(), False, True, 0)
        self.hbox.pack_start(self.label, True, True)

        self.add(self.hbox)
        self.show_all()

    def connect_icon(self, func):
        """Connect the supplied function to clicking on the group icon"""
        pass

    def update(self):
        """Update our contents"""
        self.label.set_text("%s %s" % (self.termtext, self.sizetext))

    def update_terminal_size(self, width, height):
        """Update the displayed terminal size"""
        self.sizetext = "%sx%s" % (width, height)
        self.update()

    def set_terminal_title(self, widget, title):
        """Update the terminal title"""
        self.termtext = title
        self.update()

    def set_group_label(self, name):
        """Set the name of the group"""
        if name:
            self.grouplabel.set_text(name)
            self.grouplabel.show()
        else:
            self.grouplabel.hide()

    def on_clicked(self, widget, event):
        """Handle a click on the label"""
        pass

gobject.type_register(Titlebar)
