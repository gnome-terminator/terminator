#!/usr/bin/python
#    TerminatorConfig - layered config classes
#    Copyright (C) 2006-2010  cmsj@tenshu.net
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, version 2 only.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

"""Terminator by Chris Jones <cmsj@tenshu.net>

Classes relating to configuration

>>> DEFAULTS['global_config']['focus']
'click'
>>> config = Config()
>>> config['focus'] = 'sloppy'
>>> config['focus']
'sloppy'
>>> DEFAULTS['global_config']['focus']
'click'
>>> config2 = Config()
>>> config2['focus']
'sloppy'
>>> config2['focus'] = 'click'
>>> config2['focus']
'click'
>>> config['focus']
'click'
>>> config['geometry_hinting'].__class__.__name__
'bool'
>>> plugintest = {}
>>> plugintest['foo'] = 'bar'
>>> config.plugin_set_config('testplugin', plugintest)
>>> config.plugin_get_config('testplugin')
{'foo': 'bar'}
>>> config.plugin_get('testplugin', 'foo')
'bar'
>>> config.get_profile()
'default'
>>> config.set_profile('my_first_new_testing_profile')
>>> config.get_profile()
'my_first_new_testing_profile'
>>> config.del_profile('my_first_new_testing_profile')
>>> config.get_profile()
'default'
>>> config.list_profiles().__class__.__name__
'list'
>>> config.options_set({})
>>> config.options_get()
{}
>>> 

"""

import platform
import os
import sys
from copy import copy
from configobj.configobj import ConfigObj, flatten_errors
from configobj.validate import Validator
from borg import Borg
from util import dbg, err, DEBUG, get_config_dir, dict_diff

DEFAULTS = {
        'global_config':   {
            'focus'                 : 'click',
            'enable_real_transparency'  : True,
            'handle_size'           : -1,
            'geometry_hinting'      : True,
            'window_state'          : 'normal',
            'borderless'            : False,
            'tab_position'          : 'top',
            'close_button_on_tab'   : True,
            'hide_tabbar'           : False,
            'scroll_tabbar'         : False,
            'try_posix_regexp'      : platform.system() != 'Linux',
            'disabled_plugins'      : ['TestPlugin', 'CustomCommandsMenu'],
        },
        'keybindings': {
            'zoom_in'          : '<Control>plus',
            'zoom_out'         : '<Control>minus',
            'zoom_normal'      : '<Control>0',
            'new_tab'          : '<Shift><Control>t',
            'go_next'          : '<Shift><Control>n', # FIXME: Define ctrl-tab
            'go_prev'          : '<Shift><Control>p', #FIXME: ctrl-shift-tab
            'go_up'            : '<Alt>Up',
            'go_down'          : '<Alt>Down',
            'go_left'          : '<Alt>Left',
            'go_right'         : '<Alt>Right',
            'split_horiz'      : '<Shift><Control>o',
            'split_vert'       : '<Shift><Control>e',
            'close_term'       : '<Shift><Control>w',
            'copy'             : '<Shift><Control>c',
            'paste'            : '<Shift><Control>v',
            'toggle_scrollbar' : '<Shift><Control>s',
            'search'           : '<Shift><Control>f',
            'close_window'     : '<Shift><Control>q',
            'resize_up'        : '<Shift><Control>Up',
            'resize_down'      : '<Shift><Control>Down',
            'resize_left'      : '<Shift><Control>Left',
            'resize_right'     : '<Shift><Control>Right',
            'move_tab_right'   : '<Shift><Control>Page_Down',
            'move_tab_left'    : '<Shift><Control>Page_Up',
            'toggle_zoom'      : '<Shift><Control>x',
            'scaled_zoom'      : '<Shift><Control>z',
            'next_tab'         : '<Control>Page_Down',
            'prev_tab'         : '<Control>Page_Up',
            'switch_to_tab_1'  : '',
            'switch_to_tab_2'  : '',
            'switch_to_tab_3'  : '',
            'switch_to_tab_4'  : '',
            'switch_to_tab_5'  : '',
            'switch_to_tab_6'  : '',
            'switch_to_tab_7'  : '',
            'switch_to_tab_8'  : '',
            'switch_to_tab_9'  : '',
            'switch_to_tab_10' : '',
            'full_screen'      : 'F11',
            'reset'            : '<Shift><Control>r',
            'reset_clear'      : '<Shift><Control>g',
            'hide_window'      : '<Shift><Control><Alt>a',
            'group_all'        : '<Super>g',
            'ungroup_all'      : '<Shift><Super>g',
            'group_tab'        : '<Super>t',
            'ungroup_tab'      : '<Shift><Super>t',
            'new_window'       : '<Shift><Control>i',
        },
        'profiles': {
            'default':  {
                'allow_bold'            : True,
                'audible_bell'          : False,
                'visible_bell'          : True,
                'urgent_bell'           : False,
                'background_color'      : '#000000000000',
                'background_darkness'   : 0.5,
                'background_type'       : 'solid',
                'background_image'      : None,
                'backspace_binding'     : 'ascii-del',
                'delete_binding'        : 'escape-sequence',
                'color_scheme'          : 'grey_on_black',
                'cursor_blink'          : True,
                'cursor_shape'          : 'block',
                'cursor_color'          : '',
                'emulation'             : 'xterm',
                'font'                  : 'Mono 10',
                'foreground_color'      : '#aaaaaaaaaaaa',
                'scrollbar_position'    : "right",
                'scroll_background'     : True,
                'scroll_on_keystroke'   : True,
                'scroll_on_output'      : True,
                'scrollback_lines'      : 500,
                'exit_action'           : 'close',
                'palette'   :'#000000000000:#CDCD00000000:#0000CDCD0000:\
#CDCDCDCD0000:#30BF30BFA38E:#A53C212FA53C:\
#0000CDCDCDCD:#FAFAEBEBD7D7:#404040404040:\
#FFFF00000000:#0000FFFF0000:#FFFFFFFF0000:\
#00000000FFFF:#FFFF0000FFFF:#0000FFFFFFFF:\
#FFFFFFFFFFFF',
                'word_chars'            : '-A-Za-z0-9,./?%&#:_',
                'mouse_autohide'        : True,
                'update_records'        : True,
                'login_shell'           : False,
                'use_custom_command'    : False,
                'custom_command'        : '',
                'use_system_font'       : True,
                'use_theme_colors'      : False,
                'encoding'              : 'UTF-8',
                'active_encodings'      : ['UTF-8', 'ISO-8859-1'],
                'focus_on_close'        : 'auto',
                'force_no_bell'         : False,
                'cycle_term_tab'        : True,
                'copy_on_selection'     : False,
                'title_tx_txt_color'    : '#FFFFFF',
                'title_tx_bg_color'     : '#C80003',
                'title_rx_txt_color'    : '#FFFFFF',
                'title_rx_bg_color'     : '#0076C9',
                'title_ia_txt_color'    : '#000000',
                'title_ia_bg_color'     : '#C0BEBF',
                'alternate_screen_scroll': True,
                'split_to_group'        : False,
                'autoclean_groups'      : True,
                'http_proxy'            : '',
                'ignore_hosts'          : ['localhost','127.0.0.0/8','*.local'],
            },
        },
        'layouts': {
        },
        'plugins': {
        },
}

class Config(object):
    """Class to provide a slightly richer config API above ConfigBase"""
    base = None
    profile = None
    
    def __init__(self, profile='default'):
        self.base = ConfigBase()
        self.profile = profile

    def __getitem__(self, key):
        """Look up a configuration item"""
        return(self.base.get_item(key, self.profile))

    def __setitem__(self, key, value):
        """Set a particular configuration item"""
        return(self.base.set_item(key, value, self.profile))

    def get_profile(self):
        """Get our profile"""
        return(self.profile)

    def set_profile(self, profile):
        """Set our profile (which usually means change it)"""
        dbg('Config::set_profile: Changing profile to %s' % profile)
        self.profile = profile
        if not self.base.profiles.has_key(profile):
            dbg('Config::set_profile: %s does not exist, creating' % profile)
            self.base.profiles[profile] = copy(DEFAULTS['profiles']['default'])

    def add_profile(self, profile):
        """Add a new profile"""
        return(self.base.add_profile(profile))

    def del_profile(self, profile):
        """Delete a profile"""
        if profile == self.profile:
            err('Config::del_profile: Deleting in-use profile %s.' % profile)
            self.set_profile('default')
        if self.base.profiles.has_key(profile):
            del(self.base.profiles[profile])

    def rename_profile(self, profile, newname):
        """Rename a profile"""
        if self.base.profiles.has_key(profile):
            self.base.profiles[newname] = self.base.profiles[profile]
            del(self.base.profiles[profile])
            if profile == self.profile:
                self.profile = newname

    def list_profiles(self):
        """List all configured profiles"""
        return(self.base.profiles.keys())

    def save(self):
        """Cause ConfigBase to save our config to file"""
        return(self.base.save())

    def options_set(self, options):
        """Set the command line options"""
        self.base.command_line_options = options

    def options_get(self):
        """Get the command line options"""
        return(self.base.command_line_options)

    def plugin_get(self, pluginname, key):
        """Get a plugin config value"""
        return(self.base.get_item(key, plugin=pluginname))

    def plugin_set(self, pluginname, key, value):
        """Set a plugin config value"""
        return(self.base.set_item(key, value, plugin=pluginname))

    def plugin_get_config(self, plugin):
        """Return a whole config tree for a given plugin"""
        return(self.base.get_plugin(plugin))

    def plugin_set_config(self, plugin, tree):
        """Set a whole config tree for a given plugin"""
        return(self.base.set_plugin(plugin, tree))

class ConfigBase(Borg):
    """Class to provide access to our user configuration"""
    loaded = None
    sections = None
    global_config = None
    profiles = None
    keybindings = None
    plugins = None
    layouts = None
    command_line_options = None

    def __init__(self):
        """Class initialiser"""

        Borg.__init__(self, self.__class__.__name__)

        self.prepare_attributes()
        self.load()

    def prepare_attributes(self):
        """Set up our borg environment"""
        if self.loaded is None:
            self.loaded = False
        if self.sections is None:
            self.sections = ['global_config', 'keybindings', 'profiles',
                             'layouts', 'plugins']
        if self.global_config is None:
            self.global_config = copy(DEFAULTS['global_config'])
        if self.profiles is None:
            self.profiles = {}
            self.profiles['default'] = copy(DEFAULTS['profiles']['default'])
        if self.keybindings is None:
            self.keybindings = copy(DEFAULTS['keybindings'])
        if self.plugins is None:
            self.plugins = {}
        if self.layouts is None:
            self.layouts = copy(DEFAULTS['layouts'])

    def defaults_to_configspec(self):
        """Convert our tree of default values into a ConfigObj validation
        specification"""
        configspecdata = {}

        section = {}
        for key in DEFAULTS['global_config']:
            keytype = DEFAULTS['global_config'][key].__class__.__name__
            value = DEFAULTS['global_config'][key]
            if keytype == 'int':
                keytype = 'integer'
            elif keytype == 'str':
                keytype = 'string'
            elif keytype == 'bool':
                keytype = 'boolean'
            elif keytype == 'list':
                value = 'list(%s)' % ','.join(value)

            keytype = '%s(default=%s)' % (keytype, value)

            section[key] = keytype
        configspecdata['global_config'] = section

        section = {}
        for key in DEFAULTS['keybindings']:
            value = DEFAULTS['keybindings'][key]
            if value is None or value == '':
                continue
            section[key] = 'string(default=%s)' % value
        configspecdata['keybindings'] = section

        section = {}
        for key in DEFAULTS['profiles']['default']:
            keytype = DEFAULTS['profiles']['default'][key].__class__.__name__
            value = DEFAULTS['profiles']['default'][key]
            if keytype == 'int':
                keytype = 'integer'
            elif keytype == 'bool':
                keytype = 'boolean'
            elif keytype == 'str':
                keytype = 'string'
                value = '"%s"' % value
            elif keytype == 'list':
                value = 'list(%s)' % ','.join(value)

            keytype = '%s(default=%s)' % (keytype, value)

            section[key] = keytype
        configspecdata['profiles'] = {}
        configspecdata['profiles']['__many__'] = section

        configspec = ConfigObj(configspecdata)
        if DEBUG == True:
            configspec.write(open('/tmp/terminator_configspec_debug.txt', 'w'))
        return(configspec)

    def load(self):
        """Load configuration data from our various sources"""
        if self.loaded is True:
            dbg('ConfigBase::load: config already loaded')
            return

        filename = os.path.join(get_config_dir(), 'epic-config')
        try:
            configfile = open(filename, 'r')
        except Exception, ex:
            dbg('ConfigBase::load: Unable to open %s (%s)' % (filename, ex))
            return

        configspec = self.defaults_to_configspec()
        parser = ConfigObj(configfile, configspec=configspec)
        validator = Validator()
        result = parser.validate(validator, preserve_errors=True)

        if result != True:
            err('ConfigBase::load: config format is not valid')
            for (section_list, key, other) in flatten_errors(parser, result):
                if key is not None:
                    print('[%s]: %s is invalid' % (','.join(section_list), key))
                else:
                    print ('[%s] missing' % ','.join(section_list))

        for section_name in self.sections:
            dbg('ConfigBase::load: Processing section: %s' % section_name)
            section = getattr(self, section_name)
            if section_name == 'profiles':
                for profile in parser[section_name]:
                    dbg('ConfigBase::load: Processing profile: %s' % profile)
                    if not section.has_key(section_name):
                        section[profile] = copy(DEFAULTS['profiles']['default'])
                    section[profile].update(parser[section_name][profile])
            elif section_name == ['layouts', 'plugins']:
                for part in parser[section_name]:
                    dbg('ConfigBase::load: Processing %s: %s' % (section_name,
                                                                 part))
                    section[part] = parser[section_name][part]
            else:
                try:
                    section.update(parser[section_name])
                except KeyError, ex:
                    dbg('ConfigBase::load: skipping loading missing section %s' %
                            section_name)

        self.loaded = True
        
    def save(self):
        """Save the config to a file"""
        dbg('ConfigBase::save: saving config')
        parser = ConfigObj()
        parser.indent_type = '  '

        for section_name in ['global_config', 'keybindings']:
            dbg('ConfigBase::save: Processing section: %s' % section_name)
            section = getattr(self, section_name)
            parser[section_name] = dict_diff(DEFAULTS[section_name], section)

        parser['profiles'] = {}
        for profile in self.profiles:
            dbg('ConfigBase::save: Processing profile: %s' % profile)
            parser['profiles'][profile] = dict_diff(DEFAULTS['profiles']['default'],
                    self.profiles[profile])

        parser['layouts'] = {}
        for layout in self.layouts:
            dbg('ConfigBase::save: Processing layout: %s' % layout)
            parser['layouts'][layout] = self.layouts[layout]

        parser['plugins'] = {}
        for plugin in self.plugins:
            dbg('ConfigBase::save: Processing plugin: %s' % plugin)
            parser['plugins'][plugin] = self.plugins[plugin]

        config_dir = get_config_dir()
        if not os.path.isdir(config_dir):
            os.makedirs(config_dir)
        try:
            parser.write(open(os.path.join(config_dir, 'epic-config'), 'w'))
        except Exception, ex:
            err('ConfigBase::save: Unable to save config: %s' % ex)

    def get_item(self, key, profile='default', plugin=None):
        """Look up a configuration item"""
        if self.global_config.has_key(key):
            dbg('ConfigBase::get_item: %s found in globals: %s' %
                    (key, self.global_config[key]))
            return(self.global_config[key])
        elif self.profiles[profile].has_key(key):
            dbg('ConfigBase::get_item: %s found in profile %s: %s' % (
                    key, profile, self.profiles[profile][key]))
            return(self.profiles[profile][key])
        elif key == 'keybindings':
            return(self.keybindings)
        elif plugin is not None and self.plugins[plugin].has_key(key):
            dbg('ConfigBase::get_item: %s found in plugin %s: %s' % (
                    key, plugin, self.plugins[plugin][key]))
            return(self.plugins[plugin][key])
        else:
            raise KeyError('ConfigBase::get_item: unknown key %s' % key)

    def set_item(self, key, value, profile='default', plugin=None):
        """Set a configuration item"""
        dbg('ConfigBase::set_item: Setting %s=%s (profile=%s, plugin=%s)' %
                (key, value, profile, plugin))

        if self.global_config.has_key(key):
            self.global_config[key] = value
        elif self.profiles[profile].has_key(key):
            self.profiles[profile][key] = value
        elif key == 'keybindings':
            self.keybindings = value
        elif plugin is not None:
            if not self.plugins.has_key(plugin):
                self.plugins[plugin] = {}
            self.plugins[plugin][key] = value
        else:
            raise KeyError('ConfigBase::set_item: unknown key %s' % key)

        return(True)

    def get_plugin(self, plugin):
        """Return a whole tree for a plugin"""
        if self.plugins.has_key(plugin):
            return(self.plugins[plugin])

    def set_plugin(self, plugin, tree):
        """Set a whole tree for a plugin"""
        self.plugins[plugin] = tree

    def add_profile(self, profile):
        """Add a new profile"""
        if profile in self.profiles:
            return(False)
        self.profiles[profile] = copy(DEFAULTS['profiles']['default'])
        return(True)

if __name__ == '__main__':
    import doctest
    (failed, attempted) = doctest.testmod()
    print "%d/%d tests failed" % (failed, attempted)
    sys.exit(failed)
