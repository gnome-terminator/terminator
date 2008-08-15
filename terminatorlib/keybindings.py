
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
    self.configure({})

  def configure(self, bindings):
    self.keys = bindings
    self.reload()

  def reload(self):
    self._lookup = {}
    self._masks = 0
    for action, binding in self.keys.items():
      try:
        mask, key = self._parsebinding(binding)
        keyval = gtk.gdk.keyval_from_name(key)
        if keyval == 0:
          raise KeymapError("Key '%s' is unrecognised" % key)
      except KeymapError, e:
        e.action = action
        raise e
      else:
        self._lookup.setdefault(mask, {})
        self._lookup[mask][keyval] = action
        if key == 'Tab':
          self._lookup[mask][gtk.keysyms.ISO_Left_Tab] = action
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
    return (mask, re.sub(Modifier, '', binding))

  def _lookup_modifier(self, modifier):
    try:
      return self.modifiers[modifier.lower()]
    except KeyError:
      raise KeymapError("Unhandled modifier '<%s>'" % modifier)

  def lookup(self, event):
    mask = event.state & self._masks
    return self._lookup.get(mask, self.empty).get(event.keyval, None)

