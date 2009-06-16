#!/usr/bin/python

from terminatorlib.config import dbg,err,DEFAULTS,TerminatorConfValuestoreRC
from terminatorlib.keybindings import TerminatorKeybindings
from terminatorlib.version import APP_NAME, APP_VERSION
from terminatorlib import translation

import gtk, gobject

class ProfileEditor:
  # lists of which settings to put in which tabs
  appearance = ['titlebars', 'zoomedtitlebar', 'titletips', 'allow_bold', 'audible_bell', 'visible_bell', 'urgent_bell', 'force_no_bell', 'background_darkness', 'background_type', 'background_image', 'cursor_blink', 'cursor_shape', 'font', 'scrollbar_position', 'scroll_background', 'use_system_font', 'use_theme_colors', 'enable_real_transparency']
  colours = ['foreground_color','background_color', 'cursor_color', 'palette']
  behaviour = ['backspace_binding', 'delete_binding', 'emulation', 'scroll_on_keystroke', 'scroll_on_output', 'alternate_screen_scroll', 'scrollback_lines', 'focus', 'focus_on_close', 'exit_action', 'word_chars', 'mouse_autohide', 'use_custom_command', 'custom_command', 'http_proxy', 'encoding']
  globals = ['fullscreen', 'maximise', 'borderless', 'handle_size', 'cycle_term_tab', 'close_button_on_tab', 'tab_position', 'copy_on_selection', 'extreme_tabs', 'try_posix_regexp']

  # metadata about the settings
  data = {'titlebars': ['Show titlebars', 'This places a bar above each terminal which displays its title.'],
          'zoomedtitlebar': ['Show titlebar when zoomed', 'This places an informative bar above a zoomed terminal to indicate there are hidden terminals.'],
          'titletips': ['Show title tooltips', 'This adds a tooltip to each terminal which contains its title'],
          'allow_bold': ['Allow bold text', 'Controls whether or not the terminals will honour requests for bold text'],
          'silent_bell': ['', 'When enabled, bell events will generate a flash. When disabled, they will generate a beep'],
          'background_darkness': ['', 'Controls how much the background will be tinted'],
          'scroll_background': ['', 'When enabled the background image will scroll with the text'],
          'force_no_bell': ['', 'Disable both the visual and audible bells'],
          'tab_position': ['', 'Controls the placement of the tab bar'],
          'use_theme_colors': ['', 'Take the foreground and background colours from the current GTK theme'],
          'enable_real_transparency': ['', 'If you are running a composited desktop (e.g. compiz), enabling this option will enable "true" transpraency'],
          'handle_size': ['', 'This controls the size of the border between terminals. Values 0 to 5 are in pixels, while -1 means the value will be decided by your normal GTK theme.'],
          'close_window': ['Quit Terminator', ''],
          'toggle_zoom': ['Toggle maximise terminal', ''],
          'scaled_zoom': ['Toggle zoomed terminal', ''],
          'prev_tab': ['Previous tab', ''],
          'split_vert': ['Split vertically', ''],
          'split_horiz': ['Split horizontally', ''],
          'go_prev': ['Focus previous terminal', ''],
          'go_next': ['Focus next terminal', ''],
          'close_term': ['Close terminal', ''],
          'new_root_tab': ['New root tab', ''],
          'zoom_normal': ['Zoom reset', ''],
          'reset': ['Reset terminal state', ''],
          'reset_clear': ['Reset and clear terminal', ''],
          'hide_window': ['Toggle visibility of the window', ''],
         }

  # dictionary for results after setting
  widgets = {}

  # combobox settings
  scrollbar_position = ['left', 'right', 'disabled']
  backspace_del_binding = ['ascii-del', 'control-h', 'escape-sequence', 'delete-sequence']
  focus = ['click', 'sloppy', 'mouse']
  background_type = ['solid', 'image', 'transparent']
  tab_position = ['top', 'bottom', 'left', 'right']
  tab_position_gtk = {'top' : gtk.POS_TOP, 'bottom' : gtk.POS_BOTTOM, 'left' : gtk.POS_LEFT, 'right' : gtk.POS_RIGHT}
  cursor_shape = ['block', 'ibeam', 'underline']

  def __init__ (self, term):
    self.term = term
    self.window = gtk.Window ()
    self.notebook = gtk.Notebook()
    self.box = gtk.VBox()
    self.warning = gtk.Label()

    self.warning.set_use_markup (True)
    self.warning.set_line_wrap (True)
    self.warning.set_markup ("<i><b>NOTE:</b> These settings will not be saved. See:</i> <tt>man terminator_config</tt>")

    self.butbox = gtk.HButtonBox()
    self.applybut = gtk.Button(stock=gtk.STOCK_APPLY)
    self.applybut.connect ("clicked", self.apply)
    self.cancelbut = gtk.Button(stock=gtk.STOCK_CLOSE)
    self.cancelbut.connect ("clicked", self.cancel)

    self.box.pack_start(self.warning, False, False)
    self.box.pack_start(self.notebook, False, False)
    self.box.pack_end(self.butbox, False, False)

    self.butbox.set_layout(gtk.BUTTONBOX_END)
    self.butbox.pack_start(self.applybut, False, False)
    self.butbox.pack_start(self.cancelbut, False, False)
    self.window.add (self.box)

    self.notebook.append_page (self.auto_add (gtk.Table (), self.globals), gtk.Label ("Global Settings"))
    self.notebook.append_page (self.prepare_keybindings (), gtk.Label ("Keybindings"))
    self.notebook.append_page (self.auto_add (gtk.Table (), self.appearance), gtk.Label ("Appearance"))
    self.notebook.append_page (self.auto_add (gtk.Table (), self.colours), gtk.Label ("Colours"))
    self.notebook.append_page (self.auto_add (gtk.Table (), self.behaviour), gtk.Label ("Behaviour"))

  def go (self):
    self.window.show_all ()

  def source_get_type (self, key):
    if DEFAULTS.has_key (key):
      return DEFAULTS[key].__class__.__name__
    elif DEFAULTS['keybindings'].has_key (key):
      return DEFAULTS['keybindings'][key].__class__.__name__
    else:
      raise KeyError

  def source_get_value (self, key):
    try:
      return self.term.conf.__getattr__(key)
    except AttributeError:
      try:
        return self.term.conf.keybindings[key]
      except AttributeError:
        pass

  def source_get_keyname (self, key):
    if self.data.has_key (key) and self.data[key][0] != '':
      label_text = self.data[key][0]
    else:
      label_text = key.replace ('_', ' ').capitalize ()
    return label_text

  def auto_add (self, table, list):
    row = 0
    for key in list:
      table.resize (row + 1, 2)
      label = gtk.Label (self.source_get_keyname (key))
      wrapperbox = gtk.HBox()
      wrapperbox.pack_start(label, False, True)  

      type = self.source_get_type (key)
      value = self.source_get_value (key)
      widget = None

      if key == 'font':
        widget = gtk.FontButton(value)
      elif key == 'scrollback_lines':
        # estimated byte size per line according to g-t:
        # sizeof(void *) + sizeof(char *) + sizeof(int) + (80 * (sizeof(int32) + 4)
        widget = gtk.SpinButton()
        widget.set_digits(0)
        widget.set_increments(100, 1000)
        widget.set_range(0, 100000)
        widget.set_value(value)
      elif key == 'scrollbar_position':
        if value == 'hidden':
          value = 'disabled'
        widget = gtk.combo_box_new_text()
        for item in self.scrollbar_position:
          widget.append_text (item)
        if value in self.scrollbar_position:
          widget.set_active (self.scrollbar_position.index(value))
      elif key == 'backspace_binding':
        widget = gtk.combo_box_new_text()
        for item in self.backspace_del_binding:
          widget.append_text (item)
        if value in self.backspace_del_binding:
          widget.set_active (self.backspace_del_binding.index(value))
      elif key == 'delete_binding':
        widget = gtk.combo_box_new_text()
        for item in self.backspace_del_binding:
          widget.append_text (item)
        if value in self.backspace_del_binding:
          widget.set_active (self.backspace_del_binding.index(value))
      elif key == 'focus':
        widget = gtk.combo_box_new_text()
        for item in self.focus:
          widget.append_text (item)
        if value in self.focus:
          widget.set_active (self.focus.index(value))
      elif key == 'background_type':
        widget = gtk.combo_box_new_text()
        for item in self.background_type:
          widget.append_text (item)
        if value in self.background_type:
          widget.set_active (self.background_type.index(value))
      elif key == 'background_darkness':
        widget = gtk.HScale ()
        widget.set_digits (1)
        widget.set_draw_value (True)
        widget.set_value_pos (gtk.POS_LEFT)
        widget.set_range (0, 1)
        widget.set_value (value)
      elif key == 'handle_size':
        widget = gtk.HScale ()
        widget.set_digits (0)
        widget.set_draw_value (True)
        widget.set_value_pos (gtk.POS_LEFT)
        widget.set_range (-1, 5)
        widget.set_value (value)
      elif key == 'foreground_color':
        widget = gtk.ColorButton (gtk.gdk.color_parse (value))
      elif key == 'background_color':
        widget = gtk.ColorButton (gtk.gdk.color_parse (value))
      elif key == 'cursor_color':
        if not value:
          value = self.source_get_value ('foreground_color')
        widget = gtk.ColorButton (gtk.gdk.color_parse (value))
      elif key == 'palette':
        colours = value.split (':')
        numcolours = len (colours)
        widget = gtk.Table (2, numcolours / 2)
        x = 0
        y = 0
        for thing in colours:
          if x == numcolours / 2:
            y += 1
            x = 0
          widget.attach (gtk.ColorButton (gtk.gdk.color_parse (thing)), x, x + 1, y, y + 1)
          x += 1
      elif key == 'background_image':
        widget = gtk.FileChooserButton('Select a File')
        filter = gtk.FileFilter()
        filter.add_mime_type ('image/*')
        widget.add_filter (filter)
        widget.set_local_only (True)
        if value:
          widget.set_filename (value)
      elif key == 'tab_position':
        widget = gtk.combo_box_new_text()
        for item in self.tab_position:
          widget.append_text (item)
        if value in self.tab_position:
          widget.set_active (self.tab_position.index(value))
      elif key == 'cursor_shape':
        widget = gtk.combo_box_new_text()
        for item in self.cursor_shape:
          widget.append_text (item)
        if value in self.cursor_shape:
          widget.set_active (self.cursor_shape.index (value))
      else:
        if type == "bool":
          widget = gtk.CheckButton ()
          widget.set_active (value)
        elif type in ["str", "int", "float"]:
          widget = gtk.Entry ()
          widget.set_text (str(value))
        elif type == "list":
          continue
        else:
          err("Unknown type: %s for key: %s" % (type, key))
          continue

      if hasattr(widget, 'set_tooltip_text') and self.data.has_key (key):
        widget.set_tooltip_text (self.data[key][1])
  
      widget.set_name(key)
      self.widgets[key] = widget
      table.attach (wrapperbox, 0, 1, row, row + 1, gtk.EXPAND|gtk.FILL, gtk.FILL)
      table.attach (widget, 1, 2, row, row + 1,  gtk.EXPAND|gtk.FILL, gtk.FILL)
      row += 1

    return (table)

  def apply (self, data):
    values = {}
    for page in [self.appearance, self.behaviour, self.globals, self.colours]:
      for property in page:
        widget = self.widgets[property]

        if isinstance (widget, gtk.SpinButton):
          value = widget.get_value ()
        elif isinstance (widget, gtk.Entry):
          value = widget.get_text()
        elif isinstance (widget, gtk.CheckButton):
          value = widget.get_active()
        elif isinstance (widget, gtk.ComboBox):
          if widget.name == 'scrollbar_position':
            bucket = self.scrollbar_position
          elif widget.name == 'backspace_binding' or widget.name == 'delete_binding':
            bucket = self.backspace_del_binding
          elif widget.name == 'focus':
            bucket = self.focus
          elif widget.name == 'background_type':
            bucket = self.background_type
          elif widget.name == 'tab_position':
            bucket = self.tab_position
          elif widget.name == 'cursor_shape':
            bucket = self.cursor_shape
          else:
            err("Unknown bucket type for %s" % widget.name)
            continue
  
          value = bucket[widget.get_active()]
        elif isinstance (widget, gtk.FontButton):
          value = widget.get_font_name()
        elif isinstance (widget, gtk.HScale):
          value = widget.get_value()
          if widget.get_digits() == 0:
            value = int(value)
        elif isinstance (widget, gtk.ColorButton):
          value = widget.get_color().to_string()
        elif isinstance (widget, gtk.FileChooserButton):
          value = widget.get_filename()
        elif widget.get_name() == 'palette':
          value = ''
          valuebits = []
          children = widget.get_children()
          children.reverse()
          for child in children:
            valuebits.append (child.get_color().to_string())
          value = ':'.join (valuebits)
        else:
          value = None
          err("skipping unknown property: %s" % property)

        values[property] = value

    has_changed = False
    changed = []
    for source in self.term.conf.sources:
      if isinstance (source, TerminatorConfValuestoreRC):
        for property in values:
          try:
            if self.source_get_value(property) != values[property]:
              dbg("%s changed from %s to %s" % (property, self.source_get_value(property), values[property]))
              source.values[property] = values[property]
              has_changed = True
              changed.append(property)
          except KeyError:
            pass
    if has_changed:
      for changer in changed:
        if changer == "fullscreen":
          self.term.fullscreen_absolute(values[changer])
        elif changer == "maximise":
          if values[changer]:
            self.term.maximize()
          else:
            self.term.unmaximize()
        elif changer == "borderless":
          self.term.window.set_decorated (not values[changer])
        elif changer == "handle_size":
          self.term.set_handle_size(values[changer])
          gtk.rc_reset_styles(gtk.settings_get_default())
        elif changer == "tab_position":
          notebook = self.term.window.get_child()
          new_pos = self.tab_position_gtk[values[changer]]
          angle = 0
          if isinstance (notebook, gtk.Notebook):
            notebook.set_tab_pos(new_pos)
            for i in xrange(0,notebook.get_n_pages()):
              notebook.get_tab_label(notebook.get_nth_page(i)).update_angle()
          pass
        elif changer == "close_button_on_tab":
          notebook = self.term.window.get_child()
          if isinstance (notebook, gtk.Notebook):
            for i in xrange(0,notebook.get_n_pages()):
              notebook.get_tab_label(notebook.get_nth_page(i)).update_closebut()
        # FIXME: which others? cycle_term_tab, copy_on_selection, extreme_tabs, try_posix_regexp
          
      self.term.reconfigure_vtes()

    # Check for changed keybindings
    changed_keybindings = []
    for row in self.liststore:
      accel = gtk.accelerator_name (row[2], row[3])
      value = self.term.conf.keybindings[row[0]]
      if isinstance (value, tuple):
        value = value[0]
      keyval = 0
      mask = 0
      if value is not None:
        (keyval, mask) = self.tkbobj._parsebinding(value)
      if (row[2], row[3]) != (keyval, mask):
        changed_keybindings.append ((row[0], accel))
        dbg("%s changed from %s to %s" % (row[0], self.term.conf.keybindings[row[0]], accel))

    newbindings = self.term.conf.keybindings
    for binding in changed_keybindings:
      newbindings[binding[0]] = binding[1]
    self.term.keybindings.configure (newbindings)

  def cancel (self, data):
    self.window.destroy()
    self.term.options = None
    del(self)

  def prepare_keybindings (self):
    self.liststore = gtk.ListStore (gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_UINT, gobject.TYPE_UINT, gobject.TYPE_BOOLEAN)
    self.liststore.set_sort_column_id (0, gtk.SORT_ASCENDING)
    self.tkbobj = TerminatorKeybindings()
    keyval = None
    mask = None

    for binding in DEFAULTS['keybindings']:
      value = self.term.conf.keybindings[binding]
      keyval = 0
      mask = 0
      if isinstance (value, tuple):
        value = value[0]
      if value is not None:
        (keyval, mask) = self.tkbobj._parsebinding (value)
      self.liststore.append ([binding, self.source_get_keyname (binding), keyval, mask, True])
      dbg("Appended row: %s, %s, %s" % (binding, keyval, mask))

    self.treeview = gtk.TreeView(self.liststore)

    cell = gtk.CellRendererText()
    col = gtk.TreeViewColumn(_("Name"))
    col.pack_start(cell, True)
    col.add_attribute(cell, "text", 0)

    self.treeview.append_column(col)

    cell = gtk.CellRendererText()
    col = gtk.TreeViewColumn(_("Action"))
    col.pack_start(cell, True)
    col.add_attribute(cell, "text", 1)

    self.treeview.append_column(col)

    cell = gtk.CellRendererAccel()
    col = gtk.TreeViewColumn(_("Keyboard shortcut"))
    col.pack_start(cell, True)
    col.set_attributes(cell, accel_key=2, accel_mods=3, editable=4)

    cell.connect ('accel-edited', self.edited)

    self.treeview.append_column(col)

    scrollwin = gtk.ScrolledWindow ()
    scrollwin.set_policy (gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
    scrollwin.add (self.treeview)
    return (scrollwin)

  def edited (self, obj, path, key, mods, code):
    iter = self.liststore.get_iter_from_string(path)
    self.liststore.set(iter, 2, key, 3, mods)
