#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""window.py - class for the main Terminator window"""

import pygtk
pygtk.require('2.0')
import gobject
import gtk
import pango

from version import APP_NAME, APP_VERSION
from util import debug, dbg, err

from container import Container

try:
    import deskbar.core.keybinder as bindkey
except ImportError:
    err('Unable to find python bindings for deskbar, "hide_window" is not' \
            'available.')

class Window(Container, gtk.Window):
    """Class implementing a top-level Terminator window"""

    title = None
    isfullscreen = None
    hidebound = None

    def __init__(self, configobject):
        """Class initialiser"""
        Container.__init__(self, configobject)
        gtk.Window.__init__(self)
        gobject.type_register(Window)
        self.register_signals(Window)

        self.set_property('allow-shrink', True)
        self.register_callbacks()
        self.apply_config()

    def register_callbacks(self):
        """Connect the GTK+ signals we care about"""
        self.connect('key-press-event', self.on_key_press)
        self.connect('delete_event', self.on_delete_event)
        self.connect('destroy', self.on_destroy_event)
        self.connect('window-state-event', self.on_window_state_changed)

        self.hidebound = False
        try:
            self.couldbind = bindkey.tomboy_keybinder_bind(
                self.config['keybindings']['hide_window'],
                self.on_hide_window)
        except KeyError:
            dbg('Unable to bind hide_window key, another instance has it.')

    def apply_config(self):
        """Apply various configuration options"""
        self.set_fullscreen(self.config['fullscreen'])
        self.set_maximised(self.config['maximised'])
        self.set_borderless(self.config['borderless'])
        self.set_real_transparency(self.config['enable_real_transparency'])
        if self.hidebound:
            self.set_hidden(self.config['hidden'])
        else:
            self.set_iconified(self.config['hidden'])

    def on_key_press(self, window, event):
        pass

    def on_delete_event(self, window, event, data=None):
        pass

    def on_destroy_event(self, widget, data=None):
        pass

    def on_window_state_changed(self, window, event):
        self.isfullscreen = bool(event.new_window_state & 
                                 gtk.gdk.WINDOW_STATE_FULLSCREEN)
        self.ismaximised = bool(event.new_window_state &
                                 gtk.gdk.WINDOW_STATE_MAXIMIZED)
        dbg('window state changed: fullscreen %s, maximised %s' %
            (self.isfullscreen, self.ismaximised))
        return(False)

    def set_maximised(self, value):
        if value == True:
            self.maximize()
        else:
            self.unmaximize()

    def set_fullscreen(self, value):
        if value == True:
            self.fullscreen()
        else:
            self.unfullscreen()

    def set_borderless(self, value):
        self.set_decorated (not value)

    def set_hidden(self, value):
        pass

    def set_iconified(self, value):
        pass

    def set_real_transparency(self, value):
        screen = self.get_screen()
        if value:
            colormap = screen.get_rgba_colormap()
        else:
            colormap = screen.get_rgb_colormap()

        if colormap:
            self.set_colormap(colormap)

CONFIG = {'fullscreen':False, 'maximised':False, 'borderless':False, 'enable_real_transparency':True, 'hidden':False}

WINDOW = Window(CONFIG)
WINDOW.show_all()
gtk.main()

# vim: set expandtab ts=4 sw=4:
