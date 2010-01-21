# Terminator by Chris Jones <cmsj@tenshu.net?
# GPL v2 only
"""terminal_menu.py - Default plugins for the terminal menu"""
import gtk
import terminatorlib.plugin as plugin

# Every plugin you want Terminator to load *must* be listed in 'available'

# This is commented out because we don't want any menu item plugins by default
#available = ['MyFirstMenuItem']
available = []

class MyFirstMenuItem(plugin.MenuItem):
    """Simple proof of concept"""
    capabilities = ['terminal_menu']

    def callback(self, menuitems, menu, terminal):
        """Add our menu items to the menu"""
        item = gtk.MenuItem('Some Menu Text')
        menuitems.append(item)

