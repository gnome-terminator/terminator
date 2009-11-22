#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""notebook.py - classes for the notebook widget"""

import gobject
import gtk

from container import Container
from newterminator import Terminator
from terminal import Terminal
from util import err

class Notebook(Container, gtk.Notebook):
    """Class implementing a gtk.Notebook container"""

    def __init__(self, window):
        """Class initialiser"""
        if isinstance(window.get_child(), gtk.Notebook):
            err('There is already a Notebook at the top of this window')
            raise(ValueError)

        Container.__init__(self)
        gtk.Notebook.__init__(self)
        self.terminator = Terminator()
        gobject.type_register(Notebook)
        self.register_signals(Notebook)
        self.configure()

        child = window.get_child()
        window.remove(child)
        window.add(self)
        self.newtab(child)
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

# vim: set expandtab ts=4 sw=4:
