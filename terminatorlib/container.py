# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""container.py - classes necessary to contain Terminal widgets"""

from gi.repository import GObject
from gi.repository import Gtk

from .factory import Factory
from .config import Config
from .util import dbg, err
from .translation import _
from .signalman import Signalman

# pylint: disable-msg=R0921
class Container(object):
    """Base class for Terminator Containers"""

    terminator = None
    immutable = None
    children = None
    config = None
    signals = None
    signalman = None

    def __init__(self):
        """Class initialiser"""
        self.children = []
        self.signals = []
        self.cnxids = Signalman()
        self.config = Config()

    def register_signals(self, widget):
        """Register gobject signals in a way that avoids multiple inheritance"""
        existing = GObject.signal_list_names(widget)
        for signal in self.signals:
            if signal['name'] in existing:
                dbg('Container:: skipping signal %s for %s, already exists' % (
                        signal['name'], widget))
            else:
                dbg('Container:: registering signal for %s on %s' % 
                        (signal['name'], widget))
                try:
                    GObject.signal_new(signal['name'],
                                       widget,
                                       signal['flags'],
                                       signal['return_type'],
                                        signal['param_types'])
                except RuntimeError:
                    err('Container:: registering signal for %s on %s failed' %
                            (signal['name'], widget))

    def connect_child(self, widget, signal, handler, *args):
        """Register the requested signal and record its connection ID"""
        self.cnxids.new(widget, signal, handler, *args)
        return

    def disconnect_child(self, widget):
        """De-register the signals for a child"""
        self.cnxids.remove_widget(widget)

    def get_offspring(self):
        """Return a list of direct child widgets, if any"""
        return(self.children)

    def get_child_metadata(self, widget):
        """Return metadata that would be useful to recreate ourselves after our
        child is .remove()d and .add()ed"""
        return None

    def split_horiz(self, widget, cwd=None):
        """Split this container horizontally"""
        return(self.split_axis(widget, True, cwd))

    def split_vert(self, widget, cwd=None):
        """Split this container vertically"""
        return(self.split_axis(widget, False, cwd))

    def split_axis(self, widget, vertical=True, cwd=None, sibling=None, siblinglast=None):
        """Default axis splitter. This should be implemented by subclasses"""
        raise NotImplementedError('split_axis')

    def rotate(self, widget, clockwise):
        """Rotate children in this container"""
        raise NotImplementedError('rotate')

    def add(self, widget, metadata=None):
        """Add a widget to the container"""
        raise NotImplementedError('add')

    def remove(self, widget):
        """Remove a widget from the container"""
        raise NotImplementedError('remove')

    def replace(self, oldwidget, newwidget):
        """Replace the child oldwidget with newwidget. This is the bare minimum
        required for this operation. Containers should override it if they have
        more complex requirements"""
        if not oldwidget in self.get_children():
            err('%s is not a child of %s' % (oldwidget, self))
            return
        self.remove(oldwidget)
        self.add(newwidget)

    def hoover(self):
        """Ensure we still have a reason to exist"""
        raise NotImplementedError('hoover')

    def get_children(self):
        """Return an ordered list of the children of this Container"""
        raise NotImplementedError('get_children')

    def closeterm(self, widget):
        """Handle the closure of a terminal"""
        try:
            if self.get_property('term_zoomed'):
                # We're zoomed, so unzoom and then start closing again
                dbg('terminal zoomed, unzooming')
                self.unzoom(widget)
                widget.close()
                return(True)
        except TypeError:
            pass

        if not self.remove(widget):
            dbg('self.remove() failed for %s' % widget)
            return(False)

        self.terminator.deregister_terminal(widget)
        widget.close()
        self.terminator.group_hoover()
        return(True)

    def resizeterm(self, widget, keyname):
        """Handle a keyboard event requesting a terminal resize"""
        raise NotImplementedError('resizeterm')

    def toggle_zoom(self, widget, fontscale = False):
        """Toggle the existing zoom state"""
        try:
            if self.get_property('term_zoomed'):
                self.unzoom(widget)
            else:
                self.zoom(widget, fontscale)
        except TypeError:
            err('Container::toggle_zoom: %s is unable to handle zooming, for \
            %s' % (self, widget))

    def zoom(self, widget, fontscale = False):
        """Zoom a terminal"""
        raise NotImplementedError('zoom')

    def unzoom(self, widget):
        """Unzoom a terminal"""
        raise NotImplementedError('unzoom')

    def construct_confirm_close(self, window, reqtype):
        """Create a confirmation dialog for closing things"""
        
        # skip this dialog if applicable
        if self.config['suppress_multiple_term_dialog']:
            return Gtk.ResponseType.ACCEPT
        
        dialog = Gtk.Dialog(_('Close?'), window, Gtk.DialogFlags.MODAL)
        dialog.set_resizable(False)
    
        dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT)
        c_all = dialog.add_button(Gtk.STOCK_CLOSE, Gtk.ResponseType.ACCEPT)
        c_all.get_children()[0].get_children()[0].get_children()[1].set_label(
                _('Close _Terminals'))
    
        primary = Gtk.Label(label=_('<big><b>Close multiple terminals?</b></big>'))
        primary.set_use_markup(True)
        primary.set_alignment(0, 0.5)
        if reqtype == 'window':
            label_text = _('This window has several terminals open. Closing \
the window will also close all terminals within it.')
        elif reqtype == 'tab':
            label_text = _('This tab has several terminals open. Closing \
the tab will also close all terminals within it.')
        else:
            label_text = ''
        secondary = Gtk.Label(label=label_text)
        secondary.set_line_wrap(True)
                    
        labels = Gtk.VBox()
        labels.pack_start(primary, False, False, 6)
        labels.pack_start(secondary, False, False, 6)
    
        image = Gtk.Image.new_from_stock(Gtk.STOCK_DIALOG_WARNING,
                                         Gtk.IconSize.DIALOG)
        image.set_alignment(0.5, 0)
    
        box = Gtk.HBox()
        box.pack_start(image, False, False, 6)
        box.pack_start(labels, False, False, 6)
        dialog.vbox.pack_start(box, False, False, 12)

        checkbox = Gtk.CheckButton(_("Do not show this message next time"))
        dialog.vbox.pack_end(checkbox, True, True, 0)
    
        dialog.show_all()

        result = dialog.run()
        
        # set configuration
        self.config.base.reload()
        self.config['suppress_multiple_term_dialog'] = checkbox.get_active()
        self.config.save()

        dialog.destroy()
                
        return(result)

    def propagate_title_change(self, widget, title):
        """Pass a title change up the widget stack"""
        maker = Factory()
        parent = self.get_parent()
        title = widget.get_window_title()

        if maker.isinstance(self, 'Notebook'):
            self.update_tab_label_text(widget, title)
        elif maker.isinstance(self, 'Window'):
            self.title.set_title(widget, title)

        if maker.isinstance(parent, 'Container'):
            parent.propagate_title_change(widget, title)

    def get_visible_terminals(self):
        """Walk the widget tree to find all of the visible terminals. That is,
        any terminals which are not hidden in another Notebook pane"""
        if not hasattr(self, 'cached_maker'):
            self.cached_maker = Factory()
        maker = self.cached_maker
        terminals = {}

        for child in self.get_offspring():
            if not child:
                continue
            if maker.isinstance(child, 'Terminal'):
                terminals[child] = child.get_allocation()
            elif maker.isinstance(child, 'Container'):
                terminals.update(child.get_visible_terminals())
            else:
                err('Unknown child type %s' % type(child))

        return(terminals)

    def describe_layout(self, count, parent, global_layout, child_order, save_cwd = False):
        """Describe our current layout"""
        layout = {}
        maker = Factory()
        mytype = maker.type(self)
        if not mytype:
            err('unable to determine own type. %s' % self)
            return({})

        layout['type'] = mytype
        layout['parent'] = parent
        layout['order'] = child_order

        if hasattr(self, 'get_position'):
            position = self.get_position()
            if hasattr(position, '__iter__'):
                position = ':'.join([str(x) for x in position])
            layout['position'] = position
        
        if hasattr(self, 'ismaximised'):
            layout['maximised'] = self.ismaximised
        
        if hasattr(self, 'isfullscreen'):
            layout['fullscreen'] = self.isfullscreen
        
        if hasattr(self, 'ratio'):
            layout['ratio'] = self.ratio

        if hasattr(self, 'get_size'):
            layout['size'] = self.get_size()

        if hasattr(self, 'title'):
            layout['title'] = self.title.text

        if mytype == 'Notebook':
            labels = []
            last_active_term = []
            for tabnum in range(0, self.get_n_pages()):
                page = self.get_nth_page(tabnum)
                label = self.get_tab_label(page)
                labels.append(label.get_custom_label())
                last_active_term.append(self.last_active_term[self.get_nth_page(tabnum)])
            layout['labels'] = labels
            layout['last_active_term'] = last_active_term
            layout['active_page'] = self.get_current_page()
        else:
            if hasattr(self, 'last_active_term') and self.last_active_term is not None:
                layout['last_active_term'] = self.last_active_term

        if mytype == 'Window':
            if self.uuid == self.terminator.last_active_window:
                layout['last_active_window'] = True
            else:
                layout['last_active_window'] = False

        name = 'child%d' % count
        count = count + 1

        global_layout[name] = layout

        child_order = 0
        for child in self.get_children():
            if hasattr(child, 'describe_layout'):
                count = child.describe_layout(count, name, global_layout, child_order, save_cwd)
            child_order = child_order + 1

        return(count)

    def create_layout(self, layout):
        """Apply settings for our layout"""
        raise NotImplementedError('create_layout')


# vim: set expandtab ts=4 sw=4:
