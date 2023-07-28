#  TerminatorConfig - layered config classes
#  Copyright (C) 2006-2010  cmsj@tenshu.net
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
>>> config.plugin_get('testplugin', 'foo', 'new')
'bar'
>>> config.plugin_get('testplugin', 'algo')
Traceback (most recent call last):
...
KeyError: 'ConfigBase::get_item: unknown key algo'
>>> config.plugin_get('testplugin', 'algo', 1)
1
>>> config.plugin_get('anothertestplugin', 'algo', 500)
500
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

import os
import shutil
from copy import copy
from configobj import ConfigObj, flatten_errors
from validate import Validator
from .borg import Borg
from .util import dbg, err, DEBUG, get_system_config_dir, get_config_dir, dict_diff, update_config_to_cell_height

from gi.repository import Gio

DEFAULTS = {
        'global_config':   {
            'dbus'                  : True,
            'focus'                 : 'click',
            'handle_size'           : -1,
            'geometry_hinting'      : False,
            'window_state'          : 'normal',
            'borderless'            : False,
            'extra_styling'         : True,
            'tab_position'          : 'top',
            'broadcast_default'     : 'group',
            'close_button_on_tab'   : True,
            'scroll_tabbar'         : False,
            'homogeneous_tabbar'    : True,
            'hide_from_taskbar'     : False,
            'always_on_top'         : False,
            'hide_on_lose_focus'    : False,
            'sticky'                : False,
            'use_custom_url_handler': False,
            'custom_url_handler'    : '',
            'inactive_color_offset': 0.8,
            'inactive_bg_color_offset': 1.0,
            'enabled_plugins'       : ['LaunchpadBugURLHandler',
                                       'LaunchpadCodeURLHandler',
                                       'APTURLHandler'],
            'suppress_multiple_term_dialog': False,
            'always_split_with_profile': False,
            'putty_paste_style'     : False,
            'putty_paste_style_source_clipboard': False,
            'disable_mouse_paste'   : False,
            'smart_copy'            : True,
            'clear_select_on_copy'  : False,
            'cell_width'            : 1.0,
            'cell_height'           : 1.0,
            'case_sensitive'        : True,
            'invert_search'         : False,
            'link_single_click'     : False,
            'title_at_bottom'       : False,
            'detachable_tabs'       : True,

            'new_tab_after_current_tab': False,
        },
        'keybindings': {
            'zoom_in'          : '<Control>plus',
            'zoom_out'         : '<Control>minus',
            'zoom_normal'      : '<Control>0',
			'zoom_in_all'	   : '',
			'zoom_out_all'	   : '',
			'zoom_normal_all'  : '',
            'new_tab'          : '<Shift><Control>t',
            'cycle_next'       : '<Control>Tab',
            'cycle_prev'       : '<Shift><Control>Tab',
            'go_next'          : '<Shift><Control>n',
            'go_prev'          : '<Shift><Control>p',
            'go_up'            : '<Alt>Up',
            'go_down'          : '<Alt>Down',
            'go_left'          : '<Alt>Left',
            'go_right'         : '<Alt>Right',
            'rotate_cw'        : '<Super>r',
            'rotate_ccw'       : '<Super><Shift>r',
            'split_auto'      :  '<Shift><Control>a',
            'split_horiz'      : '<Shift><Control>o',
            'split_vert'       : '<Shift><Control>e',
            'close_term'       : '<Shift><Control>w',
            'copy'             : '<Shift><Control>c',
            'paste'            : '<Shift><Control>v',
            'paste_selection'  : '',
            'toggle_scrollbar' : '<Shift><Control>s',
            'search'           : '<Shift><Control>f',
            'page_up'          : '',
            'page_down'        : '',
            'page_up_half'     : '',
            'page_down_half'   : '',
            'line_up'          : '',
            'line_down'        : '',
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
            'create_group'     : '',
            'group_all'        : '<Super>g',
            'group_all_toggle' : '',
            'ungroup_all'      : '<Shift><Super>g',
            'group_win'        : '',
            'group_win_toggle' : '',
            'ungroup_win'      : '<Shift><Super>w',
            'group_tab'        : '<Super>t',
            'group_tab_toggle' : '',
            'ungroup_tab'      : '<Shift><Super>t',
            'new_window'       : '<Shift><Control>i',
            'new_terminator'   : '<Super>i',
            'broadcast_off'    : '',
            'broadcast_group'  : '',
            'broadcast_all'    : '',
            'insert_number'    : '<Super>1',
            'insert_padded'    : '<Super>0',
            'edit_window_title': '<Control><Alt>w',
            'edit_tab_title'   : '<Control><Alt>a',
            'edit_terminal_title': '<Control><Alt>x',
            'layout_launcher'  : '<Alt>l',
            'next_profile'     : '',
            'previous_profile' : '', 
            'preferences'      : '',
            'preferences_keybindings' : '<Control><Shift>k',
            'help'             : 'F1'
        },
        'profiles': {
            'default':  {
                'allow_bold'            : True,
                'audible_bell'          : False,
                'visible_bell'          : False,
                'urgent_bell'           : False,
                'icon_bell'             : True,
                'background_color'      : '#000000',
                'background_darkness'   : 0.5,
                'background_type'       : 'solid',
                'background_image'      : '',
                'background_image_mode' : 'stretch_and_fill',
                'background_image_align_horiz': 'center',
                'background_image_align_vert' : 'middle',
                'backspace_binding'     : 'ascii-del',
                'delete_binding'        : 'escape-sequence',
                'cursor_blink'          : True,
                'cursor_shape'          : 'block',
                'cursor_fg_color'       : '',
                'cursor_bg_color'       : '',
                'cursor_color_default'  : True,
                'term'                  : 'xterm-256color',
                'colorterm'             : 'truecolor',
                'font'                  : 'Mono 10',
                'foreground_color'      : '#aaaaaa',
                'show_titlebar'         : True,
                'scrollbar_position'    : "right",
                'scroll_on_keystroke'   : True,
                'scroll_on_output'      : False,
                'scrollback_lines'      : 500,
                'scrollback_infinite'   : False,
                'disable_mousewheel_zoom': False,
                'exit_action'           : 'close',
                'palette'               : '#2e3436:#cc0000:#4e9a06:#c4a000:\
#3465a4:#75507b:#06989a:#d3d7cf:#555753:#ef2929:#8ae234:#fce94f:\
#729fcf:#ad7fa8:#34e2e2:#eeeeec',
                'word_chars'            : '-,./?%&#:_',
                'mouse_autohide'        : True,
                'login_shell'           : False,
                'use_custom_command'    : False,
                'custom_command'        : '',
                'use_system_font'       : True,
                'use_theme_colors'      : False,
                'bold_is_bright'        : False,
                'cell_height'           : 1.0,
                'cell_width'            : 1.0,
                'force_no_bell'         : False,
                'copy_on_selection'     : False,
                'split_to_group'        : False,
                'autoclean_groups'      : True,
                'http_proxy'            : '',
                # Titlebar
                'title_hide_sizetext'     : False,
                'title_transmit_fg_color' : '#ffffff',
                'title_transmit_bg_color' : '#c80003',
                'title_receive_fg_color'  : '#ffffff',
                'title_receive_bg_color'  : '#0076c9',
                'title_inactive_fg_color' : '#000000',
                'title_inactive_bg_color' : '#c0bebf',
                'title_use_system_font'   : True,
                'title_font'              : 'Sans 9'
            },
        },
        'layouts': {
                'default': {
                    'window0': {
                        'type': 'Window',
                        'parent': ''
                        },
                    'child1': {
                        'type': 'Terminal',
                        'parent': 'window0'
                        }
                    }
                },
        'plugins': {
        },
}

class Config(object):
    """Class to provide a slightly richer config API above ConfigBase"""
    base = None
    profile = None
    system_mono_font = None
    system_prop_font = None
    system_focus = None
    inhibited = None
    
    def __init__(self, profile='default'):
        self.base = ConfigBase()
        self.set_profile(profile)
        self.inhibited = False
        self.connect_gsetting_callbacks()

    def __getitem__(self, key, default=None):
        """Look up a configuration item"""
        return(self.base.get_item(key, self.profile, default=default))

    def __setitem__(self, key, value):
        """Set a particular configuration item"""
        return(self.base.set_item(key, value, self.profile))

    def get_profile(self):
        """Get our profile"""
        return(self.profile)

    def get_profile_by_name(self, profile):
        """Get the profile with the specified name"""
        return(self.base.profiles[profile])

    def set_profile(self, profile, force=False):
        """Set our profile (which usually means change it)"""
        options = self.options_get()
        if not force and options and options.profile and profile == 'default':
            dbg('overriding default profile to %s' % options.profile)
            profile = options.profile
        dbg('Changing profile to %s' % profile)
        self.profile = profile
        if profile not in self.base.profiles:
            dbg('%s does not exist, creating' % profile)
            self.base.profiles[profile] = copy(DEFAULTS['profiles']['default'])

    def add_profile(self, profile, toclone):
        """Add a new profile"""
        return(self.base.add_profile(profile, toclone))

    def del_profile(self, profile):
        """Delete a profile"""
        if profile == self.profile:
            # FIXME: We should solve this problem by updating terminals when we
            # remove a profile
            err('Config::del_profile: Deleting in-use profile %s.' % profile)
            self.set_profile('default')
        if profile in self.base.profiles:
            del(self.base.profiles[profile])
        options = self.options_get()
        if options and options.profile == profile:
            options.profile = None
            self.options_set(options)

    def rename_profile(self, profile, newname):
        """Rename a profile"""
        if profile in self.base.profiles:
            self.base.profiles[newname] = self.base.profiles[profile]
            del(self.base.profiles[profile])
            if profile == self.profile:
                self.profile = newname

    def list_profiles(self):
        """List all configured profiles"""
        return(list(self.base.profiles.keys()))

    def add_layout(self, name, layout):
        """Add a new layout"""
        return(self.base.add_layout(name, layout))

    def replace_layout(self, name, layout):
        """Replace an existing layout"""
        return(self.base.replace_layout(name, layout)) 

    def del_layout(self, layout):
        """Delete a layout"""
        if layout in self.base.layouts:
            del(self.base.layouts[layout])

    def rename_layout(self, layout, newname):
        """Rename a layout"""
        if layout in self.base.layouts:
            self.base.layouts[newname] = self.base.layouts[layout]
            del(self.base.layouts[layout])

    def list_layouts(self):
        """List all configured layouts"""
        return(list(self.base.layouts.keys()))

    def connect_gsetting_callbacks(self):
        """Get system settings and create callbacks for changes"""
        dbg("GSetting connects for system changes")
        # Have to preserve these to self, or callbacks don't happen
        self.gsettings_interface=Gio.Settings.new('org.gnome.desktop.interface')
        self.gsettings_interface.connect("changed::font-name", self.on_gsettings_change_event)
        self.gsettings_interface.connect("changed::monospace-font-name", self.on_gsettings_change_event)
        self.gsettings_wm=Gio.Settings.new('org.gnome.desktop.wm.preferences')
        self.gsettings_wm.connect("changed::focus-mode", self.on_gsettings_change_event)

    def get_system_prop_font(self):
        """Look up the system font"""
        if self.system_prop_font is not None:
            return(self.system_prop_font)
        elif 'org.gnome.desktop.interface' not in Gio.Settings.list_schemas():
            return
        else:
            gsettings=Gio.Settings.new('org.gnome.desktop.interface')
            value = gsettings.get_value('font-name')
            if value:
                self.system_prop_font = value.get_string()
            else:
                self.system_prop_font = "Sans 10"
            return(self.system_prop_font)

    def get_system_mono_font(self):
        """Look up the system font"""
        if self.system_mono_font is not None:
            return(self.system_mono_font)
        elif 'org.gnome.desktop.interface' not in Gio.Settings.list_schemas():
            return
        else:
            gsettings=Gio.Settings.new('org.gnome.desktop.interface')
            value = gsettings.get_value('monospace-font-name')
            if value:
                self.system_mono_font = value.get_string()
            else:
                self.system_mono_font = "Mono 10"
            return(self.system_mono_font)

    def get_system_focus(self):
        """Look up the system focus setting"""
        if self.system_focus is not None:
            return(self.system_focus)
        elif 'org.gnome.desktop.interface' not in Gio.Settings.list_schemas():
            return
        else:
            gsettings=Gio.Settings.new('org.gnome.desktop.wm.preferences')
            value = gsettings.get_value('focus-mode')
            if value:
                self.system_focus = value.get_string()
            return(self.system_focus)

    def on_gsettings_change_event(self, settings, key):
        """Handle a gsetting change event"""
        dbg('GSetting change event received. Invalidating caches')
        self.system_focus = None
        self.system_font = None
        self.system_mono_font = None
        # Need to trigger a reconfigure to change active terminals immediately
        if "Terminator" not in globals():
            from .terminator import Terminator
        Terminator().reconfigure()

    def save(self):
        """Cause ConfigBase to save our config to file"""
        if self.inhibited is True:
            return(True)
        else:
            return(self.base.save())

    def inhibit_save(self):
        """Prevent calls to save() being honoured"""
        self.inhibited = True

    def uninhibit_save(self):
        """Allow calls to save() to be honoured"""
        self.inhibited = False

    def options_set(self, options):
        """Set the command line options"""
        self.base.command_line_options = options

    def options_get(self):
        """Get the command line options"""
        return(self.base.command_line_options)

    def plugin_get(self, pluginname, key, default=None):
        """Get a plugin config value, if doesn't exist
            return default if specified
        """
        return(self.base.get_item(key, plugin=pluginname, default=default))

    def plugin_set(self, pluginname, key, value):
        """Set a plugin config value"""
        return(self.base.set_item(key, value, plugin=pluginname))

    def plugin_get_config(self, plugin):
        """Return a whole config tree for a given plugin"""
        return(self.base.get_plugin(plugin))

    def plugin_set_config(self, plugin, tree):
        """Set a whole config tree for a given plugin"""
        return(self.base.set_plugin(plugin, tree))

    def plugin_del_config(self, plugin):
        """Delete a whole config tree for a given plugin"""
        return(self.base.del_plugin(plugin))

    def layout_get_config(self, layout):
        """Return a layout"""
        return(self.base.get_layout(layout))

    def layout_set_config(self, layout, tree):
        """Set a layout"""
        return(self.base.set_layout(layout, tree))

class ConfigBase(Borg):
    """Class to provide access to our user configuration"""
    loaded = None
    whined = None
    sections = None
    global_config = None
    profiles = None
    keybindings = None
    plugins = None
    layouts = None
    command_line_options = None
    config_file_updated_to_cell_height = False

    def __init__(self):
        """Class initialiser"""

        Borg.__init__(self, self.__class__.__name__)

        self.prepare_attributes()
        from . import optionparse
        self.command_line_options = optionparse.options
        self.load()

    def prepare_attributes(self):
        """Set up our borg environment"""
        if self.loaded is None:
            self.loaded = False
        if self.whined is None:
            self.whined = False
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
            self.layouts = {}
            for layout in DEFAULTS['layouts']:
                self.layouts[layout] = copy(DEFAULTS['layouts'][layout])

    def defaults_to_configspec(self):
        """Convert our tree of default values into a ConfigObj validation
        specification"""
        configspecdata = {}

        keymap = {
                'int': 'integer',
                'str': 'string',
                'bool': 'boolean',
                }

        section = {}
        for key in DEFAULTS['global_config']:
            keytype = DEFAULTS['global_config'][key].__class__.__name__
            value = DEFAULTS['global_config'][key]
            if keytype in keymap:
                keytype = keymap[keytype]
            elif keytype == 'list':
                value = 'list(%s)' % ','.join(value)

            keytype = '%s(default=%s)' % (keytype, value)

            if key == 'custom_url_handler':
                keytype = 'string(default="")'

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
            if keytype in keymap:
                keytype = keymap[keytype]
            elif keytype == 'list':
                value = 'list(%s)' % ','.join(value)
            if keytype == 'string':
                value = '"%s"' % value

            keytype = '%s(default=%s)' % (keytype, value)

            section[key] = keytype
        configspecdata['profiles'] = {}
        configspecdata['profiles']['__many__'] = section

        section = {}
        section['type'] = 'string'
        section['parent'] = 'string'
        section['profile'] = 'string(default=default)'
        section['command'] = 'string(default="")'
        section['position'] = 'string(default="")'
        section['size'] = 'list(default=list(-1,-1))'
        configspecdata['layouts'] = {}
        configspecdata['layouts']['__many__'] = {}
        configspecdata['layouts']['__many__']['__many__'] = section

        configspecdata['plugins'] = {}

        configspec = ConfigObj(configspecdata)
        if DEBUG == True:
            configspec.write(open('/tmp/terminator_configspec_debug.txt', 'wb'))
        return(configspec)

    def load(self):
        """Load configuration data from our various sources"""
        if self.loaded is True:
            dbg('config already loaded')
            return

        if self.command_line_options and self.command_line_options.config:
            filename = self.command_line_options.config
        else:
            filename = os.path.join(get_config_dir(), 'config')
            if not os.path.exists(filename):
                filename = os.path.join(get_system_config_dir(), 'config')
        dbg('looking for config file: %s' % filename)
        try:
            #
            # Make sure we attempt to update the ‘cell_height’ config
            # only once when starting a new instance of Terminator.
            #
            if not self.config_file_updated_to_cell_height:
                update_config_to_cell_height(filename)
                self.config_file_updated_to_cell_height = True

            configfile = open(filename, 'r')
        except Exception as ex:
            if not self.whined:
                err('ConfigBase::load: Unable to open %s (%s)' % (filename, ex))
                self.whined = True
            return
        # If we have successfully loaded a config, allow future whining
        self.whined = False

        try:
            configspec = self.defaults_to_configspec()
            parser = ConfigObj(configfile, configspec=configspec)
            validator = Validator()
            result = parser.validate(validator, preserve_errors=True)
        except Exception as ex:
            err('Unable to load configuration: %s' % ex)
            return

        if result != True:
            err('ConfigBase::load: config format is not valid')
            for (section_list, key, _other) in flatten_errors(parser, result):
                if key is not None:
                    err('[%s]: %s is invalid' % (','.join(section_list), key))
                else:
                    err('[%s] missing' % ','.join(section_list))
        else:
            dbg('config validated successfully')

        for section_name in self.sections:
            dbg('Processing section: %s' % section_name)
            section = getattr(self, section_name)
            if section_name == 'profiles':
                for profile in parser[section_name]:
                    dbg('Processing profile: %s' % profile)
                    if section_name not in section:
                        # FIXME: Should this be outside the loop?
                        section[profile] = copy(DEFAULTS['profiles']['default'])
                    section[profile].update(parser[section_name][profile])
            elif section_name == 'plugins':
                if section_name not in parser:
                    continue
                for part in parser[section_name]:
                    dbg('Processing %s: %s' % (section_name, part))
                    section[part] = parser[section_name][part]
            elif section_name == 'layouts':
                for layout in parser[section_name]:
                    dbg('Processing %s: %s' % (section_name, layout))
                    if layout == 'default' and \
                       parser[section_name][layout] == {}:
                           continue
                    section[layout] = parser[section_name][layout]
            elif section_name == 'keybindings':
                if section_name not in parser:
                    continue
                for part in parser[section_name]:
                    dbg('Processing %s: %s' % (section_name, part))
                    if parser[section_name][part] == 'None':
                        section[part] = None
                    else:
                        section[part] = parser[section_name][part]
            else:
                try:
                    section.update(parser[section_name])
                except KeyError as ex:
                    dbg('skipping missing section %s' % section_name)

        self.loaded = True

    def reload(self):
        """Force a reload of the base config"""
        self.loaded = False
        self.load()

    def save(self):
        """Save the config to a file"""
        dbg('saving config')
        parser = ConfigObj(encoding='utf-8')
        parser.indent_type = '  '

        for section_name in ['global_config', 'keybindings']:
            dbg('Processing section: %s' % section_name)
            section = getattr(self, section_name)
            if section_name == 'keybindings':
                from terminatorlib.plugin import KeyBindUtil
                # for plugin KeyBindUtil assist in plugin_util
                keybindutil = KeyBindUtil();
                keyb_keys   = keybindutil.get_all_act_to_keys()
                # we only need keys as a reference so to match them
                # against new values
                keyb_keys   = dict.fromkeys(keyb_keys, "")

                default_merged_section = {**keyb_keys, **DEFAULTS[section_name]}
                merged_section = {**keyb_keys, **section}
                parser[section_name] = dict_diff(default_merged_section, merged_section)
            else:
                parser[section_name] = dict_diff(DEFAULTS[section_name], section)

        from .configjson import JSON_PROFILE_NAME, JSON_LAYOUT_NAME

        parser['profiles'] = {}
        for profile in self.profiles:
            if profile == JSON_PROFILE_NAME:
                continue
            dbg('Processing profile: %s' % profile)
            parser['profiles'][profile] = dict_diff(
                    DEFAULTS['profiles']['default'], self.profiles[profile])

        parser['layouts'] = {}
        for layout in self.layouts:
            if layout == JSON_LAYOUT_NAME:
                continue
            dbg('Processing layout: %s' % layout)
            parser['layouts'][layout] = self.layouts[layout]

        parser['plugins'] = {}
        for plugin in self.plugins:
            dbg('Processing plugin: %s' % plugin)
            parser['plugins'][plugin] = self.plugins[plugin]

        config_dir = get_config_dir()
        if not os.path.isdir(config_dir):
            os.makedirs(config_dir)

        try:
            if self.command_line_options.config:
                filename = self.command_line_options.config
            else: 
                filename = os.path.join(config_dir,'config')

            if not os.path.isfile(filename):
                open(filename, 'a').close()

            backup_file = filename + '~'
            shutil.copy2(filename, backup_file)

            with open(filename, 'wb') as fh:
                parser.write(fh)

            os.remove(backup_file)
        except Exception as ex:
            err('ConfigBase::save: Unable to save config: %s' % ex)

    def get_item(self, key, profile='default', plugin=None, default=None):
        """Look up a configuration item"""
        if profile not in self.profiles:
            # Hitting this generally implies a bug
            profile = 'default'

        if key in self.global_config:
            dbg('%s found in globals: %s' %
                    (key, self.global_config[key]))
            return(self.global_config[key])
        elif key in self.profiles[profile]:
            dbg('%s found in profile %s: %s' % (
                    key, profile, self.profiles[profile][key]))
            return(self.profiles[profile][key])
        elif key == 'keybindings':
            return(self.keybindings)
        elif plugin and plugin in self.plugins and key in self.plugins[plugin]:
            dbg('%s found in plugin %s: %s' % (
                    key, plugin, self.plugins[plugin][key]))
            return(self.plugins[plugin][key])
        elif default:
            return default
        else:
            raise KeyError('ConfigBase::get_item: unknown key %s' % key)

    def set_item(self, key, value, profile='default', plugin=None):
        """Set a configuration item"""
        dbg('Setting %s=%s (profile=%s, plugin=%s)' %
                (key, value, profile, plugin))

        if key in self.global_config:
            self.global_config[key] = value
        elif key in self.profiles[profile]:
            self.profiles[profile][key] = value
        elif key == 'keybindings':
            self.keybindings = value
        elif plugin is not None:
            if plugin not in self.plugins:
                self.plugins[plugin] = {}
            self.plugins[plugin][key] = value
        else:
            raise KeyError('ConfigBase::set_item: unknown key %s' % key)

        return(True)

    def get_plugin(self, plugin):
        """Return a whole tree for a plugin"""
        if plugin in self.plugins:
            return(self.plugins[plugin])

    def set_plugin(self, plugin, tree):
        """Set a whole tree for a plugin"""
        self.plugins[plugin] = tree

    def del_plugin(self, plugin):
        """Delete a whole tree for a plugin"""
        if plugin in self.plugins:
            del self.plugins[plugin]

    def add_profile(self, profile, toclone):
        """Add a new profile"""
        if profile in self.profiles:
            return(False)
        if toclone is not None:
            newprofile = copy(toclone)
        else:
            newprofile = copy(DEFAULTS['profiles']['default'])
        self.profiles[profile] = newprofile
        return(True)

    def add_layout(self, name, layout):
        """Add a new layout"""
        if name in self.layouts:
            return(False)
        self.layouts[name] = layout
        return(True)

    def replace_layout(self, name, layout):
        """Replaces a layout with the given name"""
        if not name in self.layouts:
            return(False)
        self.layouts[name] = layout
        return(True)

    def get_layout(self, layout):
        """Return a layout"""
        if layout in self.layouts:
            return(self.layouts[layout])
        else:
            err('layout does not exist: %s' % layout)

    def set_layout(self, layout, tree):
        """Set a layout"""
        self.layouts[layout] = tree
