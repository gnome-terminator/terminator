#!/usr/bin/python
#    TerminatorConfig - layered config classes
#    Copyright (C) 2006-2008  cmsj@tenshu.net
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, version 2 only.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

"""TerminatorConfig by Chris Jones <cmsj@tenshu.net>

The config scheme works in layers, with defaults at the base,
and a simple/flexible class which can be placed over the top
in multiple layers. This was written for Terminator, but
could be used generically. Its original use is to guarantee
default values for any config item, while allowing them to be
overridden by at least two other stores of configuration values.
Those being gconf and a plain config file.
In addition to the value, the default layer must also provide
the datatype (str, int, float and bool are currently supported).
values are found as attributes of the TerminatorConfig object.
Trying to read a value that doesn't exist will raise an 
AttributeError. This is by design. If you want to look something 
up, set a default for it first."""

import os, platform, sys, re
import pwd
import gtk, pango

try:
  import gconf
except ImportError:
  gconf = None

# set this to true to enable debugging output
# These should be moved somewhere better.
debug = False

def dbg (log = ""):
  """Print a message if debugging is enabled"""
  if debug:
    print >> sys.stderr, log

def err (log = ""):
  """Print an error message"""
  print >> sys.stderr, log

from configfile import ConfigFile, ParsedWithErrors

Defaults = {
  'gt_dir'                : '/apps/gnome-terminal',
  'profile_dir'           : '/apps/gnome-terminal/profiles',
  'titlebars'             : True,
  'zoomedtitlebar'        : True,
  'titletips'             : False,
  'allow_bold'            : True,
  'audible_bell'          : False,
  'visible_bell'          : True,
  'urgent_bell'           : False,
  'background_color'      : '#000000',
  'background_darkness'   : 0.5,
  'background_type'       : 'solid',
  'background_image'      : '',
  'backspace_binding'     : 'ascii-del',
  'delete_binding'        : 'delete-sequence',
  'cursor_blink'          : True,
  'cursor_shape'          : 'block',
  'cursor_color'          : '',
  'emulation'             : 'xterm',
  'font'                  : 'Mono 10',
  'foreground_color'      : '#AAAAAA',
  'scrollbar_position'    : "right",
  'scroll_background'     : True,
  'scroll_on_keystroke'   : True,
  'scroll_on_output'      : True,
  'scrollback_lines'      : 500,
  'focus'                 : 'click',
  'exit_action'           : 'close',
  'palette'               : '#000000000000:#CDCD00000000:#0000CDCD0000:#CDCDCDCD0000:#30BF30BFA38E:#A53C212FA53C:#0000CDCDCDCD:#FAFAEBEBD7D7:#404040404040:#FFFF00000000:#0000FFFF0000:#FFFFFFFF0000:#00000000FFFF:#FFFF0000FFFF:#0000FFFFFFFF:#FFFFFFFFFFFF',
  'word_chars'            : '-A-Za-z0-9,./?%&#:_',
  'mouse_autohide'        : True,
  'update_records'        : True,
  'login_shell'           : False,
  'use_custom_command'    : False,
  'custom_command'        : '',
  'use_system_font'       : True,
  'use_theme_colors'      : False,
  'http_proxy'            : '',
  'ignore_hosts'          : ['localhost','127.0.0.0/8','*.local'],
  'encoding'              : 'UTF-8',
  'active_encodings'      : ['UTF-8', 'ISO-8859-1'],
  'extreme_tabs'          : False,
  'fullscreen'            : False,
  'borderless'            : False,
  'maximise'              : False,
  'hidden'                : False,
  'handle_size'           : -1,
  'focus_on_close'        : 'auto',
  'f11_modifier'          : False,
  'force_no_bell'         : False,
  'cycle_term_tab'        : True,
  'copy_on_selection'     : False,
  'close_button_on_tab'   : True,
  'tab_position'          : 'top',
  'enable_real_transparency'  : False,
  'try_posix_regexp'      : platform.system() != 'Linux',
  'hide_tabbar'           : False,
  'scroll_tabbar'         : False,
  'alternate_screen_scroll': True,
  'keybindings'           : {
    'zoom_in'          : '<Ctrl>plus',
    'zoom_out'         : '<Ctrl>minus',
    'zoom_normal'      : '<Ctrl>0',
    'new_root_tab'     : '<Ctrl><Shift><Alt>T',
    'new_tab'          : '<Ctrl><Shift>T',
    'go_next'          : ('<Ctrl><Shift>N','<Ctrl>Tab'),
    'go_prev'          : ('<Ctrl><Shift>P','<Ctrl><Shift>Tab'),
    'go_up'            : '<Alt>Up',
    'go_down'          : '<Alt>Down',
    'go_left'          : '<Alt>Left',
    'go_right'         : '<Alt>Right',
    'split_horiz'      : '<Ctrl><Shift>O',
    'split_vert'       : '<Ctrl><Shift>E',
    'close_term'       : '<Ctrl><Shift>W',
    'copy'             : '<Ctrl><Shift>C',
    'paste'            : '<Ctrl><Shift>V',
    'toggle_scrollbar' : '<Ctrl><Shift>S',
    'search'           : '<Ctrl><Shift>F',
    'close_window'     : '<Ctrl><Shift>Q',
    'resize_up'        : '<Ctrl><Shift>Up',
    'resize_down'      : '<Ctrl><Shift>Down',
    'resize_left'      : '<Ctrl><Shift>Left',
    'resize_right'     : '<Ctrl><Shift>Right',
    'move_tab_right'   : '<Ctrl><Shift>Page_Down',
    'move_tab_left'    : '<Ctrl><Shift>Page_Up',
    'toggle_zoom'      : '<Ctrl><Shift>X',
    'scaled_zoom'      : '<Ctrl><Shift>Z',
    'next_tab'         : '<Ctrl>Page_Down',
    'prev_tab'         : '<Ctrl>Page_Up',
    'switch_to_tab_1'  : None,
    'switch_to_tab_2'  : None,
    'switch_to_tab_3'  : None,
    'switch_to_tab_4'  : None,
    'switch_to_tab_5'  : None,
    'switch_to_tab_6'  : None,
    'switch_to_tab_7'  : None,
    'switch_to_tab_8'  : None,
    'switch_to_tab_9'  : None,
    'switch_to_tab_10' : None,
    'full_screen'      : 'F11',
    'reset'            : '<Ctrl><Shift>R',
    'reset_clear'      : '<Ctrl><Shift>G',
    'hide_window'      : '<Ctrl><Shift><Alt>a',
  }
}


class TerminatorConfig:
  """This class is used as the base point of the config system"""
  callback = None
  sources = None
  _keys = None

  def __init__ (self, sources):
    self.sources = []

    for source in sources:
      if isinstance(source, TerminatorConfValuestore):
        self.sources.append (source)

    # We always add a default valuestore last so no valid config item ever goes unset
    source = TerminatorConfValuestoreDefault ()
    self.sources.append (source)

  def _merge_keybindings(self):
    if self._keys:
      return self._keys

    self._keys = {}
    for source in reversed(self.sources):
      try:
        val = source['keybindings']
        self._keys.update(val)
      except:
        pass
    return self._keys

  keybindings = property(_merge_keybindings)

  def __getattr__ (self, keyname):
    for source in self.sources:
      dbg ("TConfig: Looking for: '%s' in '%s'"%(keyname, source.type))
      try:
        val = source[keyname]
        dbg (" TConfig: got: '%s' from a '%s'"%(val, source.type))
        return (val)
      except KeyError:
        pass

    dbg (" TConfig: Out of sources")
    raise (AttributeError)

class TerminatorConfValuestore:
  type = "Base"
  values = None
  reconfigure_callback = None

  def __init__ (self):
    self.values = {}

  # Our settings
  def __getitem__ (self, keyname):
    if self.values.has_key (keyname):
      value = self.values[keyname]
      dbg ("Returning '%s':'%s'"%(keyname, value))
      return value
    else:
      dbg ("Failed to find '%s'"%keyname)
      raise (KeyError)

class TerminatorConfValuestoreDefault (TerminatorConfValuestore):
  def __init__ (self):
    TerminatorConfValuestore.__init__ (self)
    self.type = "Default"
    self.values = Defaults

class TerminatorConfValuestoreRC (TerminatorConfValuestore):
  rcfilename = ""
  type = "RCFile"
  def __init__ (self):
    TerminatorConfValuestore.__init__ (self)
    try:
      directory = os.environ['XDG_CONFIG_HOME']
    except KeyError, e:
      dbg(" VS_RCFile: Environment variable XDG_CONFIG_HOME not found. defaulting to ~/.config")
      directory = os.path.join (os.path.expanduser("~"), ".config")
    self.rcfilename = os.path.join(directory, "terminator/config")
    dbg(" VS_RCFile: config file located at %s" % self.rcfilename)
    self.call_parser(True)

  def set_reconfigure_callback (self, function):
    dbg (" VS_RCFile: setting callback to: %s"%function)
    self.reconfigure_callback = function
    return (True)

  def call_parser (self, is_init = False):
    dbg (" VS_RCFile: parsing config file")
    try:
      ini = ConfigFile(self.rcfilename, self._rc_set_callback())
      ini.parse()
    except IOError, e:
      dbg (" VS_RCFile: unable to open %s (%r)" % (self.rcfilename, e))
    except ParsedWithErrors, e:
      # We don't really want to produce an error dialog every run
      if not is_init:
        pass
      msg = _("""<big><b>Configuration error</b></big>

Errors were encountered while parsing terminator_config(5) file:

  <b>%s</b>

%d line(s) have been ignored.""") % (self.rcfilename, len(e.errors))

      dialog = gtk.Dialog(_("Configuration error"), None, gtk.DIALOG_MODAL,
                          (gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
      dialog.set_has_separator(False)
      dialog.set_resizable(False)

      image = gtk.image_new_from_stock(gtk.STOCK_DIALOG_WARNING, gtk.ICON_SIZE_DIALOG)
      image.set_alignment (0.5, 0)
      dmsg = gtk.Label(msg)
      dmsg.set_use_markup(True)
      dmsg.set_alignment(0, 0.5)

      textbuff = gtk.TextBuffer()
      textbuff.set_text("\n".join(map(lambda e: str(e), e.errors)))
      textview = gtk.TextView(textbuff)
      textview.set_editable(False)

      textview.modify_font(pango.FontDescription(Defaults['font']))
      textscroll = gtk.ScrolledWindow()
      textscroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
      textscroll.add(textview)
      # This should be scaled with the size of the text and font
      textscroll.set_size_request(600, 200)

      root = gtk.VBox()
      root.pack_start(dmsg, padding = 6)
      root.pack_start(textscroll, padding = 6)

      box = gtk.HBox()
      box.pack_start (image, False, False, 6)
      box.pack_start (root, False, False, 6)
      dialog.vbox.pack_start (box, False, False, 12)
      dialog.show_all()

      dialog.run()
      dialog.destroy()

    dbg("ConfigFile settings are: %r" % self.values)

  def _rc_set_callback(self):
    def callback(sections, key, value):
      dbg("Setting: section=%r with %r => %r" % (sections, key, value))
      section = None
      if len(sections) > 0:
        section = sections[0]
      if section is None:
        # handle some deprecated configs
        if key == 'silent_bell':
          err ("silent_bell config option is deprecated, for the new bell related config options, see: man terminator_config")
          if value:
            self.values['audible_bell'] = False
          else:
            self.values['audible_bell'] = True
          key = 'visible_bell'
            
        if not Defaults.has_key (key):
          raise ValueError("Unknown configuration option %r" % key)
        deftype = Defaults[key].__class__.__name__
        if key.endswith('_color'):
          try:
            gtk.gdk.color_parse(value)
            self.values[key] = value
          except ValueError:
            raise ValueError(_("Setting %r value %r not a valid colour; ignoring") % (key, value))
        elif key == 'tab_position':
          if value.lower() in ('top', 'left', 'bottom', 'right'):
            self.values[key] = value.lower()
          else:
            raise ValueError(_("%s must be one of: top, left, right, bottom") % key)
        elif deftype == 'bool':
          if value.lower () in ('true', 'yes', 'on'):
            self.values[key] = True
          elif value.lower () in ('false', 'no', 'off'):
            self.values[key] = False
          else:
            raise ValueError(_("Boolean setting %s expecting one of: yes, no, true, false, on, off") % key)
        elif deftype == 'int':
          self.values[key] = int (value)
        elif deftype == 'float':
          self.values[key] = float (value)
        elif deftype == 'list':
          raise ValueError(_("Reading list values from terminator_config(5) is not currently supported"))
        elif deftype == 'dict':
          if type(value) != dict:
            raise ValueError(_("Setting %r should be a section name") % key)
          self.values[key] = value
        else:
          self.values[key] = value

        dbg (" VS_RCFile: Set value %r to %r" % (key, self.values[key]))
      elif section == 'keybindings':
        self.values.setdefault(section, {})
        if not Defaults[section].has_key(key):
          raise ValueError("Keybinding name %r is unknown" % key)
        else:
          self.values[section][key] = value
      else:
        raise ValueError("Section name %r is unknown" % section)
    return callback

class TerminatorConfValuestoreGConf (TerminatorConfValuestore):
  profile = ""
  client = None
  cache = None
  notifies = None

  def __init__ (self, profileName = None):
    TerminatorConfValuestore.__init__ (self)
    self.type = "GConf"
    self.inactive = False
    self.cache = {}
    self.notifies = {}

    import gconf

    self.client = gconf.client_get_default ()

    # Grab a couple of values from base class to avoid recursing with our __getattr__
    self._gt_dir = Defaults['gt_dir']
    self._profile_dir = Defaults['profile_dir']

    dbg ('VSGConf: Profile bet on is: "%s"'%profileName)
    profiles = self.client.get_list (self._gt_dir + '/global/profile_list','string')
    dbg ('VSGConf: Found profiles: "%s"'%profiles)

    dbg ('VSGConf: Profile requested is: "%s"'%profileName)
    if not profileName:
      profile = self.client.get_string (self._gt_dir + '/global/default_profile')
    else:
      profile = profileName
      # In newer gnome-terminal, the profile keys are named Profile0/1 etc.
      # We have to match using visible_name instead
      for p in profiles:
        profileName2 = self.client.get_string (
          self._profile_dir + '/' + p + '/visible_name')
        if profileName == profileName2:
          profile = p

    #need to handle the list of Gconf.value
    if profile in profiles:
      dbg (" VSGConf: Found profile '%s' in profile_list"%profile)
      self.profile = '%s/%s'%(self._profile_dir, profile)
    elif "Default" in profiles:
      dbg (" VSGConf: profile '%s' not found, but 'Default' exists"%profile)
      self.profile = '%s/%s'%(self._profile_dir, "Default")
    else:
      # We're a bit stuck, there is no profile in the list
      # FIXME: Find a better way to handle this than setting a non-profile
      dbg ("VSGConf: No profile found, marking inactive")
      self.inactive = True
      return

    #set up the active encoding list
    self.active_encodings = self.client.get_list (self._gt_dir + '/global/active_encodings', 'string')
    
    self.client.add_dir (self.profile, gconf.CLIENT_PRELOAD_RECURSIVE)
    if self.on_gconf_notify:
      self.client.notify_add (self.profile, self.on_gconf_notify)

    self.client.add_dir ('/apps/metacity/general', gconf.CLIENT_PRELOAD_RECURSIVE)
    self.client.notify_add ('/apps/metacity/general/focus_mode', self.on_gconf_notify)
    self.client.add_dir ('/desktop/gnome/interface', gconf.CLIENT_PRELOAD_RECURSIVE)
    self.client.notify_add ('/desktop/gnome/interface/monospace_font_name', self.on_gconf_notify)
    # FIXME: Do we need to watch more non-profile stuff here?

  def set_reconfigure_callback (self, function):
    dbg (" VSConf: setting callback to: %s"%function)
    self.reconfigure_callback = function
    return (True)

  def on_gconf_notify (self, client, cnxn_id, entry, what):
    dbg (" VSGConf: invalidating cache")
    self.cache = {}
    dbg (" VSGConf: gconf changed, may run a callback. %s, %s"%(entry.key, entry.value))
    if entry.key[-12:] == 'visible_name':
      dbg (" VSGConf: only a visible_name change, ignoring")
      return False
    if self.reconfigure_callback:
      dbg (" VSGConf: callback is: %s"%self.reconfigure_callback)
      self.reconfigure_callback ()

  def __getitem__ (self, key = ""):
    if self.inactive:
      raise KeyError

    if self.cache.has_key (key):
      dbg (" VSGConf: returning cached value: %s"%self.cache[key])
      return (self.cache[key])

    ret = None
    value = None

    dbg (' VSGConf: preparing: %s/%s'%(self.profile, key))

    # FIXME: Ugly special cases we should look to fix in some other way.
    if key == 'font' and self['use_system_font']:
      value = self.client.get ('/desktop/gnome/interface/monospace_font_name')
    elif key == 'focus':
      value = self.client.get ('/apps/metacity/general/focus_mode')
    elif key == 'http_proxy':
      if self.client.get_bool ('/system/http_proxy/use_http_proxy'):
        dbg ('HACK: Mangling http_proxy')

        if self.client.get_bool ('/system/http_proxy/use_authentication'):
          dbg ('HACK: Using proxy authentication')
          value = 'http://%s:%s@%s:%s/'%(
            self.client.get_string ('/system/http_proxy/authentication_user'), 
            self.client.get_string ('/system/http_proxy/authentication_password'), 
            self.client.get_string ('/system/http_proxy/host'), 
            self.client.get_int ('/system/http_proxy/port'))
        else:
          dbg ('HACK: Not using proxy authentication')
          value = 'http://%s:%s/'%(
            self.client.get_string ('/system/http_proxy/host'),
            self.client.get_int ('/system/http_proxy/port'))
    elif key == 'cursor_blink':
      tmp = self.client.get_string('%s/cursor_blink_mode' % self.profile)
      if tmp in ['on', 'off'] and self.notifies.has_key ('cursor_blink'):
        self.client.notify_remove (self.notifies['cursor_blink'])
        del (self.notifies['cursor_blink'])
      if tmp == 'on':
        value = True
      elif tmp == 'off':
        value = False
      elif tmp == 'system':
        value = self.client.get_bool ('/desktop/gnome/interface/cursor_blink')
        self.notifies['cursor_blink'] = self.client.notify_add ('/desktop/gnome/interface/cursor_blink', self.on_gconf_notify)
      else:
        value = self.client.get ('%s/%s'%(self.profile, key))
    else:
      value = self.client.get ('%s/%s'%(self.profile, key))

    if value != None:
      from types import StringType,BooleanType
      if type(value) in [StringType, BooleanType]:
         ret = value
      else:
        funcname = "get_" + Defaults[key].__class__.__name__
        dbg ('  GConf: picked function: %s'%funcname)
        # Special case for str
        if funcname == "get_str":
          funcname = "get_string"
        # Special case for strlist
        if funcname == "get_strlist":
          funcname = "get_list"
        typefunc = getattr (value, funcname)
        ret = typefunc ()

      self.cache[key] = ret
      return (ret)
    else:
      raise (KeyError)

