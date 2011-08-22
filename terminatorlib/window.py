#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""window.py - class for the main Terminator window"""

import copy
import time
import pygtk
pygtk.require('2.0')
import gobject
import gtk

from util import dbg, err
import util
from translation import _
from version import APP_NAME
from container import Container
from factory import Factory
from terminator import Terminator

try:
    import keybinder
except ImportError:
    err('Warning: python-keybinder is not installed. This means the \
hide_window shortcut will be unavailable')

# pylint: disable-msg=R0904
class Window(Container, gtk.Window):
    """Class implementing a top-level Terminator window"""

    terminator = None
    title = None
    isfullscreen = None
    ismaximised = None
    hidebound = None
    hidefunc = None
    losefocus_time = 0
    position = None
    ignore_startup_show = None

    zoom_data = None

    term_zoomed = False
    __gproperties__ = {
            'term_zoomed': (gobject.TYPE_BOOLEAN,
                            'terminal zoomed',
                            'whether the terminal is zoomed',
                            False,
                            gobject.PARAM_READWRITE)
    }

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

        self.pending_set_rough_geometry_hint = False

    def do_get_property(self, prop):
        """Handle gobject getting a property"""
        if prop.name in ['term_zoomed', 'term-zoomed']:
            return(self.term_zoomed)
        else:
            raise AttributeError('unknown property %s' % prop.name)

    def do_set_property(self, prop, value):
        """Handle gobject setting a property"""
        if prop.name in ['term_zoomed', 'term-zoomed']:
            self.term_zoomed = value
        else:
            raise AttributeError('unknown property %s' % prop.name)

    def register_callbacks(self):
        """Connect the GTK+ signals we care about"""
        self.connect('key-press-event', self.on_key_press)
        self.connect('button-press-event', self.on_button_press)
        self.connect('delete_event', self.on_delete_event)
        self.connect('destroy', self.on_destroy_event)
        self.connect('window-state-event', self.on_window_state_changed)
        self.connect('focus-out-event', self.on_focus_out)
        self.connect('focus-in-event', self.on_focus_in)

        # Attempt to grab a global hotkey for hiding the window.
        # If we fail, we'll never hide the window, iconifying instead.
        try:
            self.hidebound = keybinder.bind(
                self.config['keybindings']['hide_window'],
                self.on_hide_window)
        except (KeyError, NameError):
            pass

        if not self.hidebound:
            err('Unable to bind hide_window key, another instance/window has it.')
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
        skiptaskbar = self.config['hide_from_taskbar']
        alwaysontop = self.config['always_on_top']
        sticky = self.config['sticky']

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
        self.set_always_on_top(alwaysontop)
        self.set_real_transparency()
        self.set_sticky(sticky)
        if self.hidebound:
            self.set_hidden(hidden)
            self.set_skip_taskbar_hint(skiptaskbar)
        else:
            self.set_iconified(hidden)

    def apply_icon(self):
        """Set the window icon"""
        icon_theme = gtk.IconTheme()

        try:
            icon = icon_theme.load_icon(APP_NAME, 48, 0)
        except (NameError, gobject.GError):
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
                self.tab_new(self.get_focussed_terminal())
            else:
                return(False)
            return(True)

    def on_button_press(self, window, event):
        """Handle a mouse button event. Mainly this is just a clean way to
        cancel any urgency hints that are set."""
        self.set_urgency_hint(False)
        return(False)

    def on_focus_out(self, window, event):
        """Focus has left the window"""
        for terminal in self.get_visible_terminals():
            terminal.on_window_focus_out()

        self.losefocus_time = time.time()
        if self.config['hide_on_lose_focus'] and self.get_property('visible'):
            self.position = self.get_position()
            self.hidefunc()

    def on_focus_in(self, window, event):
        """Focus has entered the window"""
        self.set_urgency_hint(False)
        # FIXME: Cause the terminal titlebars to update here

    def is_child_notebook(self):
        """Returns True if this Window's child is a Notebook"""
        maker = Factory()
        return(maker.isinstance(self.get_child(), 'Notebook'))

    def tab_new(self, widget=None, debugtab=False, _param1=None, _param2=None):
        """Make a new tab"""
        cwd = None

        if self.get_property('term_zoomed') == True:
            err("You can't create a tab while a terminal is maximised/zoomed")
            return

        if widget:
            cwd = widget.get_cwd()
        maker = Factory()
        if not self.is_child_notebook():
            dbg('Making a new Notebook')
            notebook = maker.make('Notebook', window=self)
        self.get_child().newtab(debugtab, cwd=cwd)

    def on_delete_event(self, window, event, data=None):
        """Handle a window close request"""
        maker = Factory()
        if maker.isinstance(self.get_child(), 'Terminal'):
            dbg('Window::on_delete_event: Only one child, closing is fine')
            return(False)
        elif maker.isinstance(self.get_child(), 'Container'):
            return(self.confirm_close(window, _('window')))
        else:
            dbg('unknown child: %s' % self.get_child())

    def confirm_close(self, window, type):
        """Display a confirmation dialog when the user is closing multiple
        terminals in one window"""
        dialog = self.construct_confirm_close(window, type)
        result = dialog.run()
        dialog.destroy()
        return(not (result == gtk.RESPONSE_ACCEPT))

    def on_destroy_event(self, widget, data=None):
        """Handle window destruction"""
        dbg('destroying self')
        for terminal in self.get_visible_terminals():
            terminal.close()
        self.cnxids.remove_all()
        self.terminator.deregister_window(self)
        self.destroy()
        del(self)

    def on_hide_window(self, data=None):
        """Handle a request to hide/show the window"""

        if not self.get_property('visible'):
            #Don't show if window has just been hidden because of
            #lost focus
            if (time.time() - self.losefocus_time < 0.1) and \
                self.config['hide_on_lose_focus']:
                return
            if self.position:
                self.move(self.position[0], self.position[1])
            self.show()
        else:
            self.position = self.get_position()
            self.hidefunc()

    # pylint: disable-msg=W0613
    def on_window_state_changed(self, window, event):
        """Handle the state of the window changing"""
        self.isfullscreen = bool(event.new_window_state & 
                                 gtk.gdk.WINDOW_STATE_FULLSCREEN)
        self.ismaximised = bool(event.new_window_state &
                                 gtk.gdk.WINDOW_STATE_MAXIMIZED)
        dbg('Window::on_window_state_changed: fullscreen=%s, maximised=%s' \
                % (self.isfullscreen, self.ismaximised))

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
        if value == True:
            self.ignore_startup_show = True
        else:
            self.ignore_startup_show = False

    def set_iconified(self, value):
        """Set the minimised state of the window from the supplied value"""
        if value == True:
            self.iconify()

    def set_always_on_top(self, value):
        """Set the always on top window hint from the supplied value"""
        self.set_keep_above(value)

    def set_sticky(self, value):
        """Set the sticky hint from the supplied value"""
        if value == True:
            self.stick()

    def set_real_transparency(self, value=True):
        """Enable RGBA if supported on the current screen"""
        if self.is_composited() == False:
            value = False

        screen = self.get_screen()
        if value:
            dbg('setting rgba colormap')
            colormap = screen.get_rgba_colormap()
        else:
            dbg('setting rgb colormap')
            colormap = screen.get_rgb_colormap()

        if colormap:
            self.set_colormap(colormap)
    
    def show(self, startup=False):
        """Undo the startup show request if started in hidden mode"""
        gtk.Window.show(self)
        #Present is necessary to grab focus when window is hidden from taskbar
        self.present()

        #Window must be shown, then hidden for the hotkeys to be registered
        if (self.ignore_startup_show and startup == True):
            self.hide()


    def add(self, widget, metadata=None):
        """Add a widget to the window by way of gtk.Window.add()"""
        maker = Factory()
        gtk.Window.add(self, widget)
        if maker.isinstance(widget, 'Terminal'):
            signals = {'close-term': self.closeterm,
                       'title-change': self.title.set_title,
                       'split-horiz': self.split_horiz,
                       'split-vert': self.split_vert,
                       'unzoom': self.unzoom,
                       'tab-change': self.tab_change,
                       'group-all': self.group_all,
                       'ungroup-all': self.ungroup_all,
                       'group-tab': self.group_tab,
                       'ungroup-tab': self.ungroup_tab,
                       'move-tab': self.move_tab,
                       'tab-new': [self.tab_new, widget],
                       'navigate': self.navigate_terminal}

            for signal in signals:
                args = []
                handler = signals[signal]
                if isinstance(handler, list):
                    args = handler[1:]
                    handler = handler[0]
                self.connect_child(widget, signal, handler, *args)

            widget.grab_focus()

    def remove(self, widget):
        """Remove our child widget by way of gtk.Window.remove()"""
        gtk.Window.remove(self, widget)
        self.disconnect_child(widget)
        return(True)

    def get_children(self):
        """Return a single list of our child"""
        children = []
        children.append(self.get_child())
        return(children)

    def hoover(self):
        """Ensure we still have a reason to exist"""
        if not self.get_child():
            self.emit('destroy')

    def closeterm(self, widget):
        """Handle a terminal closing"""
        Container.closeterm(self, widget)
        self.hoover()

    def split_axis(self, widget, vertical=True, cwd=None, sibling=None, widgetfirst=True):
        """Split the window"""
        if self.get_property('term_zoomed') == True:
            err("You can't split while a terminal is maximised/zoomed")
            return

        order = None
        maker = Factory()
        self.remove(widget)

        if vertical:
            container = maker.make('VPaned')
        else:
            container = maker.make('HPaned')

        if not sibling:
            sibling = maker.make('Terminal')
            sibling.set_cwd(cwd)
            sibling.spawn_child()
        self.add(container)
        container.show_all()

        order = [widget, sibling]
        if widgetfirst is False:
            order.reverse()

        for term in order:
            container.add(term)
        container.show_all()

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
        terminals = {}
        if not hasattr(self, 'cached_maker'):
            self.cached_maker = Factory()
        maker = self.cached_maker
        child = self.get_child()

        if not child:
            return([])

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

    def get_focussed_terminal(self):
        """Find which terminal we want to have focus"""
        terminals = self.get_visible_terminals()
        for terminal in terminals:
            if terminal.vte.is_focus():
                return(terminal)
        return(None)

    def deferred_set_rough_geometry_hints(self):
        # no parameters are used in set_rough_geometry_hints, so we can
        # use the set_rough_geometry_hints
        if self.pending_set_rough_geometry_hint == True:
            return
        self.pending_set_rough_geometry_hint = True
        gobject.idle_add(self.do_deferred_set_rough_geometry_hints)

    def do_deferred_set_rough_geometry_hints(self):
        self.pending_set_rough_geometry_hint = False
        self.set_rough_geometry_hints()

    def set_rough_geometry_hints(self):
        """Walk all the terminals along the top and left edges to fake up how
        many columns/rows we sort of have"""
        if not hasattr(self, 'cached_maker'):
            self.cached_maker = Factory()
        maker = self.cached_maker
        if maker.isinstance(self.get_child(), 'Notebook'):
            dbg("We don't currently support geometry hinting with tabs")
            return

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

        if column_sum == 0 or row_sum == 0:
            dbg('column_sum=%s,row_sum=%s. No terminals found in >=1 axis' %
                (column_sum, row_sum))
            return

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

        dbg('setting geometry hints: (ewidth:%s)(eheight:%s),\
(fwidth:%s)(fheight:%s)' % (extra_width, extra_height, 
                            font_width, font_height))
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
            else:
                num = cur + 1
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

    def move_tab(self, widget, direction):
        """Handle a keyboard shortcut for moving tab positions"""
        maker = Factory()
        notebook = self.get_child()

        if not maker.isinstance(notebook, 'Notebook'):
            dbg('not in a notebook, refusing to move tab %s' % direction)
            return

        dbg('moving tab %s' % direction)
        numpages = notebook.get_n_pages()
        page = notebook.get_current_page()
        child = notebook.get_nth_page(page)

        if direction == 'left':
            if page == 0:
                page = numpages
            else:
                page = page - 1
        elif direction == 'right':
            if page == numpages - 1:
                page = 0
            else:
                page = page + 1
        else:
            err('unknown direction: %s' % direction)
            return
        
        notebook.reorder_child(child, page)

    def navigate_terminal(self, terminal, direction):
        """Navigate around terminals"""
        _containers, terminals = util.enumerate_descendants(self)
        visibles = self.get_visible_terminals()
        current = terminals.index(terminal)
        length = len(terminals)
        next = None

        if length <= 1 or len(visibles) <= 1:
            return

        if direction in ['next', 'prev']:
            tmpterms = copy.copy(terminals)
            tmpterms = tmpterms[current+1:]
            tmpterms.extend(terminals[0:current])

            if direction == 'next':
                tmpterms.reverse()

            next = 0
            while len(tmpterms) > 0:
                tmpitem = tmpterms.pop()
                if tmpitem in visibles:
                    next = terminals.index(tmpitem)
                    break
        elif direction in ['left', 'right', 'up', 'down']:
            layout = self.get_visible_terminals()
            allocation = terminal.get_allocation()
            possibles = []

            # Get the co-ordinate of the appropriate edge for this direction
            edge = util.get_edge(allocation, direction)
            # Find all visible terminals which are, in their entirity, in the
            # direction we want to move
            for term in layout:
                rect = layout[term]
                if util.get_nav_possible(edge, rect, direction):
                    possibles.append(term)

            if len(possibles) == 0:
                return

            # Find out how far away each of the possible terminals is, then
            # find the smallest distance. The winning terminals are all of
            # those who are that distance away.
            offsets = {}
            for term in possibles:
                rect = layout[term]
                offsets[term] = util.get_nav_offset(edge, rect, direction)
            keys = offsets.values()
            keys.sort()
            winners = [k for k, v in offsets.iteritems() if v == keys[0]]
            next = terminals.index(winners[0])

            if len(winners) > 1:
                # Break an n-way tie using the cursor position
                term_alloc = terminal.allocation
                cursor_x = term_alloc.x + term_alloc.width / 2
                cursor_y = term_alloc.y + term_alloc.height / 2

                for term in winners:
                    rect = layout[term]
                    if util.get_nav_tiebreak(direction, cursor_x, cursor_y,
                            rect):
                        next = terminals.index(term)
                        break;
        else:
            err('Unknown navigation direction: %s' % direction)

        if next is not None:
            terminals[next].grab_focus()

    def create_layout(self, layout):
        """Apply any config items from our layout"""
        if not layout.has_key('children'):
            err('layout describes no children: %s' % layout)
            return
        children = layout['children']
        if len(children) != 1:
            # We're a Window, we can only have one child
            err('incorrect number of children for Window: %s' % layout)
            return

        child = children[children.keys()[0]]
        terminal = self.get_children()[0]
        dbg('Making a child of type: %s' % child['type'])
        if child['type'] == 'VPaned':
            self.split_axis(terminal, True)
        elif child['type'] == 'HPaned':
            self.split_axis(terminal, False)
        elif child['type'] == 'Notebook':
            self.tab_new()
            i = 2
            while i < len(child['children']):
                self.tab_new()
                i = i + 1
        elif child['type'] == 'Terminal':
            pass
        else:
            err('unknown child type: %s' % child['type'])
            return

        self.get_children()[0].create_layout(child)

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
