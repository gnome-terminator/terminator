# Terminator - multiple gnome terminals in one window
# Copyright (C) 2006-2010  cmsj@tenshu.net
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 2 only.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

"""Terminator by Chris Jones <cmsj@tenshu.net>

Validator and functions for dealing with Terminator's customisable 
keyboard shortcuts.

"""

import re
from gi.repository import Gtk, Gdk
from .util import err

class KeymapError(Exception):
    """Custom exception for errors in keybinding configurations"""

MODIFIER = re.compile('<([^<]+)>')
class Keybindings:
    """Class to handle loading and lookup of Terminator keybindings"""

    modifiers = {
        'ctrl':     Gdk.ModifierType.CONTROL_MASK,
        'control':  Gdk.ModifierType.CONTROL_MASK,
        'primary':  Gdk.ModifierType.CONTROL_MASK,
        'shift':    Gdk.ModifierType.SHIFT_MASK,
        'alt':      Gdk.ModifierType.MOD1_MASK,
        'super':    Gdk.ModifierType.SUPER_MASK,
        'hyper':    Gdk.ModifierType.HYPER_MASK,
        'mod2':	    Gdk.ModifierType.MOD2_MASK
    }

    empty = {}
    keys = None
    _masks = None
    _lookup = None

    def __init__(self):
        self.keymap = Gdk.Keymap.get_default()
        self.configure({})

    def configure(self, bindings):
        """Accept new bindings and reconfigure with them"""
        self.keys = bindings
        self.reload()

    def reload(self):
        """Parse bindings and mangle into an appropriate form"""
        self._lookup = {}
        self._masks = 0
        for action, bindings in list(self.keys.items()):
            if not isinstance(bindings, tuple):
                bindings = (bindings,)

            for binding in bindings:
                if not binding or binding == "None":
                    continue

                try:
                    keyval, mask = self._parsebinding(binding)
                    # Does much the same, but with poorer error handling.
                    #keyval, mask = Gtk.accelerator_parse(binding)
                except KeymapError as e:
                  err ("keybindings.reload failed to parse binding '%s': %s" % (binding, e))
                else:
                    if mask & Gdk.ModifierType.SHIFT_MASK:
                        if keyval == Gdk.KEY_Tab:
                            keyval = Gdk.KEY_ISO_Left_Tab
                            mask &= ~Gdk.ModifierType.SHIFT_MASK
                        else:
                            keyvals = Gdk.keyval_convert_case(keyval)
                            if keyvals[0] != keyvals[1]:
                                keyval = keyvals[1]
                                mask &= ~Gdk.ModifierType.SHIFT_MASK
                    else:
                        keyval = Gdk.keyval_to_lower(keyval)
                    self._lookup.setdefault(mask, {})
                    self._lookup[mask][keyval] = action
                    self._masks |= mask

    def _parsebinding(self, binding):
        """Parse an individual binding using gtk's binding function"""
        mask = 0
        modifiers = re.findall(MODIFIER, binding)
        if modifiers:
            for modifier in modifiers:
                mask |= self._lookup_modifier(modifier)
        key = re.sub(MODIFIER, '', binding)
        if key == '':
            raise KeymapError('No key found')
        keyval = Gdk.keyval_from_name(key)
        if keyval == 0:
            raise KeymapError("Key '%s' is unrecognised" % key)
        return (keyval, mask)

    def _lookup_modifier(self, modifier):
        """Map modifier names to gtk values"""
        try:
            return self.modifiers[modifier.lower()]
        except KeyError:
            raise KeymapError("Unhandled modifier '<%s>'" % modifier)

    def lookup(self, event):
        """Translate a keyboard event into a mapped key"""
        try:
            _found, keyval, _egp, _lvl, consumed = self.keymap.translate_keyboard_state(
                                              event.hardware_keycode, 
                                              Gdk.ModifierType(event.get_state() & ~Gdk.ModifierType.LOCK_MASK),
                                              event.group)
        except TypeError:
            err ("keybindings.lookup failed to translate keyboard event: %s" % 
                     dir(event))
            return None
        mask = (event.get_state() & ~consumed) & self._masks
        return self._lookup.get(mask, self.empty).get(keyval, None)

