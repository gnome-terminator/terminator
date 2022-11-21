"""
-Basic plugin util for key-press handling, has all mapping to be used
in layout keybindings

Vishweshwar Saran Singh Deo vssdeo@gmail.com
"""

from gi.repository import Gtk, Gdk

from terminatorlib.util import get_config_dir, err, dbg, gerr
from terminatorlib.keybindings import Keybindings, KeymapError

PLUGIN_UTIL_DESC = 0
PLUGIN_UTIL_ACT  = 1
PLUGIN_UTIL_KEYS = 2

#FIXME to sync this with keybinding preferences
class KeyBindUtil:

    keybindings = Keybindings()

    map_key_to_act  = {}
    map_act_to_keys = {}
    map_act_to_desc = {}


    #Example
    #  bind
    #  first param is desc, second is action str
    #  self.keyb.bindkey([PluginUrlFindNext , PluginUrlActFindNext, "<Alt>j"])
    #
    #  get action name
    #  act = self.keyb.keyaction(event)

    #  if act == "url_find_next":


    #check map key_val_mask -> action
    def _check_keybind_change(self, key):
        act = key[PLUGIN_UTIL_ACT]
        for key_val_mask in self.map_key_to_act:
            old_act = self.map_key_to_act[key_val_mask]
            if act == old_act:
                return key_val_mask
        return None

    #check in config before binding
    def bindkey_check_config(self, key, config):
        actstr = key[PLUGIN_UTIL_ACT]
        kbsect = config.base.get_item('keybindings')
        keystr = kbsect[actstr] if actstr in kbsect else ""
        dbg("bindkey_check_config:action (%s) key str:(%s)" % (actstr, keystr))
        if len(keystr):
            key[PLUGIN_UTIL_KEYS] = keystr
            dbg("found new Action->KeyVal in config: (%s, %s)"
                                              % (actstr, keystr));
        self.bindkey(key)

    def bindkey(self, key):
        (keyval, mask)  = self.keybindings._parsebinding(key[PLUGIN_UTIL_KEYS])
        keyval = Gdk.keyval_to_lower(keyval)
        mask = Gdk.ModifierType(mask)

        ret = (keyval, mask)
        dbg("bindkey: (%s) (%s)" %  (key[PLUGIN_UTIL_KEYS], str(ret)))

        #remove if any old key_val_mask
        old_key_val_mask = self._check_keybind_change(key)
        if old_key_val_mask:
            dbg("found old key binding, removing: (%s)" % str(old_key_val_mask))
            del self.map_key_to_act[old_key_val_mask]

        #map key-val-mask to action, used to ease key-press management
        self.map_key_to_act[ret] = key[PLUGIN_UTIL_ACT]


        #map action to key-combo-str, used in preferences->keybinding
        self.map_act_to_keys[key[PLUGIN_UTIL_ACT]]   = key[PLUGIN_UTIL_KEYS]
        #map action to key-combo description, in used preferences->keybinding
        self.map_act_to_desc[key[PLUGIN_UTIL_ACT]] = key[PLUGIN_UTIL_DESC]

    def keyaction(self, event):
        #FIXME MOD2 mask comes in the event, remove
        event.state  &= ~Gdk.ModifierType.MOD2_MASK

        keyval = Gdk.keyval_to_lower(event.keyval)
        ret = (keyval, event.state)
        dbg("keyaction: (%s)" % str(ret))
        return self.map_key_to_act.get(ret, None)

    def get_act_to_keys(self):
        return self.map_act_to_keys

    def get_act_to_desc(self):
        return self.map_act_to_desc
