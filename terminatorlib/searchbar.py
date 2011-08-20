#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""searchbar.py - classes necessary to provide a terminal search bar"""

import gtk
import gobject
import re

from translation import _
from config import Config

# pylint: disable-msg=R0904
class Searchbar(gtk.HBox):
    """Class implementing the Searchbar widget"""

    __gsignals__ = {
        'end-search': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
    }

    entry = None
    reslabel = None
    next = None
    prev = None

    vte = None
    config = None

    searchstring = None
    searchre = None
    searchrow = None

    searchits = None

    def __init__(self):
        """Class initialiser"""
        gtk.HBox.__init__(self)
        self.__gobject_init__()

        self.config = Config()

        # Search text
        self.entry = gtk.Entry()
        self.entry.set_activates_default(True)
        self.entry.show()
        self.entry.connect('activate', self.do_search)
        self.entry.connect('key-press-event', self.search_keypress)

        # Label
        label = gtk.Label(_('Search:'))
        label.show()

        # Result label
        self.reslabel = gtk.Label('')
        self.reslabel.show()

        # Close Button
        close = gtk.Button()
        close.set_relief(gtk.RELIEF_NONE)
        close.set_focus_on_click(False)
        icon = gtk.Image()
        icon.set_from_stock(gtk.STOCK_CLOSE, gtk.ICON_SIZE_MENU)
        close.add(icon)
        close.set_name('terminator-search-close-button')
        if hasattr(close, 'set_tooltip_text'):
            close.set_tooltip_text(_('Close Search bar'))
        close.connect('clicked', self.end_search)
        close.show_all()

        # Next Button
        self.next = gtk.Button(_('Next'))
        self.next.show()
        self.next.set_sensitive(False)
        self.next.connect('clicked', self.next_search)

        # Previous Button
        self.prev = gtk.Button(_('Prev'))
        self.prev.show()
        self.prev.set_sensitive(False)
        self.prev.connect('clicked', self.prev_search)

        self.pack_start(label, False)
        self.pack_start(self.entry)
        self.pack_start(self.reslabel, False)
        self.pack_start(self.prev, False, False)
        self.pack_start(self.next, False, False)
        self.pack_end(close, False, False)

        self.hide()
        self.set_no_show_all(True)

    def get_vte(self):
        """Find our parent widget"""
        parent = self.get_parent()
        if parent:
            self.vte = parent.vte

    # pylint: disable-msg=W0613
    def search_keypress(self, widget, event):
        """Handle keypress events"""
        key = gtk.gdk.keyval_name(event.keyval)
        if key == 'Escape':
            self.end_search()

    def start_search(self):
        """Show ourselves"""
        if not self.vte:
            self.get_vte()

        self.show()
        self.entry.grab_focus()

    def do_search(self, widget):
        """Trap and re-emit the clicked signal"""
        searchtext = self.entry.get_text()
        if searchtext == '':
            return

        if searchtext != self.searchstring:
            self.searchrow = self.get_vte_buffer_range()[0]
            self.searchstring = searchtext
            self.searchre = re.compile(searchtext)

        self.reslabel.set_text(_("Searching scrollback"))
        self.next.set_sensitive(True)
        self.prev.set_sensitive(True)
        self.next_search(None)

    def next_search(self, widget):
        """Search forwards and jump to the next result, if any"""
        startrow,endrow = self.get_vte_buffer_range()
        while True:
            if self.searchrow >= endrow:
                self.searchrow = startrow
                self.reslabel.set_text(_('No more results'))
                return
            buffer = self.vte.get_text_range(self.searchrow, 0,
                                             self.searchrow+1, 0,
                                             self.search_character)

            matches = self.searchre.search(buffer)
            if matches:
                self.search_hit(self.searchrow)
                self.searchrow += 1
                return
            self.searchrow += 1

    # FIXME: There is an issue in switching search direction, probably because
    # we increment/decrement self.searchrow after each search iteration
    def prev_search(self, widget):
        """Jump back to the previous search"""
        startrow,endrow = self.get_vte_buffer_range()
        while True:
            if self.searchrow <= startrow:
                self.searchrow = endrow
                self.reslabel.set_text(_('No more results'))
                return
            buffer = self.vte.get_text_range(self.searchrow, 0,
                                             self.searchrow+1, 0,
                                             self.search_character)

            matches = self.searchre.search(buffer)
            if matches:
                self.search_hit(self.searchrow)
                self.searchrow -= 1
                return
            self.searchrow -= 1

    def search_hit(self, row):
        """Update the UI for a search hit"""
        self.reslabel.set_text("%s %d" % (_('Found at row'), row))
        self.get_parent().scrollbar_jump(row)
        self.next.show()
        self.prev.show()

    def search_character(self, widget, col, row, junk):
        """We have to have a callback for each character"""
        return(True)

    def get_vte_buffer_range(self):
        """Get the range of a vte widget"""
        column, endrow = self.vte.get_cursor_position()
        if self.config['scrollback_lines'] < 0:
            startrow = 0
        else:
            startrow = max(0, endrow - self.config['scrollback_lines'])
        return(startrow, endrow)

    def end_search(self, widget=None):
        """Trap and re-emit the end-search signal"""
        self.searchrow = 0
        self.searchstring = None
        self.searchre = None
        self.reslabel.set_text('')
        self.emit('end-search')

    def get_search_term(self):
        """Return the currently set search term"""
        return(self.entry.get_text())

gobject.type_register(Searchbar)
