# SelectAll plugin for Terminator
# Author: JohnmaDev
# GPL v2 only
"""select_all.py - Terminator Plugin to select all text in the terminal buffer"""

from gi.repository import Gtk
import terminatorlib.plugin as plugin
from terminatorlib.translation import _

AVAILABLE = ['SelectAll']


class SelectAll(plugin.MenuItem):
    """Add a 'Select All' item to the terminal context menu"""
    capabilities = ['terminal_menu']

    def callback(self, menuitems, menu, terminal):
        item = Gtk.MenuItem(label=_('Select All'))
        item.connect('activate', lambda _: terminal.vte.select_all())
        menuitems.append(item)
