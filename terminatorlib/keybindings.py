
import re, gtk
import terminatorlib.config

class KeymapError(Exception):
  def __init__(self, value):
    self.value = value
    self.action = 'unknown'

  def __str__(self):
    return "Keybinding '%s' invalid: %s" % (self.action, self.value)

Modifier = re.compile('<([^<]+)>')
class TerminatorKeybindings:

  modifiers = {
    'ctrl':  gtk.gdk.CONTROL_MASK,
    'shift': gtk.gdk.SHIFT_MASK,
    'alt':   gtk.gdk.MOD1_MASK
  }

  empty = {}

  def __init__(self):
    self.keymap = gtk.gdk.keymap_get_default()
    self.configure({})

  def configure(self, bindings):
    self.keys = bindings
    self.reload()

  def reload(self):
    self._lookup = {}
    self._masks = 0
    for action, bindings in self.keys.items():
      if not isinstance(bindings, tuple):
        bindings = (bindings,)

      for binding in bindings:
        try:
          keyval, mask = self._parsebinding(binding)
          # Does much the same, but with poorer error handling.
          #keyval, mask = gtk.accelerator_parse(binding)
        except KeymapError, e:
          e.action = action
          raise e
        else:
          if mask & gtk.gdk.SHIFT_MASK:
            if keyval == gtk.keysyms.Tab:
              keyval = gtk.keysyms.ISO_Left_Tab
              mask &= ~gtk.gdk.SHIFT_MASK
            else:
              keyvals = gtk.gdk.keyval_convert_case(keyval)
              if keyvals[0] != keyvals[1]:
                keyval = keyvals[1]
                mask &= ~gtk.gdk.SHIFT_MASK
          else:
            keyval = gtk.gdk.keyval_to_lower(keyval)
          self._lookup.setdefault(mask, {})
          self._lookup[mask][keyval] = action
          self._masks |= mask

  def _parsebinding(self, binding):
    mask = 0
    modifiers = re.findall(Modifier, binding)
    if modifiers:
      for modifier in modifiers:
        mask |= self._lookup_modifier(modifier)
    key = re.sub(Modifier, '', binding)
    if key == '':
      raise KeymapError('No key found')
    keyval = gtk.gdk.keyval_from_name(key)
    if keyval == 0:
      raise KeymapError("Key '%s' is unrecognised" % key)
    return (keyval, mask)

  def _lookup_modifier(self, modifier):
    try:
      return self.modifiers[modifier.lower()]
    except KeyError:
      raise KeymapError("Unhandled modifier '<%s>'" % modifier)

  def lookup(self, event):
    keyval, egroup, level, consumed = self.keymap.translate_keyboard_state(event.hardware_keycode, event.state, event.group)
    mask = (event.state & ~consumed) & self._masks
    return self._lookup.get(mask, self.empty).get(event.keyval, None)

