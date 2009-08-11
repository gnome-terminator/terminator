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

try:
    import vte
except ImportError:
    ERROR = gtk.MessageDialog(None,
                              gtk.DIALOG_MODAL,
                              gtk.MESSAGE_ERROR,
                              gtk.BUTTONS_OK,
                              'You need to install python bindings for libvte')
    ERROR.run()
    sys.exit(1)

from cwd import get_pid_cwd, get_default_cwd

class Terminal(gtk.VBox):
    """Class implementing the VTE widget and its wrappings"""

    vte = None

    def __init__(self):
        """Class initialiser"""
        gtk.VBox.__init__(self)

        self.vte = vte.Terminal()
        self.vte.set_size(80, 24)
        self.vte._expose_data = None
        self.vte.show()

# vim: set expandtab ts=4 sw=4:
