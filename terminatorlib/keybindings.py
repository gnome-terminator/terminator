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

import re,sys
from gi.repository import Gtk, Gdk
from .util import err

class KeymapError(Exception):
    """Custom exception for errors in keybinding configurations"""

MODIFIER = re.compile('<([^<]+)>')
class Keybindings:
    """Class to handle loading and lookup of Terminator keybindings"""
    _reported_shadowed = set()   # m26: report each lost default once
    shadowed = {}

    modifiers = {
        'ctrl':     Gdk.ModifierType.CONTROL_MASK,
        'control':  Gdk.ModifierType.CONTROL_MASK,
        'primary':  Gdk.ModifierType.CONTROL_MASK,
        'shift':    Gdk.ModifierType.SHIFT_MASK,
        'alt':      Gdk.ModifierType.MOD1_MASK,
        'super':    Gdk.ModifierType.SUPER_MASK,
        'hyper':    Gdk.ModifierType.HYPER_MASK,
        'mod2':	    Gdk.ModifierType.MOD2_MASK,
        'mod4':     Gdk.ModifierType.MOD4_MASK
    }

    if sys.platform == "darwin":
        modifiers['mod2'] = Gdk.ModifierType.META_MASK

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

    @staticmethod
    def _default_bindings():
        try:
            from .config import DEFAULTS
            return DEFAULTS.get('keybindings', {}) or {}
        except Exception:
            return {}

    @staticmethod
    def _norm(bindings):
        if not isinstance(bindings, (tuple, list)):
            bindings = (bindings,)
        return tuple(b for b in bindings if b and b != 'None')

    def is_default_binding(self, action, bindings=None):
        """True when `action` still has its built-in binding."""
        if bindings is None:
            bindings = self.keys.get(action) if self.keys else None
        defaults = self._default_bindings()
        if action not in defaults:
            return False
        return self._norm(bindings) == self._norm(defaults[action])

    def reload(self):
        """Parse bindings and mangle into an appropriate form

        m26 (round2-ux P2-4): when a key combo is bound by several actions,
        a binding the user set wins over an action that only has its
        built-in default (e.g. an upgraded config binding Ctrl+Shift+Return
        to new_window keeps it; the new 'maximise' default is dropped and
        reported once).  Ties keep the old last-writer-wins behaviour.
        """
        self._lookup = {}
        self._masks = 0
        self.shadowed = {}
        owner_default = {}
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
                    is_default = self.is_default_binding(action, bindings)
                    prev = self._lookup[mask].get(keyval)
                    if prev is not None and prev != action:
                        prev_default = owner_default.get((mask, keyval), False)
                        if is_default and not prev_default:
                            # user binding already owns it: drop default
                            self.shadowed.setdefault(action, []).append(binding)
                            continue
                        if not is_default and prev_default:
                            # earlier default loses to this user binding
                            self.shadowed.setdefault(prev, []).append(binding)
                    self._lookup[mask][keyval] = action
                    owner_default[(mask, keyval)] = is_default
                    self._masks |= mask
        for action, lost in self.shadowed.items():
            key = (action, tuple(lost))
            if key in Keybindings._reported_shadowed:
                continue
            if self.is_default_binding(action) and \
                    not any(action in t.values() for t in self._lookup.values()):
                Keybindings._reported_shadowed.add(key)
                err('keybindings: default shortcut %s of %r is already bound '
                    'in your config to another action; %r has no shortcut '
                    '(rebind it in Preferences > Keybindings)' %
                    (', '.join(lost), action, action))

    def resolved_bindings(self, action):
        """Binding strings of `action` that actually reach it (not lost to a
        conflicting binding).  Used for tooltips."""
        result = []
        for binding in self._norm(self.keys.get(action) if self.keys else ()):
            try:
                keyval, mask = self._parsebinding(binding)
            except KeymapError:
                continue
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
            if self._lookup.get(mask, {}).get(keyval) == action:
                result.append(binding)
        return result

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

