#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""notebook.py - classes for the notebook widget"""

import gobject
import gtk

from newterminator import Terminator
from config import Config
from container import Container
from terminal import Terminal
from editablelabel import EditableLabel
from translation import _
from util import err

class Notebook(Container, gtk.Notebook):
    """Class implementing a gtk.Notebook container"""
    window = None

    def __init__(self, window):
        """Class initialiser"""
        if isinstance(window.get_child(), gtk.Notebook):
            err('There is already a Notebook at the top of this window')
            raise(ValueError)

        Container.__init__(self)
        gtk.Notebook.__init__(self)
        self.terminator = Terminator()
        self.window = window
        gobject.type_register(Notebook)
        self.register_signals(Notebook)
        self.configure()

        child = window.get_child()
        window.remove(child)
        window.add(self)
        self.newtab(child)

        label = TabLabel(self.window.get_title(), self)
        self.set_tab_label(child, label)
        self.set_tab_label_packing(child, not self.config['scroll_tabbar'],
                                   not self.config['scroll_tabbar'],
                                   gtk.PACK_START)

        self.show_all()

    def configure(self):
        """Apply widget-wide settings"""
        #self.connect('page-reordered', self.on_page_reordered)
        self.set_property('homogeneous', not self.config['scroll_tabbar'])
        self.set_scrollable(self.config['scroll_tabbar'])

        pos = getattr(gtk, 'POS_%s' % self.config['tab_position'].upper())
        self.set_tab_pos(pos)
        self.set_show_tabs(not self.config['hide_tabbar'])

    def split_axis(self, widget, vertical=True, sibling=None):
        """Default axis splitter. This should be implemented by subclasses"""
        raise NotImplementedError('split_axis')

    def add(self, widget):
        """Add a widget to the container"""
        raise NotImplementedError('add')

    def remove(self, widget):
        """Remove a widget from the container"""
        raise NotImplementedError('remove')

    def newtab(self, widget=None):
        """Add a new tab, optionally supplying a child widget"""
        if not widget:
            widget = Terminal()
            self.terminator.register_terminal(widget)
            widget.spawn_child()

        self.set_tab_reorderable(widget, True)
        label = TabLabel(self.window.get_title(), self)

        label.show_all()
        widget.show_all()

        self.set_tab_label(widget, label)
        self.set_tab_label_packing(widget, not self.config['scroll_tabbar'],
                                   not self.config['scroll_tabbar'],
                                   gtk.PACK_START)


        self.append_page(widget, None)
        widget.grab_focus()
        
    def resizeterm(self, widget, keyname):
        """Handle a keyboard event requesting a terminal resize"""
        raise NotImplementedError('resizeterm')

    def zoom(self, widget, fontscale = False):
        """Zoom a terminal"""
        raise NotImplementedError('zoom')

    def unzoom(self, widget):
        """Unzoom a terminal"""
        raise NotImplementedError('unzoom')

class TabLabel(gtk.HBox):
    """Class implementing a label widget for Notebook tabs"""
    notebook = None
    terminator = None
    config = None
    label = None
    icon = None
    button = None

    def __init__(self, title, notebook):
        """Class initialiser"""
        gtk.HBox.__init__(self)
        self.notebook = notebook
        self.terminator = Terminator()
        self.config = Config()

        self.label = EditableLabel(title)
        self.update_angle()

        self.pack_start(self.label, True, True)

        self.update_button()
        self.show_all()

    def update_button(self):
        """Update the state of our close button"""
        if not self.config['close_button_on_tab']:
            if self.button:
                self.button.remove(self.icon)
                self.remove(self.button)
                del(self.button)
                del(self.icon)
                self.button = None
                self.icon = None
            return

        if not self.button:
            self.button = gtk.Button()
        if not self.icon:
            self.icon = gtk.Image()
            self.icon.set_from_stock(gtk.STOCK_CLOSE,
                                     gtk.ICON_SIZE_MENU)

        self.button.set_relief(gtk.RELIEF_NONE)
        self.button.set_focus_on_click(False)
        # FIXME: Why on earth are we doing this twice?
        self.button.set_relief(gtk.RELIEF_NONE)
        self.button.add(self.icon)
        self.button.connect('clicked', self.on_close)
        self.button.set_name('terminator-tab-close-button')
        self.button.connect('style-set', self.on_style_set)
        if hasattr(self.button, 'set_tooltip_text'):
            self.button.set_tooltip_text(_('Close Tab'))
        self.pack_start(self.button, False, False)
        self.show_all()

    def update_angle(self):
        """Update the angle of a label"""
        position = self.notebook.get_tab_pos()
        if position == gtk.POS_LEFT:
            self.label.set_angle(90)
        elif position == gtk.POS_RIGHT:
            self.label.set_angle(270)
        else:
            self.label.set_angle(0)

    def on_style_set(self, widget, prevstyle):
        """Style changed, recalculate icon size"""
        x, y = gtk.icon_size_lookup_for_settings(self.button.get_settings(),
                                                 gtk.ICON_SIZE_MENU)
        self.button.set_size_request(x + 2, y + 2)

    def on_close(self, widget):
        """The close button has been clicked. Destroy the tab"""
        pass
# vim: set expandtab ts=4 sw=4:
