#!/usr/bin/env python
"""Preferences Editor for Terminator. 

Load a UIBuilder config file, display it,
populate it with our current config, then optionally read that back out and
write it to a config file

"""

import os
from gi.repository import GObject, Gtk, Gdk

from .util import dbg, err
from . import config
from .keybindings import Keybindings, KeymapError
from .translation import _
from .terminator import Terminator
from .plugin import PluginRegistry
from .version import APP_NAME

from .plugin import KeyBindUtil

def get_color_string(widcol):
    return('#%02x%02x%02x' % (widcol.red>>8, widcol.green>>8, widcol.blue>>8))

def color2hex(widget):
    """Pull the colour values out of a Gtk ColorPicker widget and return them
   as 8bit hex values, sinces its default behaviour is to give 16bit values"""
    return get_color_string(widget.get_color())

def rgba2hex(widget):
    return get_color_string(widget.get_rgba().to_color())

NUM_PALETTE_COLORS = 16

# FIXME: We need to check that we have represented all of Config() below
class PrefsEditor:
    """Class implementing the various parts of the preferences editor"""
    config = None
    registry = None
    plugins = None
    keybindings = None
    window = None
    calling_window = None
    term = None
    builder = None
    layouteditor = None
    previous_layout_selection = None
    previous_profile_selection = None
    colorschemevalues = {'black_on_yellow': 0,
                         'black_on_white': 1,
                         'grey_on_black': 2,
                         'green_on_black': 3,
                         'white_on_black': 4,
                         'orange_on_black': 5,
                         'ambience': 6,
                         'solarized_light': 7,
                         'solarized_dark': 8,
                         'gruvbox_light': 9,
                         'gruvbox_dark': 10,
                         'custom': 11}
    colourschemes = {'grey_on_black': ['#aaaaaa', '#000000'],
                     'black_on_yellow': ['#000000', '#ffffdd'],
                     'black_on_white': ['#000000', '#ffffff'],
                     'white_on_black': ['#ffffff', '#000000'],
                     'green_on_black': ['#00ff00', '#000000'],
                     'orange_on_black': ['#e53c00', '#000000'],
                     'ambience': ['#ffffff', '#300a24'],
                     'solarized_light': ['#657b83', '#fdf6e3'],
                     'solarized_dark': ['#839496', '#002b36'],
                     'gruvbox_light': ['#3c3836', '#fbf1c7'],
                     'gruvbox_dark': ['#ebdbb2', '#282828']}
    palettevalues = {'tango': 0,
                     'linux': 1,
                     'xterm': 2,
                     'rxvt': 3,
                     'ambience': 4,
                     'solarized': 5,
                     'gruvbox_light': 6,
                     'gruvbox_dark': 7,
                     'custom': 8}
    palettes = {'tango': '#000000:#cc0000:#4e9a06:#c4a000:#3465a4:\
#75507b:#06989a:#d3d7cf:#555753:#ef2929:#8ae234:#fce94f:#729fcf:\
#ad7fa8:#34e2e2:#eeeeec',
                'linux': '#000000:#aa0000:#00aa00:#aa5500:#0000aa:\
#aa00aa:#00aaaa:#aaaaaa:#555555:#ff5555:#55ff55:#ffff55:#5555ff:\
#ff55ff:#55ffff:#ffffff',
                'xterm': '#000000:#cd0000:#00cd00:#cdcd00:#0000ee:\
#cd00cd:#00cdcd:#e5e5e5:#7f7f7f:#ff0000:#00ff00:#ffff00:#5c5cff:\
#ff00ff:#00ffff:#ffffff',
                'rxvt': '#000000:#cd0000:#00cd00:#cdcd00:#0000cd:\
#cd00cd:#00cdcd:#faebd7:#404040:#ff0000:#00ff00:#ffff00:#0000ff:\
#ff00ff:#00ffff:#ffffff',
                'ambience': '#2e3436:#cc0000:#4e9a06:#c4a000:\
#3465a4:#75507b:#06989a:#d3d7cf:#555753:#ef2929:#8ae234:#fce94f:\
#729fcf:#ad7fa8:#34e2e2:#eeeeec',
                'solarized': '#073642:#dc322f:#859900:#b58900:\
#268bd2:#d33682:#2aa198:#eee8d5:#002b36:#cb4b16:#586e75:#657b83:\
#839496:#6c71c4:#93a1a1:#fdf6e3',
                'gruvbox_light': '#fbf1c7:#cc241d:#98971a:#d79921:\
#458588:#b16286:#689d6a:#7c6f64:#928374:#9d0006:#79740e:#b57614:\
#076678:#8f3f71:#427b58:#3c3836',
                'gruvbox_dark': '#282828:#cc241d:#98971a:#d79921:\
#458588:#b16286:#689d6a:#a89984:#928374:#fb4934:#b8bb26:#fabd2f:\
#83a598:#d3869b:#8ec07c:#ebdbb2'}
    keybindingnames = { 'zoom_in'          : _('Increase font size'),
                        'zoom_out'         : _('Decrease font size'),
                        'zoom_normal'      : _('Restore original font size'),
						'zoom_in_all'	   : _('Increase font size on all terminals'),
						'zoom_out_all'	   : _('Decrease font size on all terminals'),
						'zoom_normal_all'  : _('Restore original font size on all terminals'),
                        'new_tab'          : _('Create a new tab'),
                        'cycle_next'       : _('Focus the next terminal'),
                        'cycle_prev'       : _('Focus the previous terminal'),
                        'go_next'          : _('Focus the next terminal'),
                        'go_prev'          : _('Focus the previous terminal'),
                        'go_up'            : _('Focus the terminal above'),
                        'go_down'          : _('Focus the terminal below'),
                        'go_left'          : _('Focus the terminal left'),
                        'go_right'         : _('Focus the terminal right'),
                        'rotate_cw'        : _('Rotate terminals clockwise'),
                        'rotate_ccw'       : _('Rotate terminals counter-clockwise'),
                        'split_auto'       : _('Split automatically'),
                        'split_horiz'      : _('Split horizontally'),
                        'split_vert'       : _('Split vertically'),
                        'close_term'       : _('Close terminal'),
                        'copy'             : _('Copy selected text'),
                        'paste'            : _('Paste clipboard'),
                        'paste_selection'  : _('Paste primary selection'),
                        'toggle_scrollbar' : _('Show/Hide the scrollbar'),
                        'search'           : _('Search terminal scrollback'),
                        'page_up'          : _('Scroll upwards one page'),
                        'page_down'        : _('Scroll downwards one page'),
                        'page_up_half'     : _('Scroll upwards half a page'),
                        'page_down_half'   : _('Scroll downwards half a page'),
                        'line_up'          : _('Scroll upwards one line'),
                        'line_down'        : _('Scroll downwards one line'),
                        'close_window'     : _('Close window'),
                        'resize_up'        : _('Resize the terminal up'),
                        'resize_down'      : _('Resize the terminal down'),
                        'resize_left'      : _('Resize the terminal left'),
                        'resize_right'     : _('Resize the terminal right'),
                        'move_tab_right'   : _('Move the tab right'),
                        'move_tab_left'    : _('Move the tab left'),
                        'toggle_zoom'      : _('Maximize terminal'),
                        'scaled_zoom'      : _('Zoom terminal'),
                        'next_tab'         : _('Switch to the next tab'),
                        'prev_tab'         : _('Switch to the previous tab'),
                        'switch_to_tab_1'  : _('Switch to the first tab'),
                        'switch_to_tab_2'  : _('Switch to the second tab'),
                        'switch_to_tab_3'  : _('Switch to the third tab'),
                        'switch_to_tab_4'  : _('Switch to the fourth tab'),
                        'switch_to_tab_5'  : _('Switch to the fifth tab'),
                        'switch_to_tab_6'  : _('Switch to the sixth tab'),
                        'switch_to_tab_7'  : _('Switch to the seventh tab'),
                        'switch_to_tab_8'  : _('Switch to the eighth tab'),
                        'switch_to_tab_9'  : _('Switch to the ninth tab'),
                        'switch_to_tab_10' : _('Switch to the tenth tab'),
                        'full_screen'      : _('Toggle fullscreen'),
                        'reset'            : _('Reset the terminal'),
                        'reset_clear'      : _('Reset and clear the terminal'),
                        'hide_window'      : _('Toggle window visibility'),
                        'create_group'     : _('Create new group'),
                        'group_all'        : _('Group all terminals'),
                        'group_all_toggle' : _('Group/Ungroup all terminals'),
                        'ungroup_all'      : _('Ungroup all terminals'),
                        'group_win'        : _('Group terminals in window'),
                        'group_win_toggle' : _('Group/Ungroup terminals in window'),
                        'ungroup_win'      : _('Ungroup terminals in window'),
                        'group_tab'        : _('Group terminals in tab'),
                        'group_tab_toggle' : _('Group/Ungroup terminals in tab'),
                        'ungroup_tab'      : _('Ungroup terminals in tab'),
                        'new_window'       : _('Create a new window'),
                        'new_terminator'   : _('Spawn a new Terminator process'),
                        'broadcast_off'    : _('Don\'t broadcast key presses'),
                        'broadcast_group'  : _('Broadcast key presses to group'),
                        'broadcast_all'    : _('Broadcast key events to all'),
                        'insert_number'    : _('Insert terminal number'),
                        'insert_padded'    : _('Insert zero padded terminal number'),
                        'edit_window_title': _('Edit window title'),
                        'edit_terminal_title': _('Edit terminal title'),
                        'edit_tab_title'   : _('Edit tab title'),
                        'layout_launcher'  : _('Open layout launcher window'),
                        'next_profile'     : _('Switch to next profile'),
                        'previous_profile' : _('Switch to previous profile'), 
                        'preferences'	   : _('Open the Preferences window'),
                        'preferences_keybindings' : _('Open the Preferences-Keybindings window'),
                        'help'             : _('Open the manual')
            }

    def __init__ (self, term, cur_page=0):
        self.config = config.Config()
        self.config.base.reload()
        self.term = term
        self.calling_window = self.term.get_toplevel()
        self.calling_window.preventHide = True
        self.builder = Gtk.Builder()
        self.builder.set_translation_domain(APP_NAME)
        self.keybindings = Keybindings()
        self.active_message_dialog = None
        try:
            # Figure out where our library is on-disk so we can open our
            (head, _tail) = os.path.split(config.__file__)
            librarypath = os.path.join(head, 'preferences.glade')
            gladefile = open(librarypath, 'r')
            gladedata = gladefile.read()
        except Exception as ex:
            print("Failed to find preferences.glade")
            print(ex)
            return

        self.builder.add_from_string(gladedata)
        self.window = self.builder.get_object('prefswin')

        icon_theme = Gtk.IconTheme.get_default()
        if icon_theme.lookup_icon('terminator-preferences', 48, 0):
            self.window.set_icon_name('terminator-preferences')
        else:
            dbg('Unable to load Terminator preferences icon')
            icon = self.window.render_icon(Gtk.STOCK_DIALOG_INFO, Gtk.IconSize.BUTTON)
            self.window.set_icon(icon)

        self.layouteditor = LayoutEditor(self.builder)
        self.builder.connect_signals(self)
        self.layouteditor.prepare()
        self.window.show_all()
        try:
            self.config.inhibit_save()
            self.set_values()
        except Exception as e:
            err('Unable to set values: %s' % e)
        self.config.uninhibit_save()

        guiget = self.builder.get_object
        nb = guiget('notebook1')
        nb.set_current_page(cur_page)

    def on_closebutton_clicked(self, _button):
        """Close the window"""
        terminator = Terminator()
        terminator.reconfigure()
        self.window.destroy()
        self.calling_window.preventHide = False
        del(self)

    def set_values(self):
        """Update the preferences window with all the configuration from
        Config()"""
        guiget = self.builder.get_object

        ## Global tab
        # Mouse focus
        focus = self.config['focus']
        active = 0
        if focus == 'click':
            active = 1
        elif focus in ['sloppy', 'mouse']:
            active = 2
        widget = guiget('focuscombo')
        widget.set_active(active)
        # Terminal separator size
        termsepsize = self.config['handle_size']
        widget = guiget('handlesize')
        widget.set_value(float(termsepsize))
        widget = guiget('handlesize_value_label')
        widget.set_text(str(termsepsize))

        # Cell Height
        cellheightsize = self.config['cell_height']
        cellheightsize = round(float(cellheightsize),1)
        widget = guiget('cellheight')
        widget.set_value(cellheightsize)
        widget = guiget('cellheight_value_label')
        widget.set_text(str(cellheightsize))

        # Cell Width
        cellwidthsize = self.config['cell_width']
        cellwidthsize = round(float(cellwidthsize),1)
        widget = guiget('cellwidth')
        widget.set_value(cellwidthsize)
        widget = guiget('cellwidth_value_label')
        widget.set_text(str(cellwidthsize))

        # Window geometry hints
        geomhint = self.config['geometry_hinting']
        widget = guiget('wingeomcheck')
        widget.set_active(geomhint)
        # Window state
        option = self.config['window_state']
        if option == 'hidden':
            active = 1
        elif option == 'maximise':
            active = 2
        elif option == 'fullscreen':
            active = 3
        else:
            active = 0
        widget = guiget('winstatecombo')
        widget.set_active(active)
        # Window borders
        widget = guiget('winbordercheck')
        widget.set_active(not self.config['borderless'])
        # Extra styling
        widget = guiget('extrastylingcheck')
        widget.set_active(self.config['extra_styling'])
        # Tab bar position
        option = self.config['tab_position']
        widget = guiget('tabposcombo')
        if option == 'bottom':
            active = 1
        elif option == 'left':
            active = 2
        elif option == 'right':
            active = 3
        elif option == 'hidden':
            active = 4
        else:
            active = 0
        widget.set_active(active)
        # Broadcast default
        option = self.config['broadcast_default']
        widget = guiget('broadcastdefault')
        if option == 'all':
            active = 0
        elif option == 'off':
            active = 2
        else:
            active = 1
        widget.set_active(active)
        # Disable Ctrl+mousewheel zoom
        widget = guiget('disablemousewheelzoom')
        widget.set_active(self.config['disable_mousewheel_zoom'])
        # scroll_tabbar
        widget = guiget('scrolltabbarcheck')
        widget.set_active(self.config['scroll_tabbar'])
        # homogeneous_tabbar
        widget = guiget('homogeneouscheck')
        widget.set_active(self.config['homogeneous_tabbar'])
        # DBus Server
        widget = guiget('dbuscheck')
        widget.set_active(self.config['dbus'])
        # Detachable tabs
        widget = guiget('detachable_tabs')
        widget.set_active(self.config['detachable_tabs'])
        #Hide from taskbar
        widget = guiget('hidefromtaskbcheck')
        widget.set_active(self.config['hide_from_taskbar'])
        #Always on top
        widget = guiget('alwaysontopcheck')
        widget.set_active(self.config['always_on_top'])
        #Hide on lose focus
        widget = guiget('hideonlosefocuscheck')
        widget.set_active(self.config['hide_on_lose_focus'])
        #Show on all workspaces
        widget = guiget('stickycheck')
        widget.set_active(self.config['sticky'])

        # title bar at bottom
        widget = guiget('title_at_bottom_checkbutton')
        widget.set_active(self.config['title_at_bottom'])

        # new tab after current tab
        widget = guiget('new_tab_after_current_checkbutton')
        widget.set_active(self.config['new_tab_after_current_tab'])

        #Always split with profile
        widget = guiget('always_split_with_profile')
        widget.set_active(self.config['always_split_with_profile'])
        # Putty paste style
        widget = guiget('putty_paste_style')
        widget.set_active(self.config['putty_paste_style'])
        # Putty paste style source clipboard
        if self.config['putty_paste_style_source_clipboard']:
            widget = guiget('putty_paste_style_source_clipboard_radiobutton')
        else:
            widget = guiget('putty_paste_style_source_primary_radiobutton')
        widget.set_active(True)
        # Smart copy
        widget = guiget('smart_copy')
        widget.set_active(self.config['smart_copy'])
        # Clear selection on copy
        widget = guiget('clear_select_on_copy')
        widget.set_active(self.config['clear_select_on_copy'])
        # Disable mouse paste
        widget = guiget('disable_mouse_paste')
        widget.set_active(self.config['disable_mouse_paste'])

        ## Profile tab
        # Populate the profile list
        widget = guiget('profilelist')
        liststore = widget.get_model()
        profiles = self.config.list_profiles()
        if '__internal_json_profile__' in profiles:
            profiles.remove('__internal_json_profile__')
        self.profileiters = {}
        for profile in profiles:
            if profile == 'default':
                editable = False
            else:
                editable = True
            self.profileiters[profile] = liststore.append([profile, editable])
        selection = widget.get_selection()
        selection.connect('changed', self.on_profile_selection_changed)
        selection.select_iter(self.profileiters['default'])

        ## Layouts tab
        widget = guiget('layoutlist')
        liststore = widget.get_model()
        layouts = self.config.list_layouts()
        if '__internal_json_layout__' in layouts:
            layouts.remove('__internal_json_layout__')
        self.layoutiters = {}
        for layout in layouts:
            if layout == 'default':
                editable = False
            else:
                editable = True
            self.layoutiters[layout] = liststore.append([layout, editable])
        selection = widget.get_selection()
        selection.connect('changed', self.on_layout_selection_changed)
        terminator = Terminator()
        if terminator.layoutname and terminator.layoutname != '__internal_json_layout__':
            layout_to_highlight = terminator.layoutname
        else:
            layout_to_highlight = 'default'
        selection.select_iter(self.layoutiters[layout_to_highlight])
        # Now set up the selection changed handler for the layout itself
        widget = guiget('LayoutTreeView')
        selection = widget.get_selection()
        selection.connect('changed', self.on_layout_item_selection_changed)

        ## Keybindings tab
        widget   = guiget('keybindingtreeview')
        kbsearch = guiget('keybindingsearchentry')
        self.keybind_filter_str = ""

        #lets hide whatever we can in nested scope
        def filter_visible(model, treeiter, data):
            act  = model[treeiter][0]
            keys = data[act] if act in data else ""
            desc = model[treeiter][1]
            kval = model[treeiter][2]
            mask = model[treeiter][3]
            #so user can search for disabled keys also
            if not (len(keys) and kval and mask):
                act = "Disabled"

            self.keybind_filter_str = self.keybind_filter_str.lower()
            searchtxt = (act + " " + keys + " " + desc).lower()
            pos = searchtxt.find(self.keybind_filter_str)
            if (pos >= 0):
                dbg("filter find:%s in search text: %s" %
                                (self.keybind_filter_str, searchtxt))
                return True

            return False

        def on_search(widget, text):
            MAX_SEARCH_LEN = 10
            self.keybind_filter_str = widget.get_text()
            ln = len(self.keybind_filter_str)
            #its a small list & we are eager for quick search, but limit
            if (ln >=2 and ln < MAX_SEARCH_LEN):
                dbg("filter search str: %s" % self.keybind_filter_str)
                self.treemodelfilter.refilter()

        def on_search_refilter(widget):
            dbg("refilter")
            self.treemodelfilter.refilter()

        kbsearch.connect('key-press-event', on_search)
        kbsearch.connect('backspace', on_search_refilter)

        liststore = widget.get_model()
        liststore.set_sort_column_id(0, Gtk.SortType.ASCENDING)
        keybindings = self.config['keybindings']

        keybindutil          = KeyBindUtil()
        plugin_keyb_act      = keybindutil.get_all_act_to_keys()
        plugin_keyb_desc     = keybindutil.get_all_act_to_desc()
        #merge give preference to main bindings over plugin
        keybindings          = {**plugin_keyb_act,  **keybindings}
        self.keybindingnames = {**plugin_keyb_desc, **self.keybindingnames}
        #dbg("appended actions %s names %s" % (keybindings, self.keybindingnames))

        for keybinding in keybindings:
            keyval = 0
            mask = 0
            value = keybindings[keybinding]
            if value is not None and value != '':
                try:
                    (keyval, mask) = self.keybindings._parsebinding(value)
                except KeymapError:
                    pass
            liststore.append([keybinding, self.keybindingnames[keybinding],
                             keyval, mask])

        self.treemodelfilter = liststore.filter_new()
        self.treemodelfilter.set_visible_func(filter_visible, keybindings)
        widget.set_model(self.treemodelfilter)

        ## Plugins tab
        # Populate the plugin list
        widget = guiget('pluginlist')
        liststore = widget.get_model()
        self.registry = PluginRegistry()
        self.pluginiters = {}
        pluginlist = self.registry.get_available_plugins()
        self.plugins = {}
        for plugin in pluginlist:
            if plugin[0] != "_": # Do not display hidden plugins
                self.plugins[plugin] = self.registry.is_enabled(plugin)

        for plugin in self.plugins:
            self.pluginiters[plugin] = liststore.append([plugin,
                                             self.plugins[plugin]])
        selection = widget.get_selection()
        selection.connect('changed', self.on_plugin_selection_changed)
        if len(self.pluginiters) > 0:
            selection.select_iter(liststore.get_iter_first())

    def set_profile_values(self, profile):
        """Update the profile values for a given profile"""
        self.config.set_profile(profile)
        guiget = self.builder.get_object

        dbg('Setting profile %s' % profile)

        ## General tab
        # Use system font
        widget = guiget('system_font_checkbutton')
        widget.set_active(self.config['use_system_font'])
        self.on_system_font_checkbutton_toggled(widget)
        # Font selector
        widget = guiget('font_selector')

        if self.config['use_system_font'] == True:
            fontname = self.config.get_system_mono_font()
            if fontname is not None:
                widget.set_font_name(fontname)
        else:
            widget.set_font_name(self.config['font'])
        # Allow bold text
        widget = guiget('allow_bold_checkbutton')
        widget.set_active(self.config['allow_bold'])
        # Icon terminal bell
        widget = guiget('icon_bell_checkbutton')
        widget.set_active(self.config['icon_bell'])
        # Visual terminal bell
        widget = guiget('visual_bell_checkbutton')
        widget.set_active(self.config['visible_bell'])
        # Audible terminal bell
        widget = guiget('audible_bell_checkbutton')
        widget.set_active(self.config['audible_bell'])
        # WM_URGENT terminal bell
        widget = guiget('urgent_bell_checkbutton')
        widget.set_active(self.config['urgent_bell'])
        # Show titlebar
        widget = guiget('show_titlebar')
        widget.set_active(self.config['show_titlebar'])
        # Copy on selection
        widget = guiget('copy_on_selection')
        widget.set_active(self.config['copy_on_selection'])
        # Word chars
        widget = guiget('word_chars_entry')
        widget.set_text(self.config['word_chars'])
        # Word char support was missing from vte 0.38, hide from the UI
        if not hasattr(self.term.vte, 'set_word_char_exceptions'):
            guiget('word_chars_hbox').hide()
        # Cursor shape
        widget = guiget('cursor_shape_combobox')
        if self.config['cursor_shape'] == 'underline':
            active = 1
        elif self.config['cursor_shape'] == 'ibeam':
            active = 2
        else:
            active = 0
        widget.set_active(active)
        # Cursor blink
        widget = guiget('cursor_blink')
        widget.set_active(self.config['cursor_blink'])
        # Cursor use default colors
        widget = guiget('cursor_color_default_checkbutton')
        widget.set_active(self.config['cursor_color_default'])
        # Cursor foreground
        widget = guiget('cursor_fg_color')
        try:
            widget.set_color(Gdk.color_parse(self.config['cursor_fg_color']))
        except:
            try:
                widget.set_color(Gdk.color_parse(self.config['background_color']))
            except:
                widget.set_color(Gdk.color_parse('#000000'))
        # Cursor background
        widget = guiget('cursor_bg_color')
        try:
            widget.set_color(Gdk.color_parse(self.config['cursor_bg_color']))
        except:
            try:
                widget.set_color(Gdk.color_parse(self.config['foreground_color']))
            except:
                widget.set_color(Gdk.color_parse('#ffffff'))

        ## Command tab
        # Login shell
        widget = guiget('login_shell_checkbutton')
        widget.set_active(self.config['login_shell'])
        # Use Custom command
        widget = guiget('use_custom_command_checkbutton')
        widget.set_active(self.config['use_custom_command'])
        self.on_use_custom_command_checkbutton_toggled(widget)
        # Custom Command
        widget = guiget('custom_command_entry')
        widget.set_text(self.config['custom_command'])
        # Exit action
        widget = guiget('exit_action_combobox')
        if self.config['exit_action'] == 'restart':
            widget.set_active(1)
        elif self.config['exit_action'] == 'hold':
            widget.set_active(2)
        else:
            # Default is to close the terminal
            widget.set_active(0)

        ## Colors tab
        # Use system colors
        widget = guiget('use_theme_colors_checkbutton')
        widget.set_active(self.config['use_theme_colors'])
        # Bold is bright
        widget = guiget('bold_text_is_bright_checkbutton')
        widget.set_active(self.config['bold_is_bright'])
        # Colorscheme
        widget = guiget('color_scheme_combobox')
        scheme = None
        for ascheme in self.colourschemes:
            forecol = self.colourschemes[ascheme][0]
            backcol = self.colourschemes[ascheme][1]
            if self.config['foreground_color'].lower() == forecol and \
               self.config['background_color'].lower() == backcol:
                scheme = ascheme
                break
        if scheme not in self.colorschemevalues:
            if self.config['foreground_color'] in [None, ''] or \
               self.config['background_color'] in [None, '']:
                scheme = 'grey_on_black'
            else:
                scheme = 'custom'
        # NOTE: The scheme is set in the GUI widget after the fore/back colours
        # Foreground color
        widget = guiget('foreground_colorbutton')
        widget.set_events(Gdk.EventMask.BUTTON_PRESS_MASK)

        if scheme == 'custom':
            widget.set_sensitive(True)
        else:
            widget.set_sensitive(False)
        # Background color
        widget = guiget('background_colorbutton')
        widget.set_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        if scheme == 'custom':
            widget.set_sensitive(True)
        else:
            widget.set_sensitive(False)
        # Now actually set the scheme
        widget = guiget('color_scheme_combobox')
        widget.set_active(self.colorschemevalues[scheme])
        # Palette scheme
        widget = guiget('palette_combobox')
        palette = None
        for apalette in self.palettes:
            if self.config['palette'].lower() == self.palettes[apalette]:
                palette = apalette
        if palette not in self.palettevalues:
            if self.config['palette'] in [None, '']:
                palette = 'rxvt'
            else:
                palette = 'custom'
        # NOTE: The palette selector is set after the colour pickers
        # Palette colour pickers
        for palette_id in range(0, NUM_PALETTE_COLORS):
            widget = self.get_palette_widget(palette_id)
            widget.set_events(Gdk.EventMask.BUTTON_PRESS_MASK)
            def on_palette_click(event, data, widget=widget):
                self.edit_palette_button(widget)
            widget.connect('button-press-event', on_palette_click)
        self.load_palette()
        # Now set the palette selector widget
        widget = guiget('palette_combobox')
        widget.set_active(self.palettevalues[palette])
        # Inactive terminal shading
        widget = guiget('inactive_color_offset')
        widget.set_value(float(self.config['inactive_color_offset']))
        widget = guiget('inactive_color_offset_value_label')
        widget.set_text('%d%%' % (int(float(self.config['inactive_color_offset'])*100)))
        widget = guiget('inactive_bg_color_offset')
        widget.set_value(float(self.config['inactive_bg_color_offset']))
        widget = guiget('inactive_bg_color_offset_value_label')
        widget.set_text('%d%%' % (int(float(self.config['inactive_bg_color_offset'])*100)))
        # Open links with a single click (instead of a Ctrl-left click)
        widget = guiget('link_single_click')
        widget.set_active(self.config['link_single_click'])
        # Use custom URL handler
        widget = guiget('use_custom_url_handler_checkbox')
        widget.set_active(self.config['use_custom_url_handler'])
        self.on_use_custom_url_handler_checkbutton_toggled(widget)
        # Custom URL handler
        widget = guiget('custom_url_handler_entry')
        widget.set_text(self.config['custom_url_handler'])

        ## Background tab
        # Radio values
        if self.config['background_type'] == 'solid':
            guiget('solid_radiobutton').set_active(True)
        elif self.config['background_type'] == 'transparent':
            guiget('transparent_radiobutton').set_active(True)
        elif self.config['background_type'] == 'image':
            guiget('image_radiobutton').set_active(True)
        self.update_background_tab()
        # Background image
        widget = guiget('background_image_file')
        widget.set_filename(self.config['background_image'])

        widget = guiget('background_image_mode_combobox')
        if self.config['background_image_mode'] == 'scale_and_fit':
            widget.set_active(1)
        elif self.config['background_image_mode'] == 'scale_and_crop':
            widget.set_active(2)
        elif self.config['background_image_mode'] == 'tiling':
            widget.set_active(3)
        else:
            # default to stretch_and_fill
            widget.set_active(0)

        widget = guiget('background_image_align_horiz_combobox')
        if self.config['background_image_align_horiz'] == 'center':
            widget.set_active(1)
        elif self.config['background_image_align_horiz'] == 'right':
            widget.set_active(2)
        else:
            # default to left
            widget.set_active(0)

        widget = guiget('background_image_align_vert_combobox')
        if self.config['background_image_align_vert'] == 'middle':
            widget.set_active(1)
        elif self.config['background_image_align_vert'] == 'bottom':
            widget.set_active(2)
        else:
            # default to top
            widget.set_active(0)

        # Background shading
        widget = guiget('background_darkness_scale')
        widget.set_value(float(self.config['background_darkness']))
   
        ## Scrolling tab
        # Scrollbar position
        widget = guiget('scrollbar_position_combobox')
        value = self.config['scrollbar_position']
        if value == 'left':
            widget.set_active(0)
        elif value in ['disabled', 'hidden']:
            widget.set_active(2)
        else:
            widget.set_active(1)
        # Scrollback lines
        widget = guiget('scrollback_lines_spinbutton')
        widget.set_value(self.config['scrollback_lines'])
        # Scrollback infinite
        widget = guiget('scrollback_infinite')
        widget.set_active(self.config['scrollback_infinite'])
        # Scroll on output
        widget = guiget('scroll_on_output_checkbutton')
        widget.set_active(self.config['scroll_on_output'])
        # Scroll on keystroke
        widget = guiget('scroll_on_keystroke_checkbutton')
        widget.set_active(self.config['scroll_on_keystroke'])

        ## Compatibility tab
        # Backspace key
        widget = guiget('backspace_binding_combobox')
        value = self.config['backspace_binding']
        if value == 'control-h':
            widget.set_active(1)
        elif value == 'ascii-del':
            widget.set_active(2)
        elif value == 'escape-sequence':
            widget.set_active(3)
        else:
            widget.set_active(0)
        # Delete key
        widget = guiget('delete_binding_combobox')
        value = self.config['delete_binding']
        if value == 'control-h':
            widget.set_active(1)
        elif value == 'ascii-del':
            widget.set_active(2)
        elif value == 'escape-sequence':
            widget.set_active(3)
        else:
            widget.set_active(0)

        ## Titlebar tab
        # Titlebar colors
        for bit in ['title_transmit_fg_color', 'title_transmit_bg_color',
            'title_receive_fg_color', 'title_receive_bg_color',
            'title_inactive_fg_color', 'title_inactive_bg_color']:
            widget = guiget(bit)
            widget.set_color(Gdk.color_parse(self.config[bit]))
        # Hide size text from the title bar
        widget = guiget('title_hide_sizetextcheck')
        widget.set_active(self.config['title_hide_sizetext'])
        # Use system font
        widget = guiget('title_system_font_checkbutton')
        widget.set_active(self.config['title_use_system_font'])
        self.on_title_system_font_checkbutton_toggled(widget)
        # Font selector
        widget = guiget('title_font_selector')
        if self.config['title_use_system_font'] == True:
            fontname = self.config.get_system_prop_font()
            if fontname is not None:
                widget.set_font_name(fontname)
        else:
            widget.set_font_name(self.config['title_font'])

    def set_layout(self, layout_name):
        """Set a layout"""
        self.layouteditor.set_layout(layout_name)

    def on_wingeomcheck_toggled(self, widget):
        """Window geometry setting changed"""
        self.config['geometry_hinting'] = widget.get_active()
        self.config.save()

    def on_homogeneous_toggled(self, widget):
        """homogeneous_tabbar setting changed"""
        guiget = self.builder.get_object
        self.config['homogeneous_tabbar'] = widget.get_active()
        scroll_toggled = guiget('scrolltabbarcheck')
        if widget.get_active():
            scroll_toggled.set_sensitive(True)
        else:
            scroll_toggled.set_active(True)
            scroll_toggled.set_sensitive(False)
        self.config.save()

    def on_scroll_toggled(self, widget):
        """scroll_tabbar setting changed"""
        self.config['scroll_tabbar'] = widget.get_active()
        self.config.save()

    def on_dbuscheck_toggled(self, widget):
        """DBus server setting changed"""
        self.config['dbus'] = widget.get_active()
        self.config.save()

    def on_detachable_tabs_toggled(self, widget):
        self.config['detachable_tabs'] = widget.get_active()
        self.config.save()

    def on_disable_mousewheel_zoom_toggled(self, widget):
        """Ctrl+mousewheel zoom setting changed"""
        self.config['disable_mousewheel_zoom'] = widget.get_active()
        self.config.save()

    def on_winbordercheck_toggled(self, widget):
        """Window border setting changed"""
        self.config['borderless'] = not widget.get_active()
        self.config.save()

    def on_extrastylingcheck_toggled(self, widget):
        """Extra styling setting changed"""
        self.config['extra_styling'] = widget.get_active()
        self.config.save()

    def on_hidefromtaskbcheck_toggled(self, widget):
        """Hide from taskbar setting changed"""
        self.config['hide_from_taskbar'] = widget.get_active()
        self.config.save()

    def on_alwaysontopcheck_toggled(self, widget):
        """Always on top setting changed"""
        self.config['always_on_top'] = widget.get_active()
        self.config.save()

    def on_hideonlosefocuscheck_toggled(self, widget):
        """Hide on lose focus setting changed"""
        self.config['hide_on_lose_focus'] = widget.get_active()
        self.config.save()

    def on_stickycheck_toggled(self, widget):
        """Sticky setting changed"""
        self.config['sticky'] = widget.get_active()
        self.config.save()

    def on_title_hide_sizetextcheck_toggled(self, widget):
        """Window geometry setting changed"""
        self.config['title_hide_sizetext'] = widget.get_active()
        self.config.save()

    def on_title_at_bottom_checkbutton_toggled(self, widget):
        """Title at bottom setting changed"""
        self.config['title_at_bottom'] = widget.get_active()
        self.config.save()

    def on_new_tab_after_current_checkbutton_toggled(self, widget):
        """New tab after current tab """
        self.config['new_tab_after_current_tab'] = widget.get_active()
        self.config.save()

    def on_always_split_with_profile_toggled(self, widget):
        """Always split with profile setting changed"""
        self.config['always_split_with_profile'] = widget.get_active()
        self.config.save()

    def on_allow_bold_checkbutton_toggled(self, widget):
        """Allow bold setting changed"""
        self.config['allow_bold'] = widget.get_active()
        self.config.save()

    def on_show_titlebar_toggled(self, widget):
        """Show titlebar setting changed"""
        self.config['show_titlebar'] = widget.get_active()
        self.config.save()

    def on_copy_on_selection_toggled(self, widget):
        """Copy on selection setting changed"""
        self.config['copy_on_selection'] = widget.get_active()
        self.config.save()

    def on_putty_paste_style_toggled(self, widget):
        """Putty paste style setting changed"""
        self.config['putty_paste_style'] = widget.get_active()
        self.config.save()

    def on_putty_paste_style_source_clipboard_toggled(self, widget):
        """PuTTY paste style source changed"""
        guiget = self.builder.get_object
        clipboardwidget = guiget('putty_paste_style_source_clipboard_radiobutton')
        self.config['putty_paste_style_source_clipboard'] = clipboardwidget.get_active()
        self.config.save()

    def on_smart_copy_toggled(self, widget):
        """Putty paste style setting changed"""
        self.config['smart_copy'] = widget.get_active()
        self.config.save()

    def on_clear_select_on_copy_toggled(self,widget):
        """Clear selection on smart copy"""
        self.config['clear_select_on_copy'] = widget.get_active()
        self.config.save()

    def on_disable_mouse_paste_toggled(self, widget):
        """Disable mouse paste"""
        self.config['disable_mouse_paste'] = widget.get_active()
        self.config.save()

    def on_cursor_blink_toggled(self, widget):
        """Cursor blink setting changed"""
        self.config['cursor_blink'] = widget.get_active()
        self.config.save()

    def on_icon_bell_checkbutton_toggled(self, widget):
        """Icon bell setting changed"""
        self.config['icon_bell'] = widget.get_active()
        self.config.save()

    def on_visual_bell_checkbutton_toggled(self, widget):
        """Visual bell setting changed"""
        self.config['visible_bell'] = widget.get_active()
        self.config.save()

    def on_audible_bell_checkbutton_toggled(self, widget):
        """Audible bell setting changed"""
        self.config['audible_bell'] = widget.get_active()
        self.config.save()

    def on_urgent_bell_checkbutton_toggled(self, widget):
        """Window manager bell setting changed"""
        self.config['urgent_bell'] = widget.get_active()
        self.config.save()

    def on_login_shell_checkbutton_toggled(self, widget):
        """Login shell setting changed"""
        self.config['login_shell'] = widget.get_active()
        self.config.save()

    def on_scroll_on_keystroke_checkbutton_toggled(self, widget):
        """Scroll on keystrong setting changed"""
        self.config['scroll_on_keystroke'] = widget.get_active()
        self.config.save()

    def on_scroll_on_output_checkbutton_toggled(self, widget):
        """Scroll on output setting changed"""
        self.config['scroll_on_output'] = widget.get_active()
        self.config.save()

    def on_delete_binding_combobox_changed(self, widget):
        """Delete binding setting changed"""
        selected = widget.get_active()
        if selected == 1:
            value = 'control-h'
        elif selected == 2:
            value = 'ascii-del'
        elif selected == 3:
            value = 'escape-sequence'
        else:
            value = 'automatic'
        self.config['delete_binding'] = value
        self.config.save()

    def on_backspace_binding_combobox_changed(self, widget):
        """Backspace binding setting changed"""
        selected = widget.get_active()
        if selected == 1:
            value = 'control-h'
        elif selected == 2:
            value = 'ascii-del'
        elif selected == 3:
            value = 'escape-sequence'
        else:
            value = 'automatic'
        self.config['backspace_binding'] = value
        self.config.save()

    def on_scrollback_lines_spinbutton_value_changed(self, widget):
        """Scrollback lines setting changed"""
        value = widget.get_value_as_int()
        self.config['scrollback_lines'] = value
        self.config.save()

    def on_scrollback_infinite_toggled(self, widget):
        """Scrollback infiniteness changed"""
        spinbutton = self.builder.get_object('scrollback_lines_spinbutton')
        value = widget.get_active()
        if value == True:
            spinbutton.set_sensitive(False)
        else:
            spinbutton.set_sensitive(True)
        self.config['scrollback_infinite'] = value
        self.config.save()

    def on_scrollbar_position_combobox_changed(self, widget):
        """Scrollbar position setting changed"""
        selected = widget.get_active()
        if selected == 1:
            value = 'right'
        elif selected == 2:
            value = 'hidden'
        else:
            value = 'left'
        self.config['scrollbar_position'] = value
        self.config.save()

    def on_background_image_file_set(self,widget):
        self.config['background_image'] = widget.get_filename()
        self.config.save()

    def on_background_image_mode_changed(self, widget):
        selected = widget.get_active()
        if selected == 1:
            value = 'scale_and_fit'
        elif selected == 2:
            value = 'scale_and_crop'
        elif selected == 3:
            value = 'tiling'
        else:
            value = 'stretch_and_fill'
        self.config['background_image_mode'] = value
        self.config.save()

    def on_background_image_align_horiz_changed(self, widget):
        selected = widget.get_active()
        if selected == 1:
            value = 'center'
        elif selected == 2:
            value = 'right'
        else:
            value = 'left'
        self.config['background_image_align_horiz'] = value
        self.config.save()

    def on_background_image_align_vert_changed(self, widget):
        selected = widget.get_active()
        if selected == 1:
            value = 'middle'
        elif selected == 2:
            value = 'bottom'
        else:
            value = 'top'
        self.config['background_image_align_vert'] = value
        self.config.save()

    def on_darken_background_scale_value_changed(self, widget):
        """Background darkness setting changed"""
        value = widget.get_value()  # This one is rounded according to the UI.
        if value > 1.0:
          value = 1.0
        self.config['background_darkness'] = value
        self.config.save()

    def on_palette_combobox_changed(self, widget):
        """Palette selector changed"""
        value = None
        active = widget.get_active()

        for key in list(self.palettevalues.keys()):
            if self.palettevalues[key] == active:
                value = key

        if value in self.palettes:
            palette = self.palettes[value]
            palettebits = palette.split(':')
            for palette_id in range(0, NUM_PALETTE_COLORS):
                # Update the visible elements
                color = Gdk.color_parse(palettebits[palette_id])
                self.load_palette_color(palette_id, color)
        elif value == 'custom':
            palettebits = []
            for palette_id in range(0, NUM_PALETTE_COLORS):
                # Save the custom values into the configuration.
                palettebits.append(get_color_string(self.get_palette_color(palette_id)))
            palette = ':'.join(palettebits)
        else:
            err('Unknown palette value: %s' % value)
            return

        self.config['palette'] = palette
        self.config.save()

    def on_foreground_colorbutton_draw(self, widget, cr):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        col = Gdk.color_parse(self.config['foreground_color'])
        cr.rectangle(0, 0, width, height)
        cr.set_source_rgba(0.7, 0.7, 0.7, 1)
        cr.fill()
        cr.rectangle(1, 1, width-2, height-2)
        cr.set_source_rgba(col.red_float, col.green_float, col.blue_float)
        cr.fill()

    def on_foreground_colorbutton_click(self, event, data):
        dialog = Gtk.ColorChooserDialog("Choose Terminal Text Color")
        fg = self.config['foreground_color']
        dialog.set_rgba(Gdk.RGBA.from_color(Gdk.color_parse(self.config['foreground_color'])))
        dialog.connect('notify::rgba', self.on_foreground_colorpicker_color_change)
        res = dialog.run()
        if res != Gtk.ResponseType.OK:
            self.config['foreground_color'] = fg
            self.config.save()
            terminator = Terminator()
            terminator.reconfigure()
        dialog.destroy()

    def on_foreground_colorpicker_color_change(self, widget, color):
        """Foreground color changed"""
        self.config['foreground_color'] = rgba2hex(widget)
        self.config.save()
        terminator = Terminator()
        terminator.reconfigure()

    def on_background_colorbutton_draw(self, widget, cr):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        col = Gdk.color_parse(self.config['background_color'])
        cr.rectangle(0, 0, width, height)
        cr.set_source_rgba(0.7, 0.7, 0.7, 1)
        cr.fill()
        cr.rectangle(1, 1, width-2, height-2)
        cr.set_source_rgba(col.red_float, col.green_float, col.blue_float)
        cr.fill()

    def on_background_colorbutton_click(self, event, data):
        dialog = Gtk.ColorChooserDialog("Choose Terminal Background Color")
        orig = self.config['background_color']
        dialog.connect('notify::rgba', self.on_background_colorpicker_color_change)
        dialog.set_rgba(Gdk.RGBA.from_color(Gdk.color_parse(orig)))
        res = dialog.run()
        if res != Gtk.ResponseType.OK:
            self.config['background_color'] = orig
            self.config.save()
            terminator = Terminator()
            terminator.reconfigure()
        dialog.destroy()

    def on_background_colorpicker_color_change(self, widget, color):
        """Background color changed"""
        self.config['background_color'] = rgba2hex(widget)
        self.config.save()
        terminator = Terminator()
        terminator.reconfigure()

    def get_palette_widget(self, palette_id):
        """Returns the palette widget for the given palette ID."""
        guiget = self.builder.get_object
        return guiget('palette_colorpicker_%d' % (palette_id + 1))

    def get_palette_id(self, widget):
        """Returns the palette ID for the given palette widget."""
        for palette_id in range(0, NUM_PALETTE_COLORS):
            if widget == self.get_palette_widget(palette_id):
                return palette_id
        return None

    def get_palette_color(self, palette_id):
        """Returns the configured Gdk color for the given palette ID."""
        if self.config['palette'] in self.palettes:
            colourpalette = self.palettes[self.config['palette']]
        else:
            colourpalette = self.config['palette'].split(':')
        return Gdk.color_parse(colourpalette[palette_id])

    def on_palette_colorpicker_draw(self, widget, cr):
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        cr.rectangle(0, 0, width, height)
        cr.set_source_rgba(0.7, 0.7, 0.7, 1)
        cr.fill()
        cr.rectangle(1, 1, width-2, height-2)
        col = self.get_palette_color(self.get_palette_id(widget))
        cr.set_source_rgba(col.red_float, col.green_float, col.blue_float)
        cr.fill()

    def load_palette_color(self, palette_id, color):
        """Given a palette ID and a Gdk color, load that color into the
        specified widget."""
        widget = self.get_palette_widget(palette_id)
        widget.queue_draw()

    def replace_palette_color(self, palette_id, color):
        """Replace the configured palette color for the given palette ID
        with the given color."""
        palettebits = self.config['palette'].split(':')
        palettebits[palette_id] = get_color_string(color)
        self.config['palette'] = ':'.join(palettebits)
        self.config.save()

    def load_palette(self):
        """Load the palette from the configuration into the color buttons."""
        colourpalette = self.config['palette'].split(':')
        for palette_id in range(0, NUM_PALETTE_COLORS):
            color = Gdk.color_parse(colourpalette[palette_id])
            self.load_palette_color(palette_id, color)

    def edit_palette_button(self, widget):
        """When the palette colorbutton is clicked, open a dialog to
        configure a custom color."""
        terminator = Terminator()
        palette_id = self.get_palette_id(widget)
        orig = self.get_palette_color(palette_id)

        try:
            # Create the dialog to choose a custom color
            dialog = Gtk.ColorChooserDialog("Choose Palette Color")
            dialog.set_rgba(Gdk.RGBA.from_color(orig))

            def on_color_set(_, color):
                # The color is set, so save the palette config and refresh Terminator
                self.replace_palette_color(palette_id, dialog.get_rgba().to_color())
                terminator.reconfigure()
            dialog.connect('notify::rgba', on_color_set)

            # Show the dialog
            res = dialog.run()
            if res != Gtk.ResponseType.OK:
                # User cancelled the color change, so reset to the original.
                self.replace_palette_color(palette_id, orig)
                terminator.reconfigure()
        finally:
            if dialog:
                dialog.destroy()

    def on_exit_action_combobox_changed(self, widget):
        """Exit action changed"""
        selected = widget.get_active()
        if selected == 1:
            value = 'restart'
        elif selected == 2:
            value = 'hold'
        else:
            value = 'close'
        self.config['exit_action'] = value
        self.config.save()

    def on_custom_url_handler_entry_changed(self, widget):
        """Custom URL handler value changed"""
        self.config['custom_url_handler'] = widget.get_text()
        self.config.save()

    def on_custom_command_entry_changed(self, widget):
        """Custom command value changed"""
        self.config['custom_command'] = widget.get_text()
        self.config.save()

    def on_cursor_color_default_checkbutton_toggled(self, checkbutton):
        """Cursor: Use default colors changed"""
        guiget = self.builder.get_object

        value = checkbutton.get_active()
        guiget('cursor_fg_color').set_sensitive(not value)
        guiget('cursor_bg_color').set_sensitive(not value)

        if not value:
            self.config['cursor_fg_color'] = color2hex(guiget('cursor_fg_color'))
            self.config['cursor_bg_color'] = color2hex(guiget('cursor_bg_color'))
            self.config.save()

        self.config['cursor_color_default'] = value
        self.config.save()

    def on_cursor_fg_color_color_set(self, widget):
        """Cursor foreground color changed"""
        self.config['cursor_fg_color'] = color2hex(widget)
        self.config.save()

    def on_cursor_bg_color_color_set(self, widget):
        """Cursor background color changed"""
        self.config['cursor_bg_color'] = color2hex(widget)
        self.config.save()

    def on_cursor_shape_combobox_changed(self, widget):
        """Cursor shape changed"""
        selected = widget.get_active()
        if selected == 1:
            value = 'underline'
        elif selected == 2:
            value = 'ibeam'
        else:
            value = 'block'
        self.config['cursor_shape'] = value
        self.config.save()

    def on_word_chars_entry_changed(self, widget):
        """Word characters changed"""
        self.config['word_chars'] = widget.get_text()
        self.config.save()

    def on_font_selector_font_set(self, widget):
        """Font changed"""
        self.config['font'] = widget.get_font_name()
        self.config.save()

    def on_title_font_selector_font_set(self, widget):
        """Titlebar Font changed"""
        self.config['title_font'] = widget.get_font_name()
        self.config.save()

    def on_title_receive_bg_color_color_set(self, widget):
        """Title receive background colour changed"""
        self.config['title_receive_bg_color'] = color2hex(widget)
        self.config.save()

    def on_title_receive_fg_color_color_set(self, widget):
        """Title receive foreground colour changed"""
        self.config['title_receive_fg_color'] = color2hex(widget)
        self.config.save()

    def on_title_inactive_bg_color_color_set(self, widget):
        """Title inactive background colour changed"""
        self.config['title_inactive_bg_color'] = color2hex(widget)
        self.config.save()

    def on_title_transmit_bg_color_color_set(self, widget):
        """Title transmit background colour changed"""
        self.config['title_transmit_bg_color'] = color2hex(widget)
        self.config.save()

    def on_title_inactive_fg_color_color_set(self, widget):
        """Title inactive foreground colour changed"""
        self.config['title_inactive_fg_color'] = color2hex(widget)
        self.config.save()

    def on_title_transmit_fg_color_color_set(self, widget):
        """Title transmit foreground colour changed"""
        self.config['title_transmit_fg_color'] = color2hex(widget)
        self.config.save()

    def on_inactive_color_offset_value_changed(self, widget):
        """Inactive color offset setting changed"""
        value = widget.get_value()  # This one is rounded according to the UI.
        if value > 1.0:
          value = 1.0
        self.config['inactive_color_offset'] = value
        self.config.save()
        guiget = self.builder.get_object
        label_widget = guiget('inactive_color_offset_value_label')
        label_widget.set_text('%d%%' % (int(value * 100)))

    def on_inactive_bg_color_offset_value_changed(self, widget):
        """Inactive background color offset setting changed"""
        value = widget.get_value()  # This one is rounded according to the UI.
        if value > 1.0:
          value = 1.0
        self.config['inactive_bg_color_offset'] = value
        self.config.save()
        guiget = self.builder.get_object
        label_widget = guiget('inactive_bg_color_offset_value_label')
        label_widget.set_text('%d%%' % (int(value * 100)))

    def on_handlesize_value_changed(self, widget):
        """Handle size changed"""
        value = widget.get_value()  # This one is rounded according to the UI.
        value = int(value)          # Cast to int.
        if value > 20:
            value = 20
        self.config['handle_size'] = value
        self.config.save()
        guiget = self.builder.get_object
        label_widget = guiget('handlesize_value_label')
        label_widget.set_text(str(value))

    def on_cellheight_value_changed(self, widget):
        """Handles cell height changed"""
        value = widget.get_value()
        value = round(float(value), 1)
        if value > 2.0:
            value = 2.0
        self.config['cell_height'] = value
        self.config.save()
        guiget = self.builder.get_object
        label_widget = guiget('cellheight_value_label')
        label_widget.set_text(str(value))

    def on_cellwidth_value_changed(self, widget):
        """Handles cell width changed"""
        value = widget.get_value()
        value = round(float(value), 1)
        if value > 2.0:
            value = 2.0
        self.config['cell_width'] = value
        self.config.save()
        guiget = self.builder.get_object
        label_widget = guiget('cellwidth_value_label')
        label_widget.set_text(str(value))

    def on_focuscombo_changed(self, widget):
        """Focus type changed"""
        selected = widget.get_active()
        if selected == 1:
            value = 'click'
        elif selected == 2:
            value = 'mouse'
        else:
            value = 'system'
        self.config['focus'] = value
        self.config.save()

    def on_tabposcombo_changed(self, widget):
        """Tab position changed"""
        selected = widget.get_active()
        if selected == 1:
            value = 'bottom'
        elif selected == 2:
            value = 'left'
        elif selected == 3:
            value = 'right'
        elif selected == 4:
            value = 'hidden'
        else:
            value = 'top'
        self.config['tab_position'] = value
        self.config.save()

    def on_broadcastdefault_changed(self, widget):
        """Broadcast default changed"""
        selected = widget.get_active()
        if selected == 0:
            value = 'all'
        elif selected == 2:
            value = 'off'
        else:
            value = 'group'
        self.config['broadcast_default'] = value
        self.config.save()

    def on_winstatecombo_changed(self, widget):
        """Window state changed"""
        selected = widget.get_active()
        if selected == 1:
            value = 'hidden'
        elif selected == 2:
            value = 'maximise'
        elif selected == 3:
            value = 'fullscreen'
        else:
            value = 'normal'
        self.config['window_state'] = value
        self.config.save()

    # helper function, not a signal
    def addprofile(self, name, toclone):
        """Add a profile"""
        guiget = self.builder.get_object

        treeview = guiget('profilelist')
        model = treeview.get_model()
        values = [ r[0] for r in model ]

        newprofile = name
        if newprofile in values:
            i = 1
            while newprofile in values:
                i = i + 1
                newprofile = '%s %d' % (name, i)

        if self.config.add_profile(newprofile, toclone):
            res = model.append([newprofile, True])
            if res:
                path = model.get_path(res)
                treeview.set_cursor(path, column=treeview.get_column(0),
                                    start_editing=True)

        self.layouteditor.update_profiles()

    def on_profileaddbutton_clicked(self, _button):
        """Add a new profile to the list"""
        self.addprofile(_('New Profile'), None)

    def on_profileremovebutton_clicked(self, _button):
        """Remove a profile from the list"""
        guiget = self.builder.get_object

        treeview = guiget('profilelist')
        selection = treeview.get_selection()
        (model, rowiter) = selection.get_selected()
        profile = model.get_value(rowiter, 0)

        if profile == 'default':
            # We shouldn't let people delete this profile
            return

        self.previous_profile_selection = None
        self.config.del_profile(profile)
        model.remove(rowiter)
        selection.select_iter(model.get_iter_first())
        self.layouteditor.update_profiles()

    def on_profileclonebutton_clicked(self, _button):
        """"Clone a profile and add the new one to the list"""
        guiget = self.builder.get_object

        treeview = guiget('profilelist')
        selection = treeview.get_selection()
        (model, rowiter) = selection.get_selected()
        profile = model.get_value(rowiter, 0)

        toclone = self.config.get_profile_by_name(profile)
        self.addprofile(profile, toclone)

    def on_layoutaddbutton_clicked(self, _button):
        """Add a new layout to the list"""
        terminator = Terminator()
        current_layout = terminator.describe_layout()
        guiget = self.builder.get_object

        treeview = guiget('layoutlist')
        model = treeview.get_model()
        values = [ r[0] for r in model ]

        name = _('New Layout')
        if name in values:
            i = 0
            while name in values:
                i = i + 1
                name = '%s %d' % (_('New Layout'), i)

        if self.config.add_layout(name, current_layout):
            res = model.append([name, True])
            if res:
                path = model.get_path(res)
                treeview.set_cursor(path, start_editing=True)

        self.config.save()

    def on_layoutrefreshbutton_clicked(self, _button):
        """Refresh the terminals status and update"""
        terminator = Terminator()
        current_layout = terminator.describe_layout()

        guiget = self.builder.get_object
        treeview = guiget('layoutlist')
        selected = treeview.get_selection()
        (model, rowiter) = selected.get_selected()
        name = model.get_value(rowiter, 0)

        if self.config.replace_layout(name, current_layout):
            treeview.set_cursor(model.get_path(rowiter), column=treeview.get_column(0), start_editing=False)
        self.config.save()
        self.layouteditor.set_layout(name)

    def on_layoutremovebutton_clicked(self, _button):
        """Remove a layout from the list"""
        guiget = self.builder.get_object

        treeview = guiget('layoutlist')
        selection = treeview.get_selection()
        (model, rowiter) = selection.get_selected()
        layout = model.get_value(rowiter, 0)

        if layout == 'default':
            # We shouldn't let people delete this layout
            return

        self.previous_selection = None
        self.config.del_layout(layout)
        model.remove(rowiter)
        selection.select_iter(model.get_iter_first())
        self.config.save()

    def on_link_single_click_toggled(self, checkbox):
        """Configure link_single_click option from checkbox."""
        guiget = self.builder.get_object
        widget = guiget('link_single_click')
        self.config['link_single_click'] = widget.get_active()
        self.config.save()

    def on_use_custom_url_handler_checkbutton_toggled(self, checkbox):
        """Toggling the use_custom_url_handler checkbox needs to alter the
        sensitivity of the custom_url_handler entrybox"""
        guiget = self.builder.get_object
        widget = guiget('custom_url_handler_entry')
        value = checkbox.get_active()

        widget.set_sensitive(value)
        self.config['use_custom_url_handler'] = value
        self.config.save()

    def on_use_custom_command_checkbutton_toggled(self, checkbox):
        """Toggling the use_custom_command checkbox needs to alter the
        sensitivity of the custom_command entrybox"""
        guiget = self.builder.get_object
        widget = guiget('custom_command_entry')
        value = checkbox.get_active()

        widget.set_sensitive(value)
        self.config['use_custom_command'] = value
        self.config.save()

    def on_system_font_checkbutton_toggled(self, checkbox):
        """Toggling the use_system_font checkbox needs to alter the
        sensitivity of the font selector"""
        guiget = self.builder.get_object
        widget = guiget('font_selector')
        value = checkbox.get_active()

        widget.set_sensitive(not value)
        self.config['use_system_font'] = value
        self.config.save()
        
        if self.config['use_system_font'] == True:
            fontname = self.config.get_system_mono_font()
            if fontname is not None:
                widget.set_font_name(fontname)
        else:
            widget.set_font_name(self.config['font'])

    def on_title_system_font_checkbutton_toggled(self, checkbox):
        """Toggling the title_use_system_font checkbox needs to alter the
        sensitivity of the font selector"""
        guiget = self.builder.get_object
        widget = guiget('title_font_selector')
        value = checkbox.get_active()

        widget.set_sensitive(not value)
        self.config['title_use_system_font'] = value
        self.config.save()

        if self.config['title_use_system_font'] == True:
            fontname = self.config.get_system_prop_font()
            if fontname is not None:
                widget.set_font_name(fontname)
        else:
            widget.set_font_name(self.config['title_font'])

    def on_reset_compatibility_clicked(self, widget):
        """Reset the confusing and annoying backspace/delete options to the
        safest values"""
        guiget = self.builder.get_object

        widget = guiget('backspace_binding_combobox')
        widget.set_active(2)
        widget = guiget('delete_binding_combobox')
        widget.set_active(3)

    def on_background_type_toggled(self, _widget):
        """The background type was toggled"""
        self.update_background_tab()

    def update_background_tab(self):
        """Update the background tab"""
        guiget = self.builder.get_object

        # Background type
        backtype = None
        imagewidget = guiget('image_radiobutton')
        transwidget = guiget('transparent_radiobutton')

        if imagewidget.get_active() == True:
            backtype = 'image'
        elif transwidget.get_active() == True:
            backtype = 'transparent'
        else:
            backtype = 'solid'
        self.config['background_type'] = backtype
        self.config.save()

        # toggle sensitivity of widgets related to background image
        for element in ('background_image_file',
                        'background_image_align_horiz_combobox',
                        'background_image_align_vert_combobox',
                        'background_image_mode_combobox'):
            guiget(element).set_sensitive(backtype == 'image')

        if backtype in ('transparent', 'image'):
            guiget('darken_background_scale').set_sensitive(True)
        else:
            guiget('darken_background_scale').set_sensitive(False)

    def on_profile_selection_changed(self, selection):
        """A different profile was selected"""
        (listmodel, rowiter) = selection.get_selected()
        if not rowiter:
            # Something is wrong, just jump to the first item in the list
            treeview = selection.get_tree_view()
            liststore = treeview.get_model()
            selection.select_iter(liststore.get_iter_first())
            return
        profile = listmodel.get_value(rowiter, 0)
        self.set_profile_values(profile)
        self.previous_profile_selection = profile

        widget = self.builder.get_object('profileremovebutton')
        if profile == 'default':
            widget.set_sensitive(False)
        else:
            widget.set_sensitive(True)

    def on_plugin_selection_changed(self, selection):
        """A different plugin was selected"""
        (listmodel, rowiter) = selection.get_selected()
        if not rowiter:
            # Something is wrong, just jump to the first item in the list
            treeview = selection.get_tree_view()
            liststore = treeview.get_model()
            selection.select_iter(liststore.get_iter_first())
            return
        plugin = listmodel.get_value(rowiter, 0)
        self.set_plugin(plugin)
        self.previous_plugin_selection = plugin

        widget = self.builder.get_object('plugintogglebutton')

    def on_plugin_toggled(self, cell, path):
        """A plugin has been enabled or disabled"""
        treeview = self.builder.get_object('pluginlist')
        model = treeview.get_model()
        plugin = model[path][0]

        if not self.plugins[plugin]:
            # Plugin is currently disabled, load it
            self.registry.enable(plugin)
        else:
            # Plugin is currently enabled, unload it
            self.registry.disable(plugin)

        self.plugins[plugin] = not self.plugins[plugin]
        # Update the treeview
        model[path][1] = self.plugins[plugin]

        enabled_plugins = [x for x in self.plugins if self.plugins[x] == True]
        self.config['enabled_plugins'] = enabled_plugins
        self.config.save()

    def set_plugin(self, plugin):
        """Show the preferences for the selected plugin, if any"""
        pluginpanelabel = self.builder.get_object('pluginpanelabel')
        pluginconfig = self.config.plugin_get_config(plugin)
        # FIXME: Implement this, we need to auto-construct a UI for the plugin

    def on_profile_name_edited(self, cell, path, newtext):
        """Update a profile name"""
        oldname = cell.get_property('text')
        if oldname == newtext or oldname == 'default':
            return
        dbg('Changing %s to %s' % (oldname, newtext))
        self.config.rename_profile(oldname, newtext)
        self.config.save()

        widget = self.builder.get_object('profilelist')
        model = widget.get_model()
        itera = model.get_iter(path)
        model.set_value(itera, 0, newtext)

        if oldname == self.previous_profile_selection:
            self.previous_profile_selection = newtext

    def on_layout_selection_changed(self, selection):
        """A different layout was selected"""
        self.layouteditor.on_layout_selection_changed(selection)

    def on_layout_item_selection_changed(self, selection):
        """A different item in the layout was selected"""
        self.layouteditor.on_layout_item_selection_changed(selection)

    def on_layout_profile_chooser_changed(self, widget):
        """A different profile has been selected for this item"""
        self.layouteditor.on_layout_profile_chooser_changed(widget)

    def on_layout_profile_command_changed(self, widget):
        """A different command has been entered for this item"""
        self.layouteditor.on_layout_profile_command_activate(widget)

    def on_layout_profile_workingdir_changed(self, widget):
        """A different working directory has been entered for this item"""
        self.layouteditor.on_layout_profile_workingdir_activate(widget)

    def on_layout_name_edited(self, cell, path, newtext):
        """Update a layout name"""
        oldname = cell.get_property('text')
        if oldname == newtext or oldname == 'default':
            return
        dbg('Changing %s to %s' % (oldname, newtext))
        self.config.rename_layout(oldname, newtext)
        self.config.save()

        widget = self.builder.get_object('layoutlist')
        model = widget.get_model()
        itera = model.get_iter(path)
        model.set_value(itera, 0, newtext)

        if oldname == self.previous_layout_selection:
            self.previous_layout_selection = newtext

        if oldname == self.layouteditor.layout_name:
            self.layouteditor.layout_name = newtext

    def on_color_scheme_combobox_changed(self, widget):
        """Update the fore/background colour pickers"""
        value = None
        guiget = self.builder.get_object
        active = widget.get_active()

        for key in list(self.colorschemevalues.keys()):
            if self.colorschemevalues[key] == active:
                value = key

        fore = guiget('foreground_colorbutton')
        back = guiget('background_colorbutton')
        fore.set_sensitive(True)
        back.set_sensitive(True)

        forecol = None
        backcol = None
        if value in self.colourschemes:
            forecol = self.colourschemes[value][0]
            backcol = self.colourschemes[value][1]
            self.config['foreground_color'] = forecol
            self.config['background_color'] = backcol
        self.config.save()

    def on_use_theme_colors_checkbutton_toggled(self, widget):
        """Update colour pickers"""
        guiget = self.builder.get_object
        active = widget.get_active()

        scheme = guiget('color_scheme_combobox')
        fore = guiget('foreground_colorbutton')
        back = guiget('background_colorbutton')

        if active:
            for widget in [scheme, fore, back]:
                widget.set_sensitive(False)
        else:
            scheme.set_sensitive(True)
            self.on_color_scheme_combobox_changed(scheme)

        self.config['use_theme_colors'] = active
        self.config.save()

    def on_bold_text_is_bright_checkbutton_toggled(self, widget):
        """Bold-is-bright setting changed"""
        self.config['bold_is_bright'] = widget.get_active()
        self.config.save()

    def on_cellrenderer_accel_edited(self, liststore, path, key, mods, _code):
        inpath = path #save for debugging
        trpath = Gtk.TreePath.new_from_string(inpath)
        path   = str(self.treemodelfilter.convert_path_to_child_path(trpath))
        dbg("convert path with filter from: %s to: %s" %
                                        (inpath, path))
        """Handle an edited keybinding"""
        # Ignore `Gdk.KEY_Tab` so that `Shift+Tab` is displayed as `Shift+Tab`
        # in `Preferences>Keybindings` and NOT `Left Tab` (see `Gdk.KEY_ISO_Left_Tab`).
        if mods & Gdk.ModifierType.SHIFT_MASK and key != Gdk.KEY_Tab:
            key_with_shift = Gdk.Keymap.translate_keyboard_state(
                self.keybindings.keymap,
                hardware_keycode=_code,
                state=Gdk.ModifierType.SHIFT_MASK,
                group=0,
            )
            keyval_lower, keyval_upper = Gdk.keyval_convert_case(key)

            # Remove the Shift modifier from `mods` if a new key binding doesn't
            # contain a letter and its key value (`key`) can't be modified by a
            # Shift key.
            if key_with_shift.level != 0 and keyval_lower == keyval_upper:
                mods = Gdk.ModifierType(mods & ~Gdk.ModifierType.SHIFT_MASK)
                key = key_with_shift.keyval

        accel = Gtk.accelerator_name(key, mods)
        current_binding = liststore.get_value(liststore.get_iter(path), 0)
        parsed_accel = Gtk.accelerator_parse(accel)

        keybindutil          = KeyBindUtil()
        keybindings          = self.config["keybindings"]
        #merge give preference to main bindings over plugin
        plugin_keyb_act      = keybindutil.get_all_act_to_keys()
        keybindings          = {**plugin_keyb_act,  **keybindings}

        duplicate_bindings = []
        for conf_binding, conf_accel in keybindings.items():
            if conf_accel is None:
                continue

            parsed_conf_accel = Gtk.accelerator_parse(conf_accel)

            if (
                parsed_accel == parsed_conf_accel
                and current_binding != conf_binding
            ):
                duplicate_bindings.append((conf_binding, conf_accel))

        if duplicate_bindings:
            dialog = Gtk.MessageDialog(
                transient_for=self.window,
                flags=Gtk.DialogFlags.MODAL,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.CLOSE,
                text="Duplicate Key Bindings Are Not Allowed",
            )

            accel_label = Gtk.accelerator_get_label(key, mods)
            # get the first found duplicate
            duplicate_keybinding_name = duplicate_bindings[0][0]

            message = (
                "Key binding `{0}` is already in use to trigger the `{1}` action."
            ).format(accel_label, self.keybindingnames[duplicate_keybinding_name])
            dialog.format_secondary_text(message)

            self.active_message_dialog = dialog
            dialog.run()
            dialog.destroy()
            self.active_message_dialog = None

            return

        celliter = liststore.get_iter_from_string(path)
        liststore.set(celliter, 2, key, 3, mods)

        binding = liststore.get_value(liststore.get_iter(path), 0)
        accel = Gtk.accelerator_name(key, mods)
        self.config['keybindings'][binding] = accel

        plugin_keyb_desc = keybindutil.get_act_to_desc(binding)
        if plugin_keyb_desc:
            dbg("modifying plugin binding: %s, %s, %s" %
                                    (plugin_keyb_desc, binding, accel))
            keybindutil.bindkey([plugin_keyb_desc, binding, accel])
        else:
            dbg("skipping: %s" % binding)
            pass

        self.config.save()

    def on_cellrenderer_accel_cleared(self, liststore, path):
        inpath = path #save for debugging
        trpath = Gtk.TreePath.new_from_string(inpath)
        path   = str(self.treemodelfilter.convert_path_to_child_path(trpath))
        dbg("convert path with filter from: %s to: %s" %
                                        (inpath, path))

        """Handle the clearing of a keybinding accelerator"""
        celliter = liststore.get_iter_from_string(path)
        liststore.set(celliter, 2, 0, 3, 0)

        binding = liststore.get_value(liststore.get_iter(path), 0)
        self.config['keybindings'][binding] = ""
        self.config.save()

    def on_open_manual(self,  widget):
        """Open the fine manual"""
        self.term.key_help()

class LayoutEditor:
    profile_ids_to_profile = None
    profile_profile_to_ids = None
    layout_name = None
    layout_item = None
    builder = None
    treeview = None
    treestore = None
    config = None

    def __init__(self, builder):
        """Initialise ourself"""
        self.config = config.Config()
        self.builder = builder

    def prepare(self, layout=None):
        """Do the things we can't do in __init__"""
        self.treeview = self.builder.get_object('LayoutTreeView')
        self.treestore = self.builder.get_object('LayoutTreeStore')
        self.update_profiles()
        if layout:
            self.set_layout(layout)

    def set_layout(self, layout_name):
        """Load a particular layout"""
        self.layout_name = layout_name
        store = self.treestore
        layout = self.config.layout_get_config(layout_name)
        listitems = {}
        store.clear()

        children = list(layout.keys())
        i = 0
        while children != []:
            child = children.pop()
            child_type = layout[child]['type']
            parent = layout[child]['parent']

            if child_type != 'Window' and parent not in layout:
                # We have an orphan!
                err('%s is an orphan in this layout. Discarding' % child)
                continue
            try:
                parentiter = listitems[parent]
            except KeyError:
                if child_type == 'Window':
                    parentiter = None
                else:
                    # We're not ready for this widget yet
                    children.insert(0, child)
                    continue

            if child_type == 'VPaned':
                child_type = 'Vertical split'
            elif child_type == 'HPaned':
                child_type = 'Horizontal split'

            listitems[child] = store.append(parentiter, [child, child_type])

        treeview = self.builder.get_object('LayoutTreeView')
        treeview.expand_all()

    def update_profiles(self):
        """Update the list of profiles"""
        self.profile_ids_to_profile = {}
        self.profile_profile_to_ids= {}
        chooser = self.builder.get_object('layout_profile_chooser')

        profiles = self.config.list_profiles()
        profiles.sort()
        i = 0
        for profile in profiles:
            self.profile_ids_to_profile[i] = profile
            self.profile_profile_to_ids[profile] = i
            chooser.append_text(profile)
            i = i + 1

    def on_layout_selection_changed(self, selection):
        """A different layout was selected"""
        (listmodel, rowiter) = selection.get_selected()
        if not rowiter:
            # Something is wrong, just jump to the first item in the list
            selection.select_iter(self.treestore.get_iter_first())
            return
        layout = listmodel.get_value(rowiter, 0)
        self.set_layout(layout)
        self.previous_layout_selection = layout

        widget = self.builder.get_object('layoutremovebutton')
        if layout == 'default':
            widget.set_sensitive(False)
        else:
            widget.set_sensitive(True)

        command = self.builder.get_object('layout_profile_command')
        chooser = self.builder.get_object('layout_profile_chooser')
        workdir = self.builder.get_object('layout_profile_workingdir')
        command.set_sensitive(False)
        chooser.set_sensitive(False)
        workdir.set_sensitive(False)

    def on_layout_item_selection_changed(self, selection):
        """A different item in the layout was selected"""
        (treemodel, rowiter) = selection.get_selected()
        if not rowiter:
            return
        item = treemodel.get_value(rowiter, 0)
        self.layout_item = item
        self.set_layout_item(item)

    def set_layout_item(self, item_name):
        """Set a layout item"""
        layout = self.config.layout_get_config(self.layout_name)
        layout_item = layout[self.layout_item]
        command = self.builder.get_object('layout_profile_command')
        chooser = self.builder.get_object('layout_profile_chooser')
        workdir = self.builder.get_object('layout_profile_workingdir')

        if layout_item['type'] != 'Terminal':
            command.set_sensitive(False)
            chooser.set_sensitive(False)
            workdir.set_sensitive(False)
            return

        command.set_sensitive(True)
        chooser.set_sensitive(True)
        workdir.set_sensitive(True)
        if 'command' in layout_item and layout_item['command'] != '':
            command.set_text(layout_item['command'])
        else:
            command.set_text('')

        if 'profile' in layout_item and layout_item['profile'] != '':
            chooser.set_active(self.profile_profile_to_ids[layout_item['profile']])
        else:
            chooser.set_active(0)

        if 'directory' in layout_item and layout_item['directory'] != '':
            workdir.set_text(layout_item['directory'])
        else:
            workdir.set_text('')

    def on_layout_profile_chooser_changed(self, widget):
        """A new profile has been selected for this item"""
        if not self.layout_item:
            return
        profile = widget.get_active_text()
        layout = self.config.layout_get_config(self.layout_name)
        layout[self.layout_item]['profile'] = profile
        self.config.save()

    def on_layout_profile_command_activate(self, widget):
        """A new command has been entered for this item"""
        command = widget.get_text()
        layout = self.config.layout_get_config(self.layout_name)
        layout[self.layout_item]['command'] = command
        self.config.save()

    def on_layout_profile_workingdir_activate(self, widget):
        """A new working directory has been entered for this item"""
        workdir = widget.get_text()
        layout = self.config.layout_get_config(self.layout_name)
        layout[self.layout_item]['directory'] = workdir
        self.config.save()

if __name__ == '__main__':
    from . import util
    util.DEBUG = True
    from . import terminal
    TERM = terminal.Terminal()
    PREFEDIT = PrefsEditor(TERM)

    Gtk.main()
