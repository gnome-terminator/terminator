#!/usr/bin/python

from terminatorlib.config import dbg,err,Defaults
from terminatorlib.version import APP_NAME, APP_VERSION

import gtk

class ProfileEditor:
  # lists of which settings to put in which tabs
  appearance = ['titlebars', 'titletips', 'allow_bold', 'silent_bell', 'force_no_bell', 'background_darkness', 'background_type', 'background_image', 'cursor_blink', 'font', 'scrollbar_position', 'scroll_background', 'use_system_font', 'use_theme_colors', 'enable_real_transparency']
  colours = ['foreground_color','background_color', 'palette']
  behaviour = ['backspace_binding', 'delete_binding', 'emulation', 'scroll_on_keystroke', 'scroll_on_output', 'scrollback_lines', 'focus', 'focus_on_close', 'exit_action', 'word_chars', 'mouse_autohide', 'use_custom_command', 'custom_command', 'http_proxy', 'encoding']
  globals = ['fullscreen', 'maximise', 'borderless', 'handle_size', 'cycle_term_tab', 'close_button_on_tab', 'tab_position', 'copy_on_selection', 'extreme_tabs', 'try_posix_regexp']

  # metadata about the settings
  data = {'titlebars': ['Show titlebars', 'This places a bar above each terminal which displays its title.'],
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
         }

  def __init__ (self):
    self.window = gtk.Window ()
    self.notebook = gtk.Notebook()
    self.box = gtk.VBox()
    self.butbox = gtk.HButtonBox()
    self.applybut = gtk.Button(stock=gtk.STOCK_APPLY)
    self.cancelbut = gtk.Button(stock=gtk.STOCK_CANCEL)
    self.box.pack_start(self.notebook, False, False)
    self.box.pack_end(self.butbox, False, False)
    self.butbox.set_layout(gtk.BUTTONBOX_END)
    self.butbox.pack_start(self.applybut, False, False)
    self.butbox.pack_start(self.cancelbut, False, False)
    self.window.add (self.box)

    self.notebook.append_page (self.auto_add (gtk.Table (), self.globals), gtk.Label ("Global Settings"))
    self.notebook.append_page (self.auto_add (gtk.Table (), Defaults['keybindings']), gtk.Label ("Keybindings"))
    self.notebook.append_page (self.auto_add (gtk.Table (), self.appearance), gtk.Label ("Appearance"))
    self.notebook.append_page (self.auto_add (gtk.Table (), self.colours), gtk.Label ("Colours"))
    self.notebook.append_page (self.auto_add (gtk.Table (), self.behaviour), gtk.Label ("Behaviour"))

  def go (self):
    self.window.show_all ()

  def source_get_type (self, key):
    if Defaults.has_key (key):
      return Defaults[key].__class__.__name__
    elif Defaults['keybindings'].has_key (key):
      return Defaults['keybindings'][key].__class__.__name__
    else:
      raise KeyError

  def source_get_value (self, key):
    if Defaults.has_key (key):
      return Defaults[key]
    elif Defaults['keybindings'].has_key (key):
      return Defaults['keybindings'][key]
    else:
      raise KeyError

  def auto_add (self, table, list):
    row = 0
    for key in list:
      table.resize (row + 1, 2)
      if self.data.has_key (key) and self.data[key][0] != '':
        label_text = self.data[key][0]
      else:
        label_text = key.replace ('_', ' ').capitalize ()
      label = gtk.Label (label_text)
    
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
        widget = gtk.combo_box_new_text()
        widget.append_text ('left')
        widget.append_text ('right')
        widget.append_text ('disabled')
        widget.set_active (0)
      elif key == 'backspace_binding':
        widget = gtk.combo_box_new_text()
        widget.append_text ('ascii-del')
        widget.append_text ('control-h')
        widget.append_text ('escape-sequence')
        widget.set_active (0)
      elif key == 'delete_binding':
        widget = gtk.combo_box_new_text()
        widget.append_text ('ascii-del')
        widget.append_text ('control-h')
        widget.append_text ('escape-sequence')
        widget.set_active (2)
      elif key == 'focus':
        widget = gtk.combo_box_new_text()
        widget.append_text ('click')
        widget.append_text ('sloppy')
        widget.set_active (0)
      elif key == 'background_type':
        widget = gtk.combo_box_new_text()
        widget.append_text ('solid')
        widget.append_text ('image')
        widget.append_text ('transparent')
        widget.set_active (0)
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
      elif key == 'tab_position':
        widget = gtk.combo_box_new_text()
        widget.append_text ('top')
        widget.append_text ('bottom')
        widget.append_text ('left')
        widget.append_text ('right')
        widget.set_active (0)
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
          print "Unknown type: " + type
          continue

      if hasattr(widget, 'set_tooltip_text') and self.data.has_key (key):
        widget.set_tooltip_text (self.data[key][1])
   
      table.attach (label, 0, 1, row, row + 1, gtk.EXPAND|gtk.FILL, gtk.FILL)
      table.attach (widget, 1, 2, row, row + 1,  gtk.EXPAND|gtk.FILL, gtk.FILL)
      row += 1

    return (table)

