#!/usr/bin/env python2
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""terminal_popup_menu.py - classes necessary to provide a terminal context 
menu"""

import string

from gi.repository import Gtk

from version import APP_NAME
from translation import _
from encoding import TerminatorEncoding
from terminator import Terminator
from util import err, dbg
from config import Config
from prefseditor import PrefsEditor
import plugin

class TerminalPopupMenu(object):
    """Class implementing the Terminal context menu"""
    terminal = None
    terminator = None
    config = None

    def __init__(self, terminal):
        """Class initialiser"""
        self.terminal = terminal
        self.terminator = Terminator()
        self.config = Config()

    def show(self, widget, event=None):
        """Display the context menu"""
        terminal = self.terminal

        menu = Gtk.Menu()
        self.popup_menu = menu
        url = None
        button = None
        time = None

        self.config.set_profile(terminal.get_profile())

        if event:
            url = terminal.vte.match_check_event(event)
            button = event.button
            time = event.time
        else:
            time = 0
            button = 3

        if url and url[0]:
            dbg("URL matches id: %d" % url[1])
            if not url[1] in terminal.matches.values():
                err("Unknown URL match id: %d" % url[1])
                dbg("Available matches: %s" % terminal.matches)

            nameopen = None
            namecopy = None
            if url[1] == terminal.matches['email']:
                nameopen = _('_Send email to...')
                namecopy = _('_Copy email address')
            elif url[1] == terminal.matches['voip']:
                nameopen = _('Ca_ll VoIP address')
                namecopy = _('_Copy VoIP address')
            elif url[1] in terminal.matches.values():
                # This is a plugin match
                for pluginname in terminal.matches:
                    if terminal.matches[pluginname] == url[1]:
                        break

                dbg("Found match ID (%d) in terminal.matches plugin %s" %
                        (url[1], pluginname))
                registry = plugin.PluginRegistry()
                registry.load_plugins()
                plugins = registry.get_plugins_by_capability('url_handler')
                for urlplugin in plugins:
                    if urlplugin.handler_name == pluginname:
                        dbg("Identified matching plugin: %s" %
                                urlplugin.handler_name)
                        nameopen = _(urlplugin.nameopen)
                        namecopy = _(urlplugin.namecopy)
                        break

            if not nameopen:
                nameopen = _('_Open link')
            if not namecopy:
                namecopy = _('_Copy address')

            icon = Gtk.Image.new_from_stock(Gtk.STOCK_JUMP_TO,
                                            Gtk.IconSize.MENU)
            item = Gtk.ImageMenuItem.new_with_mnemonic(nameopen)
            item.set_property('image', icon)
            item.connect('activate', lambda x: terminal.open_url(url, True))
            menu.append(item)

            item = Gtk.MenuItem.new_with_mnemonic(namecopy)
            item.connect('activate', 
                         lambda x: terminal.clipboard.set_text(terminal.prepare_url(url), len(terminal.prepare_url(url))))
            menu.append(item)

            menu.append(Gtk.SeparatorMenuItem())

        item = Gtk.ImageMenuItem.new_with_mnemonic(_('_Copy'))
        item.connect('activate', lambda x: terminal.vte.copy_clipboard())
        item.set_sensitive(terminal.vte.get_has_selection())
        menu.append(item)

        item = Gtk.ImageMenuItem.new_with_mnemonic(_('_Paste'))
        item.connect('activate', lambda x: terminal.paste_clipboard())
        menu.append(item)

        menu.append(Gtk.SeparatorMenuItem())

        if not terminal.is_zoomed():
            item = Gtk.ImageMenuItem.new_with_mnemonic(_('Split H_orizontally'))
            image = Gtk.Image()
            image.set_from_icon_name(APP_NAME + '_horiz', Gtk.IconSize.MENU)
            item.set_image(image)
            if hasattr(item, 'set_always_show_image'):
                item.set_always_show_image(True)
            item.connect('activate', lambda x: terminal.emit('split-horiz',
                self.terminal.get_cwd()))
            menu.append(item)

            item = Gtk.ImageMenuItem.new_with_mnemonic(_('Split V_ertically'))
            image = Gtk.Image()
            image.set_from_icon_name(APP_NAME + '_vert', Gtk.IconSize.MENU)
            item.set_image(image)
            if hasattr(item, 'set_always_show_image'):
                item.set_always_show_image(True)
            item.connect('activate', lambda x: terminal.emit('split-vert',
                self.terminal.get_cwd()))
            menu.append(item)

            item = Gtk.MenuItem.new_with_mnemonic(_('Open _Tab'))
            item.connect('activate', lambda x: terminal.emit('tab-new', False,
                terminal))
            menu.append(item)

            if self.terminator.debug_address is not None:
                item = Gtk.MenuItem.new_with_mnemonic(_('Open _Debug Tab'))
                item.connect('activate', lambda x:
                        terminal.emit('tab-new', True, terminal))
                menu.append(item)

            menu.append(Gtk.SeparatorMenuItem())

        item = Gtk.ImageMenuItem.new_with_mnemonic(_('_Close'))
        item.connect('activate', lambda x: terminal.close())
        menu.append(item)

        menu.append(Gtk.SeparatorMenuItem())

        if not terminal.is_zoomed():
            sensitive = not terminal.get_toplevel() == terminal.get_parent()

            item = Gtk.MenuItem.new_with_mnemonic(_('_Zoom terminal'))
            item.connect('activate', terminal.zoom)
            item.set_sensitive(sensitive)
            menu.append(item)

            item = Gtk.MenuItem.new_with_mnemonic(_('Ma_ximize terminal'))
            item.connect('activate', terminal.maximise)
            item.set_sensitive(sensitive)
            menu.append(item)

            menu.append(Gtk.SeparatorMenuItem())
        else:
            item = Gtk.MenuItem.new_with_mnemonic(_('_Restore all terminals'))
            item.connect('activate', terminal.unzoom)
            menu.append(item)

            menu.append(Gtk.SeparatorMenuItem())

        if self.config['show_titlebar'] == False:
            item = Gtk.MenuItem.new_with_mnemonic(_('Grouping'))
            submenu = self.terminal.populate_group_menu()
            submenu.show_all()
            item.set_submenu(submenu)
            menu.append(item)
            menu.append(Gtk.SeparatorMenuItem())

        item = Gtk.CheckMenuItem.new_with_mnemonic(_('Show _scrollbar'))
        item.set_active(terminal.scrollbar.get_property('visible'))
        item.connect('toggled', lambda x: terminal.do_scrollbar_toggle())
        menu.append(item)

        if hasattr(Gtk, 'Builder'):  # VERIFY FOR GTK3: is this ever false?
            item = Gtk.MenuItem.new_with_mnemonic(_('_Preferences'))
            item.connect('activate', lambda x: PrefsEditor(self.terminal))
            menu.append(item)

        profilelist = sorted(self.config.list_profiles(), key=string.lower)

        if len(profilelist) > 1:
            item = Gtk.MenuItem.new_with_mnemonic(_('Profiles'))
            submenu = Gtk.Menu()
            item.set_submenu(submenu)
            menu.append(item)

            current = terminal.get_profile()

            group = None

            for profile in profilelist:
                profile_label = profile
                if profile_label == 'default':
                    profile_label = profile.capitalize()
                item = Gtk.RadioMenuItem(profile_label, group)
                if profile == current:
                    item.set_active(True)
                item.connect('activate', terminal.force_set_profile, profile)
                submenu.append(item)

        self.add_encoding_items(menu)

        try:
            menuitems = []
            registry = plugin.PluginRegistry()
            registry.load_plugins()
            plugins = registry.get_plugins_by_capability('terminal_menu')
            for menuplugin in plugins:
                menuplugin.callback(menuitems, menu, terminal)
            
            if len(menuitems) > 0:
                menu.append(Gtk.SeparatorMenuItem())

            for menuitem in menuitems:
                menu.append(menuitem)
        except Exception, ex:
            err('TerminalPopupMenu::show: %s' % ex)

        menu.show_all()
        menu.popup(None, None, None, None, button, time)

        return(True)


    def add_encoding_items(self, menu):
        """Add the encoding list to the menu"""
        terminal = self.terminal
        active_encodings = terminal.config['active_encodings']
        item = Gtk.MenuItem.new_with_mnemonic(_("Encodings"))
        menu.append (item)
        submenu = Gtk.Menu ()
        item.set_submenu (submenu)
        encodings = TerminatorEncoding ().get_list ()
        encodings.sort (lambda x, y: cmp (x[2].lower (), y[2].lower ()))

        current_encoding = terminal.vte.get_encoding ()
        group = None

        if current_encoding not in active_encodings:
            active_encodings.insert (0, _(current_encoding))

        for encoding in active_encodings:
            if encoding == terminal.default_encoding:
                extratext = " (%s)" % _("Default")
            elif encoding == current_encoding and \
                 terminal.custom_encoding == True:
                extratext = " (%s)" % _("User defined")
            else:
                extratext = ""
    
            radioitem = Gtk.RadioMenuItem (_(encoding) + extratext, group)
    
            if encoding == current_encoding:
                radioitem.set_active (True)
    
            if group is None:
                group = radioitem
    
            radioitem.connect ('activate', terminal.on_encoding_change, 
                               encoding)
            submenu.append (radioitem)
    
        item = Gtk.MenuItem.new_with_mnemonic(_("Other Encodings"))
        submenu.append (item)
        #second level
    
        submenu = Gtk.Menu ()
        item.set_submenu (submenu)
        group = None
    
        for encoding in encodings:
            if encoding[1] in active_encodings:
                continue

            if encoding[1] is None:
                label = "%s %s" % (encoding[2], terminal.vte.get_encoding ())
            else:
                label = "%s %s" % (encoding[2], encoding[1])
    
            radioitem = Gtk.RadioMenuItem (label, group)
            if group is None:
                group = radioitem
    
            if encoding[1] == current_encoding:
                radioitem.set_active (True)

            radioitem.connect ('activate', terminal.on_encoding_change, 
                               encoding[1])
            submenu.append (radioitem)

