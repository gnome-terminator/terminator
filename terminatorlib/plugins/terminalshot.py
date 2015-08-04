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

# Every plugin you want Terminator to load *must* be listed in 'AVAILABLE'
AVAILABLE = ['TerminalShot']

class TerminalShot(plugin.MenuItem):
    """Add custom commands to the terminal menu"""
    capabilities = ['terminal_menu']
    dialog_action = gtk.FILE_CHOOSER_ACTION_SAVE
    dialog_buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
                      gtk.STOCK_SAVE, gtk.RESPONSE_OK)

    def __init__(self):
        plugin.MenuItem.__init__(self)

    def callback(self, menuitems, menu, terminal):
        """Add our menu items to the menu"""
        item = gtk.MenuItem(_('Terminal _screenshot'))
        item.connect("activate", self.terminalshot, terminal)
        menuitems.append(item)

    def terminalshot(self, _widget, terminal):
        """Handle the taking, prompting and saving of a terminalshot"""
        # Grab a pixbuf of the terminal
        orig_pixbuf = widget_pixbuf(terminal)

        savedialog = gtk.FileChooserDialog(title=_("Save image"),
                                           action=self.dialog_action,
                                           buttons=self.dialog_buttons)
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
        if response == gtk.RESPONSE_OK:
            path = os.path.join(savedialog.get_current_folder(),
                                savedialog.get_filename())
            orig_pixbuf.save(path, 'png')

        savedialog.destroy()
