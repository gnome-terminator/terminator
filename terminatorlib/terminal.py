#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""terminal.py - classes necessary to provide Terminal widgets"""

import sys
import os
import pygtk
pygtk.require('2.0')
import gtk
import gobject

from util import dbg, err, gerr
from config import Config
from cwd import get_default_cwd
from titlebar import Titlebar
from searchbar import Searchbar

try:
    import vte
except ImportError:
    gerr('You need to install python bindings for libvte')
    sys.exit(1)

# pylint: disable-msg=R0904
class Terminal(gtk.VBox):
    """Class implementing the VTE widget and its wrappings"""

    __gsignals__ = {
        'close-term': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
    }

    TARGET_TYPE_VTE = 8

    vte = None
    terminalbox = None
    titlebar = None
    searchbar = None

    cwd = None
    clipboard = None

    matches = None
    config = None
    default_encoding = None

    composite_support = None

    def __init__(self):
        """Class initialiser"""
        gtk.VBox.__init__(self)
        self.__gobject_init__()

        self.matches = {}

        self.config = Config()

        self.cwd = get_default_cwd()
        self.clipboard = gtk.clipboard_get(gtk.gdk.SELECTION_CLIPBOARD)

        self.vte = vte.Terminal()
        self.vte.set_size(80, 24)
        self.vte._expose_data = None
        if not hasattr(self.vte, "set_opacity") or not hasattr(self.vte,
                "is_composited"):
            self.composite_support = False
        self.vte.show()

        self.default_encoding = self.vte.get_encoding()
        self.update_url_matches(self.config['try_posix_regexp'])

        self.terminalbox = self.create_terminalbox()

        self.titlebar = Titlebar()
        self.titlebar.connect_icon(self.on_group_button_press)
        self.searchbar = Searchbar()

        self.show()
        self.pack_start(self.titlebar, False)
        self.pack_start(self.terminalbox)
        self.pack_end(self.searchbar)

        self.connect_signals()

        os.putenv('COLORTERM', 'gnome-terminal')

        env_proxy = os.getenv('http_proxy')
        if not env_proxy:
            if self.config['http_proxy'] and self.config['http_proxy'] != '':
                os.putenv('http_proxy', self.config['http_proxy'])

    def create_terminalbox(self):
        """Create a GtkHBox containing the terminal and a scrollbar"""

        terminalbox = gtk.HBox()
        scrollbar = gtk.VScrollbar(self.vte.get_adjustment())
        position = self.config['scrollbar_position']

        if position not in ('hidden', 'disabled'):
            scrollbar.show()

        if position == 'left':
            func = terminalbox.pack_end
        else:
            func = terminalbox.pack_start

        func(self.vte)
        func(scrollbar, False)
        terminalbox.show()

        return(terminalbox)

    def update_url_matches(self, posix = True):
        """Update the regexps used to match URLs"""
        userchars = "-A-Za-z0-9"
        passchars = "-A-Za-z0-9,?;.:/!%$^*&~\"#'"
        hostchars = "-A-Za-z0-9"
        pathchars = "-A-Za-z0-9_$.+!*(),;:@&=?/~#%'\""
        schemes   = "(news:|telnet:|nntp:|file:/|https?:|ftps?:|webcal:)"
        user      = "[" + userchars + "]+(:[" + passchars + "]+)?"
        urlpath   = "/[" + pathchars + "]*[^]'.}>) \t\r\n,\\\"]"

        if posix:
            dbg ('update_url_matches: Trying POSIX URL regexps.  Set \
                    try_posix_regexp = False in config to only try GNU \
                    if you get (harmless) VTE warnings.')
            lboundry = "[[:<:]]"
            rboundry = "[[:>:]]"
        else: # GNU
            dbg ('update_url_matches: Trying GNU URL regexps.  Set \
                    try_posix_regexp = True in config if URLs are not \
                    detected.')
            lboundry = "\\<"
            rboundry = "\\>"

        self.matches['full_uri'] = self.vte.match_add(lboundry + schemes + 
                "//(" + user + "@)?[" + hostchars  +".]+(:[0-9]+)?(" + 
                urlpath + ")?" + rboundry + "/?")

        if self.matches['full_uri'] == -1:
            if posix:
                err ('update_url_matches: POSIX match failed, trying GNU')
                self.update_url_matches(posix = False)
            else:
                err ('update_url_matches: Failed adding URL match patterns')
        else:
            self.matches['voip'] = self.vte.match_add(lboundry + 
                    '(callto:|h323:|sip:)' + "[" + userchars + "+][" + 
                    userchars + ".]*(:[0-9]+)?@?[" + pathchars + "]+" + 
                    rboundry)
            self.matches['addr_only'] = self.vte.match_add (lboundry + 
                    "(www|ftp)[" + hostchars + "]*\.[" + hostchars + 
                    ".]+(:[0-9]+)?(" + urlpath + ")?" + rboundry + "/?")
            self.matches['email'] = self.vte.match_add (lboundry + 
                    "(mailto:)?[a-zA-Z0-9][a-zA-Z0-9.+-]*@[a-zA-Z0-9]\
                            [a-zA-Z0-9-]*\.[a-zA-Z0-9][a-zA-Z0-9-]+\
                            [.a-zA-Z0-9-]*" + rboundry)
            self.matches['nntp'] = self.vte.match_add (lboundry + 
                    '''news:[-A-Z\^_a-z{|}~!"#$%&'()*+,./0-9;:=?`]+@\
                            [-A-Za-z0-9.]+(:[0-9]+)?''' + rboundry)
            # if the url looks like a Launchpad changelog closure entry 
            # LP: #92953 - make it a url to http://bugs.launchpad.net
            self.matches['launchpad'] = self.vte.match_add (
                    '\\bLP:? #?[0-9]+\\b')

    def connect_signals(self):
        """Connect all the gtk signals and drag-n-drop mechanics"""

        self.vte.connect('key-press-event', self.on_keypress)
        self.vte.connect('button-press-event', self.on_buttonpress)
        self.vte.connect('popup-menu', self.popup_menu)

        srcvtetargets = [("vte", gtk.TARGET_SAME_APP, self.TARGET_TYPE_VTE)]
        dsttargets = [("vte", gtk.TARGET_SAME_APP, self.TARGET_TYPE_VTE), 
                ('text/plain', 0, 0), ('STRING', 0, 0), ('COMPOUND_TEXT', 0, 0)]

        for (widget, mask) in [
            (self.vte, gtk.gdk.CONTROL_MASK | gtk.gdk.BUTTON3_MASK), 
            (self.titlebar, gtk.gdk.CONTROL_MASK)]:
            widget.drag_source_set(mask, srcvtetargets, gtk.gdk.ACTION_MOVE)

        self.vte.drag_dest_set(gtk.DEST_DEFAULT_MOTION |
                gtk.DEST_DEFAULT_HIGHLIGHT | gtk.DEST_DEFAULT_DROP,
                dsttargets, gtk.gdk.ACTION_MOVE)

        for widget in [self.vte, self.titlebar]:
            widget.connect('drag-begin', self.on_drag_begin, self)
            widget.connect('drag-data-get', self.on_drag_data_get,
            self)

        self.vte.connect('drag-motion', self.on_drag_motion, self)
        self.vte.connect('drag-data-received',
            self.on_drag_data_received, self)

        if self.config['copy_on_selection']:
            self.vte.connect('selection-changed', lambda widget:
                self.vte.copy_clipboard())

        if self.composite_support:
            self.vte.connect('composited-changed',
                self.on_composited_changed)

        self.vte.connect('window-title-changed',
            self.on_vte_title_change)
        self.vte.connect('grab-focus', self.on_vte_focus)
        self.vte.connect('focus-out-event', self.on_vte_focus_out)
        self.vte.connect('focus-in-event', self.on_vte_focus_in)
        self.vte.connect('resize-window', self.on_resize_window)
        self.vte.connect('size-allocate', self.on_vte_size_allocate)

        if self.config['exit_action'] == 'restart':
            self.vte.connect('child-exited', self.spawn_child)
        elif self.config['exit_action'] in ('close', 'left'):
            self.vte.connect('child-exited', self.close_term)

        self.vte.add_events(gtk.gdk.ENTER_NOTIFY_MASK)
        self.vte.connect('enter_notify_event',
            self.on_vte_notify_enter)

        self.vte.connect_after('realize', self.reconfigure)

    def reconfigure(self):
        """Reconfigure our settings"""
        pass

    def on_group_button_press(self):
        """Handler for the group button"""
        pass

    def on_keypress(self):
        """Handler for keyboard events"""
        pass

    def on_buttonpress(self):
        """Handler for mouse events"""
        pass
    
    def popup_menu(self):
        """Display the context menu"""
        pass

    def on_drag_begin(self):
        pass

    def on_drag_data_get(self):
        pass

    def on_drag_motion(self):
        pass

    def on_drag_data_received(self):
        pass

    def on_vte_title_change(self):
        pass

    def on_vte_focus(self):
        pass

    def on_vte_focus_out(self):
        pass

    def on_vte_focus_in(self):
        pass

    def on_resize_window(self):
        pass

    def on_vte_size_allocate(self):
        pass

    def on_vte_notify_enter(self):
        pass

    def close_term(self):
        self.emit('close-term')

    def hide_titlebar(self):
        self.titlebar.hide()

    def show_titlebar(self):
        self.titlebar.show()

    def spawn_child(self):
        pass

gobject.type_register(Terminal)
# vim: set expandtab ts=4 sw=4:
