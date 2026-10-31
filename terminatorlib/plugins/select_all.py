# SelectAll plugin for Terminator
# Author: JohnmaDev
# GPL v2 only
"""select_all.py - Terminator Plugin to select all text in the terminal buffer"""

from gi.repository import Gtk
import terminatorlib.plugin as plugin
from terminatorlib.config import Config
from terminatorlib.terminator import Terminator
from terminatorlib.translation import _
from terminatorlib.plugin import KeyBindUtil
from terminatorlib.util import dbg

AVAILABLE = ['SelectAll']

PluginActSelectAll = "plugin_select_all"
PluginSelectAllDesc = "Plugin Select All"


class SelectAll(plugin.MenuItem):
    """Add a 'Select All' item to the terminal context menu and keybinding"""
    capabilities = ['terminal_menu']

    def __init__(self):
        plugin.MenuItem.__init__(self)
        self.config = Config()
        self.keyb = KeyBindUtil(self.config)
        self.keyb.bindkey_check_config(
            [_(PluginSelectAllDesc), PluginActSelectAll, "<Alt>a"])
        self.windows = Terminator().get_windows()
        for window in self.windows:
            window.connect('key-press-event', self.on_keypress)

    def unload(self):
        for window in self.windows:
            try:
                window.disconnect_by_func(self.on_keypress)
            except Exception:
                dbg("no connected signals")
        self.keyb.unbindkey(
            [_(PluginSelectAllDesc), PluginActSelectAll, "<Alt>a"])

    def on_keypress(self, widget, event):
        act = self.keyb.keyaction(event)
        if act == PluginActSelectAll:
            terminal = Terminator().get_focussed_terminal()
            if terminal:
                terminal.vte.select_all()
                return True
        return False

    def callback(self, menuitems, menu, terminal):
        item = Gtk.MenuItem(label=_('Select All'))
        item.connect('activate', lambda _: terminal.vte.select_all())
        menuitems.append(item)
