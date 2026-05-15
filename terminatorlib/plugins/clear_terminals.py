# Terminator plugin by jachoo_
# GPL v2 only
"""clear_terminals.py - Additional key shortcut [Ctrl+Shift+L] to clear all terminals at once"""

from gi.repository import Gtk, GObject, Gdk
from terminatorlib.terminator import Terminator
from terminatorlib import plugin
from terminatorlib.config import Config
from terminatorlib.util import dbg

AVAILABLE = ['ClearTerminals']


class ClearTerminals(plugin.Plugin):
    capabilities = ['ClearTerminals']
    key = "<Control><Shift>l"
    cmd_name = "clear_terminals"
    key_bind = ["ClearTerminals", cmd_name, key]
    config = Config()
    keyb = plugin.KeyBindUtil(config)

    def __init__(self):
        super().__init__()
        self.keyb.bindkey_check_config(self.key_bind)
        for window in Terminator().get_windows():
            window.connect('key-press-event', self.on_keypress)

    def unload(self):
        dbg("unloading")
        self.keyb.unbindkey(self.key_bind)

    def on_keypress(self, widget, event):
        act = self.keyb.keyaction(event)
        if act == self.cmd_name:
            dbg("keyaction: (%s) (%s)" % (str(act), event.keyval))
            e = Gdk.EventKey()
            e.window = event.window
            e.type = Gdk.EventType.KEY_PRESS
            e.state = Gdk.ModifierType.CONTROL_MASK
            e.send_event = False
            e.time = event.time
            e.keyval = 108
            Terminator().all_emit(self, 'key-press-event', e)
            return True
