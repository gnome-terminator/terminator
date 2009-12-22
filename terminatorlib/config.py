#!/usr/bin/python
#    TerminatorConfig - layered config classes
#    Copyright (C) 2006-2008  cmsj@tenshu.net
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

>>> config = Config()
>>> config['focus']
'click'
>>> config['focus'] = 'sloppy'
>>>

"""

import platform
from borg import Borg

DEFAULTS = {
        'global':   {
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
        'layout':   {
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

class ConfigBase(Borg, dict):
    """Class to provide access to our user configuration"""
    global_config = None
    profiles = None
    keybindings = None
    plugins = None

    def __init__(self):
        """Class initialiser"""

        Borg.__init__(self, self.__class__.__name__)
        dict.__init__(self)

        self.prepare_attributes()
        self.load_config()

    def prepare_attributes(self):
        """Set up our borg environment"""
        if self.global_config is None:
            self.global_config = DEFAULTS['global']
        if self.profiles is None:
            self.profiles = {}
            self.profiles['default'] = DEFAULTS['profiles']['default']
        if self.keybindings is None:
            self.keybindings = DEFAULTS['keybindings']
        if self.plugins is None:
            self.plugins = {}

    def load_config(self):
        """Load configuration data from our various sources"""
        # FIXME: Load our config from wherever and merge it into the defaults
        pass

    def get_item(self, key, profile='default', plugin=None):
        """Look up a configuration item"""
        if self.global_config.has_key(key):
            return(self.global_config[key])
        elif self.profiles['default'].has_key(key):
            return(self.profiles[profile][key])
        elif key == 'keybindings':
            return(self.keybindings)
        elif plugin is not None and self.plugins[plugin].has_key(key):
            return(self.plugins[plugin][key])
        else:
            raise KeyError('ConfigBase::get_item: unknown key %s' % key)

if __name__ == '__main__':
    import doctest
    (failed, attempted) = doctest.testmod()
    print "%d/%d tests failed" % (failed, attempted)
