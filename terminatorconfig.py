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

# import standard python libs
import os, sys

# import unix-lib
import pwd

# set this to true to enable debugging output
debug = True

def dbg (log = ""):
  if debug:
    print >> sys.stderr, log

class TerminatorConfig:
  callback = None
  sources = []

  def __init__ (self, sources = []):
    for source in sources:
      if isinstance(source, TerminatorConfValuestore):
        self.sources.append (source)

    # We always add a default valuestore last so no valid config item ever goes unset
    source = TerminatorConfValuestoreDefault ()
    self.sources.append (source)
    
  def __getattr__ (self, keyname):
    dbg ("Config: Looking for: %s"%keyname)
    for source in self.sources:
      try:
        val = getattr (source, keyname)
        dbg ("Config: got: %s from a %s"%(val, source.type))
        return (val)
      except:
        dbg ("Config: no value found in %s."%source.type)
        pass
    dbg ("Config: Out of sources")
    raise (AttributeError)

class TerminatorConfValuestore:
  type = "Base"
  values = {}
  reconfigure_callback = None

  # Our settings
  # FIXME: Is it acceptable to not explicitly store the type, but
  #         instead infer it from defaults[key].__class__.__name__
  defaults = {
    'gt_dir'                : [str, '/apps/gnome-terminal'],
    'profile_dir'           : [str, '/apps/gnome-terminal/profiles'],
    'titlebars'             : [bool, True],
    'titletips'             : [bool, False],
    'allow_bold'            : [bool, False],
    'silent_bell'           : [bool, True],
    'background_color'      : [str, '#000000'],
    'background_darkness'   : [float, 0.5],
    'background_type'       : [str, 'solid'],
    'backspace_binding'     : [str, 'ascii-del'],
    'delete_binding'        : [str, 'delete-sequence'],
    'cursor_blink'          : [bool, False],
    'emulation'             : [str, 'xterm'],
    'font'                  : [str, 'Serif 10'],
    'foreground_color'      : [str, '#AAAAAA'],
    'scrollbar_position'    : [str, "right"],
    'scroll_background'     : [bool, True],
    'scroll_on_keystroke'   : [bool, False],
    'scroll_on_output'      : [bool, False],
    'scrollback_lines'      : [int, 100],
    'focus'                 : [str, 'sloppy'],
    'exit_action'           : [str, 'close'],
    'palette'               : [str, '#000000000000:#CDCD00000000:#0000CDCD0000:#CDCDCDCD0000:#30BF30BFA38E:#A53C212FA53C:#0000CDCDCDCD:#FAFAEBEBD7D7:#404040404040:#FFFF00000000:#0000FFFF0000:#FFFFFFFF0000:#00000000FFFF:#FFFF0000FFFF:#0000FFFFFFFF:#FFFFFFFFFFFF'],
    'word_chars'            : [str, '-A-Za-z0-9,./?%&#:_'],
    'mouse_autohide'        : [bool, True],
    'update_records'        : [bool, True],
    'login_shell'           : [bool, False],
    'use_custom_command'    : [bool, False],
    'custom_command'        : [str, ''],
    'use_system_font'       : [bool, True],
    'use_theme_colors'      : [bool, True],
  }

  def __getattr__ (self, keyname):
    if self.values.has_key (keyname):
      return self.values[keyname][1]
    else:
      raise (AttributeError)

class TerminatorConfValuestoreDefault (TerminatorConfValuestore):
  def __init__ (self):
    self.type = "Default"
    self.values = self.defaults

class TerminatorConfValuestoreRC (TerminatorConfValuestore):
  rcfilename = ""
  #FIXME: use inotify to watch the rc, split __init__ into a parsing function
  #       that can be re-used when rc changes.
  def __init__ (self):
    self.type = "RCFile"
    self.rcfilename = pwd.getpwuid (os.getuid ())[5] + "/.terminatorrc"
    if os.path.exists (self.rcfilename):
      rcfile = open (self.rcfilename)
      rc = rcfile.readlines ()
      rcfile.close ()

      for item in rc:
        try:
          item = item.strip ()
          if item and item[0] != '#':
            (key, value) = item.split ("=")
            dbg ("VS_RCFile: Setting value %s to %s"%(key, value))
            self.values[key] = [self.defaults[key][0], self.defaults[key][0](value)]
        except:
          pass

class TerminatorConfValuestoreGConf (TerminatorConfValuestore):
  profile = ""
  client = None

  def __init__ (self, profile = None):
    self.type = "GConf"

    import gconf

    self.client = gconf.client_get_default ()

    # Grab a couple of values from base class to avoid recursing with our __getattr__
    self._gt_dir = self.defaults['gt_dir'][1]
    self._profile_dir = self.defaults['profile_dir'][1]

    if not profile:
      profile = self.client.get_string (self._gt_dir + '/global/default_profile')
    profiles = self.client.get_list (self._gt_dir + '/global/profile_list','string')

    if profile in profiles:
      dbg ("VSGConf: Found profile '%s' in profile_list"%profile)
      self.profile = '%s/%s'%(self._profile_dir, profile)
    elif "Default" in profiles:
      dbg ("VSGConf: profile '%s' not found, but 'Default' exists"%profile)
      self.profile = '%s/%s'%(self._profile_dir, "Default")
    else:
      # We're a bit stuck, there is no profile in the list
      # FIXME: Find a better way to handle this than setting a non-profile
      dbg ("No profile found, deleting __getattr__")
      del (self.__getattr__)

    self.client.add_dir (self.profile, gconf.CLIENT_PRELOAD_RECURSIVE)
    if self.on_gconf_notify:
      self.client.notify_add (self.profile, self.on_gconf_notify)

    self.client.add_dir ('/apps/metacity/general', gconf.CLIENT_PRELOAD_RECURSIVE)
    self.client.notify_add ('/apps/metacity/general/focus_mode', self.on_gconf_notify)
    # FIXME: Do we need to watch more non-profile stuff here?

  def set_reconfigure_callback (self, function):
    dbg ("Config: setting callback to: %s"%function)
    self.reconfigure_callback = function
    return (True)

  def on_gconf_notify (self, client, cnxn_id, entry, what):
    dbg ("VSGConf: gconf changed, callback is: %s"%self.reconfigure_callback)
    if self.reconfigure_callback:
      self.reconfigure_callback ()

  def __getattr__ (self, key = ""):
    ret = None

    dbg ('VSGConf: preparing: %s/%s'%(self.profile, key))
    
    if key == 'font':
      if self.use_system_font:
        value = self.client.get ('/desktop/gnome/interface/monospace_font_name')
    else:
      value = self.client.get ('%s/%s'%(self.profile, key))
    dbg ('VSGConf: getting: %s'%value)
    if value:
      funcname = "get_" + self.defaults[key][0].__name__
      # Special case for str
      if funcname == "get_str":
        funcname = "get_string"
      typefunc = getattr (value, funcname)
      ret = typefunc ()

      return (ret)
    else:
      raise (AttributeError)

if __name__ == '__main__':

  stores = []
  stores.append (TerminatorConfValuestoreRC ())

  try:
    import gconf
    stores.append (TerminatorConfValuestoreGConf ())
  except:
    pass

  foo = TerminatorConfig (stores)

  ## cmsj: this is my testing ground
  ##       ensure that font is set in the Default gconf profile
  ##       set titlebars in the RC file
  ##       remove titletips from gconf/RC
  ##       do not define blimnle in any way

  # This should come from gconf (it's set by gnome-terminal)
  print foo.font

  # This should come from RC
  print foo.titlebars

  # This should come from defaults
  print foo.titletips

  # This should raise AttributeError
  print foo.blimnle
