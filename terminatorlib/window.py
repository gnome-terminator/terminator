#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""window.py - class for the main Terminator window"""

import pygtk
pygtk.require('2.0')
import gobject
import gtk

from util import dbg, err
from translation import _
from version import APP_NAME
from container import Container
from factory import Factory
from newterminator import Terminator

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

    zoom_data = None
    term_zoomed = gobject.property(type=bool, default=False)

    def __init__(self, geometry=None, forcedtitle=None, role=None):
        """Class initialiser"""
        self.terminator = Terminator()
        self.terminator.register_window(self)

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
        if forcedtitle is not None:
            self.title.force_title(forcedtitle)

        if role is not None:
            self.set_role(role)

        if geometry is not None:
            if not self.parse_geometry(geometry):
                err('Window::__init__: Unable to parse geometry: %s' % geometry)

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
        self.set_fullscreen(self.config['window_state'] == 'fullscreen')
        self.set_maximised(self.config['window_state'] == 'maximise')
        self.set_borderless(self.config['borderless'])
        self.set_real_transparency()
        if self.hidebound:
            self.set_hidden(self.config['window_state'] == 'hidden')
        else:
            self.set_iconified(self.config['window_state'] == 'hidden')

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
        maker = Factory()
        # FIXME: We probably want to cancel window urgency here

        mapping = self.terminator.keybindings.lookup(event)

        if mapping:
            dbg('Window::on_key_press: looked up %r' % mapping)
            if mapping == 'full_screen':
                self.set_fullscreen(not self.isfullscreen)
            elif mapping == 'close_window':
                if not self.on_delete_event(window,
                        gtk.gdk.Event(gtk.gdk.DELETE)):
                    self.on_destroy_event(window,
                            gtk.gdk.Event(gtk.gdk.DESTROY))
            elif mapping == 'new_tab':
                self.tab_new()
            else:
                return(False)
            return(True)

    def tab_new(self):
        """Make a new tab"""
        maker = Factory()
        if not maker.isinstance(self.get_child(), 'Notebook'):
            notebook = maker.make('Notebook', window=self)
        self.get_child().newtab()

    def on_delete_event(self, window, event, data=None):
        """Handle a window close request"""
        maker = Factory()
        if maker.isinstance(self.get_child(), 'Terminal'):
            dbg('Window::on_delete_event: Only one child, closing is fine')
            return(False)
        return(self.confirm_close(window, _('window')))

    def confirm_close(self, window, type):
        """Display a confirmation dialog when the user is closing multiple
        terminals in one window"""
        dialog = self.construct_confirm_close(window, type)
        result = dialog.run()
        dialog.destroy()
        return(not (result == gtk.RESPONSE_ACCEPT))

    def on_destroy_event(self, widget, data=None):
        """Handle window descruction"""
        self.terminator.deregister_window(self)
        self.destroy()
        del(self)

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
        dbg('Window::on_window_state_changed: fullscreen=%s, maximised=%s' %
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

    def set_real_transparency(self, value=True):
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
        maker = Factory()
        gtk.Window.add(self, widget)
        if maker.isinstance(widget, 'Terminal'):
            signals = {'close-term': self.closeterm,
                       'title-change': self.title.set_title,
                       'split-horiz': self.split_horiz,
                       'split-vert': self.split_vert,
                       'unzoom': self.unzoom}

            for signal in signals:
                self.connect_child(widget, signal, signals[signal])

            widget.grab_focus()

    def remove(self, widget):
        """Remove our child widget by way of gtk.Window.remove()"""
        gtk.Window.remove(self, widget)
        self.disconnect_child(widget)
        return(True)

    def split_axis(self, widget, vertical=True, sibling=None):
        """Split the window"""
        maker = Factory()
        self.remove(widget)

        if vertical:
            container = maker.make('VPaned')
        else:
            container = maker.make('HPaned')

        if not sibling:
            sibling = maker.make('Terminal')
        self.add(container)
        container.show_all()

        for term in [widget, sibling]:
            container.add(term)
        container.show_all()

        sibling.spawn_child()

    def zoom(self, widget, font_scale=True):
        """Zoom a terminal widget"""
        children = self.get_children()

        if widget in children:
            # This widget is a direct child of ours and we're a Window
            # so zooming is a no-op
            return

        self.zoom_data = widget.get_zoom_data()
        self.zoom_data['widget'] = widget
        self.zoom_data['old_child'] = children[0]
        self.zoom_data['font_scale'] = font_scale

        self.remove(self.zoom_data['old_child'])
        self.zoom_data['old_parent'].remove(widget)
        self.add(widget)
        self.set_property('term_zoomed', True)

        if font_scale:
            widget.zoomcnxid = widget.connect('size-allocate',
                    widget.zoom_scale, self.zoom_data)

        widget.grab_focus()

    def unzoom(self, widget):
        """Restore normal terminal layout"""
        if not self.get_property('term_zoomed'):
            # We're not zoomed anyway
            dbg('Window::unzoom: not zoomed, no-op')
            return

        widget = self.zoom_data['widget']
        if self.zoom_data['font_scale']:
            widget.vte.set_font(self.zoom_data['old_font'])

        self.remove(widget)
        self.add(self.zoom_data['old_child'])
        self.zoom_data['old_parent'].add(widget)
        widget.grab_focus()
        self.zoom_data = None
        self.set_property('term_zoomed', False)

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
            self.set_title(None, newtext)
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
