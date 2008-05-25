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
import os, sys, re

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
    for source in self.sources:
      dbg ("TConfig: Looking for: '%s' in '%s'"%(keyname, source.type))
      try:
        val = getattr (source, keyname)
        dbg (" TConfig: got: '%s' from a '%s'"%(val, source.type))
        return (val)
      except:
        pass

    dbg (" TConfig: Out of sources")
    raise (AttributeError)

class TerminatorConfValuestore:
  type = "Base"
  values = {}
  reconfigure_callback = None

  # Our settings
  defaults = {
    'gt_dir'                : '/apps/gnome-terminal',
    'profile_dir'           : '/apps/gnome-terminal/profiles',
    'titlebars'             : True,
    'titletips'             : False,
    'allow_bold'            : True,
    'silent_bell'           : True,
    'background_color'      : '#000000',
    'background_darkness'   : 0.5,
    'background_type'       : 'solid',
    'background_image'      : '',
    'backspace_binding'     : 'ascii-del',
    'delete_binding'        : 'delete-sequence',
    'cursor_blink'          : False,
    'emulation'             : 'xterm',
    'font'                  : 'Serif 10',
    'foreground_color'      : '#AAAAAA',
    'scrollbar_position'    : "right",
    'scroll_background'     : True,
    'scroll_on_keystroke'   : False,
    'scroll_on_output'      : False,
    'scrollback_lines'      : 100,
    'focus'                 : 'sloppy',
    'exit_action'           : 'close',
    'palette'               : '#000000000000:#CDCD00000000:#0000CDCD0000:#CDCDCDCD0000:#30BF30BFA38E:#A53C212FA53C:#0000CDCDCDCD:#FAFAEBEBD7D7:#404040404040:#FFFF00000000:#0000FFFF0000:#FFFFFFFF0000:#00000000FFFF:#FFFF0000FFFF:#0000FFFFFFFF:#FFFFFFFFFFFF',
    'word_chars'            : '-A-Za-z0-9,./?%&#:_',
    'mouse_autohide'        : True,
    'update_records'        : True,
    'login_shell'           : False,
    'use_custom_command'    : False,
    'custom_command'        : '',
    'use_system_font'       : True,
    'use_theme_colors'      : True,
    'http_proxy'            : '',
    'ignore_hosts'          : ['localhost','127.0.0.0/8','*.local'],
    'encoding'              : 'UTF-8',
    'active_encodings'      : ['UTF-8', 'ISO-8859-1'],
    'background_image'      : '',
    'extreme_tabs'          : False,
  }

  def __getattr__ (self, keyname):
    if self.values.has_key (keyname):
      dbg ("Returning '%s'"%keyname)
      return self.values[keyname]
    else:
      dbg ("Failed to find '%s'"%keyname)
      raise (AttributeError)

class TerminatorConfValuestoreDefault (TerminatorConfValuestore):
  def __init__ (self):
    self.type = "Default"
    self.values = self.defaults

class TerminatorConfValuestoreRC (TerminatorConfValuestore):
  rcfilename = ""
  splitter = re.compile("\s*=\s*")
  #FIXME: use inotify to watch the rc, split __init__ into a parsing function
  #       that can be re-used when rc changes.
  def __init__ (self):
    self.type = "RCFile"
    self.rcfilename = os.path.join(os.path.expanduser("~"), ".terminatorrc")
    if os.path.exists (self.rcfilename):
      rcfile = open (self.rcfilename)
      rc = rcfile.readlines ()
      rcfile.close ()

      for item in rc:
        try:
          item = item.strip ()
          if item and item[0] != '#':
            (key, value) = self.splitter.split (item)

            # Check if this is actually a key we care about
            if not self.defaults.has_key (key):
              raise AttributeError;

            deftype = self.defaults[key].__class__.__name__
            if deftype == 'bool':
              if value.lower () == 'true':
                self.values[key] = True
              elif value.lower () == 'false':
                self.values[key] = False
              else:
                raise AttributeError
            elif deftype == 'int':
              self.values[key] = int (value)
            elif deftype == 'float':
              self.values[key] = float (value)
            elif deftype == 'list':
              print >> sys.stderr, _("Reading list values from .terminatorrc is not currently supported")
              raise ValueError
            else:
              self.values[key] = value

            dbg (" VS_RCFile: Set value '%s' to '%s'"%(key, self.values[key]))
        except Exception, e:
          dbg (" VS_RCFile: %s Exception handling: %s" % (type(e), item))
          pass

class TerminatorConfValuestoreGConf (TerminatorConfValuestore):
  profile = ""
  client = None
  cache = {}

  def __init__ (self, profile = None):
    self.type = "GConf"

    import gconf

    self.client = gconf.client_get_default ()

    # Grab a couple of values from base class to avoid recursing with our __getattr__
    self._gt_dir = self.defaults['gt_dir']
    self._profile_dir = self.defaults['profile_dir']

    if not profile:
      profile = self.client.get_string (self._gt_dir + '/global/default_profile')
    profiles = self.client.get_list (self._gt_dir + '/global/profile_list','string')

    #set up the active encoding list
    self.active_encodings = self.client.get_list (self._gt_dir + '/global/active_encodings', 'string')
    
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
      dbg ("No profile found, deleting __getattr__")
      del (self.__getattr__)

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
    dbg (" VSGConf: gconf changed, callback is: %s"%self.reconfigure_callback)
    if self.reconfigure_callback:
      self.reconfigure_callback ()

  def __getattr__ (self, key = ""):
    if self.cache.has_key (key):
      dbg (" VSGConf: returning cached value: %s"%self.cache[key])
      return (self.cache[key])

    ret = None
    value = None

    dbg (' VSGConf: preparing: %s/%s'%(self.profile, key))

    # FIXME: Ugly special cases we should look to fix in some other way.
    if key == 'font' and self.use_system_font:
      value = self.client.get ('/desktop/gnome/interface/monospace_font_name')
    elif key == 'focus':
      value = self.client.get ('/apps/metacity/general/focus_mode')
    elif key == 'http_proxy':
      if self.client.get_bool ('/system/http_proxy/use_http_proxy'):
        dbg ('HACK: Mangling http_proxy')

        if self.client.get_bool ('use_authentication'):
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
    else:
      value = self.client.get ('%s/%s'%(self.profile, key))

    if value:
      funcname = "get_" + self.defaults[key].__class__.__name__
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
  #print foo.blimnle

  # http_proxy is a value that is allowed to not exist
  print "final proxy: %s"%foo.http_proxy
