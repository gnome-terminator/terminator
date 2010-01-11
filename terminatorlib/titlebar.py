#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""titlebar.py - classes necessary to provide a terminal title bar"""

import gtk
import gobject

from version import APP_NAME
from util import dbg
from terminator import Terminator
from editablelabel import EditableLabel

# pylint: disable-msg=R0904
# pylint: disable-msg=W0613
class Titlebar(gtk.EventBox):
    """Class implementing the Titlebar widget"""

    terminator = None
    oldtitle = None
    termtext = None
    sizetext = None
    label = None
    ebox = None
    groupicon = None
    grouplabel = None
    groupentry = None

    __gsignals__ = {
            'clicked': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
            'edit-done': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
            'create-group': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
                (gobject.TYPE_STRING,)),
    }

    def __init__(self):
        """Class initialiser"""
        gtk.EventBox.__init__(self)
        self.__gobject_init__()

        self.terminator = Terminator()

        self.label = EditableLabel()
        self.label.connect('edit-done', self.on_edit_done)
        self.ebox = gtk.EventBox()
        grouphbox = gtk.HBox()
        self.grouplabel = gtk.Label()
        self.groupicon = gtk.Image()

        self.groupentry = gtk.Entry()
        self.groupentry.set_no_show_all(True)
        self.groupentry.connect('focus-out-event', self.groupentry_cancel)
        self.groupentry.connect('activate', self.groupentry_activate)
        self.groupentry.connect('key-press-event', self.groupentry_keypress)

        groupsend_type = self.terminator.groupsend_type
        if self.terminator.groupsend == groupsend_type['all']:
            icon_name = 'all'
        elif self.terminator.groupsend == groupsend_type['group']:
            icon_name = 'group'
        elif self.terminator.groupsend == groupsend_type['off']:
            icon_name = 'off'
        self.set_from_icon_name('_active_broadcast_%s' % icon_name, 
                gtk.ICON_SIZE_MENU)

        grouphbox.pack_start(self.groupicon, False, True, 2)
        grouphbox.pack_start(self.grouplabel, False, True, 2)
        grouphbox.pack_start(self.groupentry, False, True, 2)

        self.ebox.add(grouphbox)
        self.ebox.show_all()

        hbox = gtk.HBox()
        hbox.pack_start(self.ebox, False, True, 0)
        hbox.pack_start(gtk.VSeparator(), False, True, 0)
        hbox.pack_start(self.label, True, True)

        self.add(hbox)
        self.show_all()

        self.connect('button-press-event', self.on_clicked)

    def connect_icon(self, func):
        """Connect the supplied function to clicking on the group icon"""
        self.ebox.connect('button-release-event', func)

    def update(self):
        """Update our contents"""
        self.label.set_text("%s %s" % (self.termtext, self.sizetext))
        # FIXME: Aren't we supposed to be setting a colour here too?

    def set_from_icon_name(self, name, size = gtk.ICON_SIZE_MENU):
        """Set an icon for the group label"""
        if not name:
            self.groupicon.hide()
            return
        
        self.groupicon.set_from_icon_name(APP_NAME + name, size)
        self.groupicon.show()

    def update_terminal_size(self, width, height):
        """Update the displayed terminal size"""
        self.sizetext = "%sx%s" % (width, height)
        self.update()

    def set_terminal_title(self, widget, title):
        """Update the terminal title"""
        self.termtext = title
        self.update()
        # Return False so we don't interrupt any chains of signal handling
        return False

    def set_group_label(self, name):
        """Set the name of the group"""
        if name:
            self.grouplabel.set_text(name)
            self.grouplabel.show()
        else:
            self.grouplabel.hide()

    def on_clicked(self, widget, event):
        """Handle a click on the label"""
        self.emit('clicked')

    def on_edit_done(self, widget):
        """Re-emit an edit-done signal from an EditableLabel"""
        self.emit('edit-done')

    def create_group(self):
        """Create a new group"""
        self.groupentry.show()
        self.groupentry.grab_focus()

    def groupentry_cancel(self, widget, event):
        """Hide the group name entry"""
        self.groupentry.set_text('')
        self.groupentry.hide()
        self.get_parent().grab_focus()

    def groupentry_activate(self, widget):
        """Actually cause a group to be created"""
        groupname = self.groupentry.get_text()
        dbg('Titlebar::groupentry_activate: creating group: %s' % groupname)
        self.groupentry_cancel(None, None)
        self.emit('create-group', groupname)

    def groupentry_keypress(self, widget, event):
        """Handle keypresses on the entry widget"""
        key = gtk.gdk.keyval_name(event.keyval)
        if key == 'Escape':
            self.groupentry_cancel(None, None)

gobject.type_register(Titlebar)
