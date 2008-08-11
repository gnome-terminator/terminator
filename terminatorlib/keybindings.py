
import re, gtk

class KeymapError(Exception):
  def __init__(self, value):
    self.value = value
    self.action = 'unknown'

  def __str__(self):
    return "Keybinding '%s' invalid: %s" % (self.action, self.value)

class TerminatorKeybindings:
  Modifier = re.compile('<([^<]+)>')
  keys = {
    'zoom_in':          '<Ctrl>plus',
    'zoom_out':         '<Ctrl>minus',
    'zoom_normal':      '<Ctrl>0',
    'new_root_tab':     '<Ctrl><Shift><Alt>T',
    'new_tab':          '<Ctrl><Shift>T',
    'go_next':          '<Ctrl><Shift>N',
    'go_prev':          '<Ctrl><Shift>P',
    'split_horiz':      '<Ctrl><Shift>O',
    'split_vert':       '<Ctrl><Shift>E',
    'close_term':       '<Ctrl><Shift>W',
    'copy':             '<Ctrl><Shift>C',
    'paste':            '<Ctrl><Shift>V',
    'toggle_scrollbar': '<Ctrl><Shift>S',
    'close_window':     '<Ctrl><Shift>Q',
    'resize_up':        '<Ctrl><Shift>Up',
    'resize_down':      '<Ctrl><Shift>Down',
    'resize_left':      '<Ctrl><Shift>Left',
    'resize_right':     '<Ctrl><Shift>Right',
    'move_tab_right':   '<Ctrl><Shift>Page_Down',
    'move_tab_left':    '<Ctrl><Shift>Page_Up',
    'toggle_zoom':      '<Ctrl><Shift>X',
    'scaled_zoom':      '<Ctrl><Shift>Z',
    'next_tab':         '<Ctrl>Page_Down',
    'prev_tab':         '<Ctrl>Page_Up',
    'go_prev':          '<Ctrl><Shift>Tab',
    'go_next':          '<Ctrl>Tab',
    'full_screen':      'F11',
  }

  modifiers = {
    'ctrl':  gtk.gdk.CONTROL_MASK,
    'shift': gtk.gdk.SHIFT_MASK,
    'alt':   gtk.gdk.MOD1_MASK
  }

  empty = {}

  def __init__(self):
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
          self._lookup[mask][gtk.gdk.keyval_from_name('ISO_Left_Tab')] = action
        self._masks |= mask

  def _parsebinding(self, binding):
    mask = 0
    modifiers = re.findall(self.Modifier, binding)
    if modifiers:
      for modifier in modifiers:
        mask |= self._lookup_modifier(modifier)
    key = re.sub(self.Modifier, '', binding)
    if key == '':
      raise KeymapError('No key found')
    return (mask, re.sub(self.Modifier, '', binding))

  def _lookup_modifier(self, modifier):
    try:
      return self.modifiers[modifier.lower()]
    except KeyError:
      raise KeymapError("Unhandled modifier '<%s>'" % modifier)

  def lookup(self, event):
    mask = event.state & self._masks
    return self._lookup.get(mask, self.empty).get(event.keyval, None)

