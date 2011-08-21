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
    terminal = None
    config = None
    oldtitle = None
    termtext = None
    sizetext = None
    label = None
    ebox = None
    groupicon = None
    grouplabel = None
    groupentry = None
    bellicon = None

    __gsignals__ = {
            'clicked': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
            'edit-done': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
            'create-group': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
                (gobject.TYPE_STRING,)),
    }

    def __init__(self, terminal):
        """Class initialiser"""
        gtk.EventBox.__init__(self)
        self.__gobject_init__()

        self.terminator = Terminator()
        self.terminal = terminal
        self.config = self.terminal.config

        self.label = EditableLabel()
        self.label.connect('edit-done', self.on_edit_done)
        self.ebox = gtk.EventBox()
        grouphbox = gtk.HBox()
        self.grouplabel = gtk.Label()
        self.groupicon = gtk.Image()
        self.bellicon = gtk.Image()
        self.bellicon.set_no_show_all(True)

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

        self.bellicon.set_from_icon_name('terminal-bell', gtk.ICON_SIZE_MENU)
        hbox = gtk.HBox()
        hbox.pack_start(self.ebox, False, True, 0)
        hbox.pack_start(gtk.VSeparator(), False, True, 0)
        hbox.pack_start(self.label, True, True)
        hbox.pack_end(self.bellicon, False, False, 2)

        self.add(hbox)
        hbox.show_all()
        self.set_no_show_all(True)
        self.show()

        self.connect('button-press-event', self.on_clicked)

    def connect_icon(self, func):
        """Connect the supplied function to clicking on the group icon"""
        self.ebox.connect('button-release-event', func)

    def update(self, other=None):
        """Update our contents"""
        default_bg = False
        if self.config['title_hide_sizetext']:
            self.label.set_text("%s" % self.termtext)
        else:
            self.label.set_text("%s %s" % (self.termtext, self.sizetext))

        if other:
            term = self.terminal
            terminator = self.terminator
            if other == 'window-focus-out':
                title_fg = self.config['title_inactive_fg_color']
                title_bg = self.config['title_inactive_bg_color']
                icon = '_receive_off'
                default_bg = True
                group_fg = self.config['title_inactive_fg_color']
                group_bg = self.config['title_inactive_bg_color']
            elif term != other and term.group and term.group == other.group:
                if terminator.groupsend == terminator.groupsend_type['off']:
                    title_fg = self.config['title_inactive_fg_color']
                    title_bg = self.config['title_inactive_bg_color']
                    icon = '_receive_off'
                    default_bg = True
                else:
                    title_fg = self.config['title_receive_fg_color']
                    title_bg = self.config['title_receive_bg_color']
                    icon = '_receive_on'
                group_fg = self.config['title_receive_fg_color']
                group_bg = self.config['title_receive_bg_color']
            elif term != other and not term.group or term.group != other.group:
                if terminator.groupsend == terminator.groupsend_type['all']:
                    title_fg = self.config['title_receive_fg_color']
                    title_bg = self.config['title_receive_bg_color']
                    icon = '_receive_on'
                else:
                    title_fg = self.config['title_inactive_fg_color']
                    title_bg = self.config['title_inactive_bg_color']
                    icon = '_receive_off'
                    default_bg = True
                group_fg = self.config['title_inactive_fg_color']
                group_bg = self.config['title_inactive_bg_color']
            else:
                # We're the active terminal
                title_fg = self.config['title_transmit_fg_color']
                title_bg = self.config['title_transmit_bg_color']
                if terminator.groupsend == terminator.groupsend_type['all']:
                    icon = '_active_broadcast_all'
                elif terminator.groupsend == terminator.groupsend_type['group']:
                    icon = '_active_broadcast_group'
                else:
                    icon = '_active_broadcast_off'
                group_fg = self.config['title_transmit_fg_color']
                group_bg = self.config['title_transmit_bg_color']

            self.label.modify_fg(gtk.STATE_NORMAL,
                    gtk.gdk.color_parse(title_fg))
            self.grouplabel.modify_fg(gtk.STATE_NORMAL,
                    gtk.gdk.color_parse(group_fg))
            self.modify_bg(gtk.STATE_NORMAL, 
                    gtk.gdk.color_parse(title_bg))
            if not self.get_desired_visibility():
                if default_bg == True:
                    color = term.get_style().bg[gtk.STATE_NORMAL]
                else:
                    color = gtk.gdk.color_parse(title_bg)
            self.update_visibility()
            self.ebox.modify_bg(gtk.STATE_NORMAL,
                    gtk.gdk.color_parse(group_bg))
            self.set_from_icon_name(icon, gtk.ICON_SIZE_MENU)

    def update_visibility(self):
        """Make the titlebar be visible or not"""
        if not self.get_desired_visibility():
            dbg('hiding titlebar')
            self.hide()
            self.label.hide()
        else:
            dbg('showing titlebar')
            self.show()
            self.label.show()

    def get_desired_visibility(self):
        """Returns True if the titlebar is supposed to be visible. False if
        not"""
        if self.editing() == True or self.terminal.group:
            dbg('implicit desired visibility')
            return(True)
        else:
            dbg('configured visibility: %s' % self.config['show_titlebar'])
            return(self.config['show_titlebar'])

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
        self.update_visibility()

    def on_clicked(self, widget, event):
        """Handle a click on the label"""
        self.show()
        self.label.show()
        self.emit('clicked')

    def on_edit_done(self, widget):
        """Re-emit an edit-done signal from an EditableLabel"""
        self.emit('edit-done')

    def editing(self):
        """Determine if we're currently editing a group name or title"""
        return(self.groupentry.get_property('visible') or self.label.editing())

    def create_group(self):
        """Create a new group"""
        self.groupentry.show()
        self.groupentry.grab_focus()
        self.update_visibility()

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

    def icon_bell(self):
        """A bell signal requires we display our bell icon"""
        self.bellicon.show()
        gobject.timeout_add(1000, self.icon_bell_hide)

    def icon_bell_hide(self):
        """Handle a timeout which means we now hide the bell icon"""
        self.bellicon.hide()
        return(False)

    def get_custom_string(self):
        """If we have a custom string set, return it, otherwise None"""
        if self.label.is_custom():
            return(self.label.get_text())
        else:
            return(None)

    def set_custom_string(self, string):
        """Set a custom string"""
        self.label.set_text(string)
        self.label.set_custom()

gobject.type_register(Titlebar)
