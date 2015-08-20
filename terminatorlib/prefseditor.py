#!/usr/bin/python
"""Preferences Editor for Terminator.

Load a UIBuilder config file, display it,
populate it with our current config, then optionally read that back out and
write it to a config file

"""

import os
import gtk
import gobject

from util import dbg, err
import config
from keybindings import Keybindings, KeymapError
from translation import _
from encoding import TerminatorEncoding
from terminator import Terminator
from plugin import PluginRegistry
from version import APP_NAME

def color2hex(widget):
    """Pull the colour values out of a Gtk ColorPicker widget and return them
    as 8bit hex values, sinces its default behaviour is to give 16bit values"""
    widcol = widget.get_color()
    return('#%02x%02x%02x' % (widcol.red>>8, widcol.green>>8, widcol.blue>>8))

# FIXME: We need to check that we have represented all of Config() below
class PrefsEditor:
    """Class implementing the various parts of the preferences editor"""
    config = None
    registry = None
    plugins = None
    keybindings = None
    window = None
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
                         'custom': 9}
    colourschemes = {'grey_on_black': ['#aaaaaa', '#000000'],
                     'black_on_yellow': ['#000000', '#ffffdd'],
                     'black_on_white': ['#000000', '#ffffff'],
                     'white_on_black': ['#ffffff', '#000000'],
                     'green_on_black': ['#00ff00', '#000000'],
                     'orange_on_black': ['#e53c00', '#000000'],
                     'ambience': ['#ffffff', '#300a24'],
                     'solarized_light': ['#657b83', '#fdf6e3'],
                     'solarized_dark': ['#839496', '#002b36']}
    palettevalues = {'tango': 0,
                     'linux': 1,
                     'xterm': 2,
                     'rxvt': 3,
                     'ambience': 4,
                     'solarized': 5,
                     'custom': 6}
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
#839496:#6c71c4:#93a1a1:#fdf6e3'}
    keybindingnames = { 'zoom_in'          : _('Increase font size'),
                        'zoom_out'         : _('Decrease font size'),
                        'zoom_normal'      : _('Restore original font size'),
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
                        'split_horiz'      : _('Split horizontally'),
                        'split_vert'       : _('Split vertically'),
                        'close_term'       : _('Close terminal'),
                        'copy'             : _('Copy selected text'),
                        'paste'            : _('Paste clipboard'),
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
                        'toggle_zoom'      : _('Maximise terminal'),
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
                        'group_all'        : _('Group all terminals'),
                        'group_all_toggle' : _('Group/Ungroup all terminals'),
                        'ungroup_all'      : _('Ungroup all terminals'),
                        'group_tab'        : _('Group terminals in tab'),
                        'group_tab_toggle' : _('Group/Ungroup terminals in tab'),
                        'ungroup_tab'      : _('Ungroup terminals in tab'),
                        'new_window'       : _('Create a new window'),
                        'new_terminator'   : _('Spawn a new Terminator process'),
                        'broadcast_off'    : _('Don\'t broadcast key presses'),
                        'broadcast_group'  : _('Broadcast key presses to group'),
                        'broadcast_all'    : _('Broadcast key events to all'),
                        'insert_number'    : _('Insert terminal number'),
                        'insert_padded'    : _('Insert padded terminal number'),
                        'edit_window_title': _('Edit window title'),
                        'layout_launcher'  : _('Open layout launcher window'),
                        'next_profile'     : _('Switch to next profile'),
                        'previous_profile' : _('Switch to previous profile'), 
                        'help'             : _('Open the manual')
            }

    def __init__ (self, term):
        self.config = config.Config()
        self.config.base.reload()
        self.term = term
        self.builder = gtk.Builder()
        self.builder.set_translation_domain(APP_NAME)
        self.keybindings = Keybindings()
        try:
            # Figure out where our library is on-disk so we can open our
            (head, _tail) = os.path.split(config.__file__)
            librarypath = os.path.join(head, 'preferences.glade')
            gladefile = open(librarypath, 'r')
            gladedata = gladefile.read()
        except Exception, ex:
            print "Failed to find preferences.glade"
            print ex
            return

        self.builder.add_from_string(gladedata)
        self.window = self.builder.get_object('prefswin')

        icon_theme = gtk.icon_theme_get_default()
        if icon_theme.lookup_icon('terminator-preferences', 48, 0):
            self.window.set_icon_name('terminator-preferences')
        else:
            dbg('Unable to load Terminator preferences icon')
            icon = self.window.render_icon(gtk.STOCK_DIALOG_INFO, gtk.ICON_SIZE_BUTTON)
            self.window.set_icon(icon)

        self.layouteditor = LayoutEditor(self.builder)
        self.builder.connect_signals(self)
        self.layouteditor.prepare()
        self.window.show_all()
        try:
            self.config.inhibit_save()
            self.set_values()
        except Exception, e:
            err('Unable to set values: %s' % e)
        self.config.uninhibit_save()

    def on_closebutton_clicked(self, _button):
        """Close the window"""
        terminator = Terminator()
        terminator.reconfigure()
        self.window.destroy()
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
        # scroll_tabbar
        widget = guiget('scrolltabbarcheck')
        widget.set_active(self.config['scroll_tabbar'])
        # homogeneous_tabbar
        widget = guiget('homogeneouscheck')
        widget.set_active(self.config['homogeneous_tabbar'])
        # DBus Server
        widget = guiget('dbuscheck')
        widget.set_active(self.config['dbus'])
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
        #Hide size text from the title bar
        widget = guiget('title_hide_sizetextcheck')
        widget.set_active(self.config['title_hide_sizetext'])
        #Always split with profile
        widget = guiget('always_split_with_profile')
        widget.set_active(self.config['always_split_with_profile'])
        #Titlebar font selector
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

        ## Profile tab
        # Populate the profile list
        widget = guiget('profilelist')
        liststore = widget.get_model()
        profiles = self.config.list_profiles()
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
        if terminator.layoutname:
            layout_to_highlight = terminator.layoutname
        else:
            layout_to_highlight = 'default'
        selection.select_iter(self.layoutiters[layout_to_highlight])
        # Now set up the selection changed handler for the layout itself
        widget = guiget('LayoutTreeView')
        selection = widget.get_selection()
        selection.connect('changed', self.on_layout_item_selection_changed)

        ## Keybindings tab
        widget = guiget('keybindingtreeview')
        liststore = widget.get_model()
        liststore.set_sort_column_id(0, gtk.SORT_ASCENDING)
        keybindings = self.config['keybindings']
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

        ## Plugins tab
        # Populate the plugin list
        widget = guiget('pluginlist')
        liststore = widget.get_model()
        self.registry = PluginRegistry()
        self.pluginiters = {}
        pluginlist = self.registry.get_available_plugins()
        self.plugins = {}
        for plugin in pluginlist:
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

        dbg('PrefsEditor::set_profile_values: Setting profile %s' % profile)

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
        # Anti-alias
        widget = guiget('antialias_checkbutton')
        widget.set_active(self.config['antialias'])
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
        # Cursor colour
        widget = guiget('cursor_color')
        try:
            widget.set_color(gtk.gdk.Color(self.config['cursor_color']))
        except ValueError:
            self.config['cursor_color'] = "#FFFFFF"
            widget.set_color(gtk.gdk.Color(self.config['cursor_color']))

        ## Command tab
        # Login shell
        widget = guiget('login_shell_checkbutton')
        widget.set_active(self.config['login_shell'])
        # Login records
        widget = guiget('update_records_checkbutton')
        widget.set_active(self.config['update_records'])
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
        widget = guiget('foreground_colorpicker')
        widget.set_color(gtk.gdk.Color(self.config['foreground_color']))
        if scheme == 'custom':
            widget.set_sensitive(True)
        else:
            widget.set_sensitive(False)
        # Background color
        widget = guiget('background_colorpicker')
        widget.set_color(gtk.gdk.Color(self.config['background_color']))
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
        colourpalette = self.config['palette'].split(':')
        for i in xrange(1, 17):
            widget = guiget('palette_colorpicker_%d' % i)
            widget.set_color(gtk.gdk.Color(colourpalette[i - 1]))
        # Now set the palette selector widget
        widget = guiget('palette_combobox')
        widget.set_active(self.palettevalues[palette])
        # Titlebar colors
        for bit in ['title_transmit_fg_color', 'title_transmit_bg_color',
            'title_receive_fg_color', 'title_receive_bg_color',
            'title_inactive_fg_color', 'title_inactive_bg_color']:
            widget = guiget(bit)
            widget.set_color(gtk.gdk.Color(self.config[bit]))
        # Inactive terminal shading
        widget = guiget('inactive_color_offset')
        widget.set_value(float(self.config['inactive_color_offset']))
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
        elif self.config['background_type'] == 'image':
            guiget('image_radiobutton').set_active(True)
        elif self.config['background_type'] == 'transparent':
            guiget('transparent_radiobutton').set_active(True)
        self.update_background_tab()
        # Background image file
        if self.config['background_image'] != '':
            widget = guiget('background_image_filechooser')
            if self.config['background_image'] is not None and \
               self.config['background_image'] != '':
                widget.set_filename(self.config['background_image'])
        # Background image scrolls
        widget = guiget('scroll_background_checkbutton')
        widget.set_active(self.config['scroll_background'])
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
        # Scroll on outut
        widget = guiget('scroll_on_output_checkbutton')
        widget.set_active(self.config['scroll_on_output'])
        # Scroll on keystroke
        widget = guiget('scroll_on_keystroke_checkbutton')
        widget.set_active(self.config['scroll_on_keystroke'])
        # Scroll in alternate mode
        widget = guiget('alternate_screen_scroll_checkbutton')
        widget.set_active(self.config['alternate_screen_scroll'])

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
        # Encoding
        rowiter = None
        widget = guiget('encoding_combobox')
        encodingstore = guiget('EncodingListStore')
        value = self.config['encoding']
        encodings = TerminatorEncoding().get_list()
        encodings.sort(lambda x, y: cmp(x[2].lower(), y[2].lower()))

        for encoding in encodings:
            if encoding[1] is None:
                continue

            label = "%s %s" % (encoding[2], encoding[1])
            rowiter = encodingstore.append([label, encoding[1]])

            if encoding[1] == value:
                widget.set_active_iter(rowiter)

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

    def on_winbordercheck_toggled(self, widget):
        """Window border setting changed"""
        self.config['borderless'] = not widget.get_active()
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

    def on_always_split_with_profile_toggled(self, widget):
        """Always split with profile setting changed"""
        self.config['always_split_with_profile'] = widget.get_active()
        self.config.save()

    def on_allow_bold_checkbutton_toggled(self, widget):
        """Allow bold setting changed"""
        self.config['allow_bold'] = widget.get_active()
        self.config.save()

    def on_antialias_checkbutton_toggled(self, widget):
        """Anti-alias setting changed"""
        self.config['antialias'] = widget.get_active()
        self.config.save()

    def on_show_titlebar_toggled(self, widget):
        """Show titlebar setting changed"""
        self.config['show_titlebar'] = widget.get_active()
        self.config.save()

    def on_copy_on_selection_toggled(self, widget):
        """Copy on selection setting changed"""
        self.config['copy_on_selection'] = widget.get_active()
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

    def on_update_records_checkbutton_toggled(self, widget):
        """Update records setting changed"""
        self.config['update_records'] = widget.get_active()
        self.config.save()

    def on_scroll_background_checkbutton_toggled(self, widget):
        """Scroll background setting changed"""
        self.config['scroll_background'] = widget.get_active()
        self.config.save()

    def on_alternate_screen_scroll_checkbutton_toggled(self, widget):
        """Scroll in alt-mode setting changed"""
        self.config['alternate_screen_scroll'] = widget.get_active()
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
            value == 'escape-sequence'
        else:
            value = 'automatic'
        self.config['backspace_binding'] = value
        self.config.save()

    def on_encoding_combobox_changed(self, widget):
        """Encoding setting changed"""
        selected = widget.get_active_iter()
        liststore = widget.get_model()
        value = liststore.get_value(selected, 1)

        self.config['encoding'] = value
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

    def on_darken_background_scale_change_value(self, widget, scroll, value):
        """Background darkness setting changed"""
        self.config['background_darkness'] = round(value, 2)
        self.config.save()

    def on_background_image_filechooser_file_set(self, widget):
        """Background image setting changed"""
        self.config['background_image'] = widget.get_filename()
        self.config.save()

    def on_palette_combobox_changed(self, widget):
        """Palette selector changed"""
        value = None
        guiget = self.builder.get_object
        active = widget.get_active()

        for key in self.palettevalues.keys():
            if self.palettevalues[key] == active:
                value = key

        if value == 'custom':
            sensitive = True
        else:
            sensitive = False

        for num in xrange(1, 17):
            picker = guiget('palette_colorpicker_%d' % num)
            picker.set_sensitive(sensitive)

        if value in self.palettes:
            palette = self.palettes[value]
            palettebits = palette.split(':')
            for num in xrange(1, 17):
                # Update the visible elements
                picker = guiget('palette_colorpicker_%d' % num)
                picker.set_color(gtk.gdk.Color(palettebits[num - 1]))
        elif value == 'custom':
            palettebits = []
            for num in xrange(1, 17):
                picker = guiget('palette_colorpicker_%d' % num)
                palettebits.append(color2hex(picker))
            palette = ':'.join(palettebits)
        else:
            err('Unknown palette value: %s' % value)
            return

        self.config['palette'] = palette
        self.config.save()

    def on_background_colorpicker_color_set(self, widget):
        """Background color changed"""
        self.config['background_color'] = color2hex(widget)
        self.config.save()

    def on_foreground_colorpicker_color_set(self, widget):
        """Foreground color changed"""
        self.config['foreground_color'] = color2hex(widget)
        self.config.save()

    def on_palette_colorpicker_color_set(self, widget):
        """A palette colour changed"""
        palette = None
        palettebits = []
        guiget = self.builder.get_object

        # FIXME: We do this at least once elsewhere. refactor!
        for num in xrange(1, 17):
            picker = guiget('palette_colorpicker_%d' % num)
            value = color2hex(picker)
            palettebits.append(value)
        palette = ':'.join(palettebits)

        self.config['palette'] = palette
        self.config.save()

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

    def on_cursor_color_color_set(self, widget):
        """Cursor colour changed"""
        self.config['cursor_color'] = color2hex(widget)
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
        """Title transmit backgruond colour changed"""
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

    def on_inactive_color_offset_change_value(self, widget, scroll, value):
        """Inactive color offset setting changed"""
        if value > 1.0:
          value = 1.0
        self.config['inactive_color_offset'] = round(value, 2)
        self.config.save()

    def on_handlesize_change_value(self, widget, scroll, value):
        """Handle size changed"""
        value = int(value)
        if value > 5:
            value = 5
        self.config['handle_size'] = value
        self.config.save()

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

    def on_profileaddbutton_clicked(self, _button):
        """Add a new profile to the list"""
        guiget = self.builder.get_object

        treeview = guiget('profilelist')
        model = treeview.get_model()
        values = [ r[0] for r in model ]

        newprofile = _('New Profile')
        if newprofile in values:
            i = 1
            while newprofile in values:
                i = i + 1
                newprofile = '%s %d' % (_('New Profile'), i)

        if self.config.add_profile(newprofile):
            res = model.append([newprofile, True])
            if res:
                path = model.get_path(res)
                treeview.set_cursor(path, focus_column=treeview.get_column(0),
                                    start_editing=True)

        self.layouteditor.update_profiles()

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
                treeview.set_cursor(path, focus_column=treeview.get_column(0),
                                    start_editing=True)

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
            treeview.set_cursor(model.get_path(rowiter), focus_column=treeview.get_column(0), start_editing=False)
        self.config.save()

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
        if transwidget.get_active() == True:
            backtype = 'transparent'
        elif imagewidget.get_active() == True:
            backtype = 'image'
        else:
            backtype = 'solid'
        self.config['background_type'] = backtype
        self.config.save()

        if backtype == 'image':
            guiget('background_image_filechooser').set_sensitive(True)
            guiget('scroll_background_checkbutton').set_sensitive(True)
        else:
            guiget('background_image_filechooser').set_sensitive(False)
            guiget('scroll_background_checkbutton').set_sensitive(False)
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
        oldname_broken = cell.get_property('text')
        
        guiget = self.builder.get_object
        treeview = guiget('profilelist')
        treeselection = treeview.get_selection()
        treeselection.select_path(path)
        (model, pathlist) = treeselection.get_selected_rows()
        tree_iter = model.get_iter(pathlist[0])
        oldname = model.get_value(tree_iter,0)
        if oldname != oldname_broken:
            dbg('edited signal provides the wrong cell: %s != %s' %(oldname, oldname_broken))

        if oldname == newtext or oldname == 'default':
            return
        dbg('PrefsEditor::on_profile_name_edited: Changing %s to %s' %
        (oldname, newtext))
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
        oldname_broken = cell.get_property('text')

        guiget = self.builder.get_object
        treeview = guiget('layoutlist')
        treeselection = treeview.get_selection()
        treeselection.select_path(path)
        (model, pathlist) = treeselection.get_selected_rows()
        tree_iter = model.get_iter(pathlist[0])
        oldname = model.get_value(tree_iter,0)
        if oldname != oldname_broken:
            dbg('edited signal provides the wrong cell: %s != %s' %(oldname, oldname_broken))

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

        for key in self.colorschemevalues.keys():
            if self.colorschemevalues[key] == active:
                value = key

        fore = guiget('foreground_colorpicker')
        back = guiget('background_colorpicker')
        if value == 'custom':
            fore.set_sensitive(True)
            back.set_sensitive(True)
        else:
            fore.set_sensitive(False)
            back.set_sensitive(False)

        forecol = None
        backcol = None
        if value in self.colourschemes:
            forecol = self.colourschemes[value][0]
            backcol = self.colourschemes[value][1]
        elif value == 'custom':
            forecol = color2hex(fore)
            backcol = color2hex(back)
        else:
            err('Unknown colourscheme value: %s' % value)
            return

        fore.set_color(gtk.gdk.Color(forecol))
        back.set_color(gtk.gdk.Color(backcol))

        self.config['foreground_color'] = forecol
        self.config['background_color'] = backcol
        self.config.save()

    def on_use_theme_colors_checkbutton_toggled(self, widget):
        """Update colour pickers"""
        guiget = self.builder.get_object
        active = widget.get_active()

        scheme = guiget('color_scheme_combobox')
        fore = guiget('foreground_colorpicker')
        back = guiget('background_colorpicker')

        if active:
            for widget in [scheme, fore, back]:
                widget.set_sensitive(False)
        else:
            scheme.set_sensitive(True)
            self.on_color_scheme_combobox_changed(scheme)

        self.config['use_theme_colors'] = active
        self.config.save()

    def on_cellrenderer_accel_edited(self, liststore, path, key, mods, _code):
        """Handle an edited keybinding"""
        celliter = liststore.get_iter_from_string(path)
        liststore.set(celliter, 2, key, 3, mods)

        binding = liststore.get_value(liststore.get_iter(path), 0)
        accel = gtk.accelerator_name(key, mods)
        self.config['keybindings'][binding] = accel
        self.config.save()

    def on_cellrenderer_accel_cleared(self, liststore, path):
        """Handle the clearing of a keybinding accelerator"""
        celliter = liststore.get_iter_from_string(path)
        liststore.set(celliter, 2, 0, 3, 0)

        binding = liststore.get_value(liststore.get_iter(path), 0)
        self.config['keybindings'][binding] = None
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

        children = layout.keys()
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
        model = chooser.get_model()

        model.clear()

        profiles = self.config.list_profiles()
        profiles.sort()
        i = 0
        for profile in profiles:
            self.profile_ids_to_profile[i] = profile
            self.profile_profile_to_ids[profile] = i
            model.append([profile])
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
        if layout_item.has_key('command') and layout_item['command'] != '':
            command.set_text(layout_item['command'])
        else:
            command.set_text('')

        if layout_item.has_key('profile') and layout_item['profile'] != '':
            chooser.set_active(self.profile_profile_to_ids[layout_item['profile']])
        else:
            chooser.set_active(0)

        if layout_item.has_key('directory') and layout_item['directory'] != '':
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
    import util
    util.DEBUG = True
    import terminal
    TERM = terminal.Terminal()
    PREFEDIT = PrefsEditor(TERM)

    gtk.main()
