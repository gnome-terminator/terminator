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

Classes relating to configuratoin"""

import platform
from borg import Borg

DEFAULTS = {
  'gt_dir'                : '/apps/gnome-terminal',
  'profile_dir'           : '/apps/gnome-terminal/profiles',
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
  'focus'                 : 'click',
  'exit_action'           : 'close',
  'palette'               : '#000000000000:#CDCD00000000:#0000CDCD0000:\
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
  'http_proxy'            : '',
  'ignore_hosts'          : ['localhost','127.0.0.0/8','*.local'],
  'encoding'              : 'UTF-8',
  'active_encodings'      : ['UTF-8', 'ISO-8859-1'],
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
  'enable_real_transparency'  : True,
  'title_tx_txt_color'    : '#FFFFFF',
  'title_tx_bg_color'     : '#C80003',
  'title_rx_txt_color'    : '#FFFFFF',
  'title_rx_bg_color'     : '#0076C9',
  'title_ia_txt_color'    : '#000000',
  'title_ia_bg_color'     : '#C0BEBF',
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
    'group_all'        : '<Super>g',
    'ungroup_all'      : '<Super><Shift>g',
    'group_tab'        : '<Super>t',
    'ungroup_tab'      : '<Super><Shift>T',
    'new_window'       : '<Ctrl><Shift>I',
  }
}

class Config(Borg, dict):
    """Class to provide access to our user configuration"""

    def __init__(self):
        """Class initialiser"""

        Borg.__init__(self)
        dict.__init__(self)

    def __getitem__(self, key):
        """Look up a configuration item"""
        return(DEFAULTS[key])

