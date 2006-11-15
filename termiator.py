#!/usr/bin/python
import sys
import string
import gtk
import vte
import gconf
import pango

class TerminatorTerm:
  # FIXME: How do we get a list of profile keys to be dynamic about this?
  GCONF_PROFILE_DIR = "/apps/gnome-terminal/profiles/Default"

  defaults = {
    'allow_bold'            : True,
    'audible_bell'          : False,
    'background'            : None,
    'background_color'      : '#000000',
    'backspace_binding'     : 'ascii-del',
    'cursor_blinks'         : False,
    'emulation'             : 'xterm',
    'font_name'             : 'Serif 10',
    'foreground_color'      : '#AAAAAA',
    'scroll_on_keystroke'   : False,
    'scroll_on_output'      : False,
    'scrollback_lines'      : 100,
    'visible_bell'          : False
  }

  def __init__ (self, term):
    self.gconf_client = gconf.client_get_default ()
    self.gconf_client.add_dir (self.GCONF_PROFILE_DIR, gconf.CLIENT_PRELOAD_RECURSIVE)

    self._vte = vte.Terminal ()
    self.reconfigure_vte ()
    self._vte.show()  

    self._box = gtk.HBox ()
    self._scrollbar = gtk.VScrollbar (self._vte.get_adjustment ())
    self._scrollbar.show ()

    self._box.pack_start (self._vte)
    self._box.pack_start (self._scrollbar, False)

    self.gconf_client.notify_add (self.GCONF_PROFILE_DIR, self.on_gconf_notification)
    # FIXME: Register a handler for click/sloppy focus changes

    self._vte.connect ("button-press-event", self.on_vte_button_press)
    #self._vte.connect ("popup-menu", self.on_vte_popup_menu)
    self._vte.connect ("child-exited", lambda term: term.fork_command ())

    if (term.focus == "sloppy" or term.focus == "mouse"):
      print "Registering notify event"
      self._vte.add_events (gtk.gdk.ENTER_NOTIFY_MASK)
      self._vte.connect ("enter_notify_event", self.on_vte_notify_enter)

    self._vte.fork_command ()

  def reconfigure_vte (self):
    # Set our emulation
    # FIXME: This is hardcoded to xterm for now
    self._vte.set_emulation (self.defaults['emulation'])

    # Set our font, preferably from gconf settings
    if self.gconf_client.get_bool (self.GCONF_PROFILE_DIR + "/use_system_font"):
      font_name = (self.gconf_client.get_string ("/desktop/gnome/interface/monospace_font_name") or self.defaults['font_name'])
    else:
      font_name = (self.gconf_client.get_string (self.GCONF_PROFILE_DIR + "/font") or self.defaults['font_name'])

    try:
      self._vte.set_font (pango.FontDescription (font_name))
    except:
      pass

    # Set our boldness
    self._vte.set_allow_bold (self.gconf_client.get_bool (self.GCONF_PROFILE_DIR + "/allow_bold") or self.defaults['allow_bold'])

    # Set our color scheme, preferably from gconf settings
    fg_color = (self.gconf_client.get_string (self.GCONF_PROFILE_DIR + "/foreground_color") or self.defaults['foreground_color'])
    bg_color = (self.gconf_client.get_string (self.GCONF_PROFILE_DIR + "/background_color") or self.defaults['background_color'])

    self._vte.set_colors (gtk.gdk.color_parse (fg_color),
                          gtk.gdk.color_parse (bg_color),
			  [])

    # Set our cursor blinkiness
    self._vte.set_cursor_blinks = (self.gconf_client.get_bool (self.GCONF_PROFILE_DIR + "/cursor_blinks") or self.defaults['cursor_blinks'])

    # Set our audible belliness
    self._vte.set_audible_bell = not (self.gconf_client.get_bool (self.GCONF_PROFILE_DIR + "/silent_bell") or self.defaults['audible_bell'])
    # FIXME: Why is this hardcoded? there seems to be no gconf key
    self._vte.set_visible_bell (self.defaults['visible_bell'])

    # Set our scrolliness
    self._vte.set_scrollback_lines (self.gconf_client.get_int (self.GCONF_PROFILE_DIR + "/scrollback_lines") or self.defaults['scrollback_lines'])
    self._vte.set_scroll_on_keystroke (self.gconf_client.get_bool (self.GCONF_PROFILE_DIR + "/scroll_on_keystroke") or self.defaults['scroll_on_keystroke'])
    self._vte.set_scroll_on_output (self.gconf_client.get_bool (self.GCONF_PROFILE_DIR + "/scroll_on_output") or self.defaults['scroll_on_output'])

    # FIXME: Pull in the colors, cursor, bell, scrollback, bold, scroll, etc settings

  def on_gconf_notification (self, client, cnxn_id, entry, what):
    self.reconfigure_vte ()

  def on_vte_button_press (self, term, event):
    # Left mouse button should transfer focus to this vte widget
    if event.button == 1:
      self._vte.grab_focus ()
      return True

    if event.button == 3:
      return True

  def on_vte_notify_enter (self, term, event):
    print "Grabbing focus"
    term.grab_focus ()
    # FIXME: Should we eat this event or let it propagate further?
    return False

  def get_box (self):
    return self._box

class Terminator:
  def __init__ (self):
    self.gconf_client = gconf.client_get_default ()

    self.window = gtk.Window ()
    self.icon = self.window.render_icon (gtk.STOCK_DIALOG_INFO, gtk.ICON_SIZE_BUTTON)
    self.window.set_icon (self.icon)
    self.window.connect ("delete_event", self.on_delete_event)
    self.window.connect ("destroy", self.on_destroy_event)

    self.focus = self.gconf_client.get_string ("/apps/metacity/general/focus_mode")

  def on_delete_event (self, widget, event, data=None):
    # FIXME: return True if we want to keep the window open (ie a "Do you want to quit" requester)
    return False

  def on_destroy_event (self, widget, data=None):
    gtk.main_quit ()

if __name__ == '__main__':
  term = Terminator ()

  t1 = TerminatorTerm (term)
  t2 = TerminatorTerm (term)
  t3 = TerminatorTerm (term)
  t4 = TerminatorTerm (term)

  pane1 = gtk.HPaned ()
  pane1.add1 (t1.get_box ())
  pane1.add2 (t2.get_box ())

  pane2 = gtk.HPaned ()
  pane2.add1 (t3.get_box ())
  pane2.add2 (t4.get_box ())

  vpane = gtk.VPaned ()
  vpane.add1 (pane1)
  vpane.add2 (pane2)

  term.window.add (vpane)
  term.window.show_all ()

  gtk.main ()

