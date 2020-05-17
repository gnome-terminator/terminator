"""A simple browser widget with WebKit2"""

import gi
gi.require_version('WebKit2', '4.0')
from gi.repository import GObject, Gtk, WebKit2
from .terminator import Terminator

class Browser(Gtk.VBox):
    __gsignals__ = {
        'title-change': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_STRING,)),
        'tab-new': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_BOOLEAN, GObject.TYPE_OBJECT)),
        'browser-tab-new': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_BOOLEAN, GObject.TYPE_OBJECT)),
        'tab-change': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_INT,)),
        'move-tab': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_STRING,)),
    }

    def __init__(self, *args, **kwargs):
        super(Browser, self).__init__(*args, **kwargs)

        self.window_title = "New browser window"

        self.terminator = Terminator()

        self.uri_entry = Gtk.Entry()
        self.uri_entry.connect("activate", self.on_uri_set)
        self.go_button = Gtk.Button("Go")
        self.go_button.connect("clicked", self.on_uri_set)

        self.uri_bar = Gtk.HBox()
        self.uri_bar.pack_start(self.uri_entry, True, True, 0)
        self.uri_bar.pack_start(self.go_button, False, False, 0)

        self.webview = WebKit2.WebView()
        self.webview.connect('notify::title', self.on_title_change)
        self.webview.connect('notify::uri', self.on_uri)
        self.webview.load_uri('about:blank')

        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.add(self.webview)

        self.pack_start(self.uri_bar, False, False, 0)
        self.pack_start(self.scrolled_window, True, True, 0)

        self.connect('key-press-event', self.on_keypress)
        self.show_all()


    def on_uri_set(self, *args, **kwargs):
        uri = self.uri_entry.get_text()
        if '://' not in uri:
            uri = 'http://' + uri
        self.webview.load_uri(uri)

    def on_uri(self, *args, **kwargs):
        uri = self.webview.get_uri()
        self.uri_entry.set_text(uri)

    def on_keypress(self, widget, event):
        mapping = self.terminator.keybindings.lookup(event)
        if mapping:
            try:
                handler = getattr(self, "key_" + mapping)
                handler()
                return(True)
            except AttributeError:
                return(False)
        return(False)

    def get_window_title(self):
        return self.window_title

    def on_title_change(self, widget, event):
        title = widget.get_title()
        self.window_title = title
        self.emit('title-change', title)

    ########################################################################
    # FIXME: all os the keybinding handlers below were copied from Terminal
    ########################################################################

    def key_new_window(self):
        self.terminator.new_window(self.get_cwd(), self.get_profile())

    def key_new_tab(self):
        self.get_toplevel().tab_new(self)

    def key_new_browser_tab(self):
        self.get_toplevel().browser_tab_new(self)

    def key_new_terminator(self):
        spawn_new_terminator(self.origcwd, ['-u'])

    def key_move_tab_right(self):
        self.emit('move-tab', 'right')

    def key_move_tab_left(self):
        self.emit('move-tab', 'left')

    def key_next_tab(self):
        self.emit('tab-change', -1)

    def key_prev_tab(self):
        self.emit('tab-change', -2)

    def key_switch_to_tab_1(self):
        self.emit('tab-change', 0)

    def key_switch_to_tab_2(self):
        self.emit('tab-change', 1)

    def key_switch_to_tab_3(self):
        self.emit('tab-change', 2)

    def key_switch_to_tab_4(self):
        self.emit('tab-change', 3)

    def key_switch_to_tab_5(self):
        self.emit('tab-change', 4)

    def key_switch_to_tab_6(self):
        self.emit('tab-change', 5)

    def key_switch_to_tab_7(self):
        self.emit('tab-change', 6)

    def key_switch_to_tab_8(self):
        self.emit('tab-change', 7)

    def key_switch_to_tab_9(self):
        self.emit('tab-change', 8)

    def key_switch_to_tab_10(self):
        self.emit('tab-change', 9)

    def key_new_tab(self):
        self.get_toplevel().tab_new(self)

    def key_new_browser_tab(self):
        self.get_toplevel().browser_tab_new(self)

    def key_new_terminator(self):
        spawn_new_terminator(self.origcwd, ['-u'])

    def key_help(self):
        manual_index_page = manual_lookup()
        if manual_index_page:
            self.open_url(manual_index_page)


GObject.type_register(Browser)
# vim: set expandtab ts=4 sw=4:
