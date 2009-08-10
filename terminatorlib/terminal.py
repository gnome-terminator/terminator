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
    error = gtk.MessageDialog(None,
                              gtk.DIALOG_MODAL,
                              gtk.MESSAGE_ERROR,
                              gtk.BUTTONS_OK,
                              'You need to install python bindings for libvte')
    error.run()
    sys.exit(1)

from terminator import Terminator

class Terminal(gtk.VBox):
    """Class implementing the VTE widget and its wrappings"""

    def __init__(self):
        """Class initialiser"""
        pass

# vim: set expandtab ts=4 sw=4:
