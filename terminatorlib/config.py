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
>>> config['fullscreen'].__class__.__name__
'bool'
>>>

"""

import platform
import os
import sys
from copy import copy
from configobj.configobj import ConfigObj
from configobj.validate import Validator
from borg import Borg
from factory import Factory
from util import dbg, err, DEBUG, get_config_dir, dict_diff

DEFAULTS = {
        'global_config':   {
            'focus'                 : 'click',
            'enable_real_transparency'  : True,
            'handle_size'           : -1,
            'geometry_hinting'      : True,
            'fullscreen'            : False,
            'borderless'            : False,
            'maximise'              : False,
            'hidden'                : False,
            'tab_position'          : 'top',
            'close_button_on_tab'   : True,
            'hide_tabbar'           : False,
            'scroll_tabbar'         : False,
            'try_posix_regexp'      : platform.system() != 'Linux',
        },
        'keybindings': {
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
            'group_all'        : '<Super>g',
            'ungroup_all'      : '<Super><Shift>g',
            'group_tab'        : '<Super>t',
            'ungroup_tab'      : '<Super><Shift>T',
            'new_window'       : '<Ctrl><Shift>I',
        },
        'profiles': {
            'default':  {
                'titlebars'             : True,
                'zoomedtitlebar'        : True,
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

    def set_profile(self, profile):
        """Set our profile (which usually means change it)"""
        dbg('Config::set_profile: Changing profile to %s' % profile)
        self.profile = profile
        if not self.base.profiles.has_key(profile):
            dbg('Config::set_profile: %s does not exist, creating' % profile)
            self.base.profiles[profile] = copy(DEFAULTS['profiles']['default'])

    def del_profile(self, profile):
        """Delete a profile"""
        if self.base.profiles.has_key(profile):
            del(self.base.profiles[profile])

    def list_profiles(self):
        """List all configured profiles"""
        return(self.base.profiles.keys())

    def save(self):
        """Cause ConfigBase to save our config to file"""
        return(self.base.save())

class ConfigBase(Borg):
    """Class to provide access to our user configuration"""
    loaded = None
    sections = None
    global_config = None
    profiles = None
    keybindings = None
    plugins = None
    layouts = None

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
            if value is None:
                continue
            elif isinstance(value, tuple):
                value = value[0]
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

        parser.write(open(os.path.join(get_config_dir(), 'epic-config'), 'w'))

    def get_item(self, key, profile='default', plugin=None):
        """Look up a configuration item"""
        dbg('ConfigBase::get_item: %s:%s' % (profile, key))
        if self.global_config.has_key(key):
            dbg('ConfigBase::get_item: found in globals: %s' %
                    self.global_config[key])
            return(self.global_config[key])
        elif self.profiles[profile].has_key(key):
            dbg('ConfigBase::get_item: found in profile %s (%s)' % (
                    profile, self.profiles[profile][key]))
            return(self.profiles[profile][key])
        elif key == 'keybindings':
            return(self.keybindings)
        elif plugin is not None and self.plugins[plugin].has_key(key):
            dbg('ConfigBase::get_item: found in plugin %s (%s)' % (
                    plugin, self.plugins[plugin][key]))
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
        elif plugin is not None and self.plugins[plugin].has_key(key):
            self.plugins[plugin][key] = value
        else:
            raise KeyError('ConfigBase::set_item: unknown key %s' % key)

        return(True)

if __name__ == '__main__':
    import sys
    import doctest
    (failed, attempted) = doctest.testmod()
    print "%d/%d tests failed" % (failed, attempted)
    sys.exit(failed)
