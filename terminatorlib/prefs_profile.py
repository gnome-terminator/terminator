#!/usr/bin/python

from terminatorlib.config import dbg,err,Defaults
from terminatorlib.version import APP_NAME, APP_VERSION

import gtk

class ProfileEditor:
  appearance = ['titlebars', 'titletips', 'allow_bold', 'silent_bell', 'background_color', 'background_darkness', 'background_type', 'background_image', 'cursor_blink', 'font', 'foreground_color', 'scrollbar_position', 'scroll_background', 'palette', 'use_system_font', 'use_theme_colors', 'force_no_bell', 'enable_real_transparency']
  behaviour = ['delete_binding', 'emulation', 'scroll_on_keystroke', 'scroll_on_output', 'scrollback_lines', 'focus']
  data = {'titlebars': ['Show titlebars', 'This places a bar above each terminal which displays its title.'],
          'titletips': ['Show title tooltips', 'This adds a tooltip to each terminal which contains its title'],
          'allow_bold': ['Allow bold text', 'Controls whether or not the terminals will honour requests for bold text'],

         }

  def __init__ (self):
    self.window = gtk.Window ()
    self.notebook = gtk.Notebook()
    self.window.add (self.notebook)

    self.notebook.append_page (self.auto_add (gtk.Table (), self.appearance), gtk.Label ("Appearance"))
    self.notebook.append_page (self.auto_add (gtk.Table (), self.behaviour), gtk.Label ("Behaviour"))

    self.window.show_all ()

  def auto_add (self, table, list):
    row = 0
    for key in list:
      table.resize (row + 1, 2)
      if self.data.has_key (key):
        label_text = self.data[key][0]
      else:
        label_text = key.replace ('_', ' ').capitalize ()
      label = gtk.Label (label_text)
    
      type = Defaults[key].__class__.__name__
      value = Defaults[key]
      widget = None

      if key == 'font':
        #widget = gtk.FontSelection()
        #widget.set_preview_text("Terminator: The robot future of terminals")
        #widget.set_font_name(value)
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
      elif key == 'focus':
        widget = gtk.combo_box_new_text()
        widget.append_text ('click')
        widget.append_text ('sloppy')
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
   
      table.attach (label, 0, 1, row, row + 1)
      table.attach (widget, 1, 2, row, row + 1)
      row += 1

    return (table)

