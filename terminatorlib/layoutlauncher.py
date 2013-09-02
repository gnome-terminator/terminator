#!/usr/bin/python
"""Layout Launcher for Terminator. 

Load a UIBuilder config file, display it, populate it with our current layouts,
then allow launching it as a new instance

"""

import os
import gtk

from util import dbg, err, spawn_new_terminator
import config
from translation import _
from terminator import Terminator
from plugin import PluginRegistry

class LayoutLauncher:
    """Class implementing the various parts of the preferences editor"""
    terminator = None
    config = None
    registry = None
    plugins = None
    keybindings = None
    window = None
    builder = None
    layouttreeview = None
    layouttreestore = None

    def __init__ (self):	#, term):
        self.terminator = Terminator()
        self.terminator.register_launcher_window(self)

        self.config = config.Config()
        #self.term = term
        self.builder = gtk.Builder()
        #self.keybindings = Keybindings()
        try:
            # Figure out where our library is on-disk so we can open our 
            (head, _tail) = os.path.split(config.__file__)
            librarypath = os.path.join(head, 'layoutlauncher.glade')
            gladefile = open(librarypath, 'r')
            gladedata = gladefile.read()
        except Exception, ex:
            print "Failed to find layoutlauncher.glade"
            print ex
            return

        self.builder.add_from_string(gladedata)
        self.window = self.builder.get_object('layoutlauncherwin')
        #self.layouteditor = LayoutEditor(self.builder)
        self.builder.connect_signals(self)
        self.window.connect('destroy', self.on_destroy_event)
        #self.layouteditor.prepare()
        self.window.show_all()
        self.layouttreeview = self.builder.get_object('layoutlist')
        self.layouttreestore = self.builder.get_object('layoutstore')
        self.update_layouts()
        try:
            #self.config.inhibit_save()
            #self.set_values()
            pass
        except Exception, e:
            err('Unable to set values: %s' % e)
        #self.config.uninhibit_save()

    def on_destroy_event(self, widget, data=None):
        """Handle window destruction"""
        dbg('destroying self')
        self.terminator.deregister_launcher_window(self)
        self.window.destroy()
        del(self.window)

    def update_layouts(self):
        """Update the contents of the layout"""
        self.layouttreestore.clear()
        layouts = self.config.list_layouts()
        for layout in sorted(layouts, cmp=lambda x,y: cmp(x.lower(), y.lower())):
            if layout != "default":
                self.layouttreestore.append([layout])
            else:
                self.layouttreestore.prepend([layout])

    def on_launchbutton_clicked(self, widget):
        """Handle button click"""
        self.launch_layout()

    def on_row_activated(self, widget,  path,  view_column):
        """Handle item double-click and return"""
        self.launch_layout()

    def launch_layout(self):
        """Launch the selected layout as new instance"""
        dbg('We have takeoff!')
        selection=self.layouttreeview.get_selection()
        (listmodel, rowiter) = selection.get_selected()
        if not rowiter:
            # Something is wrong, just jump to the first item in the list
            selection.select_iter(self.layouttreestore.get_iter_first())
            (listmodel, rowiter) = selection.get_selected()
        layout = listmodel.get_value(rowiter, 0)
        dbg('Clicked for %s' % layout)
        spawn_new_terminator(self.terminator.origcwd, ['-u', '-l', layout])

if __name__ == '__main__':
    import util
    util.DEBUG = True
    import terminal
    LAYOUTLAUNCHER = LayoutLauncher()

    gtk.main()
