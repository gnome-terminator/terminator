#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""container.py - classes necessary to contain Terminal widgets"""

import gtk

from version import APP_NAME, APP_VERSION
from util import debug, dbg, err

try:
    import deskbar.core.keybinder as bindkey
except ImportError:
    err('Unable to find python bindings for deskbar, "hide_window" is not' \
            'available.')

class Container:
    """Base class for Terminator Containers"""

    immutable = None
    children = None
    config = None

    def __init__(self, configobject):
        """Class initialiser"""
        self.children = []
        self.config = configobject

    def get_offspring(self):
        """Return a list of child widgets, if any"""
        return(self.children)

class Window(Container, gtk.Window):
    """Class implementing a top-level Terminator window"""

    title = None
    isfullscreen = None

    def __init__(self, configobject):
        """Class initialiser"""
        Container.__init__(self, configobject)
        gtk.Window.__init__(self)

        self.set_property('allow-shrink', True)
        self.register_callbacks()
        self.apply_config()

    def register_callbacks(self):
        """Connect the GTK+ signals we care about"""
        self.connect('key-press-event', self.on_key_press)
        self.connect('delete_event', self.on_delete_event)
        self.connect('destroy', self.on_destroy_event)
        self.connect('window-state-event', self.on_window_state_changed)

        try:
            bindkey.tomboy_keybinder_bind(
                self.config['keybindings']['hide_window'],
                self.on_hide_window)
        except KeyError:
            dbg('Unable to bind hide_window key, another instance has it.')

    def apply_config(self):
        """Apply various configuration options"""
        self.set_fullscreen(self.config['fullscreen'])
        self.set_maximised(self.config['maximised'])
        self.set_borderless(self.config['borderless'])
        self.enable_rgba(self.config['enable_real_transparency'])
        self.set_hidden(self.config['hidden'])

    def on_key_press(self, window, event):
        pass

    def on_delete_event(self):
        pass

    def on_destroy_event(self):
        pass

    def on_window_state_changed(self):
        pass

    def set_fullscreen(self, value):
        pass

CONFIG = {}
WINDOW = Window(CONFIG)
gtk.main()
