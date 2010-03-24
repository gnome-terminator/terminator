#!/usr/bin/python
"""Preferences Editor for Terminator. 

Load a UIBuilder config file, display it,
populate it with our current config, then optionally read that back out and
write it to a config file

"""

import os
import gtk

from util import dbg, err
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
                         'custom': 7}

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
        self.layouteditor = LayoutEditor(self.builder)
        self.builder.connect_signals(self)
        self.layouteditor.prepare()
        self.window.show_all()
        try:
            self.config.inhibit_save()
            self.set_values()
        except Exception, e:
            err('Unable to set values: %s' % e)
        finally:
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
        # FIXME: Implement this

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
            widget.set_font_name(self.config.get_system_font())
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
        scheme = self.config['color_scheme']
        if scheme not in self.colorschemevalues:
            scheme = 'grey_on_black'
        widget.set_active(self.colorschemevalues[scheme])
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
        # Palette
        palette = self.config['palette'].split(':')
        for i in xrange(1, 17):
            widget = guiget('palette_colorpicker_%d' % i)
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

    def set_layout(self, layout_name):
        """Set a layout"""
        self.layouteditor.set_layout(layout_name)

    def on_wingeomcheck_toggled(self, widget):
        """Window geometry setting changed"""
        self.config['geometry_hinting'] = widget.get_active()
        self.config.save()

    def on_winbordercheck_toggled(self, widget):
        """Window border setting changed"""
        self.config['borderless'] = not widget.get_active()
        self.config.save()

    def on_allow_bold_checkbutton_toggled(self, widget):
        """Allow bold setting changed"""
        self.config['allow_bold'] = widget.get_active()
        self.config.save()

    def on_show_titlebar_toggled(self, widget):
        """Show titlebar setting changed"""
        self.config['show_titlebar'] = widget.get_active()
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

    def on_darken_background_scale_change_value(self, widget):
        """Background darkness setting changed"""
        self.config['background_darkness'] = widget.get_value()
        self.config.save()

    def on_background_image_filechooser_file_set(self, widget):
        """Background image setting changed"""
        self.config['background_image'] = widget.get_filename()
        self.config.save()

    def on_palette_combobox_changed(self, widget):
        """Palette selector changed"""
        # FIXME: This doesn't really exist yet.
        pass

    def on_background_colorpicker_color_set(self, widget):
        """Background color changed"""
        self.config['background_color'] = widget.get_color().to_string()
        self.config.save()

    def on_foreground_colorpicker_color_set(self, widget):
        """Foreground color changed"""
        self.config['foreground_color'] = widget.get_color().to_string()
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

    def on_custom_command_entry_activate(self, widget):
        """Custom command value changed"""
        self.config['custom_command'] = widget.get_text()
        self.config.save()

    def on_cursor_color_color_set(self, widget):
        """Cursor colour changed"""
        self.config['cursor_color'] = widget.get_color().to_string()
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

    def on_word_chars_entry_activate(self, widget):
        """Word characters changed"""
        self.config['word_chars'] = widget.get_text()
        self.config.save()

    def on_font_selector_font_set(self, widget):
        """Font changed"""
        self.config['font'] = widget.get_font_name()
        self.config.save()

    def on_title_receive_bg_color_color_set(self, widget):
        """Title receive background colour changed"""
        self.config['title_receive_bg_color'] = widget.get_color().to_string()
        self.config.save()

    def on_title_receive_fg_color_color_set(self, widget):
        """Title receive foreground colour changed"""
        self.config['title_receive_fg_color'] = widget.get_color().to_string()
        self.config.save()

    def on_title_inactive_bg_color_color_set(self, widget):
        """Title inactive background colour changed"""
        self.config['title_inactive_bg_color'] = widget.get_color().to_string()
        self.config.save()

    def on_title_transmit_bg_color_color_set(self, widget):
        """Title transmit backgruond colour changed"""
        self.config['title_transmit_bg_color'] = widget.get_color().to_string()
        self.config.save()

    def on_title_inactive_fg_color_color_set(self, widget):
        """Title inactive foreground colour changed"""
        self.config['title_inactive_fg_color'] = widget.get_color().to_string()
        self.config.save()

    def on_title_transmit_fg_color_color_set(self, widget):
        """Title transmit foreground colour changed"""
        self.config['title_transmit_fg_color'] = widget.get_color().to_string()
        self.config.save()

    def on_handlesize_change_value(self, widget):
        """Handle size changed"""
        self.config['handle_size'] = int(widget.get_value())
        self.config.save()

    def on_focuscombo_changed(self, widget):
        """Focus type changed"""
        selected  = widget.get_active()
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
        else:
            value = 'top'
        self.config['tab_position'] = value
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
        if backtype == 'transparent':
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

    def on_profile_name_edited(self, cell, path, newtext):
        """Update a profile name"""
        oldname = cell.get_property('text')
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

    def on_layout_profile_command_activate(self, widget):
        """A different command has been entered for this item"""
        self.layouteditor.on_layout_profile_command_activate(widget)

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
        elif value == 'ambience':
            forecol = '#FFFFFF'
            backcol = '#300A24'

        if forecol is not None:
            fore.set_color(gtk.gdk.Color(forecol))
        if backcol is not None:
            back.set_color(gtk.gdk.Color(backcol))

        self.config['color_scheme'] = value
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

        if layout_item['type'] != 'Terminal':
            command.set_sensitive(False)
            chooser.set_sensitive(False)
            return

        command.set_sensitive(True)
        chooser.set_sensitive(True)
        if layout_item.has_key('command') and layout_item['command'] != '':
            command.set_text(layout_item['command'])
        else:
            command.set_text('')

        if layout_item.has_key('profile') and layout_item['profile'] != '':
            chooser.set_active(self.profile_profile_to_ids[layout_item['profile']])
        else:
            chooser.set_active(0)

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

if __name__ == '__main__':
    import util
    util.DEBUG = True
    import terminal
    TERM = terminal.Terminal()
    PREFEDIT = PrefsEditor(TERM)

    gtk.main()
