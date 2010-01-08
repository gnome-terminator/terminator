#!/usr/bin/python

import gtk
import gobject

from util import dbg, err
import config
from keybindings import Keybindings
from version import APP_NAME, APP_VERSION
from translation import _

class PrefsEditor:
    data = {'titlebars': ['Show titlebars', 'This places a bar above each terminal which displays its title.'],
                    'zoomedtitlebar': ['Show titlebar when zoomed', 'This places an informative bar above a zoomed terminal to indicate there are hidden terminals.'],
                    'allow_bold': ['Allow bold text', 'Controls whether or not the terminals will honour requests for bold text'],
                    'silent_bell': ['', 'When enabled, bell events will generate a flash. When disabled, they will generate a beep'],
                    'background_darkness': ['', 'Controls how much the background will be tinted'],
                    'scroll_background': ['', 'When enabled the background image will scroll with the text'],
                    'force_no_bell': ['', 'Disable both the visual and audible bells'],
                    'tab_position': ['', 'Controls the placement of the tab bar'],
                    'use_theme_colors': ['', 'Take the foreground and background colours from the current GTK theme'],
                    'enable_real_transparency': ['', 'If you are running a composited desktop (e.g. compiz), enabling this option will enable "true" transpraency'],
                    'handle_size': ['', 'This controls the size of the border between terminals. Values 0 to 5 are in pixels, while -1 means the value will be decided by your normal GTK theme.'],
                    'close_window': ['Quit Terminator', ''],
                    'toggle_zoom': ['Toggle maximise terminal', ''],
                    'scaled_zoom': ['Toggle zoomed terminal', ''],
                    'prev_tab': ['Previous tab', ''],
                    'split_vert': ['Split vertically', ''],
                    'split_horiz': ['Split horizontally', ''],
                    'go_prev': ['Focus previous terminal', ''],
                    'go_next': ['Focus next terminal', ''],
                    'close_term': ['Close terminal', ''],
                    'new_root_tab': ['New root tab', ''],
                    'zoom_normal': ['Zoom reset', ''],
                    'reset': ['Reset terminal state', ''],
                    'reset_clear': ['Reset and clear terminal', ''],
                    'hide_window': ['Toggle visibility of the window', ''],
                    'title_tx_txt_color': ['Tx Title Foreground Color', ''],
                    'title_tx_bg_color': ['Tx Title Background Color', ''],
                    'title_rx_txt_color': ['Rx Title Foreground Color', ''],
                    'title_rx_bg_color': ['Rx Title Background Color', ''],
                    'title_ia_txt_color': ['Inactive Title Foreground Color', ''],
                    'title_ia_bg_color': ['Inactive Title Background Color', ''],
                 }

    config = None

    def __init__ (self, term):
        self.config = config.Config()
        self.term = term
        self.builder = gtk.Builder()
        try:
            gladefile = open('/home/cmsj/code/personal/terminator/branches/epicrefactor/data/preferences.glade', 'r')
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

    def set_values(self):
        """Update the preferences window with all the configuration from
        Config()"""
        guiget = self.builder.get_object

        print "SETTING VALUES"

        ## Global tab

        # Mouse focus
        # default is 'system', which == 0
        focus = self.config['focus']
        active = 0
        if focus == 'click':
            active = 1
        elif focus == 'sloppy':
            active = 2
        widget = guiget('focuscombo')
        widget.set_active(active)

        # Terminal separator size
        # default is -1
        termsepsize = self.config['handle_size']
        widget = guiget('handlesize')
        widget.set_value(termsepsize)

        # Window geometry hints
        # default is True
        geomhint = self.config['geometry_hinting']
        widget = guiget('wingeomcheck')
        widget.set_active(geomhint)

        # Window state
        # default is not maximised, not fullscreen
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
        # default is True
        widget = guiget('winbordercheck')
        widget.set_active(not self.config['borderless'])
        
        # Tab bar position
        # default is top
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
        print "VALUES ALL SET"

    def set_profile_values(self, profile):
        """Update the profile values for a given profile"""
        self.config.set_profile(profile)
        guiget = self.builder.get_object

        dbg('PrefsEditor::set_profile_values: Setting profile %s' % profile)

        ## General tab
        # Use system font
        widget = guiget('system-font-checkbutton')
        widget.set_active(self.config['use_system_font'])
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

    def on_profile_selection_changed(self, selection):
        """A different profile was selected"""
        (listmodel, rowiter) = selection.get_selected()
        profile = listmodel.get_value(rowiter, 0)
        self.set_profile_values(profile)

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
