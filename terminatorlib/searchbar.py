#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""searchbar.py - classes necessary to provide a terminal search bar"""

import gtk
import gobject

from translation import _

class Searchbar(gtk.HBox):
    """Class implementing the Searchbar widget"""

    __gsignals__ = {
        'do-search': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        'next-search': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        'end-search': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
    }

    entry = None
    reslabel = None
    next = None

    def __init__(self):
        """Class initialiser"""
        gtk.HBox.__init__(self)
        self.__gobject__init()

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
        self.next.connect('clicked', self.next_search)

        self.pack_start(label, False)
        self.pack_start(self.entry)
        self.pack_start(self.reslabel, False)
        self.pack_start(self.next, False, False)
        self.pack_end(close, False, False)

        self.show()

    def search_keypress(self, widget, event):
        """Handle keypress events"""
        key = gtk.gdk.keyval_name(event.keyval)
        if key == 'Escape':
            self.end_search()

    def do_search(self, widget):
        """Trap and re-emit the clicked signal"""
        self.emit('do-search', widget)

    def next_search(self, widget):
        """Trap and re-emit the next-search signal"""
        self.emit('next-search', widget)

    def end_search(self, widget):
        """Trap and re-emit the end-search signal"""
        self.emit('end-search', widget)

    def get_search_term(self):
        """Return the currently set search term"""
        return(self.entry.get_text())

    def set_search_label(self, string = ''):
        """Set the  search label"""
        self.reslabel.set_text(string)

    def hide_next(self):
        """Hide the Next button"""
        self.next.hide()

    def show_next(self):
        """Show the Next button"""
        self.next.show()

gobject.type_register(Searchbar)
