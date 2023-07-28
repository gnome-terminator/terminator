# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""terminal_popup_menu.py - classes necessary to provide a terminal context 
menu"""

from gi.repository import Gtk, Gdk

from .version import APP_NAME
from .translation import _
from .terminator import Terminator
from .util import err, dbg, spawn_new_terminator
from .config import Config
from .prefseditor import PrefsEditor
from . import plugin
from .layoutlauncher import LayoutLauncher

class TerminalPopupMenu(object):
    """Class implementing the Terminal context menu"""
    terminal = None
    terminator = None
    config = None
    accelgrp = None

    def __init__(self, terminal):
        """Class initialiser"""
        self.terminal = terminal
        self.terminator = Terminator()
        self.config = Config()
        self.accelgrp = Gtk.AccelGroup()

    def get_menu_item_mask(self, maskstr):
        mask = 0
        if maskstr is None:
            return mask
        maskstr = maskstr.lower()
        if maskstr.find('<Shift>'.lower()) >= 0:
            mask = mask | Gdk.ModifierType.SHIFT_MASK
            dbg("adding mask <Shift> %s" % mask)

        ctrl = (maskstr.find('<Control>'.lower()) >= 0 or
                maskstr.find('<Primary>'.lower()) >= 0)
        if ctrl:
            mask = mask | Gdk.ModifierType.CONTROL_MASK
            dbg("adding mask <Control> %s" % mask)

        if maskstr.find('<Alt>'.lower()) >= 0:
            mask = mask | Gdk.ModifierType.MOD1_MASK
            dbg("adding mask <Alt> %s" % mask)

        mask = Gdk.ModifierType(mask)
        dbg("menu_item_mask :%d" % mask)
        return mask

    def menu_item(self, menutype, actstr, menustr):
        act     = self.config.base.get_item('keybindings', actstr)
        maskstr = act[actstr] if actstr in act else ""
        mask    = self.get_menu_item_mask(maskstr)

        accelchar = ""
        pos = menustr.lower().find("_")
        if (pos >= 0 and pos+1 < len(menustr)):
            accelchar = menustr.lower()[pos+1]

        #this may require tweak. what about shortcut function keys ?
        if maskstr:
            mpos = maskstr.rfind(">")
            #can't have a char at 0 position as <> is len 2
            if mpos >= 0 and mpos+1 < len(maskstr):
                configaccelchar = maskstr[mpos+1:]
                #ensure to take only 1 char else ignore
                if len(configaccelchar) == 1:
                    dbg("found accelchar in config:%s  override:%s"
                                    %  (configaccelchar, accelchar))
                    accelchar = configaccelchar

        dbg("action from config:%s for item:%s with shortcut accelchar:(%s)"
                                    % (maskstr, menustr, accelchar))
        item = menutype.new_with_mnemonic(_(menustr))
        if mask:
            item.add_accelerator("activate",
                                self.accelgrp,
                                Gdk.keyval_from_name(accelchar),
                                mask,
                                Gtk.AccelFlags.VISIBLE)
        return item

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
            if not url[1] in list(terminal.matches.values()):
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
            elif url[1] in list(terminal.matches.values()):
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

        item = self.menu_item(Gtk.ImageMenuItem, 'copy', '_Copy')
        item.connect('activate', lambda x: terminal.vte.copy_clipboard())
        item.set_sensitive(terminal.vte.get_has_selection())

        menu.append(item)

        item = self.menu_item(Gtk.ImageMenuItem, 'paste', '_Paste')
        item.connect('activate', lambda x: terminal.paste_clipboard())
        menu.append(item)

        menu.append(Gtk.SeparatorMenuItem())

        item = self.menu_item(Gtk.ImageMenuItem, 'edit_window_title',
                                                 'Set _Window Title')
        item.connect('activate', lambda x: terminal.key_edit_window_title())
        menu.append(item)
        
        if not terminal.is_zoomed():
            item = self.menu_item(Gtk.ImageMenuItem, 'split_auto',
                                                     'Split _Auto')
            """
            image = Gtk.Image()
            image.set_from_icon_name(APP_NAME + '_auto', Gtk.IconSize.MENU)
            item.set_image(image)
            if hasattr(item, 'set_always_show_image'):
                item.set_always_show_image(True)
            """
            item.connect('activate', lambda x: terminal.emit('split-auto',
                self.terminal.get_cwd()))
            menu.append(item)


            item = self.menu_item(Gtk.ImageMenuItem, 'split_horiz',
                                                     'Split H_orizontally')
            image = Gtk.Image()
            image.set_from_icon_name(APP_NAME + '_horiz', Gtk.IconSize.MENU)
            item.set_image(image)
            if hasattr(item, 'set_always_show_image'):
                item.set_always_show_image(True)
            item.connect('activate', lambda x: terminal.emit('split-horiz',
                self.terminal.get_cwd()))
            menu.append(item)

            item = self.menu_item(Gtk.ImageMenuItem, 'split_vert',
                                                     'Split V_ertically')
            image = Gtk.Image()
            image.set_from_icon_name(APP_NAME + '_vert', Gtk.IconSize.MENU)
            item.set_image(image)
            if hasattr(item, 'set_always_show_image'):
                item.set_always_show_image(True)
            item.connect('activate', lambda x: terminal.emit('split-vert',
                self.terminal.get_cwd()))
            menu.append(item)

            item = self.menu_item(Gtk.MenuItem, 'new_tab', 'Open _Tab')
            item.connect('activate', lambda x: terminal.emit('tab-new', False,
                terminal))
            menu.append(item)

            if self.terminator.debug_address is not None:
                item = Gtk.MenuItem.new_with_mnemonic(_('Open _Debug Tab'))
                item.connect('activate', lambda x:
                        terminal.emit('tab-new', True, terminal))
                menu.append(item)

            menu.append(Gtk.SeparatorMenuItem())

        item = self.menu_item(Gtk.ImageMenuItem, 'close_term', '_Close')
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

        if terminal.is_held_open:
            item = Gtk.MenuItem.new_with_mnemonic(_('Relaunch Command'))
            item.connect('activate', lambda x: terminal.spawn_child())
            menu.append(item)
            menu.append(Gtk.SeparatorMenuItem())

        item = self.menu_item(Gtk.CheckMenuItem, 'toggle_readonly', '_Read only')
        item.set_active(not(terminal.vte.get_input_enabled()))
        item.connect('toggled', lambda x: terminal.do_readonly_toggle())
        menu.append(item)

        item = self.menu_item(Gtk.CheckMenuItem, 'toggle_scrollbar',
                                                   'Show _scrollbar')
        item.set_active(terminal.scrollbar.get_property('visible'))
        item.connect('toggled', lambda x: terminal.do_scrollbar_toggle())
        menu.append(item)

        if hasattr(Gtk, 'Builder'):  # VERIFY FOR GTK3: is this ever false?
            item = self.menu_item(Gtk.MenuItem, 'preferences',
                                                '_Preferences')
            item.connect('activate', lambda x: PrefsEditor(self.terminal))
            menu.append(item)

        profilelist = sorted(self.config.list_profiles(), key=str.lower)

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

        self.add_layout_launcher(menu)

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
        except Exception as ex:
            err('TerminalPopupMenu::show: %s' % ex)

        menu.show_all()
        menu.popup_at_pointer(None)

        return(True)

    def add_layout_launcher(self, menu):
        """Add the layout list to the menu"""
        item = self.menu_item(Gtk.MenuItem, 'layout_launcher', '_Layouts...')
        menu.append(item)
        submenu = Gtk.Menu()
        item.set_submenu(submenu)
        layouts = self.config.list_layouts()
        for layout in layouts:
                item = Gtk.MenuItem(layout)
                item.connect('activate', lambda x: spawn_new_terminator(self.terminator.origcwd, ['-u', '-l', x.get_label()]))
                submenu.append(item)
