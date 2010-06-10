#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""terminalshot.py - Terminator Plugin to take 'screenshots' of individual
terminals"""

import os
import gtk
import terminatorlib.plugin as plugin
from terminatorlib.translation import _
from terminatorlib.util import widget_pixbuf

# Every plugin you want Terminator to load *must* be listed in 'available'
available = ['TerminalShot']

class TerminalShot(plugin.MenuItem):
    """Add custom commands to the terminal menu"""
    capabilities = ['terminal_menu']

    def __init__( self):
        pass

    def callback(self, menuitems, menu, terminal):
        """Add our menu items to the menu"""
        item = gtk.MenuItem(_('Terminal screenshot'))
        item.connect("activate", self.terminalshot, terminal)
        menuitems.append(item)

    def terminalshot(self, widget, terminal):
        # Grab a pixbuf of the terminal
        orig_pixbuf = widget_pixbuf(terminal)

        dialog_action = gtk.FILE_CHOOSER_ACTION_SAVE
        dialog_buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                          gtk.STOCK_SAVE, gtk.RESPONSE_OK)
        savedialog = gtk.FileChooserDialog(title="Save image",
                                           action=dialog_action,
                                           buttons=dialog_buttons)
        savedialog.set_do_overwrite_confirmation(True)
        savedialog.set_local_only(True)

        pixbuf = orig_pixbuf.scale_simple(orig_pixbuf.get_width() / 2, 
                                     orig_pixbuf.get_height() / 2,
                                     gtk.gdk.INTERP_BILINEAR)
        image = gtk.image_new_from_pixbuf(pixbuf)
        savedialog.set_preview_widget(image)

        savedialog.show_all()
        response = savedialog.run()
        path = None
        if response not in [gtk.RESPONSE_NONE, gtk.RESPONSE_DELETE_EVENT,
                            gtk.RESPONSE_CANCEL]:
            path = os.path.join(savedialog.get_current_folder(),
                                savedialog.get_filename())
        savedialog.destroy()

        if path:
            orig_pixbuf.save(path, 'png')

