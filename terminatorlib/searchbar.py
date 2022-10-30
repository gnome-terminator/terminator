# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""searchbar.py - classes necessary to provide a terminal search bar"""

import gi
from gi.repository import Gtk, Gdk
gi.require_version('Vte', '2.91')  # vte-0.38 (gnome-3.14)
from gi.repository import Vte
from gi.repository import GObject
from gi.repository import GLib

from .translation import _
from .config import Config
from . import regex
from .util import dbg

# pylint: disable-msg=R0904
class Searchbar(Gtk.HBox):
    """Class implementing the Searchbar widget"""

    __gsignals__ = {
        'end-search': (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    entry = None
    next = None
    prev = None
    wrap = None

    vte = None
    config = None

    searchstring = None
    searchre = None

    def __init__(self):
        """Class initialiser"""
        GObject.GObject.__init__(self)

        # default regex flags are not CASELESS
        self.regex_flags_pcre2 = regex.FLAGS_PCRE2
        self.regex_flags_glib = regex.FLAGS_GLIB

        self.config = Config()

        self.get_style_context().add_class("terminator-terminal-searchbar")

        # Search text
        self.entry = Gtk.Entry()
        self.entry.set_activates_default(True)
        self.entry.show()
        self.entry.connect('activate', self.do_search)
        self.entry.connect('key-press-event', self.search_keypress)

        # Label
        label = Gtk.Label(label=_('Search:'))
        label.show()

        # Close Button
        close = Gtk.Button()
        close.set_relief(Gtk.ReliefStyle.NONE)
        close.set_focus_on_click(False)
        icon = Gtk.Image()
        icon.set_from_stock(Gtk.STOCK_CLOSE, Gtk.IconSize.MENU)
        close.add(icon)
        close.set_name('terminator-search-close-button')
        if hasattr(close, 'set_tooltip_text'):
            close.set_tooltip_text(_('Close Search bar'))
        close.connect('clicked', self.end_search)
        close.show_all()

        # Next Button
        self.next = Gtk.Button.new_with_label('Next')
        self.next.show()
        self.next.set_sensitive(False)
        self.next.connect('clicked', self.next_search)

        # Previous Button
        self.prev = Gtk.Button.new_with_label('Prev')
        self.prev.show()
        self.prev.set_sensitive(False)
        self.prev.connect('clicked', self.prev_search)

        # Match Case checkbox
        self.match_case = Gtk.CheckButton.new_with_label('Match Case')
        self.match_case.show()
        self.match_case.set_sensitive(True)
        self.match_case.set_active(self.config.base.get_item('case_sensitive'))
        self.match_case.connect('toggled', self.match_case_toggled)

        # Wrap checkbox
        self.wrap = Gtk.CheckButton.new_with_label('Wrap')
        self.wrap.show()
        self.wrap.set_sensitive(True)
        self.wrap.set_active(True)
        self.wrap.connect('toggled', self.wrap_toggled)

        # Invert Search checkbox
        self.invert_search = Gtk.CheckButton.new_with_label('Invert Search')
        self.invert_search.show()
        self.search_is_inverted = self.config.base.get_item('invert_search')
        self.invert_search.set_active(self.search_is_inverted)
        self.invert_search.connect('toggled', self.wrap_invert_search)

        self.pack_start(label, False, True, 0)
        self.pack_start(self.entry, True, True, 0)
        self.pack_start(self.prev, False, False, 0)
        self.pack_start(self.next, False, False, 0)
        self.pack_start(self.wrap, False, False, 0)
        self.pack_start(self.match_case, False, False, 0)
        self.pack_start(self.invert_search, False, False, 0)
        self.pack_end(close, False, False, 0)

        self.hide()
        self.set_no_show_all(True)

    def wrap_invert_search(self, toggled):
        self.search_is_inverted = toggled.get_active()
        self.invert_search.set_active(toggled.get_active())
        self.config.base.set_item('invert_search', toggled.get_active())
        self.config.save()

    def wrap_toggled(self, toggled):
        toggled_state = toggled.get_active()
        self.vte.search_set_wrap_around(toggled_state)
        if toggled_state:
            self.prev.set_sensitive(True)
            self.next.set_sensitive(True)

    def match_case_toggled(self, toggled):
        """Handles Match Case checkbox toggles"""

        toggled_state = toggled.get_active()
        if not toggled_state:
            #  Add the CASELESS regex flags when the checkbox is not checked.
            try:
                self.regex_flags_pcre2 = (regex.FLAGS_PCRE2 | regex.PCRE2_CASELESS)
            except TypeError:
                # if PCRE2 support is not available
                pass

            # The code will fall back to use this GLib regex when PCRE2 is not available
            self.regex_flags_glib = (regex.FLAGS_GLIB | regex.GLIB_CASELESS)
        else:
            # Default state of the check box is unchecked. CASELESS regex flags are not added.
            self.regex_flags_pcre2 = regex.FLAGS_PCRE2
            self.regex_flags_glib = regex.FLAGS_GLIB
        
        self.config.base.set_item('case_sensitive', toggled_state)
        self.config.save()
        self.do_search(self.entry) #  Start a new search every time the check box is toggled.    

    def get_vte(self):
        """Find our parent widget"""
        parent = self.get_parent()
        if parent:
            self.vte = parent.vte
            #turn on wrap by default
            self.vte.search_set_wrap_around(True)

    # pylint: disable-msg=W0613
    def search_keypress(self, widget, event):
        """Handle keypress events"""
        key = Gdk.keyval_name(event.keyval)
        if key == 'Escape':
            self.end_search()
        else:
            self.prev.set_sensitive(False)
            self.next.set_sensitive(False)

    def start_search(self):
        """Show ourselves"""
        if not self.vte:
            self.get_vte()

        self.show()
        self.entry.grab_focus()

    def do_search(self, widget):
        """Trap and re-emit the clicked signal"""
        dbg('entered do_search')
        searchtext = self.entry.get_text()
        dbg('searchtext: %s' % searchtext)
        if searchtext == '':
            return

        self.searchre = None
        if regex.FLAGS_PCRE2:
            try:
                self.searchre = Vte.Regex.new_for_search(searchtext, len(searchtext), self.regex_flags_pcre2)
                dbg('search RE: %s' % self.searchre)
                self.vte.search_set_regex(self.searchre, 0)
            except GLib.Error:
                # happens when PCRE2 support is not builtin (Ubuntu < 19.10)
                pass

        if not self.searchre:
            # fall back to old GLib regex
            self.searchre = GLib.Regex(searchtext, self.regex_flags_glib, 0)
            dbg('search RE: %s' % self.searchre)
            self.vte.search_set_gregex(self.searchre, 0)

        self.next.set_sensitive(True)
        self.prev.set_sensitive(True)
        # switch search direction based on the inversion checkbox
        if not self.search_is_inverted:
            self.next_search(None)
        else:
            self.prev_search(None)

    def next_search(self, widget):
        """Search forwards and jump to the next result, if any"""
        found_result = self.vte.search_find_next()
        if not self.wrap.get_active():
            self.next.set_sensitive(found_result)
        else:
            self.next.set_sensitive(True)
        self.prev.set_sensitive(True)
        return

    def prev_search(self, widget):
        """Jump back to the previous search"""
        found_result = self.vte.search_find_previous()
        if not self.wrap.get_active():
            self.prev.set_sensitive(found_result)
        else:
            self.prev.set_sensitive(True)
        self.next.set_sensitive(True)
        return

    def end_search(self, widget=None):
        """Trap and re-emit the end-search signal"""
        self.searchstring = None
        self.searchre = None
        self.emit('end-search')

    def get_search_term(self):
        """Return the currently set search term"""
        return(self.entry.get_text())

GObject.type_register(Searchbar)
