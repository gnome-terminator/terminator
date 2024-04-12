"""
- With min changes to main code base, implementing mouse free url handling.
- Using shortcuts to browse URL, next / previous, clear search. Selected URL
is copied to clipboard.

- Vishweshwar Saran Singh Deo vssdeo@gmail.com
"""

import gi
gi.require_version('Vte', '2.91')  # vte-0.38 (gnome-3.14)
from gi.repository import Vte

from terminatorlib.terminator import Terminator

from terminatorlib.config import Config
import terminatorlib.plugin as plugin
from terminatorlib.plugin import KeyBindUtil

from terminatorlib.util import get_config_dir, err, dbg, gerr
from terminatorlib import regex

import re


AVAILABLE = ['MouseFreeURLHandler']

PluginUrlActFindNext = "plugin_url_find_next"
PluginUrlActFindPrev = "plugin_url_find_prev"
PluginUrlActEsc      = "plugin_url_esc"
PluginUrlActLaunch   = "plugin_url_launch"


PluginUrlFindNext = "Plugin Url Find Next"
PluginUrlFindPrev = "Plugin Url Find Prev"
PluginUrlEsc      = "Plugin Url Esc"
PluginUrlLaunch   = "Plugin Url Launch"

class MouseFreeURLHandler(plugin.Plugin):

    capabilities = ['MouseFreeHandler']
    handler_name = 'MouseFreeHandler'
    nameopen     = None
    namecopy     = None
    match        = None

    flag_http_on = False
    config       = Config()
    keyb         = KeyBindUtil(config)
    matches      = []
    matches_ptr  = -1
    vte          = None
    cur_term     = None
    #basic pattern
    searchtext  = "https?\:\/\/[^\s]+[\/\w]"

    def __init__(self):
        self.connect_signals()

        self.keyb.bindkey_check_config(
                [PluginUrlFindNext , PluginUrlActFindNext, "<Alt>j"])
        self.keyb.bindkey_check_config(
                [PluginUrlFindPrev , PluginUrlActFindPrev, "<Alt>k"])
        self.keyb.bindkey_check_config(
                [PluginUrlEsc   , PluginUrlActEsc,         "Escape"])
        self.keyb.bindkey_check_config(
                [PluginUrlLaunch, PluginUrlActLaunch,      "<Alt>Return"])

    def connect_signals(self):
        for term in Terminator().terminals:
            dbg("signal connect term:%s" % term)
            term.connect('focus-in', self.on_focus_in)

        self.windows = Terminator().get_windows()
        for window in self.windows:
            window.connect('key-press-event', self.on_keypress)

    def unload(self):
        dbg("unloading")
        for term in Terminator().terminals:
            try:
                term.disconnect_by_func(self.on_focus_in)
            except:
                dbg("no connected signals")
            
        for window in self.windows:
            try:
                window.disconnect_by_func(self.on_keypress)
            except:
                dbg("no connected signals")

        self.keyb.unbindkey(
                [PluginUrlFindNext , PluginUrlActFindNext, "<Alt>j"])
        self.keyb.unbindkey(
                [PluginUrlFindPrev , PluginUrlActFindPrev, "<Alt>k"])
        self.keyb.unbindkey(
                [PluginUrlEsc   , PluginUrlActEsc,         "Escape"])
        self.keyb.unbindkey(
                [PluginUrlLaunch, PluginUrlActLaunch,      "<Alt>Return"])

    def extract(self):
        #can we do extract more efficiently
        col, row =  self.vte.get_cursor_position()
        (txt, attr) = self.vte.get_text_range_format(
                                Vte.Format.TEXT, 0, 0, row, col)
        self.matches = re.findall(self.searchtext, txt)
        self.matches_ptr = len(self.matches)-1

    def get_selected_url(self):
        if len(self.matches):
            dbg("found selected URL (%s %s)" %
                (self.matches_ptr, self.matches[self.matches_ptr]))
            return self.matches[self.matches_ptr]
        dbg("selected URL (%s %s)" % (self.matches_ptr, "not found"))
        return None

    def get_focussed_terminal(self):
        """iterate over all the terminals to find which, if any, has focus"""
        for terminal in Terminator().terminals:
            if terminal.get_vte().has_focus():
                return(terminal)
        return(None)

    def on_focus_in(self, widget, event = None):
        dbg("focus-in clear url search buffer widget: %s" % widget)
        self.cur_term = self.get_focussed_terminal()
        self.vte      = self.cur_term.get_vte()
        self.clear_search()

    def on_keypress(self, widget, event):
        act = self.keyb.keyaction(event)
        dbg("keyaction: (%s) (%s)" % (str(act), event.keyval))

        if act == PluginUrlActFindNext:
            if not self.flag_http_on:
                dbg("search URL on")
                self.search()
                self.extract()
                #so when we start search last item be selected
                self.vte.search_find_previous()
                self.get_selected_url() # dbg url print
                self.vte.copy_clipboard()
                return True
            else:
                self.vte.search_find_next()

            if (self.matches_ptr < len(self.matches)-1):
                self.matches_ptr += 1
            else:
                self.matches_ptr = 0

            self.vte.copy_clipboard()
            self.get_selected_url() # dbg url print
            return True

        if act == PluginUrlActFindPrev:
            if not self.flag_http_on:
                self.search()
                self.extract()
                self.vte.search_find_previous()
                self.get_selected_url() # dbg url print
                self.vte.copy_clipboard()
                return True
            else:
                self.vte.search_find_previous()

            if self.matches_ptr > 0:
                self.matches_ptr -= 1
            elif len(self.matches):
                self.matches_ptr = len(self.matches)-1

            self.vte.copy_clipboard()
            self.get_selected_url() # dbg url print
            return True

        if act == PluginUrlActEsc:
            self.clear_search()
            return

        if act == PluginUrlActLaunch:
            url = self.get_selected_url()
            if url:
                self.cur_term.open_url(url, prepare=False)

            return

        #TODO: use case for KeyBindUtil
        #So this is capturing <Return> key as if user presses return
        #then the current selection would be cleared in case he types
        #more commands or text in terminal has more urls now. So next
        #time search should restart with complete text

        #For KeyBindUtil if we register <Return> then keybinding will
        #be shown in Preferences->Keybindings and if any other plugin
        #wants to listen to same key code it will throw error since in
        #UI binding has to be unique. May be we can have keybinds
        #hidden from UI which plugins can use internally

        if event.keyval == 65293: #<Return>
            self.clear_search()
            return

    def clear_search(self):
        self.matches = []
        self.flag_http_on = False
        self.matches_ptr  = -1

        if self.vte:
            self.vte.search_set_regex(None, 0)
            dbg("search URL off")
            self.vte.unselect_all()

    def search(self):
        dbg("searching text")
        self.flag_http_on = True

        self.vte.search_set_wrap_around(True)
        regex_flags_pcre2 = (regex.FLAGS_PCRE2 | regex.PCRE2_CASELESS)
        searchre = Vte.Regex.new_for_search(self.searchtext,
                        len(self.searchtext), regex_flags_pcre2)

        self.vte.search_set_regex(searchre, 0)

