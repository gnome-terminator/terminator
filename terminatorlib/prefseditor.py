#!/usr/bin/python
"""Preferences Editor for Terminator. 

Load a UIBuilder config file, display it,
populate it with our current config, then optionally read that back out and
write it to a config file

"""

import os
import gtk

from util import dbg
import config
from keybindings import Keybindings, KeymapError
from translation import _
from terminator import Terminator

# FIXME: We need to check that we have represented all of Config() below
class PrefsEditor:
    """Class implementing the various parts of the preferences editor"""
    config = None
    keybindings = None
    window = None
    builder = None
    previous_layout_selection = None
    previous_profile_selection = None
    colorschemevalues = {'black_on_yellow': 0, 
                         'black_on_white': 1,
                         'grey_on_black': 2,
                         'green_on_black': 3,
                         'white_on_black': 4,
                         'orange_on_black': 5,
                         'custom': 6}

    keybindingnames = { 'zoom_in'          : 'Increase font size',
                        'zoom_out'         : 'Decrease font size',
                        'zoom_normal'      : 'Restore original font size',
                        'new_tab'          : 'Create a new tab',
                        'cycle_next'       : 'Focus the next terminal',
                        'cycle_prev'       : 'Focus the previous terminal',
                        'go_next'          : 'Focus the next terminal',
                        'go_prev'          : 'Focus the previous terminal',
                        'go_up'            : 'Focus the terminal above',
                        'go_down'          : 'Focus the terminal below',
                        'go_left'          : 'Focus the terminal left',
                        'go_right'         : 'Focus the terminal right',
                        'split_horiz'      : 'Split horizontally',
                        'split_vert'       : 'Split vertically',
                        'close_term'       : 'Close terminal',
                        'copy'             : 'Copy selected text',
                        'paste'            : 'Paste clipboard',
                        'toggle_scrollbar' : 'Show/Hide the scrollbar',
                        'search'           : 'Search terminal scrollback',
                        'close_window'     : 'Close window',
                        'resize_up'        : 'Resize the terminal up',
                        'resize_down'      : 'Resize the terminal down',
                        'resize_left'      : 'Resize the terminal left',
                        'resize_right'     : 'Resize the terminal right',
                        'move_tab_right'   : 'Move the tab right',
                        'move_tab_left'    : 'Move the tab left',
                        'toggle_zoom'      : 'Maximise terminal',
                        'scaled_zoom'      : 'Zoom terminal',
                        'next_tab'         : 'Switch to the next tab',
                        'prev_tab'         : 'Switch to the previous tab',
                        'switch_to_tab_1'  : 'Switch to the first tab',
                        'switch_to_tab_2'  : 'Switch to the second tab',
                        'switch_to_tab_3'  : 'Switch to the third tab',
                        'switch_to_tab_4'  : 'Switch to the fourth tab',
                        'switch_to_tab_5'  : 'Switch to the fifth tab',
                        'switch_to_tab_6'  : 'Switch to the sixth tab',
                        'switch_to_tab_7'  : 'Switch to the seventh tab',
                        'switch_to_tab_8'  : 'Switch to the eighth tab',
                        'switch_to_tab_9'  : 'Switch to the ninth tab',
                        'switch_to_tab_10' : 'Switch to the tenth tab',
                        'full_screen'      : 'Toggle fullscreen',
                        'reset'            : 'Reset the terminal',
                        'reset_clear'      : 'Reset and clear the terminal',
                        'hide_window'      : 'Toggle window visibility',
                        'group_all'        : 'Group all terminals',
                        'ungroup_all'      : 'Ungroup all terminals',
                        'group_tab'        : 'Group terminals in tab',
                        'ungroup_tab'      : 'Ungroup terminals in tab',
                        'new_window'       : 'Create a new window',
                        'new_terminator'   : 'Spawn a new Terminator process',
            }

    def __init__ (self, term):
        self.config = config.Config()
        self.term = term
        self.builder = gtk.Builder()
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
        self.set_values()
        self.builder.connect_signals(self)
        self.window.show_all()

    def on_cancelbutton_clicked(self, _button):
        """Close the window"""
        self.window.destroy()
        del(self)

    def on_okbutton_clicked(self, _button):
        """Save the config"""
        self.store_values()
        self.config.save()
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
        else:
            active = 0
        widget.set_active(active)

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
        selection.select_iter(self.layoutiters['default'])

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
        # FIXME: Implement this

    def store_values(self):
        """Store the values from the GUI back into Config()"""
        guiget = self.builder.get_object

        ## Global tab
        # Focus
        widget = guiget('focuscombo')
        selected = widget.get_active()
        if selected == 0:
            value = 'system'
        elif selected == 1:
            value = 'click'
        elif selected == 2:
            value = 'mouse'
        self.config['focus'] = value
        # Handle size
        widget = guiget('handlesize')
        self.config['handle_size'] = int(widget.get_value())
        # Window geometry
        widget = guiget('wingeomcheck')
        self.config['geometry_hinting'] = widget.get_active()
        # Window state
        widget = guiget('winstatecombo')
        selected = widget.get_active()
        if selected == 0:
            value = 'normal'
        elif selected == 1:
            value = 'hidden'
        elif selected == 2:
            value = 'maximise'
        elif selected == 3:
            value = 'fullscreen'
        self.config['window_state'] = value
        # Window borders
        widget = guiget('winbordercheck')
        self.config['borderless'] = not widget.get_active()
        # Tab position
        widget = guiget('tabposcombo')
        selected = widget.get_active()
        if selected == 0:
            value = 'top'
        elif selected == 1:
            value = 'bottom'
        elif selected == 2:
            value = 'left'
        elif selected == 3:
            value = 'right'
        self.config['tab_position'] = value

        ## Profile tab
        self.store_profile_values()

        ## Layouts tab
        self.store_layout(self.previous_layout_selection)

        ## Keybindings tab
        keybindings = self.config['keybindings']
        liststore = guiget('KeybindingsListStore')
        for keybinding in liststore:
            accel = gtk.accelerator_name(keybinding[2], keybinding[3])
            keybindings[keybinding[0]] = accel

        ## Plugins tab
        # FIXME: Implement this

    def set_profile_values(self, profile):
        """Update the profile values for a given profile"""
        self.config.set_profile(profile)
        guiget = self.builder.get_object

        dbg('PrefsEditor::set_profile_values: Setting profile %s' % profile)

        ## General tab
        # Use system font
        widget = guiget('system-font-checkbutton')
        widget.set_active(self.config['use_system_font'])
        self.on_system_font_checkbutton_toggled(widget)
        # Font selector
        widget = guiget('font-selector')
        if self.config['use_system_font'] == True:
            widget.set_font_name(self.config.get_system_font())
        else:
            widget.set_font_name(self.config['font'])
        # Allow bold text
        widget = guiget('allow-bold-checkbutton')
        widget.set_active(self.config['allow_bold'])
        # Visual terminal bell
        widget = guiget('visual-bell-checkbutton')
        widget.set_active(self.config['visible_bell'])
        # Audible terminal bell
        widget = guiget('audible-bell-checkbutton')
        widget.set_active(self.config['audible_bell'])
        # WM_URGENT terminal bell
        widget = guiget('urgent-bell-checkbutton')
        widget.set_active(self.config['urgent_bell'])
        # Show titlebar
        widget = guiget('show_titlebar')
        widget.set_active(self.config['show_titlebar'])
        # Word chars
        widget = guiget('word-chars-entry')
        widget.set_text(self.config['word_chars'])
        # Cursor shape
        widget = guiget('cursor-shape-combobox')
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
        widget.set_color(gtk.gdk.Color(self.config['cursor_color']))

        ## Command tab
        # Login shell
        widget = guiget('login-shell-checkbutton')
        widget.set_active(self.config['login_shell'])
        # Login records
        widget = guiget('update-records-checkbutton')
        widget.set_active(self.config['update_records'])
        # Use Custom command
        widget = guiget('use-custom-command-checkbutton')
        widget.set_active(self.config['use_custom_command'])
        self.on_use_custom_command_checkbutton_toggled(widget)
        # Custom Command
        widget = guiget('custom-command-entry')
        widget.set_text(self.config['custom_command'])
        # Exit action
        widget = guiget('exit-action-combobox')
        if self.config['exit_action'] == 'restart':
            widget.set_active(1)
        elif self.config['exit_action'] == 'hold':
            widget.set_active(2)
        else:
            # Default is to close the terminal
            widget.set_active(0)

        ## Colors tab
        # Use system colors
        widget = guiget('use-theme-colors-checkbutton')
        widget.set_active(self.config['use_theme_colors'])
        # Colorscheme
        widget = guiget('color-scheme-combobox')
        scheme = self.config['color_scheme']
        if scheme not in self.colorschemevalues:
            scheme = 'grey_on_black'
        widget.set_active(self.colorschemevalues[scheme])
        # Foreground color
        widget = guiget('foreground-colorpicker')
        widget.set_color(gtk.gdk.Color(self.config['foreground_color']))
        if scheme == 'custom':
            widget.set_sensitive(True)
        else:
            widget.set_sensitive(False)
        # Background color
        widget = guiget('background-colorpicker')
        widget.set_color(gtk.gdk.Color(self.config['background_color']))
        if scheme == 'custom':
            widget.set_sensitive(True)
        else:
            widget.set_sensitive(False)
        # Palette
        palette = self.config['palette'].split(':')
        for i in xrange(1, 17):
            widget = guiget('palette-colorpicker-%d' % i)
            widget.set_color(gtk.gdk.Color(palette[i - 1]))
        # Titlebar colors
        for bit in ['title_transmit_fg_color', 'title_transmit_bg_color',
            'title_receive_fg_color', 'title_receive_bg_color',
            'title_inactive_fg_color', 'title_inactive_bg_color']:
            widget = guiget(bit)
            widget.set_color(gtk.gdk.Color(self.config[bit]))

        ## Background tab
        # Radio values
        if self.config['background_type'] == 'solid':
            guiget('solid-radiobutton').set_active(True)
        elif self.config['background_type'] == 'image':
            guiget('image-radiobutton').set_active(True)
        elif self.config['background_type'] == 'transparent':
            guiget('transparent-radiobutton').set_active(True)
        self.update_background_tab()
        # Background image file
        if self.config['background_image'] != '':
            widget = guiget('background-image-filechooser')
            if self.config['background_image'] is not None and \
               self.config['background_image'] != '':
                widget.set_filename(self.config['background_image'])
        # Background image scrolls
        widget = guiget('scroll-background-checkbutton')
        widget.set_active(self.config['scroll_background'])
        # Background shading
        widget = guiget('background_darkness_scale')
        widget.set_value(float(self.config['background_darkness']))

        ## Scrolling tab
        # Scrollbar position
        widget = guiget('scrollbar-position-combobox')
        value = self.config['scrollbar_position']
        if value == 'left':
            widget.set_active(0)
        elif value in ['disabled', 'hidden']:
            widget.set_active(2)
        else:
            widget.set_active(1)
        # Scrollback lines
        widget = guiget('scrollback-lines-spinbutton')
        widget.set_value(self.config['scrollback_lines'])
        # Scroll on outut
        widget = guiget('scroll-on-output-checkbutton')
        widget.set_active(self.config['scroll_on_output'])
        # Scroll on keystroke
        widget = guiget('scroll-on-keystroke-checkbutton')
        widget.set_active(self.config['scroll_on_keystroke'])

        ## Compatibility tab
        # Backspace key
        widget = guiget('backspace-binding-combobox')
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
        widget = guiget('delete-binding-combobox')
        value = self.config['delete_binding']
        if value == 'control-h':
            widget.set_active(1)
        elif value == 'ascii-del':
            widget.set_active(2)
        elif value == 'escape-sequence':
            widget.set_active(3)
        else:
            widget.set_active(0)

    def store_profile_values(self):
        """Pull out all the settings before switching profile"""
        guiget = self.builder.get_object

        ## General tab
        # Use system font
        widget = guiget('system-font-checkbutton')
        self.config['use_system_font'] = widget.get_active()
        # Font
        widget = guiget('font-selector')
        self.config['font'] = widget.get_font_name()
        # Allow bold
        widget = guiget('allow-bold-checkbutton')
        self.config['allow_bold'] = widget.get_active()
        # Visual Bell
        widget = guiget('visual-bell-checkbutton')
        self.config['visible_bell'] = widget.get_active()
        # Audible Bell
        widget = guiget('audible-bell-checkbutton')
        self.config['audible_bell'] = widget.get_active()
        # Urgent Bell
        widget = guiget('urgent-bell-checkbutton')
        self.config['urgent_bell'] = widget.get_active()
        # Show titlebar
        widget = guiget('show_titlebar')
        self.config['show_titlebar'] = widget.get_active()
        # Word chars
        widget = guiget('word-chars-entry')
        self.config['word_chars'] = widget.get_text()
        # Cursor Shape
        widget = guiget('cursor-shape-combobox')
        selected = widget.get_active()
        if selected == 0:
            value = 'block'
        elif selected == 1:
            value = 'underline'
        elif selected == 2:
            value = 'ibeam'
        self.config['cursor_shape'] = value
        # Cursor Blink
        widget = guiget('cursor_blink')
        self.config['cursor_blink'] = widget.get_active()
        # Cursor Colour
        widget = guiget('cursor_color')
        self.config['cursor_color'] = widget.get_color().to_string()
        
        ## Command tab
        # Login shell
        widget = guiget('login-shell-checkbutton')
        self.config['login_shell'] = widget.get_active()
        # Update records
        widget = guiget('update-records-checkbutton')
        self.config['update_records'] = widget.get_active()
        # Use custom command
        widget = guiget('use-custom-command-checkbutton')
        self.config['use_custom_command'] = widget.get_active()
        # Custom command
        widget = guiget('custom-command-entry')
        self.config['custom_command'] = widget.get_text()
        # Exit action
        widget = guiget('exit-action-combobox')
        selected = widget.get_active()
        if selected == 0:
            value = 'close'
        elif selected == 1:
            value = 'restart'
        elif selected == 2:
            value = 'hold'
        self.config['exit_action'] = value

        ## Colours tab
        # Use system colours
        widget = guiget('use-theme-colors-checkbutton')
        self.config['use_theme_colors'] = widget.get_active()
        # Colour scheme
        widget = guiget('color-scheme-combobox')
        selected = widget.get_active()
        if selected == 0:
            value = 'black_on_yellow'
        elif selected == 1:
            value = 'black_on_white'
        elif selected == 2:
            value = 'grey_on_black'
        elif selected == 3:
            value = 'green_on_black'
        elif selected == 4:
            value = 'white_on_black'
        elif selected == 5:
            value = 'orange_on_black'
        elif selected == 6:
            value = 'custom'
        self.config['color_scheme'] = value
        # Foreground colour
        widget = guiget('foreground-colorpicker')
        self.config['foreground_color'] = widget.get_color().to_string()
        # Background colour
        widget = guiget('background-colorpicker')
        self.config['background_color'] = widget.get_color().to_string()
        # Palette
        palette = []
        for i in xrange(1, 17):
            widget = guiget('palette-colorpicker-%d' % i)
            palette.append(widget.get_color().to_string())
        self.config['palette'] = ':'.join(palette)
        # Titlebar colours
        for bit in ['title_transmit_fg_color', 'title_transmit_bg_color',
            'title_receive_fg_color', 'title_receive_bg_color',
            'title_inactive_fg_color', 'title_inactive_bg_color']:
            widget = guiget(bit)
            self.config[bit] = widget.get_color().to_string()

        ## Background tab
        # Background type
        widget = guiget('solid-radiobutton')
        if widget.get_active() == True:
            value = 'solid'
        widget = guiget('image-radiobutton')
        if widget.get_active() == True:
            value = 'image'
        widget = guiget('transparent-radiobutton')
        if widget.get_active() == True:
            value = 'transparent'
        self.config['background_type'] = value
        # Background image
        widget = guiget('background-image-filechooser')
        self.config['background_image'] = widget.get_filename()
        # Background scrolls
        widget = guiget('scroll-background-checkbutton')
        self.config['scroll_background'] = widget.get_active()
        # Background darkness
        widget = guiget('darken-background-scale')
        self.config['background_darkness'] = widget.get_value()

        ## Scrolling tab
        # Scrollbar
        widget = guiget('scrollbar-position-combobox')
        selected = widget.get_active()
        if selected == 0:
            value = 'left'
        elif selected == 1:
            value = 'right'
        elif selected == 2:
            value = 'hidden'
        self.config['scrollbar_position'] = value
        # Scrollback lines
        widget = guiget('scrollback-lines-spinbutton')
        self.config['scrollback_lines'] = int(widget.get_value())
        # Scroll on output
        widget = guiget('scroll-on-output-checkbutton')
        self.config['scroll_on_output'] = widget.get_active()
        # Scroll on keystroke
        widget = guiget('scroll-on-keystroke-checkbutton')
        self.config['scroll_on_keystroke'] = widget.get_active()

        ## Compatibility tab
        # Backspace key
        widget = guiget('backspace-binding-combobox')
        selected = widget.get_active()
        if selected == 0:
            value = 'automatic'
        elif selected == 1:
            value = 'control-h'
        elif selected == 2:
            value = 'ascii-del'
        elif selected == 3:
            value == 'escape-sequence'
        self.config['backspace_binding'] = value
        # Delete key
        widget = guiget('delete-binding-combobox')
        selected = widget.get_active()
        if selected == 0:
            valud = 'automatic'
        elif selected == 1:
            value = 'control-h'
        elif selected == 2:
            value = 'ascii-del'
        elif selected == 3:
            value = 'escape-sequence'
        self.config['delete_binding'] = value

    def set_layout(self, layout):
        """Set a layout"""
        pass

    def store_layout(self, layout):
        """Store a layout"""
        pass

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
            i = 1
            while name in values:
                i = i + 1
                name = '%s %d' % (_('New Layout'), i)

        if self.config.add_layout(name, current_layout):
            res = model.append([name, True])
            if res:
                path = model.get_path(res)
                treeview.set_cursor(path, focus_column=treeview.get_column(0),
                                    start_editing=True)

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

        self.previous_sekection = None
        self.config.del_layout(layout)
        model.remove(rowiter)
        selection.select_iter(model.get_iter_first())

    def on_use_custom_command_checkbutton_toggled(self, checkbox):
        """Toggling the use_custom_command checkbox needs to alter the
        sensitivity of the custom_command entrybox"""
        guiget = self.builder.get_object

        widget = guiget('custom-command-entry')
        if checkbox.get_active() == True:
            widget.set_sensitive(True)
        else:
            widget.set_sensitive(False)

    def on_system_font_checkbutton_toggled(self, checkbox):
        """Toggling the use_system_font checkbox needs to alter the
        sensitivity of the font selector"""
        guiget = self.builder.get_object

        widget = guiget('font-selector')
        if checkbox.get_active() == True:
            widget.set_sensitive(False)
        else:
            widget.set_sensitive(True)

    def on_reset_compatibility_clicked(self, widget):
        """Reset the confusing and annoying backspace/delete options to the
        safest values"""
        guiget = self.builder.get_object

        widget = guiget('backspace-binding-combobox')
        widget.set_active(2)
        widget = guiget('delete-binding-combobox')
        widget.set_active(3)

    def on_background_type_toggled(self, _widget):
        """The background type was toggled"""
        self.update_background_tab()

    def update_background_tab(self):
        """Update the background tab"""
        guiget = self.builder.get_object

        # Background type
        backtype = None
        imagewidget = guiget('image-radiobutton')
        transwidget = guiget('transparent-radiobutton')
        if transwidget.get_active() == True:
            backtype = 'trans'
        elif imagewidget.get_active() == True:
            backtype = 'image'
        else:
            backtype = 'solid'
        if backtype == 'image':
            guiget('background-image-filechooser').set_sensitive(True)
            guiget('scroll-background-checkbutton').set_sensitive(True)
        else:
            guiget('background-image-filechooser').set_sensitive(False)
            guiget('scroll-background-checkbutton').set_sensitive(False)
        if backtype == 'trans':
            guiget('darken-background-scale').set_sensitive(True)
        else:
            guiget('darken-background-scale').set_sensitive(False)

    def on_profile_selection_changed(self, selection):
        """A different profile was selected"""
        if self.previous_profile_selection is not None:
            dbg('PrefsEditor::on_profile_selection_changed: Storing: %s' %
                    self.previous_profile_selection)
            self.store_profile_values()

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

    def on_profile_name_edited(self, cell, path, newtext):
        """Update a profile name"""
        oldname = cell.get_property('text')
        if oldname == newtext or oldname == 'default':
            return
        dbg('PrefsEditor::on_profile_name_edited: Changing %s to %s' %
        (oldname, newtext))
        self.config.rename_profile(oldname, newtext)
        
        widget = self.builder.get_object('profilelist')
        model = widget.get_model()
        itera = model.get_iter(path)
        model.set_value(itera, 0, newtext)

        if oldname == self.previous_profile_selection:
            self.previous_profile_selection = newtext

    def on_layout_selection_changed(self, selection):
        """A different layout was selected"""
        if self.previous_layout_selection is not None:
            dbg('Storing: %s' % self.previous_layout_selection)
            self.store_layout(self.previous_layout_selection)

        (listmodel, rowiter) = selection.get_selected()
        if not rowiter:
            # Something is wrong, just jump to the first item in the list
            treeview = selection.get_tree_view()
            liststore = treeview.get_model()
            selection.select_iter(liststore.get_iter_first())
            return
        layout = listmodel.get_value(rowiter, 0)
        self.set_layout(layout)
        self.previous_layout_selection = layout

        widget = self.builder.get_object('layoutremovebutton')
        if layout == 'default':
            widget.set_sensitive(False)
        else:
            widget.set_sensitive(True)

    def on_layout_name_edited(self, cell, path, newtext):
        """Update a layout name"""
        oldname = cell.get_property('text')
        if oldname == newtext or oldname == 'default':
            return
        dbg('Changing %s to %s' % (oldname, newtext))
        self.config.rename_layout(oldname, newtext)
        
        widget = self.builder.get_object('layoutlist')
        model = widget.get_model()
        itera = model.get_iter(path)
        model.set_value(itera, 0, newtext)

        if oldname == self.previous_layout_selection:
            self.previous_layout_selection = newtext

    def on_color_scheme_combobox_changed(self, widget):
        """Update the fore/background colour pickers"""
        value = None
        guiget = self.builder.get_object
        active = widget.get_active()
        for key in self.colorschemevalues.keys():
            if self.colorschemevalues[key] == active:
                value = key

        fore = guiget('foreground-colorpicker')
        back = guiget('background-colorpicker')
        if value == 'custom':
            fore.set_sensitive(True)
            back.set_sensitive(True)
        else:
            fore.set_sensitive(False)
            back.set_sensitive(False)

        forecol = None
        backcol = None
        if value == 'grey_on_black':
            forecol = '#AAAAAA'
            backcol = '#000000'
        elif value == 'black_on_yellow':
            forecol = '#000000'
            backcol = '#FFFFDD'
        elif value == 'black_on_white':
            forecol = '#000000'
            backcol = '#FFFFFF'
        elif value == 'white_on_black':
            forecol = '#FFFFFF'
            backcol = '#000000'
        elif value == 'green_on_black':
            forecol = '#00FF00'
            backcol = '#000000'
        elif value == 'orange_on_black':
            forecol = '#E53C00'
            backcol = '#000000'

        if forecol is not None:
            fore.set_color(gtk.gdk.Color(forecol))
        if backcol is not None:
            back.set_color(gtk.gdk.Color(backcol))

    def on_use_theme_colors_checkbutton_toggled(self, widget):
        """Update colour pickers"""
        guiget = self.builder.get_object
        active = widget.get_active()

        scheme = guiget('color-scheme-combobox')
        fore = guiget('foreground-colorpicker')
        back = guiget('background-colorpicker')

        if active:
            for widget in [scheme, fore, back]:
                widget.set_sensitive(False)
        else:
            scheme.set_sensitive(True)
            self.on_color_scheme_combobox_changed(scheme)

    def on_cellrenderer_accel_edited(self, liststore, path, key, mods, _code):
        """Handle an edited keybinding"""
        celliter = liststore.get_iter_from_string(path)
        liststore.set(celliter, 2, key, 3, mods)

    def on_cellrenderer_accel_cleared(self, liststore, path):
        """Handle the clearing of a keybinding accelerator"""
        celliter = liststore.get_iter_from_string(path)
        liststore.set(celliter, 2, 0, 3, 0)

if __name__ == '__main__':
    import util
    util.DEBUG = True
    import terminal
    TERM = terminal.Terminal()
    PREFEDIT = PrefsEditor(TERM)

    gtk.main()
