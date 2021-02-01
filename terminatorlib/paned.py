# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""paned.py - a base Paned container class and the vertical/horizontal
variants"""

import time
from gi.repository import GObject, Gtk, Gdk

from .util import dbg, err,  enumerate_descendants
from .terminator import Terminator
from .factory import Factory
from .container import Container

# pylint: disable-msg=R0921
# pylint: disable-msg=E1101
class Paned(Container):
    """Base class for Paned Containers"""

    position = None
    maker = None
    ratio = 0.5
    last_balance_time = 0
    last_balance_args = None

    def __init__(self):
        """Class initialiser"""
        self.terminator = Terminator()
        self.maker = Factory()
        Container.__init__(self)
        self.signals.append({'name': 'resize-term', 
                             'flags': GObject.SignalFlags.RUN_LAST,
                             'return_type': None, 
                             'param_types': (GObject.TYPE_STRING,)})


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
        
        self.get_toplevel().set_pos_by_ratio = True

        if not sibling:
            sibling = self.maker.make('terminal')
            sibling.set_cwd(cwd)
            if self.config['always_split_with_profile']:
                sibling.force_set_profile(None, widget.get_profile())
            sibling.spawn_child()
            if widget.group and self.config['split_to_group']:
                sibling.set_group(None, widget.group)
        elif self.config['always_split_with_profile']:
            sibling.force_set_profile(None, widget.get_profile())

        self.add(container)
        self.show_all()

        order = [widget, sibling]
        if widgetfirst is False:
            order.reverse()

        for terminal in order:
            container.add(terminal)

        self.show_all()
        sibling.grab_focus()
        
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        self.get_toplevel().set_pos_by_ratio = False


    def add(self, widget, metadata=None):
        """Add a widget to the container"""
        if len(self.children) == 0:
            self.pack1(widget, False, True)
            self.children.append(widget)
        elif len(self.children) == 1:
            if self.get_child1():
                self.pack2(widget, False, True)
            else:
                self.pack1(widget, False, True)
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
                    'size-allocate': self.new_size,
                    'zoom': top_window.zoom,
                    'tab-change': top_window.tab_change,
                    'group-all': top_window.group_all,
                    'group-all-toggle': top_window.group_all_toggle,
                    'ungroup-all': top_window.ungroup_all,
                    'group-tab': top_window.group_tab,
                    'group-tab-toggle': top_window.group_tab_toggle,
                    'ungroup-tab': top_window.ungroup_tab,
                    'move-tab': top_window.move_tab,
                    'maximise': [top_window.zoom, False],
                    'tab-new': [top_window.tab_new, widget],
                    'navigate': top_window.navigate_terminal,
                    'rotate-cw': [top_window.rotate, True],
                    'rotate-ccw': [top_window.rotate, False]}

            for signal in signals:
                args = []
                handler = signals[signal]
                if isinstance(handler, list):
                    args = handler[1:]
                    handler = handler[0]
                self.connect_child(widget, signal, handler, *args)

            if metadata and \
               'had_focus' in metadata and \
               metadata['had_focus'] == True:
                    widget.grab_focus()

        elif isinstance(widget, Gtk.Paned):
            try:
                self.connect_child(widget, 'resize-term', self.resizeterm)
                self.connect_child(widget, 'size-allocate', self.new_size)
            except TypeError:
                err('Paned::add: %s has no signal resize-term' % widget)

    def on_button_press(self, widget, event):
        """Handle button presses on a Pane"""
        if event.button == 1 and event.type == Gdk.EventType._2BUTTON_PRESS:
            if event.get_state() & Gdk.ModifierType.MOD4_MASK == Gdk.ModifierType.MOD4_MASK:
                recurse_up=True
            else:
                recurse_up=False
            
            if event.get_state() & Gdk.ModifierType.SHIFT_MASK == Gdk.ModifierType.SHIFT_MASK:
                recurse_down=True
            else:
                recurse_down=False

            self.last_balance_time = time.time()
            self.last_balance_args = (recurse_up, recurse_down)
            return True
        else:
            return False

    def on_button_release(self, widget, event):
        """Handle button presses on a Pane"""
        if event.button == 1:
            if self.last_balance_time > (time.time() - 1):
                # Dumb loop still needed, or some terms get squished on a Super rebalance
                for i in range(3):
                    while Gtk.events_pending():
                        Gtk.main_iteration_do(False)
                    self.do_redistribute(*self.last_balance_args)
        return False

    def set_autoresize(self, autoresize):
        """Must be called on the highest ancestor in one given orientation"""
        """TODO write some better doc :)"""
        maker = Factory()
        children = self.get_children()
        self.child_set_property(children[0], 'resize', False)
        self.child_set_property(children[1], 'resize', not autoresize)
        for child in children:
            if maker.type(child) == maker.type(self):
                child.set_autoresize(autoresize)

    def do_redistribute(self, recurse_up=False, recurse_down=False):
        """Evenly divide available space between sibling panes"""
        maker = Factory()
        #1 Find highest ancestor of the same type => ha
        highest_ancestor = self
        while type(highest_ancestor.get_parent()) == type(highest_ancestor):
            highest_ancestor = highest_ancestor.get_parent()

        highest_ancestor.set_autoresize(False)
        
        # (1b) If Super modifier, redistribute higher sections too
        if recurse_up:
            grandfather=highest_ancestor.get_parent()
            if maker.isinstance(grandfather, 'VPaned') or \
               maker.isinstance(grandfather, 'HPaned') :
                grandfather.do_redistribute(recurse_up, recurse_down)

        highest_ancestor._do_redistribute(recurse_up, recurse_down)

        GObject.idle_add(highest_ancestor.set_autoresize, True)
    
    def _do_redistribute(self, recurse_up=False, recurse_down=False):
        maker = Factory()
        #2 Make a list of self + all children of same type
        tree = [self, [], 0, None]
        toproc = [tree]
        number_splits = 1
        while toproc:
            curr = toproc.pop(0)
            for child in curr[0].get_children():
                if type(child) == type(curr[0]):
                    childset = [child, [], 0, curr]
                    curr[1].append(childset)
                    toproc.append(childset)
                    number_splits = number_splits+1
                else:
                    curr[1].append([None,[], 1, None])
                    p = curr
                    while p:
                        p[2] = p[2] + 1
                        p = p[3]
                    # (1c) If Shift modifier, redistribute lower sections too
                    if recurse_down and \
                      (maker.isinstance(child, 'VPaned') or \
                       maker.isinstance(child, 'HPaned')):
                        child.do_redistribute(False, True)
                    
        #3 Get ancestor x/y => a, and handle size => hs
        avail_pixels=self.get_length()
        handle_size = self.get_handlesize()
        #4 Math! eek (a - (n * hs)) / (n + 1) = single size => s
        single_size = (avail_pixels - (number_splits * handle_size)) / (number_splits + 1)
        arr_sizes = [single_size]*(number_splits+1)
        for i in range(avail_pixels % (number_splits + 1)):
            arr_sizes[i] = arr_sizes[i] + 1
        #5 Descend down setting the handle position to s
        #  (Has to handle nesting properly)
        toproc = [tree]
        while toproc:
            curr = toproc.pop(0)
            for child in curr[1]:
                toproc.append(child)
                if curr[1].index(child) == 0:
                    curr[0].set_position((child[2]*single_size)+((child[2]-1)*handle_size))

    def remove(self, widget):
        """Remove a widget from the container"""
        Gtk.Paned.remove(self, widget)
        self.disconnect_child(widget)
        self.children.remove(widget)
        return(True)

    def get_children(self):
        """Return an ordered list of our children"""
        children = []
        children.append(self.get_child1())
        children.append(self.get_child2())
        return(children)

    def get_child_metadata(self, widget):
        """Return metadata about a child"""
        metadata = {}
        metadata['had_focus'] = widget.has_focus()

    def get_handlesize(self):
        """Why oh why, gtk3?"""
        try:
            value = GObject.Value(int)
            self.style_get_property('handle-size',  value)
            return(value.get_int())
        except:
            return 0

    def wrapcloseterm(self, widget):
        """A child terminal has closed, so this container must die"""
        dbg('Paned::wrapcloseterm: Called on %s' % widget)

        if self.closeterm(widget):
            # At this point we only have one child, which is the surviving term
            sibling = self.children[0]
            first_term_sibling = sibling
            cur_tabnum = None

            focus_sibling = True
            if self.get_toplevel().is_child_notebook():
                notebook = self.get_toplevel().get_children()[0]
                cur_tabnum = notebook.get_current_page()
                tabnum = notebook.page_num_descendant(self)
                nth_page = notebook.get_nth_page(tabnum)
                exiting_term_was_last_active = (notebook.last_active_term[nth_page] == widget.uuid)
                if exiting_term_was_last_active:
                    first_term_sibling = enumerate_descendants(self)[1][0]
                    notebook.set_last_active_term(first_term_sibling.uuid)
                    notebook.clean_last_active_term()
                    self.get_toplevel().last_active_term = None
                if cur_tabnum != tabnum:
                    focus_sibling = False
            elif self.get_toplevel().last_active_term != widget.uuid:
                focus_sibling = False

            self.remove(sibling)

            metadata = None
            parent = self.get_parent()
            metadata = parent.get_child_metadata(self)
            dbg('metadata obtained for %s: %s' % (self, metadata))
            parent.remove(self)
            self.cnxids.remove_all()
            parent.add(sibling, metadata)
            if cur_tabnum:
                notebook.set_current_page(cur_tabnum)
            if focus_sibling:
                first_term_sibling.grab_focus()
            elif not sibling.get_toplevel().is_child_notebook():
                try:
                    Terminator().find_terminal_by_uuid(sibling.get_toplevel().last_active_term.urn).grab_focus()
                except AttributeError:
                    dbg('cannot find terminal with uuid: %s' % sibling.get_toplevel().last_active_term.urn)
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
        if keyname in ['up', 'down'] and isinstance(self, Gtk.VPaned):
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
        elif keyname in ['left', 'right'] and isinstance(self, Gtk.HPaned):
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
        if 'children' not in layout:
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
            map_keys = list(child_order_map.keys())
            map_keys.sort()
            for map_key in map_keys:
                keys.append(child_order_map[map_key])
        except KeyError:
            # We've failed to figure out the order. At least give the terminals
            # in the wrong order
            keys = list(children.keys())

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

        # Set the position with ratio. For some reason more reliable than by pos.
        if 'ratio' in layout:
            self.ratio = float(layout['ratio'])
            self.set_position_by_ratio()

    def grab_focus(self):
        """We don't want focus, we want a Terminal to have it"""
        self.get_child1().grab_focus()

    def rotate_recursive(self, parent, w, h, clockwise):
        """
        Recursively rotate "self" into a new paned that'll have "w" x "h" size. Attach it to "parent".

        As discussed in LP#1522542, we should build up the new layout (including the separator positions)
        in a single step. We can't rely on Gtk+ computing the allocation sizes yet, so we have to do the
        computation ourselves and carry the resulting paned sizes all the way down the widget tree.
        """
        maker = Factory()
        handle_size = self.get_handlesize()

        if isinstance(self, HPaned):
            container = VPaned()
            reverse = not clockwise
        else:
            container = HPaned()
            reverse = clockwise

        container.ratio = self.ratio
        children = self.get_children()
        if reverse:
            container.ratio = 1 - container.ratio
            children.reverse()

        if isinstance(self, HPaned):
            w1 = w2 = w
            h1 = pos = self.position_by_ratio(h, handle_size, container.ratio)
            h2 = max(h - h1 - handle_size, 0)
        else:
            h1 = h2 = h
            w1 = pos = self.position_by_ratio(w, handle_size, container.ratio)
            w2 = max(w - w1 - handle_size, 0)

        container.set_pos(pos)
        parent.add(container)

        if maker.isinstance(children[0], 'Terminal'):
            children[0].get_parent().remove(children[0])
            container.add(children[0])
        else:
            children[0].rotate_recursive(container, w1, h1, clockwise)

        if maker.isinstance(children[1], 'Terminal'):
            children[1].get_parent().remove(children[1])
            container.add(children[1])
        else:
            children[1].rotate_recursive(container, w2, h2, clockwise)

    def new_size(self, widget, allocation):
        if self.get_toplevel().set_pos_by_ratio:
            self.set_position_by_ratio()
        else:
            self.set_position(self.get_position())
    
    def position_by_ratio(self, total_size, handle_size, ratio):
        non_separator_size = max(total_size - handle_size, 0)
        ratio = min(max(ratio, 0.0), 1.0)
        return int(round(non_separator_size * ratio))

    def ratio_by_position(self, total_size, handle_size, position):
        non_separator_size = max(total_size - handle_size, 0)
        if non_separator_size == 0:
            return None
        position = min(max(position, 0), non_separator_size)
        return float(position) / float(non_separator_size)

    def set_position_by_ratio(self):
        # Fix for strange race condition where every so often get_length returns 1. (LP:1655027)
        while self.terminator.doing_layout and self.get_length() == 1:
            while Gtk.events_pending():
                Gtk.main_iteration()

        self.set_pos(self.position_by_ratio(self.get_length(), self.get_handlesize(), self.ratio))

    def set_position(self, pos):
        newratio = self.ratio_by_position(self.get_length(), self.get_handlesize(), pos)
        if newratio is not None:
            self.ratio = newratio
        self.set_pos(pos)

class HPaned(Paned, Gtk.HPaned):
    """Merge Gtk.HPaned into our base Paned Container"""
    def __init__(self):
        """Class initialiser"""
        Paned.__init__(self)
        GObject.GObject.__init__(self)
        self.props.wide_handle = True
        self.register_signals(HPaned)
        self.cnxids.new(self, 'button-press-event', self.on_button_press)
        self.cnxids.new(self, 'button-release-event', self.on_button_release)

    def get_length(self):
        return(self.get_allocated_width())

    def set_pos(self, pos):
        Gtk.HPaned.set_position(self, pos)
        self.set_property('position-set',  True)

class VPaned(Paned, Gtk.VPaned):
    """Merge Gtk.VPaned into our base Paned Container"""
    def __init__(self):
        """Class initialiser"""
        Paned.__init__(self)
        GObject.GObject.__init__(self)
        self.props.wide_handle = True
        self.register_signals(VPaned)
        self.cnxids.new(self, 'button-press-event', self.on_button_press)
        self.cnxids.new(self, 'button-release-event', self.on_button_release)

    def get_length(self):
        return(self.get_allocated_height())

    def set_pos(self, pos):
        Gtk.VPaned.set_position(self, pos)
        self.set_property('position-set',  True)

GObject.type_register(HPaned)
GObject.type_register(VPaned)
# vim: set expandtab ts=4 sw=4:
