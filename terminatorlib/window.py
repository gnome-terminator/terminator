#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""window.py - class for the main Terminator window"""

import pygtk
pygtk.require('2.0')
import gobject
import gtk
import glib

from util import dbg, err
from translation import _
from version import APP_NAME
from container import Container
from factory import Factory
from terminator import Terminator

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

    def __init__(self):
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

        options = self.config.options_get()
        if options:
            if options.forcedtitle is not None:
                self.title.force_title(options.forcedtitle)

            if options.role is not None:
                self.set_role(options.role)

            if options.geometry is not None:
                if not self.parse_geometry(options.geometry):
                    err('Window::__init__: Unable to parse geometry: %s' % 
                            options.geometry)

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
        except (KeyError, NameError):
            pass

        if not self.hidebound:
            dbg('Unable to bind hide_window key, another instance has it.')
            self.hidefunc = self.iconify
        else:
            self.hidefunc = self.hide

    def apply_config(self):
        """Apply various configuration options"""
        options = self.config.options_get()
        maximise = self.config['window_state'] == 'maximise'
        fullscreen = self.config['window_state'] == 'fullscreen'
        hidden = self.config['window_state'] == 'hidden'
        borderless = self.config['borderless']

        if options:
            if options.maximise:
                maximise = True
            if options.fullscreen:
                fullscreen = True
            if options.hidden:
                hidden = True
            if options.borderless:
                borderless = True

        self.set_fullscreen(fullscreen)
        self.set_maximised(maximise)
        self.set_borderless(borderless)
        self.set_real_transparency()
        if self.hidebound:
            self.set_hidden(hidden)
        else:
            self.set_iconified(hidden)

    def apply_icon(self):
        """Set the window icon"""
        icon_theme = gtk.IconTheme()

        try:
            icon = icon_theme.load_icon(APP_NAME, 48, 0)
        except (NameError, glib.GError):
            dbg('Unable to load 48px Terminator icon')
            icon = self.render_icon(gtk.STOCK_DIALOG_INFO, gtk.ICON_SIZE_BUTTON)

        self.set_icon(icon)

    def on_key_press(self, window, event):
        """Handle a keyboard event"""
        maker = Factory()

        self.set_urgency_hint(False)

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
            dbg('setting rgba colormap')
            colormap = screen.get_rgba_colormap()
        else:
            dbg('setting rgb colormap')
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

            self.connect_child(widget, 'tab-change', self.tab_change)
            self.connect_child(widget, 'group-all', self.group_all)
            self.connect_child(widget, 'ungroup-all', self.ungroup_all)
            self.connect_child(widget, 'group-tab', self.group_tab)
            self.connect_child(widget, 'ungroup-tab', self.ungroup_tab)

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
            widget.cnxids.new(widget, 'size-allocate', 
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

    def get_visible_terminals(self):
        """Walk down the widget tree to find all of the visible terminals.
        Mostly using Container::get_visible_terminals()"""
        maker = Factory()
        child = self.get_child()
        terminals = {}

        # If our child is a Notebook, reset to work from its visible child
        if maker.isinstance(child, 'Notebook'):
            pagenum = child.get_current_page()
            child = child.get_nth_page(pagenum)

        if maker.isinstance(child, 'Container'):
            terminals.update(child.get_visible_terminals())
        elif maker.isinstance(child, 'Terminal'):
            terminals[child] = child.get_allocation()
        else:
            err('Unknown child type %s' % type(child))

        return(terminals)

    def set_rough_geometry_hints(self):
        """Walk all the terminals along the top and left edges to fake up how
        many columns/rows we sort of have"""
        terminals = self.get_visible_terminals()
        column_sum = 0
        row_sum = 0

        for terminal in terminals:
            rect = terminal.get_allocation()
            if rect.x == 0:
                cols, rows = terminal.get_size()
                row_sum = row_sum + rows
            if rect.y == 0:
                cols, rows = terminal.get_size()
                column_sum = column_sum + cols

        # FIXME: I don't think we should just use whatever font size info is on
        # the last terminal we inspected. Looking up the default profile font
        # size and calculating its character sizes would be rather expensive
        # though.
        font_width, font_height = terminal.get_font_size()
        total_font_width = font_width * column_sum
        total_font_height = font_height * row_sum

        win_width, win_height = self.get_size()
        extra_width = win_width - total_font_width
        extra_height = win_height - total_font_height

        self.set_geometry_hints(self, -1, -1, -1, -1, extra_width,
                extra_height, font_width, font_height, -1.0, -1.0)

    def tab_change(self, widget, num=None):
        """Change to a specific tab"""
        if num is None:
            err('must specify a tab to change to')

        maker = Factory()
        child = self.get_child()

        if not maker.isinstance(child, 'Notebook'):
            dbg('child is not a notebook, nothing to change to')
            return

        if num == -1:
            # Go to the next tab
            cur = child.get_current_page()
            pages = child.get_n_pages()
            if cur == pages - 1:
                num = 0
        elif num == -2:
            # Go to the previous tab
            cur = child.get_current_page()
            if cur > 0:
                num = cur - 1
            else:
                num = child.get_n_pages() - 1

        child.set_current_page(num)
        # Work around strange bug in gtk-2.12.11 and pygtk-2.12.1
        # Without it, the selection changes, but the displayed page doesn't
        # change
        child.set_current_page(child.get_current_page())

    # FIXME: All of these (un)group_(all|tab) methods need refactoring work
    def group_all(self, widget):
        """Group all terminals"""
        # FIXME: Why isn't this being done by Terminator() ?
        group = _('All')
        self.terminator.create_group(group)
        for terminal in self.terminator.terminals:
            terminal.set_group(None, group)

    def ungroup_all(self, widget):
        """Ungroup all terminals"""
        for terminal in self.terminator.terminals:
            terminal.set_group(None, None)

    def group_tab(self, widget):
        """Group all terminals in the current tab"""
        maker = Factory()
        notebook = self.get_child()

        if not maker.isinstance(notebook, 'Notebook'):
            dbg('not in a notebook, refusing to group tab')
            return

        pagenum = notebook.get_current_page()
        while True:
            group = _('Tab %d') % pagenum
            if group not in self.terminator.groups:
                break
            pagenum += 1
        for terminal in self.get_visible_terminals():
            terminal.set_group(None, group)

    def ungroup_tab(self, widget):
        """Ungroup all terminals in the current tab"""
        maker = Factory()
        notebook = self.get_child()

        if not maker.isinstance(notebook, 'Notebook'):
            dbg('note in a notebook, refusing to ungroup tab')
            return
        
        for terminal in self.get_visible_terminals():
            terminal.set_group(None, None)

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
