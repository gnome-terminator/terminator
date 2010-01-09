#!/usr/bin/python

import os
import gtk
import gobject

from util import dbg, err
import config
from keybindings import Keybindings
from version import APP_NAME, APP_VERSION
from translation import _

class PrefsEditor:
    config = None
    window = None
    builder = None
    previous_selection = None
    colorschemevalues = {'black_on_yellow': 0, 
                         'black_on_white': 1,
                         'grey_on_black': 2,
                         'green_on_black': 3,
                         'white_on_black': 4,
                         'orange_on_black': 5,
                         'custom': 6}

    def __init__ (self, term):
        self.config = config.Config()
        self.term = term
        self.builder = gtk.Builder()
        try:
            # Figure out where our library is on-disk so we can open our 
            (head, tail) = os.path.split(config.__file__)
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

    def on_cancelbutton_clicked(self, button):
        """Close the window"""
        self.window.destroy()
        del(self)

    def on_okbutton_clicked(self, button):
        """Save the config"""
        self.store_values()
        self.config.save()
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
        elif focus == 'sloppy':
            active = 2
        widget = guiget('focuscombo')
        widget.set_active(active)
        # Terminal separator size
        termsepsize = self.config['handle_size']
        widget = guiget('handlesize')
        widget.set_value(termsepsize)
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
            self.profileiters[profile] = liststore.append([profile])
        selection = widget.get_selection()
        selection.connect('changed', self.on_profile_selection_changed)
        selection.select_iter(self.profileiters['default'])

        ## Layouts tab
        # FIXME: Implement this

        ## Keybindings tab
        # FIXME: Implement this

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
        self.config['handle_size'] = widget.get_value()
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
        self.store_profile_values(self.previous_selection)

        ## Layouts tab
        # FIXME: Implement this

        ## Keybindings tab
        # FIXME: Implement this

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
        # Cursor shape
        widget = guiget('cursor-shape-combobox')
        if self.config['cursor_shape'] == 'underline':
            active = 1
        elif self.config['cursor_shape'] == 'ibeam':
            active = 2
        else:
            active = 0
        widget.set_active(active)
        # Word chars
        widget = guiget('word-chars-entry')
        widget.set_text(self.config['word_chars'])

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
        # FIXME: Do the Palette schemes and pickers

        ## Background tab
        # Radio values
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
        widget.set_value(self.config['background_darkness'])

        if self.config['background_type'] == 'solid':
            guiget('solid-radiobutton').set_active(True)
        elif self.config['background_type'] == 'image':
            guiget('image-radiobutton').set_active(True)
        elif self.config['background_type'] == 'transparent':
            guiget('trans-radiobutton').set_active(True)

        ## Scrolling tab
        # Scrollbar position
        widget = guiget('scrollbar-position-combobox')
        value = self.config['scrollbar_position']
        if value == 'left':
            widget.set_active(0)
        elif value == 'disabled':
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
            widget.set_active(0)
        elif value == 'escape-sequence':
            widget.set_active(2)
        else:
            widget.set_active(1)
        # Delete key
        widget = guiget('delete-binding-combobox')
        value = self.config['delete_binding']
        if value == 'control-h':
            widget.set_active(0)
        elif value == 'ascii-del':
            widget.set_active(1)
        else:
            widget.set_active(2)

    def store_profile_values(self, profile):
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
        # Word chars
        widget = guiget('word-chars-entry')
        self.config['word_chars'] = widget.get_text()
        
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
        # FIXME: Do the palette schemes and palette

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
        elif selected ==2:
            value = 'hidden'
        self.config['scrollbar_position'] = value
        # Scrollback lines
        widget = guiget('scrollback-lines-spinbutton')
        self.config['scrollback_lines'] = widget.get_value()
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
            value = 'control-h'
        elif selected == 1:
            value = 'ascii-del'
        elif selected == 2:
            value =='escape-sequence'
        self.config['backspace_binding'] = value
        # Delete key
        widget = guiget('delete-binding-combobox')
        selected = widget.get_active()
        if selected == 0:
            value = 'control-h'
        elif selected == 1:
            value = 'ascii-del'
        elif selected == 2:
            value = 'escape-sequence'
        self.config['delete_binding'] = value

    def on_profileaddbutton_clicked(self, button):
        """Add a new profile to the list"""
        guiget = self.builder.get_object

        treeview = guiget('profilelist')
        model = treeview.get_model()
        values = [ r[0] for r in model ]

        newprofile = _('New Profile')
        if newprofile in values:
            i = 0
            while newprofile in values:
                i = i + 1
                newprofile = '%s %d' % (_('New Profile'), i)

        if self.config.add_profile(newprofile):
            model.append([newprofile])

    def on_profileremovebutton_clicked(self, button):
        """Remove a profile from the list"""
        guiget = self.builder.get_object

        treeview = guiget('profilelist')
        selection = treeview.get_selection()
        (model, rowiter) = selection.get_selected()
        profile = model.get_value(rowiter, 0)

        if profile == 'default':
            # We shouldn't let people delete this profile
            return

        self.config.del_profile(profile)
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
        widget.set_active(1)
        widget = guiget('delete-binding-combobox')
        widget.set_active(2)

    def on_background_type_toggled(self, widget):
        """The background type was toggled"""
        self.update_background_tab()

    def update_background_tab(self):
        """Update the background tab"""
        guiget = self.builder.get_object

        # Background type
        backtype = None
        solidwidget = guiget('solid-radiobutton')
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
        if self.previous_selection is not None:
            self.store_profile_values(self.previous_selection)

        (listmodel, rowiter) = selection.get_selected()
        if not rowiter:
            # Something is wrong, just jump to the first item in the list
            treeview = selection.get_tree_view()
            liststore = treeview.get_model()
            selection.select_iter(liststore.get_iter_first())
            return
        profile = listmodel.get_value(rowiter, 0)
        self.set_profile_values(profile)
        self.previous_selection = profile

        widget = self.builder.get_object('profileremovebutton')
        if profile == 'default':
            widget.set_sensitive(False)
        else:
            widget.set_sensitive(True)

    def on_profile_name_edited(self, cell, path, newtext):
        """Update a profile name"""
        oldname = cell.get_property('text')
        if oldname == newtext:
            return
        dbg('PrefsEditor::on_profile_name_edited: Changing %s to %s' %
        (oldname, newtext))
        self.config.rename_profile(oldname, newtext)
        
        widget = self.builder.get_object('profilelist')
        model = widget.get_model()
        iter = model.get_iter(path)
        model.set_value(iter, 0, newtext)

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

    def source_get_type (self, key):
        if config.DEFAULTS['global_config'].has_key (key):
            print "found %s in global_config" % key
            return config.DEFAULTS['global_config'][key].__class__.__name__
        elif config.DEFAULTS['profiles']['default'].has_key (key):
            print "found %s in profiles" % key
            return config.DEFAULTS['profiles']['default'][key].__class__.__name__
        elif config.DEFAULTS['keybindings'].has_key (key):
            print "found %s in keybindings" % key
            return config.DEFAULTS['keybindings'][key].__class__.__name__
        else:
            print "could not find %s" % key
            raise KeyError

    def source_get_value (self, key):
        return self.config[key]

    def source_get_keyname (self, key):
        if self.data.has_key (key) and self.data[key][0] != '':
            label_text = self.data[key][0]
        else:
            label_text = key.replace ('_', ' ').capitalize ()
        return label_text

    def apply (self, data):
        pass

    def cancel (self, data):
        self.window.destroy()
        self.term.options = None
        del(self)

    def prepare_keybindings (self):
        self.liststore = gtk.ListStore (gobject.TYPE_STRING, gobject.TYPE_STRING, gobject.TYPE_UINT, gobject.TYPE_UINT, gobject.TYPE_BOOLEAN)
        self.liststore.set_sort_column_id (0, gtk.SORT_ASCENDING)
        self.tkbobj = Keybindings()
        keyval = None
        mask = None

        for binding in config.DEFAULTS['keybindings']:
            value = self.config['keybindings'][binding]
            keyval = 0
            mask = 0
            if isinstance (value, tuple):
                value = value[0]
            if value is not None and value != "None":
                try:
                    (keyval, mask) = self.tkbobj._parsebinding (value)
                except KeymapError:
                    pass
            self.liststore.append ([binding, self.source_get_keyname (binding), keyval, mask, True])
            dbg("Appended row: %s, %s, %s" % (binding, keyval, mask))

        self.treeview = gtk.TreeView(self.liststore)

        cell = gtk.CellRendererText()
        col = gtk.TreeViewColumn(_("Name"))
        col.pack_start(cell, True)
        col.add_attribute(cell, "text", 0)

        self.treeview.append_column(col)

        cell = gtk.CellRendererText()
        col = gtk.TreeViewColumn(_("Action"))
        col.pack_start(cell, True)
        col.add_attribute(cell, "text", 1)

        self.treeview.append_column(col)

        cell = gtk.CellRendererAccel()
        col = gtk.TreeViewColumn(_("Keyboard shortcut"))
        col.pack_start(cell, True)
        col.set_attributes(cell, accel_key=2, accel_mods=3, editable=4)

        cell.connect ('accel-edited', self.edited)
        cell.connect ('accel-cleared', self.cleared)

        self.treeview.append_column(col)

        scrollwin = gtk.ScrolledWindow ()
        scrollwin.set_policy (gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        scrollwin.add (self.treeview)
        return (scrollwin)

    def edited (self, obj, path, key, mods, code):
        iter = self.liststore.get_iter_from_string(path)
        self.liststore.set(iter, 2, key, 3, mods)

    def cleared (self, obj, path):
        iter = self.liststore.get_iter_from_string(path)
        self.liststore.set(iter, 2, 0, 3, 0)

if __name__ == '__main__':
    import terminal
    term = terminal.Terminal()
    foo = PrefsEditor(term)

    gtk.main()
