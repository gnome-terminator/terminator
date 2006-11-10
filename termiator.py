#!/usr/bin/python
import sys
import string
import getopt
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

  def __init__ (self):
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

    self._vte.connect ("button-press-event", self.on_vte_button_press)
    #self._vte.connect ("popup-menu", self.on_vte_popup_menu)
    self._vte.connect ("child-exited", lambda term: term.fork_command ())

    self._vte.fork_command ()

  def reconfigure_vte (self):
    self._vte.set_emulation (self.defaults['emulation'])

    if self.gconf_client.get_bool (self.GCONF_PROFILE_DIR + "/use_system_font"):
      font_name = (self.gconf_client.get_string ("/desktop/gnome/interface/monospace_font_name") or self.defaults['font_name'])
    else:
      font_name = (self.gconf_client.get_string (self.GCONF_PROFILE_DIR + "/font") or self.defaults['font_name'])

    try:
      self._vte.set_font (pango.FontDescription (font_name))
    except:
      pass

    # FIXME: Pull in the colors, cursor, bell, scrollback, bold, scroll, etc settings

  def on_gconf_notification (self, client, cnxn_id, entry, what):
    self.reconfigure_vte ()

  def on_vte_button_press (self, term, event):
    if event.button == 1:
      print "Left mouse button"
      self._vte.grab_focus ()
      return True
    if event.button == 3:
      return True

  def get_box (self):
    return self._box

class Terminator:
  def __init__ (self):
    self.window = gtk.Window ()
    self.window.connect ("delete_event", self.on_delete_event)
    self.window.connect ("destroy", self.on_destroy_event)

  def on_delete_event (self, widget, event, data=None):
    # FIXME: return True if we want to keep the window open (ie a "Do you want to quit" requester)
    return False

  def on_destroy_event (self, widget, data=None):
    gtk.main_quit ()

if __name__ == '__main__':
  term = Terminator ()

  t1 = TerminatorTerm ()
  t2 = TerminatorTerm ()
  t3 = TerminatorTerm ()
  t4 = TerminatorTerm ()

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

