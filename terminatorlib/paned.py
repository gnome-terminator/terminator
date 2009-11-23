#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""paned.py - a base Paned container class and the vertical/horizontal
variants"""

import gobject
import gtk

from util import dbg, err, get_top_window
from newterminator import Terminator
from terminal import Terminal
from container import Container

# pylint: disable-msg=R0921
# pylint: disable-msg=E1101
class Paned(Container):
    """Base class for Paned Containers"""

    def __init__(self):
        """Class initialiser"""
        self.terminator = Terminator()
        Container.__init__(self)
        self.signals.append({'name': 'resize-term', 
                             'flags': gobject.SIGNAL_RUN_LAST,
                             'return_type': gobject.TYPE_NONE, 
                             'param_types': (gobject.TYPE_STRING,)})


    # pylint: disable-msg=W0613
    def set_initial_position(self, widget, event):
        """Set the initial position of the widget"""
        if isinstance(self, gtk.VPaned):
            position = self.allocation.height / 2
        else:
            position = self.allocation.width / 2

        dbg("Paned::set_initial_position: Setting position to: %d" % position)
        self.set_position(position)
        self.disconnect(self.cnxids['init'])
        del(self.cnxids['init'])

    # pylint: disable-msg=W0613
    def split_axis(self, widget, vertical=True, sibling=None):
        """Default axis splitter. This should be implemented by subclasses"""
        self.remove(widget)
        if vertical:
            container = VPaned()
        else:
            container = HPaned()

        if not sibling:
            sibling = Terminal()
        self.terminator.register_terminal(sibling)
        sibling.spawn_child()

        self.add(container)
        self.show_all()

        container.add(widget)
        container.add(sibling)

        self.show_all()

    def add(self, widget):
        """Add a widget to the container"""
        if len(self.children) == 0:
            self.pack1(widget, True, True)
            self.children.append(widget)
        elif len(self.children) == 1:
            if self.get_child1():
                self.pack2(widget, True, True)
            else:
                self.pack1(widget, True, True)
            self.children.append(widget)
        else:
            raise ValueError('Paned widgets can only have two children')

        self.cnxids[widget] = []
        if isinstance(widget, Terminal):
            top_window = get_top_window(self)

            # FIXME: somehow propagate the title-change signal to the Window
            signals = {'close-term': self.wrapcloseterm,
                    'split-horiz': self.split_horiz,
                    'split-vert': self.split_vert,
                    'resize-term': self.resizeterm,
                    'zoom': top_window.zoom}

            for signal in signals:
                self.connect_child(widget, signal, signals[signal])

            self.connect_child(widget, 'maximise', top_window.zoom,
                    False)

            widget.grab_focus()

        elif isinstance(widget, gtk.Paned):
            try:
                self.connect_child(widget, 'resize-term', self.resizeterm)
            except TypeError:
                err('Paned::add: %s has no signal resize-term' % widget)

    def remove(self, widget):
        """Remove a widget from the container"""
        gtk.Paned.remove(self, widget)
        self.disconnect_child(widget)
        self.children.remove(widget)
        return(True)

    def wrapcloseterm(self, widget):
        """A child terminal has closed, so this container must die"""
        if self.closeterm(widget):
            # At this point we only have one child, which is the surviving term
            sibling = self.children[0]
            self.remove(sibling)

            parent = self.get_parent()
            if 'remove_page' in dir(parent):
              page_num = parent.page_num( self )
              parent.remove_page( page_num )
              parent.insert_page( sibling, None, page_num )
            else:
              parent.remove(self)
              parent.add(sibling)
            del(self)
        else:
            dbg("Paned::wrapcloseterm: self.closeterm failed")

    def hoover(self):
        """Check that we still have a reason to exist"""
        if len(self.children) == 1:
            dbg('Paned::hoover: We only have one child, die')
            parent = self.get_parent()
            parent.remove(self)
            child = self.children[0]
            self.remove(child)
            parent.add(child)
            del(self)

    def resizeterm(self, widget, keyname):
        """Handle a keyboard event requesting a terminal resize"""
        if keyname in ['up', 'down'] and isinstance(self, gtk.VPaned):
            # This is a key we can handle
            position = self.get_position()

            if isinstance(widget, Terminal):
                fontheight = widget.vte.get_char_height()
            else:
                fontheight = 10

            if keyname == 'up':
                self.set_position(position - fontheight)
            else:
                self.set_position(position + fontheight)
        elif keyname in ['left', 'right'] and isinstance(self, gtk.HPaned):
            # This is a key we can handle
            position = self.get_position()

            if isinstance(widget, Terminal):
                fontwidth = widget.vte.get_char_width()
            else:
                fontwidth = 10

            if keyname == 'left':
                self.set_position(position - fontwidth)
            else:
                self.set_position(position + fontwidth)
        else:
            # This is not a key we can handle
            self.emit('resize-term', keyname)

class HPaned(Paned, gtk.HPaned):
    """Merge gtk.HPaned into our base Paned Container"""
    def __init__(self):
        """Class initialiser"""
        Paned.__init__(self)
        gtk.HPaned.__init__(self)
        self.register_signals(HPaned)
        self.cnxids['init'] = self.connect('expose-event',
                self.set_initial_position)

class VPaned(Paned, gtk.VPaned):
    """Merge gtk.VPaned into our base Paned Container"""
    def __init__(self):
        """Class initialiser"""
        Paned.__init__(self)
        gtk.VPaned.__init__(self)
        self.register_signals(VPaned)
        self.cnxids['init'] = self.connect('expose-event',
                self.set_initial_position)

gobject.type_register(HPaned)
gobject.type_register(VPaned)
# vim: set expandtab ts=4 sw=4:
