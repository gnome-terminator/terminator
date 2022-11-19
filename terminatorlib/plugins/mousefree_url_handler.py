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
from terminatorlib.plugin_util import KeyBindUtil

from terminatorlib.util import get_config_dir, err, dbg, gerr
from terminatorlib.keybindings import Keybindings, KeymapError
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

    capabilities = ['url_handler']
    handler_name = 'MouseFreeURLHandler'
    nameopen     = None
    namecopy     = None
    match        = None

    flag_http_on = False
    keyb  = KeyBindUtil()
    matches      = []
    matches_ptr  = -1
    #basic pattern
    searchtext  = "https?\:\/\/[^\s]+[\/\w]"

    def __init__(self):
        self.connect_signals()

        config = Config()
        self.keyb.bindkey_check_config([PluginUrlFindNext , PluginUrlActFindNext, "<Alt>j"], config)
        self.keyb.bindkey_check_config([PluginUrlFindPrev , PluginUrlActFindPrev, "<Alt>k"], config)
        self.keyb.bindkey_check_config([PluginUrlEsc   , PluginUrlActEsc,    "Escape"],      config)
        self.keyb.bindkey_check_config([PluginUrlLaunch, PluginUrlActLaunch, "<Alt>Return"], config)

    def connect_signals(self):
        self.windows = Terminator().get_windows()
        for window in self.windows:
            window.connect('key-press-event', self.on_keypress)
        return

    def callback(self, url):
        """Actually we don't need to do anything for this to work"""
        return(url)

    def extract(self):
        #can we do extract more efficiently
        col, row =  self.vte.get_cursor_position()
        (txt, attr) = self.vte.get_text_range(0,0,row, col)
        self.matches = re.findall(self.searchtext, txt)
        self.matches_ptr = len(self.matches)-1

    def get_term(self):
        return  Terminator().last_focused_term

    def get_selected_url(self):
        if len(self.matches):
            dbg("selected URL (%s %s)" % (self.matches_ptr, self.matches[self.matches_ptr]))
            return self.matches[self.matches_ptr]
        dbg("selected URL (%s %s)" % (self.matches_ptr, "not found"))
        return None

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
                self.get_selected_url() # dbg url print
                self.vte.search_find_previous()
                self.vte.copy_clipboard()
                return True

            self.vte.search_find_previous()

            if self.matches_ptr > 0:
                self.matches_ptr -= 1
            elif len(self.matches):
                self.matches_ptr = len(self.matches)-1

            self.vte.copy_clipboard()
            self.get_selected_url() # dbg url print
            return True

        if act == PluginUrlActEsc:
            self.matches = []
            self.vte = self.get_term().get_vte()
            self.vte.search_set_regex(None, 0)
            self.flag_http_on = False
            dbg("search URL off")

        if act == PluginUrlActLaunch:
            url = self.get_selected_url()
            if url:
                self.get_term().open_url(url, prepare=False)

    def search(self):
        self.flag_http_on = True
        self.vte = self.get_term().get_vte()

        self.vte.search_set_wrap_around(True)
        regex_flags_pcre2 = (regex.FLAGS_PCRE2 | regex.PCRE2_CASELESS)
        searchre = Vte.Regex.new_for_search(self.searchtext,
                        len(self.searchtext), regex_flags_pcre2)

        self.vte.search_set_regex(searchre, 0)

