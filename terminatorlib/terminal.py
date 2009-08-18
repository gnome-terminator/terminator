#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""terminal.py - classes necessary to provide Terminal widgets"""

import sys
import pygtk
pygtk.require('2.0')
import gobject
import gtk
import pango

from cwd import get_pid_cwd, get_default_cwd
from util import dbg, err, gerr
from config import Config
from titlebar import Titlebar
from searchbox import Searchbox

try:
    import vte
except ImportError:
    gerr('You need to install python bindings for libvte')
    sys.exit(1)

class Terminal(gtk.VBox):
    """Class implementing the VTE widget and its wrappings"""

    vte = None
    titlebar = None
    searchbar = None

    matches = None
    config = None
    default_encoding = None

    def __init__(self):
        """Class initialiser"""
        gtk.VBox.__init__(self)
        self.matches = {}

        self.config = Config()

        self.vte = vte.Terminal()
        self.vte.set_size(80, 24)
        self.vte._expose_data = None
        self.vte.show()
        self.default_encoding = self.vte.get_encoding()
        self.update_url_matches(self.config['try_posix_regexp'])

        self.titlebar = Titlebar()
        self.searchbar = Searchbar()

        self.show()
        self.pack_start(self.titlebar, False)
        self.pack_start(self.terminalbox)
        self.pack_end(self.searchbar)

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

        self.matches['full_uri'] = self._vte.match_add(lboundry + schemes + 
                "//(" + user + "@)?[" + hostchars  +".]+(:[0-9]+)?(" + 
                urlpath + ")?" + rboundry + "/?")

        if self.matches['full_uri'] == -1:
            if posix:
                err ('update_url_matches: POSIX match failed, trying GNU')
                self.update_url_matches(posix = False)
            else:
                err ('update_url_matches: Failed adding URL match patterns')
        else:
            self.matches['voip'] = self._vte.match_add(lboundry + 
                    '(callto:|h323:|sip:)' + "[" + userchars + "+][" + 
                    userchars + ".]*(:[0-9]+)?@?[" + pathchars + "]+" + 
                    rboundry)
            self.matches['addr_only'] = self._vte.match_add (lboundry + 
                    "(www|ftp)[" + hostchars + "]*\.[" + hostchars + 
                    ".]+(:[0-9]+)?(" + urlpath + ")?" + rboundry + "/?")
            self.matches['email'] = self._vte.match_add (lboundry + 
                    "(mailto:)?[a-zA-Z0-9][a-zA-Z0-9.+-]*@[a-zA-Z0-9][a-zA-Z0-9-]*\.[a-zA-Z0-9][a-zA-Z0-9-]+[.a-zA-Z0-9-]*" + rboundry)
            self.matches['nntp'] = self._vte.match_add (lboundry + 
                    '''news:[-A-Z\^_a-z{|}~!"#$%&'()*+,./0-9;:=?`]+@[-A-Za-z0-9.]+(:[0-9]+)?''' + rboundry)
            # if the url looks like a Launchpad changelog closure entry 
            # LP: #92953 - make it a url to http://bugs.launchpad.net
            self.matches['launchpad'] = self._vte.match_add (
                    '\\bLP:? #?[0-9]+\\b')

# vim: set expandtab ts=4 sw=4:
