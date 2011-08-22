#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""paned.py - a base Paned container class and the vertical/horizontal
variants"""

import gobject
import gtk

from util import dbg, err
from terminator import Terminator
from factory import Factory
from container import Container

# pylint: disable-msg=R0921
# pylint: disable-msg=E1101
class Paned(Container):
    """Base class for Paned Containers"""

    position = None
    maker = None

    def __init__(self):
        """Class initialiser"""
        self.terminator = Terminator()
        self.maker = Factory()
        Container.__init__(self)
        self.signals.append({'name': 'resize-term', 
                             'flags': gobject.SIGNAL_RUN_LAST,
                             'return_type': gobject.TYPE_NONE, 
                             'param_types': (gobject.TYPE_STRING,)})


    # pylint: disable-msg=W0613
    def set_initial_position(self, widget, event):
        """Set the initial position of the widget"""
        if not self.position:
            if isinstance(self, gtk.VPaned):
                self.position = self.allocation.height / 2
            else:
                self.position = self.allocation.width / 2

        dbg("Paned::set_initial_position: Setting position to: %d" % self.position)
        self.set_position(self.position)
        self.cnxids.remove_signal(self, 'expose-event')

    # pylint: disable-msg=W0613
    def split_axis(self, widget, vertical=True, cwd=None, sibling=None,
            widgetfirst=True):
        """Default axis splitter. This should be implemented by subclasses"""
        order = None

        self.remove(widget)
        if vertical:
            container = VPaned()
        else:
            container = HPaned()

        if not sibling:
            sibling = self.maker.make('terminal')
            sibling.set_cwd(cwd)
            sibling.spawn_child()

        self.add(container)
        self.show_all()

        order = [widget, sibling]
        if widgetfirst is False:
            order.reverse()

        for terminal in order:
            container.add(terminal)

        self.show_all()

    def add(self, widget, metadata=None):
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

        if self.maker.isinstance(widget, 'Terminal'):
            top_window = self.get_toplevel()
            signals = {'close-term': self.wrapcloseterm,
                    'split-horiz': self.split_horiz,
                    'split-vert': self.split_vert,
                    'title-change': self.propagate_title_change,
                    'resize-term': self.resizeterm,
                    'zoom': top_window.zoom,
                    'tab-change': top_window.tab_change,
                    'group-all': top_window.group_all,
                    'ungroup-all': top_window.ungroup_all,
                    'group-tab': top_window.group_tab,
                    'ungroup-tab': top_window.ungroup_tab,
                    'move-tab': top_window.move_tab,
                    'maximise': [top_window.zoom, False],
                    'tab-new': [top_window.tab_new, widget],
                    'navigate': top_window.navigate_terminal}

            for signal in signals:
                args = []
                handler = signals[signal]
                if isinstance(handler, list):
                    args = handler[1:]
                    handler = handler[0]
                self.connect_child(widget, signal, handler, *args)

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

    def get_children(self):
        """Return an ordered list of our children"""
        children = []
        children.append(self.get_child1())
        children.append(self.get_child2())
        return(children)

    def wrapcloseterm(self, widget):
        """A child terminal has closed, so this container must die"""
        dbg('Paned::wrapcloseterm: Called on %s' % widget)
        if self.closeterm(widget):
            # At this point we only have one child, which is the surviving term
            sibling = self.children[0]
            self.remove(sibling)

            metadata = None
            parent = self.get_parent()
            metadata = parent.get_child_metadata(self)
            dbg('metadata obtained for %s: %s' % (self, metadata))
            parent.remove(self)
            self.cnxids.remove_all()
            parent.add(sibling, metadata)
            sibling.grab_focus()
            del(self)
        else:
            dbg("Paned::wrapcloseterm: self.closeterm failed")

    def hoover(self):
        """Check that we still have a reason to exist"""
        if len(self.children) == 1:
            dbg('Paned::hoover: We only have one child, die')
            parent = self.get_parent()
            child = self.children[0]
            self.remove(child)
            parent.replace(self, child)
            del(self)

    def resizeterm(self, widget, keyname):
        """Handle a keyboard event requesting a terminal resize"""
        if keyname in ['up', 'down'] and isinstance(self, gtk.VPaned):
            # This is a key we can handle
            position = self.get_position()

            if self.maker.isinstance(widget, 'Terminal'):
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

            if self.maker.isinstance(widget, 'Terminal'):
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

    def create_layout(self, layout):
        """Apply layout configuration"""
        if not layout.has_key('children'):
            err('layout specifies no children: %s' % layout)
            return

        children = layout['children']
        if len(children) != 2:
            # Paned widgets can only have two children
            err('incorrect number of children for Paned: %s' % layout)
            return

        keys = []

        # FIXME: This seems kinda ugly. All we want here is to know the order
        # of children based on child['order']
        try:
            child_order_map = {}
            for child in children:
                key = children[child]['order']
                child_order_map[key] = child
            map_keys = child_order_map.keys()
            map_keys.sort()
            for map_key in map_keys:
                keys.append(child_order_map[map_key])
        except KeyError:
            # We've failed to figure out the order. At least give the terminals
            # in the wrong order
            keys = children.keys()

        num = 0
        for child_key in keys:
            child = children[child_key]
            dbg('Making a child of type: %s' % child['type'])
            if child['type'] == 'Terminal':
                pass
            elif child['type'] == 'VPaned':
                if num == 0:
                    terminal = self.get_child1()
                else:
                    terminal = self.get_child2()
                self.split_axis(terminal, True)
            elif child['type'] == 'HPaned':
                if num == 0:
                    terminal = self.get_child1()
                else:
                    terminal = self.get_child2()
                self.split_axis(terminal, False)
            else:
                err('unknown child type: %s' % child['type'])
            num = num + 1

        self.get_child1().create_layout(children[keys[0]])
        self.get_child2().create_layout(children[keys[1]])

        # Store the position for later
        if layout['position']:
            self.position = int(layout['position'])

    def grab_focus(self):
        """We don't want focus, we want a Terminal to have it"""
        self.get_child1().grab_focus()

class HPaned(Paned, gtk.HPaned):
    """Merge gtk.HPaned into our base Paned Container"""
    def __init__(self):
        """Class initialiser"""
        Paned.__init__(self)
        gtk.HPaned.__init__(self)
        self.register_signals(HPaned)
        self.cnxids.new(self, 'expose-event', self.set_initial_position)

class VPaned(Paned, gtk.VPaned):
    """Merge gtk.VPaned into our base Paned Container"""
    def __init__(self):
        """Class initialiser"""
        Paned.__init__(self)
        gtk.VPaned.__init__(self)
        self.register_signals(VPaned)
        self.cnxids.new(self, 'expose-event', self.set_initial_position)

gobject.type_register(HPaned)
gobject.type_register(VPaned)
# vim: set expandtab ts=4 sw=4:
