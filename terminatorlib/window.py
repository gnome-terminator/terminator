#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""window.py - class for the main Terminator window"""

import pygtk
pygtk.require('2.0')
import gobject
import gtk

from util import dbg, err
from version import APP_NAME
from container import Container
from newterminator import Terminator
from terminal import Terminal

try:
    import deskbar.core.keybinder as bindkey
except ImportError:
    err('Unable to find python bindings for deskbar, "hide_window" is not' \
            'available.')

# pylint: disable-msg=R0904
class Window(Container, gtk.Window):
    """Class implementing a top-level Terminator window"""

    terminator = None
    title = None
    isfullscreen = None
    ismaximised = None
    hidebound = None
    hidefunc = None
    cnxids = None

    term_zoomed = gobject.property(type=bool, default=False)

    def __init__(self):
        """Class initialiser"""
        self.terminator = Terminator()
        self.cnxids = []

        Container.__init__(self)
        gtk.Window.__init__(self)
        gobject.type_register(Window)
        self.register_signals(Window)

        self.set_property('allow-shrink', True)
        self.apply_icon()

        self.register_callbacks()
        self.apply_config()

        self.title = WindowTitle(self)
        self.title.update()

    def register_callbacks(self):
        """Connect the GTK+ signals we care about"""
        self.connect('key-press-event', self.on_key_press)
        self.connect('delete_event', self.on_delete_event)
        self.connect('destroy', self.on_destroy_event)
        self.connect('window-state-event', self.on_window_state_changed)

        # Attempt to grab a global hotkey for hiding the window.
        # If we fail, we'll never hide the window, iconifying instead.
        try:
            self.hidebound = bindkey.tomboy_keybinder_bind(
                self.config['keybindings']['hide_window'],
                self.on_hide_window)
        except NameError:
            pass

        if not self.hidebound:
            dbg('Unable to bind hide_window key, another instance has it.')
            self.hidefunc = self.iconify
        else:
            self.hidefunc = self.hide

    def apply_config(self):
        """Apply various configuration options"""
        self.set_fullscreen(self.config['fullscreen'])
        self.set_maximised(self.config['maximise'])
        self.set_borderless(self.config['borderless'])
        self.set_real_transparency(self.config['enable_real_transparency'])
        if self.hidebound:
            self.set_hidden(self.config['hidden'])
        else:
            self.set_iconified(self.config['hidden'])

    def apply_icon(self):
        """Set the window icon"""
        icon_theme = gtk.IconTheme()

        try:
            icon = icon_theme.load_icon(APP_NAME, 48, 0)
        except NameError:
            dbg('Unable to load 48px Terminator icon')
            icon = self.render_icon(gtk.STOCK_DIALOG_INFO, gtk.ICON_SIZE_BUTTON)

        self.set_icon(icon)

    def on_key_press(self, window, event):
        """Handle a keyboard event"""
        pass

    def on_delete_event(self, window, event, data=None):
        """Handle a window close request"""
        pass

    def on_destroy_event(self, widget, data=None):
        """Handle window descruction"""
        pass

    def on_hide_window(self, data):
        """Handle a request to hide/show the window"""
        pass

    # pylint: disable-msg=W0613
    def on_window_state_changed(self, window, event):
        """Handle the state of the window changing"""
        self.isfullscreen = bool(event.new_window_state & 
                                 gtk.gdk.WINDOW_STATE_FULLSCREEN)
        self.ismaximised = bool(event.new_window_state &
                                 gtk.gdk.WINDOW_STATE_MAXIMIZED)
        dbg('window state changed: fullscreen %s, maximised %s' %
            (self.isfullscreen, self.ismaximised))

        return(False)

    def set_maximised(self, value):
        """Set the maximised state of the window from the supplied value"""
        if value == True:
            self.maximize()
        else:
            self.unmaximize()

    def set_fullscreen(self, value):
        """Set the fullscreen state of the window from the supplied value"""
        if value == True:
            self.fullscreen()
        else:
            self.unfullscreen()

    def set_borderless(self, value):
        """Set the state of the window border from the supplied value"""
        self.set_decorated (not value)

    def set_hidden(self, value):
        """Set the visibility of the window from the supplied value"""
        pass

    def set_iconified(self, value):
        """Set the minimised state of the window from the value"""
        pass

    def set_real_transparency(self, value):
        """Enable RGBA if supported on the current screen"""
        screen = self.get_screen()
        if value:
            colormap = screen.get_rgba_colormap()
        else:
            colormap = screen.get_rgb_colormap()

        if colormap:
            self.set_colormap(colormap)

    def add(self, widget):
        """Add a widget to the window by way of gtk.Window.add()"""
        if isinstance(widget, Terminal):
            self.cnxids.append(widget.connect('close-term', self.closeterm))
            self.cnxids.append(widget.connect('title-change', 
                                                self.title.set_title))
            self.cnxids.append(widget.connect('split-horiz', self.split_horiz))
            self.cnxids.append(widget.connect('split-vert', self.split_vert))
        gtk.Window.add(self, widget)

    def remove(self, widget):
        """Remove our child widget by way of gtk.Window.remove()"""
        gtk.Window.remove(self, widget)
        for cnxid in self.cnxids:
            widget.disconnect(cnxid)
        self.cnxids = []

    def split_axis(self, widget, vertical=True):
        """Split the window"""
        # FIXME: this .remove isn't good enough, what about signal handlers?
        self.remove(widget)

        # FIXME: we should be creating proper containers, not these gtk widgets
        if vertical:
            container = gtk.VPaned()
        else:
            container = gtk.HPaned()

        sibling = Terminal()
        self.terminator.register_terminal(sibling)

        container.pack1(widget, True, True)
        container.pack2(sibling, True, True)
        container.show()

        self.add(container)
        sibling.spawn_child()

class WindowTitle(object):
    """Class to handle the setting of the window title"""

    window = None
    text = None
    forced = None

    def __init__(self, window):
        """Class initialiser"""
        self.window = window
        self.forced = False

    def set_title(self, widget, text):
        """Set the title"""
        if not self.forced:
            self.text = text
            self.update()

    def force_title(self, newtext):
        """Force a specific title"""
        if newtext:
            self.set_title(newtext)
            self.forced = True
        else:
            self.forced = False

    def update(self):
        """Update the title automatically"""
        title = None

        # FIXME: What the hell is this for?!
        if self.forced:
            title = self.text
        else:
            title = "%s" % self.text

        self.window.set_title(title)

# vim: set expandtab ts=4 sw=4:
