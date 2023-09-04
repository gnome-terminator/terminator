"""
- bookmark plugin, basic features 
- Requires support of KeyBindUtil from Plugin which assists short cuts
- may be edit option  can be added via Preferences Plugin window 
- config has = so rhs can be used for tags
- TODO: config changes if can be brought to plugin code
-       support in Preferences window
-       limit on number of urls via Preferences ?
-       display shortcuts in menu
-       selection of urls from keyboard
-
- Defaults:
- press <Alt>b (see below) to add current dir in bookmark <Alt>r to remove
- sub-menu via right click->bookmarks->urls->(act menu)
-
- Vishweshwar Saran Singh Deo vssdeo@gmail.com
"""

import gi
gi.require_version('Vte', '2.91')  # vte-0.38 (gnome-3.14)
from gi.repository import Vte

from gi.repository import Gtk
from terminatorlib.terminator import Terminator

from terminatorlib.config import Config
import terminatorlib.plugin as plugin
from terminatorlib.plugin import KeyBindUtil

from terminatorlib.util import get_config_dir, err, dbg, gerr
from terminatorlib import regex

import re


AVAILABLE = ['BookmarkPlugin']

PluginActAdd = "plugin_add"
PluginActDel = "plugin_del"
#PluginActSel = "plugin_sel"

PluginAddDesc = "Plugin Add Bookmark"
PluginDelDesc = "Plugin Del Bookmark"
#PluginSelDesc = "Plugin Select Bookmark"

class BookmarkPlugin(plugin.MenuItem):

    capabilities = ['terminal_menu']
    handler_name = 'BookmarkPlugin'
    nameopen     = None
    namecopy     = None

    config       = Config()
    keyb         = KeyBindUtil(config)

    def __init__(self):
        self.connect_signals()

        self.keyb.bindkey_check_config(
                [PluginAddDesc , PluginActAdd, "<Alt>b"])
        self.keyb.bindkey_check_config(
                [PluginDelDesc , PluginActDel, "<Alt>r"])
        #self.keyb.bindkey_check_config(
        #        [PluginSelDesc , PluginActSel, "<Alt>Return"])

        sections = self.config.plugin_get_config(self.__class__.__name__)
        if not isinstance(sections, dict):
            return
   
    def connect_signals(self):
        self.windows = Terminator().get_windows()
        for window in self.windows:
            window.connect('key-press-event', self.on_keypress)

    def callback(self, menuitems, menu, terminal):
        item = Gtk.MenuItem.new_with_label('Bookmarks')
        bmarks = self.config.plugin_get_config(self.__class__.__name__)

        smenu = Gtk.Menu()
        add_item = Gtk.MenuItem('Add Bookmark')
        add_item.connect('activate', lambda x: self.add_bookmark())
        smenu.append(add_item)

        for bmark in bmarks:
            sitem = Gtk.MenuItem(bmark)
            #sitem.connect('activate', 
            #    lambda x, d=bmark: self.open_bookmark_tab(terminal, d))

            smenu.append(sitem)
    
            #sub-menu to remove via right click->bookmarks->urls->(act menu)
            act_smenu = Gtk.Menu()
            act_sitem_open_tab = Gtk.MenuItem('Open in New Window')
            act_sitem_open_tab.connect('activate', 
                lambda x, d=bmark: self.open_bookmark_window(terminal, d))
            act_smenu.append(act_sitem_open_tab)

            act_sitem_open_win = Gtk.MenuItem('Open in New Tab')
            act_sitem_open_win.connect('activate', 
                lambda x, d=bmark: self.open_bookmark_tab(terminal, d))
            act_smenu.append(act_sitem_open_win)

            act_sitem_item_del = Gtk.MenuItem('Remove Bookmark')
            act_sitem_item_del.connect('activate', 
                lambda x, d=bmark: self.del_bookmark(d))
            act_smenu.append(act_sitem_item_del)

            sitem.set_submenu(act_smenu)
            
        item.set_submenu(smenu)
        menuitems.append(item)
        
    def unload(self):
        dbg("unloading")
            
        for window in self.windows:
            try:
                window.disconnect_by_func(self.on_keypress)
            except:
                dbg("no connected signals")

        self.keyb.unbindkey(
                [PluginAddDesc , PluginActAdd, "<Alt>b"])
        self.keyb.unbindkey(
                [PluginDelDesc , PluginActDel, "<Alt>r"])
        #self.keyb.unbindkey(
        #        [PluginSelDesc , PluginActSel, "<Alt>Return"])

    def get_term(self):
        return  Terminator().last_focused_term

    def open_bookmark_tab(self, terminal, bookmark):
        terminal.get_toplevel().tab_new(cwd=bookmark)

    def open_bookmark_window(self, terminal, bookmark):
        Terminator().new_window(cwd = bookmark)

    def del_bookmark(self, bookmark):
        dbg("del bookmark:(%s)" % bookmark)
        bmarks = self.config.plugin_get_config(self.__class__.__name__)
        bmarks.pop(bookmark, None)
        self.config.save()

    def add_bookmark(self):
        cwd = self.get_term().get_cwd()
        dbg("add bookmark: %s" % cwd)
        self.config.plugin_set(self.__class__.__name__, cwd, '')
        self.config.save()

    def on_keypress(self, widget, event):
        act = self.keyb.keyaction(event)
        dbg("keyaction: (%s) (%s)" % (str(act), event.keyval))

        if act == PluginActAdd:
            self.add_bookmark()
            return True

        if act == PluginActDel:
            cwd = self.get_term().get_cwd()
            self.del_bookmark(cwd)
            return True

        #if act == PluginActSel:
        #    dbg("sel bookmark")
        #    return True


