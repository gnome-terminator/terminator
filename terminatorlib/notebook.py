#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""notebook.py - classes for the notebook widget"""

import gobject
import gtk

from terminator import Terminator
from config import Config
from factory import Factory
from container import Container
from editablelabel import EditableLabel
from translation import _
from util import err, dbg, get_top_window, enumerate_descendants

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

        self.show_all()

    def configure(self):
        """Apply widget-wide settings"""
        # FIXME: The old reordered handler updated Terminator.terminals with
        # the new order of terminals. We probably need to preserve this for
        # navigation to next/prev terminals.
        #self.connect('page-reordered', self.on_page_reordered)
        self.set_property('homogeneous', not self.config['scroll_tabbar'])
        self.set_scrollable(self.config['scroll_tabbar'])

        pos = getattr(gtk, 'POS_%s' % self.config['tab_position'].upper())
        self.set_tab_pos(pos)
        self.set_show_tabs(not self.config['hide_tabbar'])

    def split_axis(self, widget, vertical=True, sibling=None):
        """Split the axis of a terminal inside us"""
        page_num = self.page_num(widget)
        if page_num == -1:
            err('Notebook::split_axis: %s not found in Notebook' % widget)
            return

        label = self.get_tab_label(widget)
        self.remove(widget)

        maker = Factory()
        if vertical:
            container = maker.make('vpaned')
        else:
            container = maker.make('hpaned')

        if not sibling:
            sibling = maker.make('terminal')
        sibling.spawn_child()

        self.insert_page(container, None, page_num)
        self.set_tab_label(container, label)
        self.show_all()

        container.add(widget)
        container.add(sibling)
        self.set_current_page(page_num)

        self.show_all()

    def add(self, widget):
        """Add a widget to the container"""
        self.newtab(widget)

    def remove(self, widget):
        """Remove a widget from the container"""
        page_num = self.page_num(widget)
        if page_num == -1:
            err('%s not found in Notebook. Actual parent is: %s' % 
                    (widget, widget.get_parent()))
            return(False)
        self.remove_page(page_num)
        self.disconnect_child(widget)
        return(True)

    def newtab(self, widget=None):
        """Add a new tab, optionally supplying a child widget"""
        maker = Factory()
        top_window = get_top_window(self)

        if not widget:
            widget = maker.make('Terminal')
            widget.spawn_child()

        signals = {'close-term': self.wrapcloseterm,
                   'split-horiz': self.split_horiz,
                   'split-vert': self.split_vert,
                   'title-change': self.propagate_title_change,
                   'unzoom': self.unzoom,
                   'tab-change': top_window.tab_change,
                   'group-all': top_window.group_all,
                   'ungroup-all': top_window.ungroup_all,
                   'group-tab': top_window.group_tab,
                   'ungroup-tab': top_window.ungroup_tab,
                   'move-tab': top_window.move_tab,
                   'tab-new': top_window.tab_new,
                   'navigate': top_window.navigate_terminal}

        if maker.isinstance(widget, 'Terminal'):
            for signal in signals:
                self.connect_child(widget, signal, signals[signal])

        self.set_tab_reorderable(widget, True)
        label = TabLabel(self.window.get_title(), self)
        label.connect('close-clicked', self.closetab)

        label.show_all()
        widget.show_all()

        self.append_page(widget, None)
        self.set_tab_label(widget, label)
        self.set_tab_label_packing(widget, not self.config['scroll_tabbar'],
                                   not self.config['scroll_tabbar'],
                                   gtk.PACK_START)

        self.set_current_page(-1)
        widget.grab_focus()

    def wrapcloseterm(self, widget):
        """A child terminal has closed"""
        dbg('Notebook::wrapcloseterm: called on %s' % widget)
        if self.closeterm(widget):
            dbg('Notebook::wrapcloseterm: closeterm succeeded')
            self.hoover()
        else:
            dbg('Notebook::wrapcloseterm: closeterm failed')

    def closetab(self, widget, label):
        """Close a tab"""
        tabnum = None
        try:
            nb = widget.notebook
        except AttributeError:
            err('TabLabel::closetab: called on non-Notebook: %s' % widget)
            return

        for i in xrange(0, nb.get_n_pages()):
            if label == nb.get_tab_label(nb.get_nth_page(i)):
                tabnum = i
                break

        if not tabnum:
            err('TabLabel::closetab: %s not in %s. Bailing.' % (label, nb))
            return

        maker = Factory()
        child = nb.get_nth_page(tabnum)

        if maker.isinstance(child, 'Terminal'):
            dbg('Notebook::closetab: child is a single Terminal')
            child.close()
        elif maker.isinstance(child, 'Container'):
            dbg('Notebook::closetab: child is a Container')
            dialog = self.construct_confirm_close(self.window, _('tab'))
            result = dialog.run()
            dialog.destroy()

            if result == gtk.RESPONSE_ACCEPT:
                containers = None
                objects = None
                containers, objects = enumerate_descendants(child)

                while len(objects) > 0:
                    descendant = objects.pop()
                    descendant.close()
                    while gtk.events_pending():
                        gtk.main_iteration()
                return
            else:
                dbg('Notebook::closetab: user cancelled request')
                return
        else:
            err('Notebook::closetab: child is unknown type %s' % child)
            return

        nb.remove_page(tabnum)
        del(label)

    def resizeterm(self, widget, keyname):
        """Handle a keyboard event requesting a terminal resize"""
        raise NotImplementedError('resizeterm')

    def zoom(self, widget, fontscale = False):
        """Zoom a terminal"""
        raise NotImplementedError('zoom')

    def unzoom(self, widget):
        """Unzoom a terminal"""
        raise NotImplementedError('unzoom')

    def find_tab_root(self, widget):
        """Look for the tab child which is or ultimately contains the supplied
        widget"""
        parent = widget.get_parent()
        previous = parent

        while parent is not None and parent is not self:
            previous = parent
            parent = parent.get_parent()

        if previous == self:
            return(widget)
        else:
            return(previous)

    def update_tab_label_text(self, widget, text):
        """Update the text of a tab label"""
        notebook = self.find_tab_root(widget)
        label = self.get_tab_label(notebook)
        if not label:
            err('Notebook::update_tab_label_text: %s not found' % widget)
            return
        
        label.set_label(text)

    def hoover(self):
        """Clean up any empty tabs and if we only have one tab left, die"""
        numpages = self.get_n_pages()
        while numpages > 0:
            numpages = numpages - 1
            page = self.get_nth_page(numpages)
            if not page:
                dbg('Removing empty page: %d' % numpages)
                self.remove_page(numpages)

        if self.get_n_pages() == 1:
            dbg('Last page, removing self')
            child = self.get_nth_page(0)
            self.remove_page(0)
            parent = self.get_parent()
            parent.remove(self)
            self.cnxids.remove_all()
            parent.add(child)
            del(self)

class TabLabel(gtk.HBox):
    """Class implementing a label widget for Notebook tabs"""
    notebook = None
    terminator = None
    config = None
    label = None
    icon = None
    button = None

    __gsignals__ = {
            'close-clicked': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
                (gobject.TYPE_OBJECT,)),
    }

    def __init__(self, title, notebook):
        """Class initialiser"""
        gtk.HBox.__init__(self)
        self.__gobject_init__()

        self.notebook = notebook
        self.terminator = Terminator()
        self.config = Config()

        self.label = EditableLabel(title)
        self.update_angle()

        self.pack_start(self.label, True, True)

        self.update_button()
        self.show_all()

    def set_label(self, text):
        """Update the text of our label"""
        self.label.set_text(text)

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

        self.button.set_focus_on_click(False)
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

    def on_close(self, _widget):
        """The close button has been clicked. Destroy the tab"""
        self.emit('close-clicked', self)

# vim: set expandtab ts=4 sw=4:
