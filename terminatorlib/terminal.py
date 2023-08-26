# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""terminal.py - classes necessary to provide Terminal widgets"""


import os
import signal
import gi
from gi.repository import GLib, GObject, Pango, Gtk, Gdk, GdkPixbuf, cairo
gi.require_version('Vte', '2.91')  # vte-0.38 (gnome-3.14)
from gi.repository import Vte
import subprocess
try:
    from urllib.parse import unquote as urlunquote
except ImportError:
    from urllib import unquote as urlunquote

from .util import dbg, err, spawn_new_terminator, make_uuid, manual_lookup, display_manager
from . import util
from .config import Config
from .cwd import get_pid_cwd
from .factory import Factory
from .terminator import Terminator
from .titlebar import Titlebar
from .terminal_popup_menu import TerminalPopupMenu
from .prefseditor import PrefsEditor
from .searchbar import Searchbar
from .translation import _
from .signalman import Signalman
from . import plugin
from terminatorlib.layoutlauncher import LayoutLauncher
from . import regex

# pylint: disable-msg=R0904
class Terminal(Gtk.VBox):
    """Class implementing the VTE widget and its wrappings"""

    __gsignals__ = {
        'pre-close-term': (GObject.SignalFlags.RUN_LAST, None, ()),
        'close-term': (GObject.SignalFlags.RUN_LAST, None, ()),
        'title-change': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_STRING,)),
        'insert-term-name': (GObject.SignalFlags.RUN_LAST, None, ()),
        'enumerate': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_INT,)),
        'group-tab': (GObject.SignalFlags.RUN_LAST, None, ()),
        'group-tab-toggle': (GObject.SignalFlags.RUN_LAST, None, ()),
        'ungroup-tab': (GObject.SignalFlags.RUN_LAST, None, ()),
        'ungroup-all': (GObject.SignalFlags.RUN_LAST, None, ()),
        'split-auto': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_STRING,)),
        'split-horiz': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_STRING,)),
        'split-vert': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_STRING,)),
        'rotate-cw': (GObject.SignalFlags.RUN_LAST, None, ()),
        'rotate-ccw': (GObject.SignalFlags.RUN_LAST, None, ()),
        'tab-new': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_BOOLEAN, GObject.TYPE_OBJECT)),
        'tab-top-new': (GObject.SignalFlags.RUN_LAST, None, ()),
        'focus-in': (GObject.SignalFlags.RUN_LAST, None, ()),
        'focus-out': (GObject.SignalFlags.RUN_LAST, None, ()),
        'zoom': (GObject.SignalFlags.RUN_LAST, None, ()),
        'maximise': (GObject.SignalFlags.RUN_LAST, None, ()),
        'unzoom': (GObject.SignalFlags.RUN_LAST, None, ()),
        'resize-term': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_STRING,)),
        'navigate': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_STRING,)),
        'tab-change': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_INT,)),
        'group-all': (GObject.SignalFlags.RUN_LAST, None, ()),
        'group-all-toggle': (GObject.SignalFlags.RUN_LAST, None, ()),
        'move-tab': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_STRING,)),
        'group-win': (GObject.SignalFlags.RUN_LAST, None, ()),
        'group-win-toggle': (GObject.SignalFlags.RUN_LAST, None, ()),
        'ungroup-win': (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    TARGET_TYPE_VTE = 8
    TARGET_TYPE_MOZ = 9

    MOUSEBUTTON_LEFT = 1
    MOUSEBUTTON_MIDDLE = 2
    MOUSEBUTTON_RIGHT = 3

    terminator = None
    vte = None
    terminalbox = None
    scrollbar = None
    titlebar = None
    searchbar = None

    group = None
    cwd = None
    origcwd = None
    command = None
    clipboard = None
    pid = None

    matches = None
    regex_flags = None
    config = None
    custom_font_size = None
    layout_command = None
    relaunch_command = None
    directory = None

    is_held_open = False

    fgcolor_active = None
    fgcolor_inactive = None
    bgcolor = None
    bgcolor_inactive = None
    palette_active = None
    palette_inactive = None

    composite_support = None

    cnxids = None
    targets_for_new_group = None

    def __init__(self):
        """Class initialiser"""
        GObject.GObject.__init__(self)

        self.terminator = Terminator()
        self.terminator.register_terminal(self)

        # FIXME: Surely these should happen in Terminator::register_terminal()?
        self.connect('enumerate', self.terminator.do_enumerate)
        self.connect('insert-term-name', self.terminator.do_insert_term_name)
        self.connect('focus-in', self.terminator.focus_changed)
        self.connect('focus-out', self.terminator.focus_left)

        self.matches = {}
        self.cnxids = Signalman()

        self.config = Config()

        self.cwd = get_pid_cwd()
        self.origcwd = self.terminator.origcwd
        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)

        self.pending_on_vte_size_allocate = False

        self.vte = Vte.Terminal()
        self.vte.set_allow_hyperlink(True)
        self.vte._draw_data = None
        if not hasattr(self.vte, "set_opacity") or \
           not hasattr(self.vte, "is_composited"):
            self.composite_support = False
        else:
            self.composite_support = True
        dbg('composite_support: %s' % self.composite_support)

        self.vte.show()

        #force to load for new window/terminal use case loading plugin
        #and connecting signals, note the line update_url_matches also
        #calls load_plugins, but it won't reload since already loaded

        self.load_plugins(force = True)

        self.update_url_matches()

        self.terminalbox = self.create_terminalbox()

        self.titlebar = Titlebar(self)
        self.titlebar.connect_icon(self.on_group_button_press)
        self.titlebar.connect('edit-done', self.on_edit_done)
        self.connect('title-change', self.titlebar.set_terminal_title)
        self.titlebar.connect('create-group', self.really_create_group)
        self.titlebar.update('window-focus-out')
        self.titlebar.show_all()

        self.searchbar = Searchbar()
        self.searchbar.connect('end-search', self.on_search_done)

        self.show()
        if self.config['title_at_bottom']:
            self.pack_start(self.terminalbox, True, True, 0)
            self.pack_start(self.titlebar, False, True, 0)
        else:
            self.pack_start(self.titlebar, False, True, 0)
            self.pack_start(self.terminalbox, True, True, 0)

        self.pack_end(self.searchbar, True, True, 0)

        self.connect_signals()

        os.putenv('TERM', self.config['term'])
        os.putenv('COLORTERM', self.config['colorterm'])

        env_proxy = os.getenv('http_proxy')
        if not env_proxy:
            if self.config['http_proxy'] and self.config['http_proxy'] != '':
                os.putenv('http_proxy', self.config['http_proxy'])
        self.reconfigure()
        self.vte.set_size(80, 24)

    def set_background_image(self,image):
        try: 
            bg_pixbuf = GdkPixbuf.Pixbuf.new_from_file(image)
            self.background_image = Gdk.cairo_surface_create_from_pixbuf(bg_pixbuf, 1, None)
            self.vte.set_clear_background(False)
            self.vte.connect("draw", self.background_draw)
        except Exception as e:
            self.background_image = None
            self.vte.set_clear_background(True)
            err('error loading background image: %s, %s' % (type(e).__name__,e))

    def get_vte(self):
        """This simply returns the vte widget we are using"""
        return(self.vte)

    def force_set_profile(self, widget, profile):
        """Forcibly set our profile"""
        self.set_profile(widget, profile, True)

    def set_profile(self, _widget, profile, force=False):
        """Set our profile"""
        if profile != self.config.get_profile():
            self.config.set_profile(profile, force)
            self.reconfigure()

    def get_profile(self):
        """Return our profile name"""
        return(self.config.profile)

    def switch_to_next_profile(self):
        profilelist = self.config.list_profiles()
        list_length = len(profilelist)

        if list_length > 1:
            if profilelist.index(self.get_profile()) + 1 == list_length:
                self.force_set_profile(False, profilelist[0])
            else:
                self.force_set_profile(False, profilelist[profilelist.index(self.get_profile()) + 1])

    def switch_to_previous_profile(self):
        profilelist = self.config.list_profiles()
        list_length = len(profilelist)

        if list_length > 1:
            if profilelist.index(self.get_profile()) == 0:
                self.force_set_profile(False, profilelist[list_length - 1])
            else:
                self.force_set_profile(False, profilelist[profilelist.index(self.get_profile()) - 1])

    def get_cwd(self):
        """Return our cwd"""
        vte_cwd = self.vte.get_current_directory_uri()
        if vte_cwd:
            # OSC7 pwd gives an answer
            return(GLib.filename_from_uri(vte_cwd)[0])
        else:
            # Fall back to old gtk2 method
            dbg('calling get_pid_cwd')
            return(get_pid_cwd(self.pid))

    def close(self):
        """Close ourselves"""
        dbg('close: called')
        self.cnxids.remove_widget(self.vte)
        self.emit('close-term')
        if self.pid is not None:
            try:
                dbg('close: killing %d' % self.pid)
                os.kill(self.pid, signal.SIGHUP)
            except Exception as ex:
                # We really don't want to care if this failed. Deep OS voodoo is
                # not what we should be doing.
                dbg('os.kill failed: %s' % ex)
                pass

        if self.vte:
            self.terminalbox.remove(self.vte)
            del(self.vte)

    def create_terminalbox(self):
        """Create a GtkHBox containing the terminal and a scrollbar"""

        terminalbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        self.scrollbar = Gtk.Scrollbar.new(Gtk.Orientation.VERTICAL, adjustment=self.vte.get_vadjustment())
        self.scrollbar.set_no_show_all(True)

        terminalbox.pack_start(self.vte, True, True, 0)
        terminalbox.pack_start(self.scrollbar, False, True, 0)
        terminalbox.show_all()

        return(terminalbox)

    def load_plugins(self, force = False):
        registry = plugin.PluginRegistry()
        registry.load_plugins(force)

    def _add_regex(self, name, re):
        match = -1
        if regex.FLAGS_PCRE2:
            try:
                reg = Vte.Regex.new_for_match(re, len(re), self.regex_flags or regex.FLAGS_PCRE2)
                match = self.vte.match_add_regex(reg, 0)
            except GLib.Error:
                # happens when PCRE2 support is not builtin (Ubuntu < 19.10)
                pass

        # try the "old" glib regex
        if match < 0:
            reg = GLib.Regex.new(re, self.regex_flags or regex.FLAGS_GLIB, 0)
            match = self.vte.match_add_gregex(reg, 0)

        self.matches[name] = match
        self.vte.match_set_cursor_name(self.matches[name], 'pointer')

    def update_url_matches(self):
        """Update the regexps used to match URLs"""
        userchars = "-A-Za-z0-9"
        passchars = "-A-Za-z0-9,?;.:/!%$^*&~\"#'"
        hostchars = "-A-Za-z0-9:\[\]"
        pathchars = "-A-Za-z0-9_$.+!*(),;:@&=?/~#%'"
        schemes   = "(news:|telnet:|nntp:|file:/|https?:|ftps?:|webcal:|ssh:)"
        user      = "[" + userchars + "]+(:[" + passchars + "]+)?"
        urlpath   = "/[" + pathchars + "]*[^]'.}>) \t\r\n,\\\"]"

        lboundry = "\\b"
        rboundry = "\\b"

        re = (lboundry + schemes +
                "//(" + user + "@)?[" + hostchars  +".]+(:[0-9]+)?(" +
                urlpath + ")?" + rboundry + "/?")
        self._add_regex('full_uri', re)

        if self.matches['full_uri'] == -1:
            err ('Terminal::update_url_matches: Failed adding URL matches')
        else:
            re = (lboundry +
                    '(callto:|h323:|sip:)' + "[" + userchars + "+][" +
                    userchars + ".]*(:[0-9]+)?@?[" + pathchars + "]+" +
                    rboundry)
            self._add_regex('voip', re)

            re = (lboundry +
                    "(www|ftp)[" + hostchars + "]*\.[" + hostchars +
                    ".]+(:[0-9]+)?(" + urlpath + ")?" + rboundry + "/?")
            self._add_regex('addr_only', re)

            re = (lboundry +
                    "(mailto:)?[a-zA-Z0-9][a-zA-Z0-9.+-]*@[a-zA-Z0-9]" +
                            "[a-zA-Z0-9-]*\.[a-zA-Z0-9][a-zA-Z0-9-]+" +
                            "[.a-zA-Z0-9-]*" + rboundry)
            self._add_regex('email', re)

            re = (lboundry +
                  """news:[-A-Z\^_a-z{|}~!"#$%&'()*+,./0-9;:=?`]+@""" +
                            "[-A-Za-z0-9.]+(:[0-9]+)?" + rboundry)
            self._add_regex('nntp', re)

            # Now add any matches from plugins
            try:
                registry = plugin.PluginRegistry()
                registry.load_plugins()
                plugins = registry.get_plugins_by_capability('url_handler')

                for urlplugin in plugins:
                    name = urlplugin.handler_name
                    match = urlplugin.match
                    if name in self.matches:
                        dbg('refusing to add duplicate match %s' % name)
                        continue

                    self._add_regex(name, match)

                    dbg('added plugin URL handler for %s (%s) as %d' %
                        (name, urlplugin.__class__.__name__,
                        self.matches[name]))
            except Exception as ex:
                err('Exception occurred adding plugin URL match: %s, %s' % (type(ex).__name__, ex))

    def match_add(self, name, match):
        """Register a URL match"""
        if name in self.matches:
            err('Terminal::match_add: Refusing to create duplicate match %s' % name)
            return

        self._add_regex(name, match)

    def match_remove(self, name):
        """Remove a previously registered URL match"""
        if name not in self.matches:
            err('Terminal::match_remove: Unable to remove non-existent match %s' % name)
            return
        self.vte.match_remove(self.matches[name])
        del(self.matches[name])

    def maybe_copy_clipboard(self):
        if self.config['copy_on_selection'] and self.vte.get_has_selection():
            self.vte.copy_clipboard()

    def connect_signals(self):
        """Connect all the gtk signals and drag-n-drop mechanics"""

        self.scrollbar.connect('button-press-event', self.on_buttonpress)

        self.cnxids.new(self.vte, 'key-press-event', self.on_keypress)
        self.cnxids.new(self.vte, 'button-press-event', self.on_buttonpress)
        self.cnxids.new(self.vte, 'scroll-event', self.on_mousewheel)
        self.cnxids.new(self.vte, 'popup-menu', self.popup_menu)

        srcvtetargets = [("vte", Gtk.TargetFlags.SAME_APP, self.TARGET_TYPE_VTE)]
        dsttargets = [("vte", Gtk.TargetFlags.SAME_APP, self.TARGET_TYPE_VTE),
                      ('text/x-moz-url', 0, self.TARGET_TYPE_MOZ),
                      ('_NETSCAPE_URL', 0, 0)]
        '''
        The following should work, but on my system it corrupts the returned
        TargetEntry's in the newdstargets with binary crap, causing "Segmentation
        fault (core dumped)" when the later drag_dest_set gets called.
        
        dsttargetlist = Gtk.TargetList.new([])
        dsttargetlist.add_text_targets(0)
        dsttargetlist.add_uri_targets(0)
        dsttargetlist.add_table(dsttargets)
        
        newdsttargets = Gtk.target_table_new_from_list(dsttargetlist)
        '''
        # FIXME: Temporary workaround for the problems with the correct way of doing things
        dsttargets.extend([('text/plain', 0, 0),
                           ('text/plain;charset=utf-8', 0, 0),
                           ('TEXT', 0, 0),
                           ('STRING', 0, 0),
                           ('UTF8_STRING', 0, 0),
                           ('COMPOUND_TEXT', 0, 0),
                           ('text/uri-list', 0, 0)])
        # Convert to target entries
        srcvtetargets = [Gtk.TargetEntry.new(*tgt) for tgt in srcvtetargets]
        dsttargets = [Gtk.TargetEntry.new(*tgt) for tgt in dsttargets]

        dbg('Finalised drag targets: %s' % dsttargets)

        for (widget, mask) in [
            (self.vte, Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.BUTTON3_MASK),
            (self.titlebar, Gdk.ModifierType.BUTTON1_MASK)]:
            widget.drag_source_set(mask, srcvtetargets, Gdk.DragAction.MOVE)

        self.vte.drag_dest_set(Gtk.DestDefaults.MOTION |
                Gtk.DestDefaults.HIGHLIGHT | Gtk.DestDefaults.DROP,
                dsttargets, Gdk.DragAction.COPY | Gdk.DragAction.MOVE)

        for widget in [self.vte, self.titlebar]:
            self.cnxids.new(widget, 'drag-begin', self.on_drag_begin, self)
            self.cnxids.new(widget, 'drag-data-get', self.on_drag_data_get,
            self)

        self.cnxids.new(self.vte, 'drag-motion', self.on_drag_motion, self)
        self.cnxids.new(self.vte, 'drag-data-received',
            self.on_drag_data_received, self)

        self.cnxids.new(self.vte, 'selection-changed',
            lambda widget: self.maybe_copy_clipboard())

        if self.composite_support:
            self.cnxids.new(self.vte, 'composited-changed', self.reconfigure)

        self.cnxids.new(self.vte, 'window-title-changed', lambda x:
            self.emit('title-change', self.get_window_title()))
        self.cnxids.new(self.vte, 'grab-focus', self.on_vte_focus)
        self.cnxids.new(self.vte, 'focus-in-event', self.on_vte_focus_in)
        self.cnxids.new(self.vte, 'focus-out-event', self.on_vte_focus_out)
        self.cnxids.new(self.vte, 'size-allocate', self.deferred_on_vte_size_allocate)

        self.vte.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK)
        self.cnxids.new(self.vte, 'enter_notify_event',
            self.on_vte_notify_enter)

        self.cnxids.new(self.vte, 'realize', self.reconfigure)

    def create_popup_group_menu(self, widget, event = None):
        """Pop up a menu for the group widget"""
        if event:
            button = event.button
            time = event.time
        else:
            button = 0
            time = 0

        menu = self.populate_group_menu()
        menu.show_all()
        menu.popup_at_widget(widget,Gdk.Gravity.SOUTH_WEST,Gdk.Gravity.NORTH_WEST,None)
        return(True)

    def populate_group_menu(self):
        """Fill out a group menu"""
        menu = Gtk.Menu()
        self.group_menu = menu
        groupitems = []

        item = Gtk.MenuItem.new_with_mnemonic(_('N_ew group...'))
        item.connect('activate', self.create_group)
        menu.append(item)

        if len(self.terminator.groups) > 0:
            cnxs = []
            item = Gtk.RadioMenuItem.new_with_mnemonic(groupitems, _('_None'))
            groupitems = item.get_group()
            item.set_active(self.group == None)
            cnxs.append([item, 'toggled', self.set_group, None])
            menu.append(item)

            for group in self.terminator.groups:
                item = Gtk.RadioMenuItem.new_with_label(groupitems, group)
                groupitems = item.get_group()
                item.set_active(self.group == group)
                cnxs.append([item, 'toggled', self.set_group, group])
                menu.append(item)

            for cnx in cnxs:
                cnx[0].connect(cnx[1], cnx[2], cnx[3])

        if self.group != None or len(self.terminator.groups) > 0:
            menu.append(Gtk.SeparatorMenuItem())

        if self.group != None:
            item = Gtk.MenuItem(_('Remove group %s') % self.group)
            item.connect('activate', self.ungroup, self.group)
            menu.append(item)

        if util.has_ancestor(self, Gtk.Window):
            item = Gtk.MenuItem.new_with_mnemonic(_('G_roup all in window'))
            item.connect('activate', lambda x: self.emit('group_win'))
            menu.append(item)

            if len(self.terminator.groups) > 0:
                item = Gtk.MenuItem.new_with_mnemonic(_('Ungro_up all in window'))
                item.connect('activate', lambda x: self.emit('ungroup_win'))
                menu.append(item)

        if util.has_ancestor(self, Gtk.Notebook):
            item = Gtk.MenuItem.new_with_mnemonic(_('G_roup all in tab'))
            item.connect('activate', lambda x: self.emit('group_tab'))
            menu.append(item)

            if len(self.terminator.groups) > 0:
                item = Gtk.MenuItem.new_with_mnemonic(_('Ungro_up all in tab'))
                item.connect('activate', lambda x: self.emit('ungroup_tab'))
                menu.append(item)

        if len(self.terminator.groups) > 0:
            item = Gtk.MenuItem(_('Remove all groups'))
            item.connect('activate', lambda x: self.emit('ungroup-all'))
            menu.append(item)

        if self.group != None:
            menu.append(Gtk.SeparatorMenuItem())

            item = Gtk.MenuItem(_('Close group %s') % self.group)
            item.connect('activate', lambda x:
                         self.terminator.closegroupedterms(self.group))
            menu.append(item)

        menu.append(Gtk.SeparatorMenuItem())

        groupitems = []
        cnxs = []

        for key, value in list({_('Broadcast _all'):'all',
                          _('Broadcast _group'):'group',
                          _('Broadcast _off'):'off'}.items()):
            item = Gtk.RadioMenuItem.new_with_mnemonic(groupitems, key)
            groupitems = item.get_group()
            dbg('%s active: %s' %
                    (key, self.terminator.groupsend ==
                        self.terminator.groupsend_type[value]))
            item.set_active(self.terminator.groupsend ==
                    self.terminator.groupsend_type[value])
            cnxs.append([item, 'activate', self.set_groupsend, self.terminator.groupsend_type[value]])
            menu.append(item)

        for cnx in cnxs:
            cnx[0].connect(cnx[1], cnx[2], cnx[3])

        menu.append(Gtk.SeparatorMenuItem())

        item = Gtk.CheckMenuItem.new_with_mnemonic(_('_Split to this group'))
        item.set_active(self.config['split_to_group'])
        item.connect('toggled', lambda x: self.do_splittogroup_toggle())
        menu.append(item)

        item = Gtk.CheckMenuItem.new_with_mnemonic(_('Auto_clean groups'))
        item.set_active(self.config['autoclean_groups'])
        item.connect('toggled', lambda x: self.do_autocleangroups_toggle())
        menu.append(item)

        menu.append(Gtk.SeparatorMenuItem())

        item = Gtk.MenuItem.new_with_mnemonic(_('_Insert terminal number'))
        item.connect('activate', lambda x: self.emit('enumerate', False))
        menu.append(item)

        item = Gtk.MenuItem.new_with_mnemonic(_('Insert zero _padded terminal number'))
        item.connect('activate', lambda x: self.emit('enumerate', True))
        menu.append(item)

        item = Gtk.MenuItem.new_with_mnemonic(_('Insert terminal _name'))
        item.connect('activate', lambda x: self.emit('insert-term-name'))
        menu.append(item)

        return(menu)

    def set_group(self, _item, name):
        """Set a particular group"""
        if self.group == name:
            # already in this group, no action needed
            return
        dbg('Setting group to %s' % name)
        self.group = name
        self.titlebar.set_group_label(name)
        self.terminator.group_hoover()

    def create_group(self, _item):
        """Trigger the creation of a group via the titlebar (because popup 
        windows are really lame)"""
        self.titlebar.create_group()

    def really_create_group(self, _widget, groupname):
        """The titlebar has spoken, let a group be created"""
        self.terminator.create_group(groupname)
        self.set_group(None, groupname)

    def ungroup(self, _widget, data):
        """Remove a group"""
        # FIXME: Could we emit and have Terminator do this?
        for term in self.terminator.terminals:
            if term.group == data:
                term.set_group(None, None)
        self.terminator.group_hoover()

    def set_groupsend(self, _widget, value):
        """Set the groupsend mode"""
        # FIXME: Can we think of a smarter way of doing this than poking?
        if value in list(self.terminator.groupsend_type.values()):
            dbg('setting groupsend to %s' % value)
            self.terminator.groupsend = value

    def do_splittogroup_toggle(self):
        """Toggle the splittogroup mode"""
        self.config['split_to_group'] = not self.config['split_to_group']

    def do_autocleangroups_toggle(self):
        """Toggle the autocleangroups mode"""
        self.config['autoclean_groups'] = not self.config['autoclean_groups']

    def reconfigure(self, _widget=None):
        """Reconfigure our settings"""
        dbg('Terminal::reconfigure')
        self.cnxids.remove_signal(self.vte, 'realize')

        # Handle child command exiting
        self.cnxids.remove_signal(self.vte, 'child-exited')

        if self.config['exit_action'] == 'restart':
            self.cnxids.new(self.vte, 'child-exited', self.spawn_child, True)
        elif self.config['exit_action'] == 'hold':
            self.cnxids.new(self.vte, 'child-exited', self.held_open, True)
        elif self.config['exit_action'] in ('close', 'left'):
            self.cnxids.new(self.vte, 'child-exited',
                                            lambda x, y: self.emit('close-term'))

        # Word char support was missing from vte 0.38, silently skip this setting
        if hasattr(self.vte, 'set_word_char_exceptions'):
            self.vte.set_word_char_exceptions(self.config['word_chars'])
        self.vte.set_mouse_autohide(self.config['mouse_autohide'])

        backspace = self.config['backspace_binding']
        delete = self.config['delete_binding']

        try:
            if backspace == 'ascii-del':
                backbind = Vte.ERASE_ASCII_DELETE
            elif backspace == 'control-h':
                backbind = Vte.ERASE_ASCII_BACKSPACE
            elif backspace == 'escape-sequence':
                backbind = Vte.ERASE_DELETE_SEQUENCE
            else:
                backbind = Vte.ERASE_AUTO
        except AttributeError:
            if backspace == 'ascii-del':
                backbind = 2
            elif backspace == 'control-h':
                backbind = 1
            elif backspace == 'escape-sequence':
                backbind = 3
            else:
                backbind = 0

        try:
            if delete == 'ascii-del':
                delbind = Vte.ERASE_ASCII_DELETE
            elif delete == 'control-h':
                delbind = Vte.ERASE_ASCII_BACKSPACE
            elif delete == 'escape-sequence':
                delbind = Vte.ERASE_DELETE_SEQUENCE
            else:
                delbind = Vte.ERASE_AUTO
        except AttributeError:
            if delete == 'ascii-del':
                delbind = 2
            elif delete == 'control-h':
                delbind = 1
            elif delete == 'escape-sequence':
                delbind = 3
            else:
                delbind = 0

        self.vte.set_backspace_binding(backbind)
        self.vte.set_delete_binding(delbind)

        if not self.custom_font_size:
            try:
                if self.config['use_system_font'] == True:
                    font = self.config.get_system_mono_font()
                else:
                    font = self.config['font']
                self.set_font(Pango.FontDescription(font))
            except:
                pass
        self.vte.set_allow_bold(self.config['allow_bold'])
        if hasattr(self.vte,'set_cell_height_scale'): 
            self.vte.set_cell_height_scale(self.config['cell_height'])
        if hasattr(self.vte,'set_cell_width_scale'):
            self.vte.set_cell_width_scale(self.config['cell_width'])
        if hasattr(self.vte, 'set_bold_is_bright'):
            self.vte.set_bold_is_bright(self.config['bold_is_bright'])

        if self.config['use_theme_colors']:
            self.fgcolor_active = self.vte.get_style_context().get_color(Gtk.StateType.NORMAL)  # VERIFY FOR GTK3: do these really take the theme colors?
            self.bgcolor = self.vte.get_style_context().get_background_color(Gtk.StateType.NORMAL)
        else:
            self.fgcolor_active = Gdk.RGBA()
            self.fgcolor_active.parse(self.config['foreground_color'])
            self.bgcolor = Gdk.RGBA()
            self.bgcolor.parse(self.config['background_color'])

        if self.config['background_type'] in ('transparent', 'image'):
            self.bgcolor.alpha = self.config['background_darkness']
        else:
            self.bgcolor.alpha = 1

        if self.config['background_type'] == 'image' and self.config['background_image'] != '':
            self.set_background_image(self.config['background_image'])
        else:
            self.background_image = None

        factor = self.config['inactive_color_offset']
        if factor > 1.0:
          factor = 1.0
        self.fgcolor_inactive = self.fgcolor_active.copy()
        dbg(("fgcolor_inactive set to: RGB(%s,%s,%s)", getattr(self.fgcolor_inactive, "red"),
                                                      getattr(self.fgcolor_inactive, "green"),
                                                      getattr(self.fgcolor_inactive, "blue")))

        for bit in ['red', 'green', 'blue']:
            setattr(self.fgcolor_inactive, bit,
                    getattr(self.fgcolor_inactive, bit) * factor)

        dbg(("fgcolor_inactive set to: RGB(%s,%s,%s)", getattr(self.fgcolor_inactive, "red"),
                                                      getattr(self.fgcolor_inactive, "green"),
                                                      getattr(self.fgcolor_inactive, "blue")))

        bg_factor = self.config['inactive_bg_color_offset']
        if bg_factor > 1.0:
            bg_factor = 1.0
        self.bgcolor_inactive = self.bgcolor.copy()
        dbg(("bgcolor_inactive set to: RGB(%s,%s,%s)", getattr(self.bgcolor_inactive, "red"),
                                                      getattr(self.bgcolor_inactive, "green"),
                                                      getattr(self.bgcolor_inactive, "blue")))

        for bit in ['red', 'green', 'blue']:
            setattr(self.bgcolor_inactive, bit,
                    getattr(self.bgcolor_inactive, bit) * bg_factor)
        dbg(("bgcolor_inactive set to: RGB(%s,%s,%s)", getattr(self.bgcolor_inactive, "red"),
                                                      getattr(self.bgcolor_inactive, "green"),
                                                      getattr(self.bgcolor_inactive, "blue")))

        colors = self.config['palette'].split(':')
        self.palette_active = []
        for color in colors:
            if color:
                newcolor = Gdk.RGBA()
                newcolor.parse(color)
                self.palette_active.append(newcolor)
        if len(colors) == 16:
            # RGB values for indices 16..255 copied from vte source in order to dim them
            shades = [0, 95, 135, 175, 215, 255]
            for r in range(0, 6):
                for g in range(0, 6):
                    for b in range(0, 6):
                        newcolor = Gdk.RGBA()
                        setattr(newcolor, "red",   shades[r] / 255.0)
                        setattr(newcolor, "green", shades[g] / 255.0)
                        setattr(newcolor, "blue",  shades[b] / 255.0)
                        self.palette_active.append(newcolor)
            for y in range(8, 248, 10):
                newcolor = Gdk.RGBA()
                setattr(newcolor, "red",   y / 255.0)
                setattr(newcolor, "green", y / 255.0)
                setattr(newcolor, "blue",  y / 255.0)
                self.palette_active.append(newcolor)
        self.palette_inactive = []
        for color in self.palette_active:
            newcolor = Gdk.RGBA()
            for bit in ['red', 'green', 'blue']:
                setattr(newcolor, bit,
                        getattr(color, bit) * factor)
            self.palette_inactive.append(newcolor)
        if self.terminator.last_focused_term == self:
            self.vte.set_colors(self.fgcolor_active, self.bgcolor,
                                self.palette_active)
        else:
            self.vte.set_colors(self.fgcolor_inactive, self.bgcolor_inactive,
                                self.palette_inactive)
        profiles = self.config.base.profiles
        terminal_box_style_context = self.terminalbox.get_style_context()
        for profile in list(profiles.keys()):
            munged_profile = "terminator-profile-%s" % (
                "".join([c if c.isalnum() else "-" for c in profile]))
            if terminal_box_style_context.has_class(munged_profile):
                terminal_box_style_context.remove_class(munged_profile)
        munged_profile = "".join([c if c.isalnum() else "-" for c in self.get_profile()])
        css_class_name = "terminator-profile-%s" % (munged_profile)
        terminal_box_style_context.add_class(css_class_name)
        self.set_cursor_color()
        self.vte.set_cursor_shape(getattr(Vte.CursorShape,
                                          self.config['cursor_shape'].upper()));

        if self.config['cursor_blink'] == True:
            self.vte.set_cursor_blink_mode(Vte.CursorBlinkMode.ON)
        else:
            self.vte.set_cursor_blink_mode(Vte.CursorBlinkMode.OFF)

        if self.config['force_no_bell'] == True:
            self.vte.set_audible_bell(False)
            self.cnxids.remove_signal(self.vte, 'bell')
        else:
            self.vte.set_audible_bell(self.config['audible_bell'])
            self.cnxids.remove_signal(self.vte, 'bell')
            if self.config['urgent_bell'] == True or \
               self.config['icon_bell'] == True or \
               self.config['visible_bell'] == True:
                try:
                    self.cnxids.new(self.vte, 'bell', self.on_bell)
                except TypeError:
                    err('bell signal unavailable with this version of VTE')

        if self.config['scrollback_infinite'] == True:
            scrollback_lines = -1
        else:
            scrollback_lines = self.config['scrollback_lines']
        self.vte.set_scrollback_lines(scrollback_lines)
        self.vte.set_scroll_on_keystroke(self.config['scroll_on_keystroke'])
        self.vte.set_scroll_on_output(self.config['scroll_on_output'])

        if self.config['scrollbar_position'] in ['disabled', 'hidden']:
            self.scrollbar.hide()
        else:
            self.scrollbar.show()
            if self.config['scrollbar_position'] == 'left':
                self.terminalbox.reorder_child(self.scrollbar, 0)
            elif self.config['scrollbar_position'] == 'right':
                self.terminalbox.reorder_child(self.vte, 0)

        self.titlebar.update()
        self.vte.queue_draw()

    def set_cursor_color(self):
        """Set the cursor color appropriately"""
        if self.config['cursor_color_default']:
            self.vte.set_color_cursor(None)
            self.vte.set_color_cursor_foreground(None)
        else:
            # foreground
            cursor_fg_color = Gdk.RGBA()
            if self.config['cursor_fg_color'] == '':
                cursor_fg_color.parse(self.config['background_color'])
            else:
                cursor_fg_color.parse(self.config['cursor_fg_color'])
            self.vte.set_color_cursor_foreground(cursor_fg_color)
            # background
            cursor_bg_color = Gdk.RGBA()
            if self.config['cursor_bg_color'] == '':
                cursor_bg_color.parse(self.config['foreground_color'])
            else:
                cursor_bg_color.parse(self.config['cursor_bg_color'])
            self.vte.set_color_cursor(cursor_bg_color)

    def get_window_title(self):
        """Return the window title"""
        return self.vte.get_window_title() or str(self.command)

    def on_group_button_press(self, widget, event):
        """Handler for the group button"""
        if event.button == 1:
            if event.type == Gdk.EventType._2BUTTON_PRESS or \
               event.type == Gdk.EventType._3BUTTON_PRESS:
                # Ignore these, or they make the interaction bad
                return True
            # Super key applies interaction to all terms in group
            include_siblings=event.get_state() & Gdk.ModifierType.MOD4_MASK == Gdk.ModifierType.MOD4_MASK
            if include_siblings:
                targets=self.terminator.get_sibling_terms(self)
            else:
                targets=[self]
            if event.get_state() & Gdk.ModifierType.CONTROL_MASK == Gdk.ModifierType.CONTROL_MASK:
                dbg('on_group_button_press: toggle terminal to focused terminals group')
                focused=self.get_toplevel().get_focussed_terminal()
                if focused in targets: targets.remove(focused)
                if self != focused:
                    if focused.group is None and self.group is None:
                        # Create a new group and assign currently focused
                        # terminal to this group
                        new_group = self.terminator.new_random_group()
                        focused.set_group(None, new_group)
                        focused.titlebar.update()
                    elif self.group == focused.group:
                        new_group = None
                    else:
                        new_group = focused.group
                    [term.set_group(None, new_group) for term in targets]
                    [term.titlebar.update(focused) for term in targets]
                return True
            elif event.get_state() & Gdk.ModifierType.SHIFT_MASK == Gdk.ModifierType.SHIFT_MASK:
                dbg('on_group_button_press: rename of terminals group')
                self.targets_for_new_group = targets
                self.titlebar.create_group()
                return True
            elif event.type == Gdk.EventType.BUTTON_PRESS:
                # Single Click gives popup
                dbg('on_group_button_press: group menu popup')
                window = self.get_toplevel()
                window.preventHide = True
                self.create_popup_group_menu(widget, event)
                return True
            else:
                dbg('on_group_button_press: unknown group button interaction')
        return False

    def on_keypress(self, widget, event):
        """Handler for keyboard events"""
        if not event:
            dbg('Called on %s with no event' % widget)
            return False

        # FIXME: Does keybindings really want to live in Terminator()?
        mapping = self.terminator.keybindings.lookup(event)

        if mapping == "hide_window":
            return False

        if mapping and mapping not in ['close_window',
                                       'full_screen']:
            dbg('lookup found: %r' % mapping)
            # handle the case where user has re-bound copy to ctrl+<key>
            # we only copy if there is a selection otherwise let it fall through
            # to ^<key>
            if (mapping == "copy" and event.get_state() & Gdk.ModifierType.CONTROL_MASK):
                if self.vte.get_has_selection():
                    getattr(self, "key_" + mapping)()
                    return True
                elif not self.config['smart_copy']:
                    return True
            else:
                getattr(self, "key_" + mapping)()
                return True

        # FIXME: This is all clearly wrong. We should be doing this better
        #         maybe we can emit the key event and let Terminator() care?
        groupsend = self.terminator.groupsend
        groupsend_type = self.terminator.groupsend_type
        window_focussed = self.vte.get_toplevel().get_property('has-toplevel-focus')
        if groupsend != groupsend_type['off'] and window_focussed and self.vte.is_focus():
            if self.group and groupsend == groupsend_type['group']:
                self.terminator.group_emit(self, self.group, 'key-press-event',
                                           event)
            if groupsend == groupsend_type['all']:
                self.terminator.all_emit(self, 'key-press-event', event)

        return False

    def on_buttonpress(self, widget, event):
        """Handler for mouse events"""
        # Any button event should grab focus
        widget.grab_focus()

        if type(widget) == Gtk.VScrollbar and event.type == Gdk.EventType._2BUTTON_PRESS:
            # Suppress double-click behavior
            return True

        if self.config['putty_paste_style']:
            middle_click = [self.popup_menu, (widget, event)]
            right_click = [self.paste_clipboard, (not self.config['putty_paste_style_source_clipboard'], True)]
        else:
            middle_click = [self.paste_clipboard, (True, True)]
            right_click = [self.popup_menu, (widget, event)]

        # Ctrl-click event here.
        if event.button == self.MOUSEBUTTON_LEFT:
            # Ctrl+leftclick on a URL should open it
            if self.config["link_single_click"] or event.get_state() & Gdk.ModifierType.CONTROL_MASK == Gdk.ModifierType.CONTROL_MASK:
                # Check new OSC-8 method first
                url = self.vte.hyperlink_check_event(event)
                dbg('url: %s' % url)
                if url:
                    self.open_url(url, prepare=False)
                else:
                    dbg('OSC-8 URL not detected dropping back to regex match')
                    url = self.vte.match_check_event(event)
                    if url[0]:
                        self.open_url(url, prepare=True)
                    else:
                        dbg("No regex match, discard event.")
        elif event.button == self.MOUSEBUTTON_MIDDLE:
            # middleclick should paste the clipboard
            # try to pass it to vte widget first though
            if event.get_state() & Gdk.ModifierType.CONTROL_MASK == 0:
                if event.get_state() & Gdk.ModifierType.SHIFT_MASK == 0:
                    gtk_settings=Gtk.Settings().get_default()
                    primary_state = gtk_settings.get_property('gtk-enable-primary-paste')
                    gtk_settings.set_property('gtk-enable-primary-paste',  False)
                    if not Vte.Terminal.do_button_press_event(self.vte, event):
                        middle_click[0](*middle_click[1])
                    gtk_settings.set_property('gtk-enable-primary-paste', primary_state)
                else:
                    middle_click[0](*middle_click[1])
                return True
            return Vte.Terminal.do_button_press_event(self.vte, event)
        elif event.button == self.MOUSEBUTTON_RIGHT:
            # rightclick should display a context menu if Ctrl is not pressed,
            # plus either the app is not interested in mouse events or Shift is pressed
            if event.get_state() & Gdk.ModifierType.CONTROL_MASK == 0:
                if event.get_state() & Gdk.ModifierType.SHIFT_MASK == 0:
                    if not Vte.Terminal.do_button_press_event(self.vte, event):
                        right_click[0](*right_click[1])
                else:
                    right_click[0](*right_click[1])
                return True
        return False

    def on_mousewheel(self, widget, event):
        """Handler for modifier + mouse wheel scroll events"""
        SMOOTH_SCROLL_UP = event.direction == Gdk.ScrollDirection.SMOOTH and event.delta_y <= 0.
        SMOOTH_SCROLL_DOWN = event.direction == Gdk.ScrollDirection.SMOOTH and event.delta_y > 0.

        modifiers = event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK)
        if modifiers == Gdk.ModifierType.CONTROL_MASK:
            # Zoom the terminal(s) in or out if not disabled in config
            if self.config["disable_mousewheel_zoom"] is True:
                return False
            # Choice of target terminals depends on Shift and Super modifiers
            if event.state & Gdk.ModifierType.MOD4_MASK == Gdk.ModifierType.MOD4_MASK:
                targets = self.terminator.terminals
            elif event.state & Gdk.ModifierType.SHIFT_MASK == Gdk.ModifierType.SHIFT_MASK:
                targets = self.terminator.get_target_terms(self)
            else:
                targets = [self]
            if event.direction == Gdk.ScrollDirection.UP or SMOOTH_SCROLL_UP:
                for target in targets:
                    target.zoom_in()
                return True
            elif event.direction == Gdk.ScrollDirection.DOWN or SMOOTH_SCROLL_DOWN:
                for target in targets:
                    target.zoom_out()
                return True
        elif modifiers == Gdk.ModifierType.SHIFT_MASK:
            # Shift + mouse wheel up/down
            if event.direction == Gdk.ScrollDirection.UP or SMOOTH_SCROLL_UP:
                self.scroll_by_page(-1)
                return True
            elif event.direction == Gdk.ScrollDirection.DOWN or SMOOTH_SCROLL_DOWN:
                self.scroll_by_page(1)
                return True
        return False

    def popup_menu(self, widget, event=None):
        """Display the context menu"""
        window = self.get_toplevel()
        window.preventHide = True
        menu = TerminalPopupMenu(self)
        menu.show(widget, event)

    def do_readonly_toggle(self):
        self.vte.props.input_enabled = not self.vte.props.input_enabled

    def do_scrollbar_toggle(self):
        """Show or hide the terminal scrollbar"""
        self.toggle_widget_visibility(self.scrollbar)

    def toggle_widget_visibility(self, widget):
        """Show or hide a widget"""
        if widget.get_property('visible'):
            widget.hide()
        else:
            widget.show()

    def on_drag_begin(self, widget, drag_context, _data):
        """Handle the start of a drag event"""
        Gtk.drag_set_icon_pixbuf(drag_context, util.widget_pixbuf(self, 512), 0, 0)

    def on_drag_data_get(self, _widget, _drag_context, selection_data, info,
                         _time, data):
        """I have no idea what this does, drag and drop is a mystery. sorry."""
        selection_data.set(Gdk.atom_intern('vte', False), info,
                           bytes(str(data.terminator.terminals.index(self)),
                                 'utf-8'))

    def on_drag_motion(self, widget, drag_context, x, y, _time, _data):
        """*shrug*"""
        if not drag_context.list_targets() == [Gdk.atom_intern('vte', False)] and \
           (Gtk.targets_include_text(drag_context.list_targets()) or
           Gtk.targets_include_uri(drag_context.list_targets())):
            # copy text from another widget
            return
        srcwidget = Gtk.drag_get_source_widget(drag_context)
        if(isinstance(srcwidget, Gtk.EventBox) and
           srcwidget == self.titlebar) or widget == srcwidget:
            # on self
            return

        alloc = widget.get_allocation()

        if self.config['use_theme_colors']:
            color = self.vte.get_style_context().get_color(Gtk.StateType.NORMAL)  # VERIFY FOR GTK3 as above
        else:
            color = Gdk.RGBA()
            color.parse(self.config['foreground_color'])  # VERIFY FOR GTK3

        pos = self.get_location(widget, x, y)
        topleft = (0, 0)
        topright = (alloc.width, 0)
        topmiddle = (alloc.width/2, 0)
        bottomleft = (0, alloc.height)
        bottomright = (alloc.width, alloc.height)
        bottommiddle = (alloc.width/2, alloc.height)
        middleleft = (0, alloc.height/2)
        middleright = (alloc.width, alloc.height/2)

        coord = ()
        if pos == "right":
            coord = (topright, topmiddle, bottommiddle, bottomright)
        elif pos == "top":
            coord = (topleft, topright, middleright , middleleft)
        elif pos == "left":
            coord = (topleft, topmiddle, bottommiddle, bottomleft)
        elif pos == "bottom":
            coord = (bottomleft, bottomright, middleright , middleleft)

        # here, we define some widget internal values
        widget._draw_data = { 'color': color, 'coord' : coord }
        # redraw by forcing an event
        connec = widget.connect_after('draw', self.on_draw)
        widget.queue_draw_area(0, 0, alloc.width, alloc.height)
        widget.get_window().process_updates(True)
        # finally reset the values
        widget.disconnect(connec)
        widget._draw_data = None

    def background_draw(self, widget, cr):
        if self.background_image is None:
            return False

        # save cairo context
        cr.save()

        # draw background image
        image_mode = self.config['background_image_mode']
        image_align_horiz = self.config['background_image_align_horiz']
        image_align_vert = self.config['background_image_align_vert']

        rect = self.vte.get_allocation()
        xratio = float(rect.width) / float(self.background_image.get_width())
        yratio = float(rect.height) / float(self.background_image.get_height())
        if image_mode == 'stretch_and_fill':
            # keep stretched ratios
            xratio = xratio
            yratio = yratio
        elif image_mode == 'scale_and_fit':
            ratio = min(xratio, yratio)
            xratio = yratio = ratio
        elif image_mode == 'scale_and_crop':
            ratio = max(xratio, yratio)
            xratio = yratio = ratio
        else:
            xratio = yratio = 1
        cr.scale(xratio, yratio)

        xoffset = 0
        yoffset = 0
        if image_align_horiz == 'center':
            xoffset = (rect.width / xratio - self.background_image.get_width()) / 2
        elif image_align_horiz == 'right':
            xoffset = rect.width / xratio - self.background_image.get_width()

        if image_align_vert == 'middle':
            yoffset = (rect.height / yratio - self.background_image.get_height()) / 2
        elif image_align_vert == 'bottom':
            yoffset = rect.height / yratio - self.background_image.get_height()

        cr.set_source_surface(self.background_image, xoffset, yoffset)
        cr.get_source().set_filter(cairo.Filter.FAST)
        if image_mode == 'tiling':
            cr.get_source().set_extend(cairo.Extend.REPEAT)

        cr.paint()

        # draw transparent monochrome layer
        Gdk.cairo_set_source_rgba(cr, self.bgcolor)
        cr.paint()

        # restore cairo context
        cr.restore()

    def on_draw(self, widget, context):
        if not widget._draw_data:
            return False

        color = widget._draw_data['color']
        coord = widget._draw_data['coord']

        context.set_source_rgba(color.red, color.green, color.blue, 0.5)
        if len(coord) > 0:
            context.move_to(coord[len(coord)-1][0], coord[len(coord)-1][1])
            for i in coord:
                context.line_to(i[0], i[1])

        context.fill()
        return False

    def on_drag_data_received(self, widget, drag_context, x, y, selection_data,
            info, _time, data):
        """Something has been dragged into the terminal. Handle it as either a
        URL or another terminal."""
        # FIXME this code is a mess that I don't quite understand how it works.
        dbg('drag data received of type: %s' % (selection_data.get_data_type()))
        # print(selection_data.get_urls())
        if Gtk.targets_include_text(drag_context.list_targets()) or \
           Gtk.targets_include_uri(drag_context.list_targets()):
            # copy text with no modification yet to destination
            txt = selection_data.get_data()
            # https://bugs.launchpad.net/terminator/+bug/1518705
            if info == self.TARGET_TYPE_MOZ:
                 txt = txt.decode('utf-16')
                 # KDE ends it's text/x-moz-url text with CRLF, :shrug:
                 if not txt.endswith('\r\n'):
                   txt = txt.split('\n')[0]
            else:
                 txt = txt.decode()

            txt_lines = txt.split( "\r\n" )
            if txt_lines[-1] == '':
                for line in txt_lines[:-1]:
                    if line[0:7] != 'file://':
                        txt = txt.replace('\r\n','\n')
                        break
                else:
                    # It is a list of crlf terminated file:// URL. let's
                    # iterate over all elements except the last one.
                    str=''
                    for fname in txt_lines[:-1]:
                        fname = "'%s'" % urlunquote(fname[7:].replace("'",
                                                                      '\'\\\'\''))
                        str += fname + ' '
                    txt = str
            # Never send a CRLF to the terminal from here
            txt = txt.rstrip('\r\n')
            for term in self.terminator.get_target_terms(self):
                term.feed(txt.encode())
            return

        widgetsrc = data.terminator.terminals[int(selection_data.get_data())]
        srcvte = Gtk.drag_get_source_widget(drag_context)
        # check if computation requireds
        if (isinstance(srcvte, Gtk.EventBox) and
                srcvte == self.titlebar) or srcvte == widget:
            return

        srchbox = widgetsrc

        # The widget argument is actually a Vte.Terminal(). Turn that into a
        # terminatorlib Terminal()
        maker = Factory()
        while True:
            widget = widget.get_parent()
            if not widget:
                # We've run out of widgets. Something is wrong.
                err('Failed to find Terminal from vte')
                return
            if maker.isinstance(widget, 'Terminal'):
                break

        dsthbox = widget

        dstpaned = dsthbox.get_parent()
        srcpaned = srchbox.get_parent()

        pos = self.get_location(widget, x, y)

        srcpaned.remove(widgetsrc)
        dstpaned.split_axis(dsthbox, pos in ['top', 'bottom'], None, widgetsrc, pos in ['bottom', 'right'])
        srcpaned.hoover()
        widgetsrc.ensure_visible_and_focussed()

    def get_location(self, term, x, y):
        """Get our location within the terminal"""
        pos = ''
        # get the diagonals function for the receiving widget
        term_alloc = term.get_allocation()
        coef1 = float(term_alloc.height)/float(term_alloc.width)
        coef2 = -float(term_alloc.height)/float(term_alloc.width)
        b1 = 0
        b2 = term_alloc.height
        #determine position in rectangle
        #--------
        #|\    /|
        #| \  / |
        #|  \/  |
        #|  /\  |
        #| /  \ |
        #|/    \|
        #--------
        if (x*coef1 + b1 > y) and (x*coef2 + b2 < y):
            pos = "right"
        if (x*coef1 + b1 > y) and (x*coef2 + b2 > y):
            pos = "top"
        if (x*coef1 + b1 < y) and (x*coef2 + b2 > y):
            pos = "left"
        if (x*coef1 + b1 < y) and (x*coef2 + b2 < y):
            pos = "bottom"
        return pos

    def grab_focus(self):
        """Steal focus for this terminal"""
        if self.vte and not self.vte.has_focus():
            self.vte.grab_focus()

    def ensure_visible_and_focussed(self):
        """Make sure that we're visible and focused"""
        window = self.get_toplevel()
        try:
            topchild = window.get_children()[0]
        except IndexError:
            dbg('unable to get top child')    
            return
        maker = Factory()

        if maker.isinstance(topchild, 'Notebook'):
            # Find which page number this term is on
            tabnum = topchild.page_num_descendant(self)
            # If terms page number is not the current one, switch to it
            current_page = topchild.get_current_page()
            if tabnum != current_page:
                topchild.set_current_page(tabnum)

        self.grab_focus()

    def on_vte_focus(self, _widget):
        """Update our UI when we get focus"""
        self.emit('title-change', self.get_window_title())

    def on_vte_focus_in(self, _widget, _event):
        """Inform other parts of the application when focus is received"""
        self.vte.set_colors(self.fgcolor_active, self.bgcolor,
                            self.palette_active)
        self.set_cursor_color()
        if not self.terminator.doing_layout:
            self.terminator.last_focused_term = self
            if self.get_toplevel().is_child_notebook():
                notebook = self.get_toplevel().get_children()[0]
                notebook.set_last_active_term(self.uuid)
                notebook.clean_last_active_term()
                self.get_toplevel().last_active_term = None
            else:
                self.get_toplevel().last_active_term = self.uuid
        self.emit('focus-in')

    def on_vte_focus_out(self, _widget, _event):
        """Inform other parts of the application when focus is lost"""
        self.vte.set_colors(self.fgcolor_inactive, self.bgcolor_inactive,
                            self.palette_inactive)
        self.set_cursor_color()
        self.emit('focus-out')

    def on_window_focus_out(self):
        """Update our UI when the window loses focus"""
        self.titlebar.update('window-focus-out')

    def scrollbar_jump(self, position):
        """Move the scrollbar to a particular row"""
        self.scrollbar.set_value(position)

    def on_search_done(self, _widget):
        """We've finished searching, so clean up"""
        self.searchbar.hide()
        self.scrollbar.set_value(self.vte.get_cursor_position()[1])
        self.vte.grab_focus()

    def on_edit_done(self, _widget):
        """A child widget is done editing a label, return focus to VTE"""
        self.vte.grab_focus()

    def deferred_on_vte_size_allocate(self, widget, allocation):
        # widget & allocation are not used in on_vte_size_allocate, so we
        # can use the on_vte_size_allocate instead of duplicating the code
        if self.pending_on_vte_size_allocate:
            return
        self.pending_on_vte_size_allocate = True
        GObject.idle_add(self.do_deferred_on_vte_size_allocate, widget, allocation)

    def do_deferred_on_vte_size_allocate(self, widget, allocation):
        self.pending_on_vte_size_allocate = False
        self.on_vte_size_allocate(widget, allocation)

    def on_vte_size_allocate(self, widget, allocation):
        self.titlebar.update_terminal_size(self.vte.get_column_count(),
                self.vte.get_row_count())
        if self.config['geometry_hinting']:
            window = self.get_toplevel()
            window.deferred_set_rough_geometry_hints()
        else:
            window = self.get_toplevel()
            window.disable_geometry_hints()

    def on_vte_notify_enter(self, term, event):
        """Handle the mouse entering this terminal"""
        # FIXME: This shouldn't be looking up all these values every time
        sloppy = False
        if self.config['focus'] == 'system':
            sloppy = self.config.get_system_focus() in ['sloppy', 'mouse']
        elif self.config['focus'] in ['sloppy', 'mouse']:
            sloppy = True
        if sloppy and self.titlebar.editing() == False:
            term.grab_focus()
            return False

    def get_zoom_data(self):
        """Return a dict of information for Window"""
        data = {'old_font': self.vte.get_font().copy(),
                'old_char_height': self.vte.get_char_height(),
                'old_char_width': self.vte.get_char_width(),
                'old_allocation': self.vte.get_allocation(),
                'old_columns': self.vte.get_column_count(),
                'old_rows': self.vte.get_row_count(),
                'old_parent': self.get_parent()}

        return data

    def zoom_scale(self, widget, allocation, old_data):
        """Scale our font correctly based on how big we are not vs before"""
        self.cnxids.remove_signal(self, 'size-allocate')
        # FIXME: Is a zoom signal actually used anywhere?
        self.cnxids.remove_signal(self, 'zoom')

        new_columns = self.vte.get_column_count()
        new_rows = self.vte.get_row_count()
        new_font = self.vte.get_font()

        dbg('Resized from %dx%d to %dx%d' % (
             old_data['old_columns'],
             old_data['old_rows'],
             new_columns,
             new_rows))

        if new_rows == old_data['old_rows'] or \
           new_columns == old_data['old_columns']:
            dbg('One axis unchanged, not scaling')
            return

        scale_factor = min ( (new_columns / old_data['old_columns'] * 0.97),
                             (new_rows / old_data['old_rows'] * 1.05) )

        new_size = int(old_data['old_font'].get_size() * scale_factor)
        if new_size == 0:
            err('refusing to set a zero sized font')
            return
        new_font.set_size(new_size)
        dbg('setting new font: %s' % new_font)
        self.set_font(new_font)

    def is_zoomed(self):
        """Determine if we are a zoomed terminal"""
        window = self.get_toplevel()
        return window.is_zoomed()

    def zoom(self, widget=None):
        """Zoom ourself to fill the window"""
        self.emit('zoom')

    def maximise(self, widget=None):
        """Maximise ourself to fill the window"""
        self.emit('maximise')

    def unzoom(self, widget=None):
        """Restore normal layout"""
        self.emit('unzoom')

    def set_cwd(self, cwd=None):
        """Set our cwd"""
        if cwd is not None:
            self.cwd = cwd

    def held_open(self, widget=None, respawn=False, debugserver=False):
        self.is_held_open = True
        self.titlebar.update()

    def spawn_child(self, widget=None, respawn=False, debugserver=False, init_command=None):
        args = []
        shell = None
        command = init_command

        if self.terminator.doing_layout:
            dbg('still laying out, refusing to spawn a child')
            return

        if respawn is False:
            self.vte.grab_focus()

        self.is_held_open = False

        options = self.config.options_get()
        if options and options.command:
            command = options.command
            self.relaunch_command = command
            options.command = None
        elif options and options.execute:
            command = options.execute
            self.relaunch_command = command
            options.execute = None
        elif self.relaunch_command:
            command = self.relaunch_command
        elif self.config['use_custom_command']:
            command = self.config['custom_command']
        elif self.layout_command:
            command = self.layout_command
        elif debugserver is True:
            details = self.terminator.debug_address
            if details is not None:
                dbg('spawning debug session with: %s:%s' % (details[0],
                    details[1]))
                command = 'telnet %s %s' % (details[0], details[1])

        # working directory set in layout config
        if self.directory:
            self.set_cwd(self.directory)
        # working directory given as argument
        elif options and options.working_directory and \
                options.working_directory != '':
            self.set_cwd(options.working_directory)
            options.working_directory = ''

        if type(command) is list:
            shell = util.path_lookup(command[0])
            args = command
        else:
            shell = util.shell_lookup()

            if self.config['login_shell']:
                args.insert(0, "-l")
            else:
                args.insert(0, shell)

            if command is not None:
                args += ['-c', command]

        if shell is None:
            self.vte.feed(_('Unable to find a shell'))
            return -1

        try:
            os.putenv('WINDOWID', '%s' % self.vte.get_parent_window().xid)
        except AttributeError:
            pass

        envv = ['TERM=%s' % self.config['term'],
                'COLORTERM=%s' % self.config['colorterm'], 'PWD=%s' % self.cwd,
                'TERMINATOR_UUID=%s' % self.uuid.urn]
        if self.terminator.dbus_name:
            envv.append('TERMINATOR_DBUS_NAME=%s' % self.terminator.dbus_name)
        if self.terminator.dbus_path:
            envv.append('TERMINATOR_DBUS_PATH=%s' % self.terminator.dbus_path)

        dbg('Forking shell: "%s" with args: %s' % (shell, args))
        args.insert(0, shell)

        if util.is_flatpak():
            dbg('Flatpak detected')
            args = util.get_flatpak_args(args, envv, self.cwd)
            dbg('Forking shell: "%s" with args: %s via flatpak-spawn' % (shell, args))
        
            self.pid = self.vte.spawn_async(
                Vte.PtyFlags.NO_CTTY,
                self.cwd,
                args,
                envv,
                0,
                None,
                None,
                -1,
                None,
                None,
                None,
            )
        else:
            result, self.pid = self.vte.spawn_sync(
                    Vte.PtyFlags.DEFAULT,
                    self.cwd,
                    args,
                    envv,
                    GLib.SpawnFlags.FILE_AND_ARGV_ZERO,
                    None,
                    None,
                    None
                    )

        self.command = shell

        self.titlebar.update()

        if self.pid == -1:
            self.vte.feed(_('Unable to start shell:') + shell)
            return -1

    def prepare_url(self, urlmatch):
        """Prepare a URL from a VTE match"""
        url = urlmatch[0]
        match = urlmatch[1]

        if match == self.matches['addr_only'] and url[0:3] == 'ftp':
            url = 'ftp://' + url
        elif match == self.matches['addr_only']:
            url = 'http://' + url
        elif match in list(self.matches.values()):
            # We have a match, but it's not a hard coded one, so it's a plugin
            try:
                registry = plugin.PluginRegistry()
                registry.load_plugins()
                plugins = registry.get_plugins_by_capability('url_handler')
                dbg("URL handler plugins: {}".format(plugins))

                for urlplugin in plugins:
                    if match == self.matches[urlplugin.handler_name]:
                        newurl = urlplugin.callback(url)
                        if newurl: # If the plugin returns None, it's a false match.
                            dbg('URL prepared by %s plugin' \
                                    % urlplugin.handler_name)
                            url = newurl
                        break
            except Exception as ex:
                err('Exception occurred preparing URL: %s, %s' % (type(ex).__name__, ex))

        return url

    def open_url(self, url, prepare=False):
        """Open a given URL, conditionally unpacking it from a VTE match"""
        if prepare:
            url = self.prepare_url(url)
        dbg('URL: %s (prepared: %s)' % (url, prepare))

        # If the URL opening is managed by the plugin: do nothing.
        # (plugins can indicate they manage the URL opening by returning a "terminator://" URI).
        if url.split(":")[0] == "terminator":
            dbg("URL opening is managed by the plugin, do nothing more.")
            return

        # Else, call the URL handler.
        if self.config['use_custom_url_handler']:
            dbg("Using custom URL handler: %s" %
                self.config['custom_url_handler'])
            try:
                subprocess.Popen([self.config['custom_url_handler'], url])
                return
            except:
                dbg('custom url handler did not work, falling back to defaults')

        try:
            Gtk.show_uri(None, url, Gdk.CURRENT_TIME)
            return
        except:
            dbg('Gtk.show_uri did not work, falling through to xdg-open')

        try:
            subprocess.Popen(["xdg-open", url])
        except:
            dbg('xdg-open did not work, falling back to webbrowser.open')
            import webbrowser
            webbrowser.open(url)


    def paste_clipboard(self, primary=False, mouse=False):
        """Paste one of the two clipboards"""
        if not (mouse and self.config['disable_mouse_paste']):
            for term in self.terminator.get_target_terms(self):
                if primary:
                    term.vte.paste_primary()
                else:
                    term.vte.paste_clipboard()
            self.vte.grab_focus()

    def feed(self, text):
        """Feed the supplied text to VTE"""
        self.vte.feed_child(text)

    def zoom_in(self):
        """Increase the font size"""
        self.zoom_font(True)

    def zoom_out(self):
        """Decrease the font size"""
        self.zoom_font(False)

    def zoom_font(self, zoom_in):
        """Change the font size"""
        pangodesc = self.vte.get_font()
        fontsize = pangodesc.get_size()

        if fontsize > Pango.SCALE and not zoom_in:
            fontsize -= Pango.SCALE
        elif zoom_in:
            fontsize += Pango.SCALE

        pangodesc.set_size(fontsize)
        self.set_font(pangodesc)
        self.custom_font_size = fontsize

    def zoom_orig(self):
        """Restore original font size"""
        if self.config['use_system_font']:
            font = self.config.get_system_mono_font()
        else:
            font = self.config['font']
        dbg("restoring font to: %s" % font)
        self.set_font(Pango.FontDescription(font))
        self.custom_font_size = None

    def set_font(self, fontdesc):
        """Set the font we want in VTE"""
        self.vte.set_font(fontdesc)

    def get_cursor_position(self):
        """Return the coordinates of our cursor"""
        # FIXME: THIS METHOD IS DEPRECATED AND UNUSED
        col, row = self.vte.get_cursor_position()
        width = self.vte.get_char_width()
        height = self.vte.get_char_height()
        return col * width, row * height

    def get_font_size(self):
        """Return the width/height of our font"""
        return self.vte.get_char_width(), self.vte.get_char_height()

    def get_size(self):
        """Return the column/rows of the terminal"""
        return self.vte.get_column_count(), self.vte.get_row_count()

    def on_bell(self, widget):
        """Set the urgency hint/icon/flash for our window"""
        if self.config['urgent_bell']:
            window = self.get_toplevel()
            if window.is_toplevel():
                window.set_urgency_hint(True)
        if self.config['icon_bell']:
            self.titlebar.icon_bell()
        if self.config['visible_bell']:
            # Repurposed the code used for drag and drop overlay to provide a visual terminal flash
            alloc = widget.get_allocation()

            if self.config['use_theme_colors']:
                color = self.vte.get_style_context().get_color(Gtk.StateType.NORMAL)  # VERIFY FOR GTK3 as above
            else:
                color = Gdk.RGBA()
                color.parse(self.config['foreground_color'])  # VERIFY FOR GTK3

            coord = ((0, 0), (alloc.width, 0), (alloc.width, alloc.height), (0, alloc.height))

            # here, we define some widget internal values
            widget._draw_data = { 'color': color, 'coord' : coord }
            # redraw by forcing an event
            connec = widget.connect_after('draw', self.on_draw)
            widget.queue_draw_area(0, 0, alloc.width, alloc.height)
            widget.get_window().process_updates(True)
            # finally reset the values
            widget.disconnect(connec)
            widget._draw_data = None

            # Add timeout to clean up display
            GObject.timeout_add(100, self.on_bell_cleanup, widget, alloc)

    def on_bell_cleanup(self, widget, alloc):
        """Queue a redraw to clear the visual flash overlay"""
        widget.queue_draw_area(0, 0, alloc.width, alloc.height)
        widget.get_window().process_updates(True)
        return False

    def describe_layout(self, count, parent, global_layout, child_order, save_cwd = False):
        """Describe our layout"""
        layout = {'type': 'Terminal', 'parent': parent, 'order': child_order}
        if self.group:
            layout['group'] = self.group
        profile = self.get_profile()
        if layout != "default":
            # There's no point explicitly noting default profiles
            layout['profile'] = profile
        title = self.titlebar.get_custom_string()
        if title:
            layout['title'] = title
        layout['uuid'] = self.uuid
        if save_cwd:
            layout['directory'] = self.get_cwd()
        name = 'terminal%d' % count
        count = count + 1
        global_layout[name] = layout
        return count

    def create_layout(self, layout):
        """Apply our layout"""
        dbg('Setting layout')
        if 'command' in layout and layout['command'] != '':
            self.layout_command = layout['command']
        if 'profile' in layout and layout['profile'] != '':
            if layout['profile'] in self.config.list_profiles():
                self.set_profile(self, layout['profile'])
        if 'group' in layout and layout['group'] != '':
            # This doesn't need/use self.titlebar, but it's safer than sending
            # None
            self.really_create_group(self.titlebar, layout['group'])
        if 'title' in layout and layout['title'] != '':
            self.titlebar.set_custom_string(layout['title'])
        if 'directory' in layout and layout['directory'] != '':
            self.directory = layout['directory']
        if 'uuid' in layout and layout['uuid'] != '':
            self.uuid = make_uuid(layout['uuid'])

    def scroll_by_page(self, pages):
        """Scroll up or down in pages"""
        amount = pages * self.vte.get_vadjustment().get_page_increment()
        self.scroll_by(int(amount))

    def scroll_by_line(self, lines):
        """Scroll up or down in lines"""
        amount = lines * self.vte.get_vadjustment().get_step_increment()
        self.scroll_by(int(amount))

    def scroll_by(self, amount):
        """Scroll up or down by an amount of lines"""
        adjustment = self.vte.get_vadjustment()
        bottom = adjustment.get_upper() - adjustment.get_page_size()
        value = adjustment.get_value() + amount
        adjustment.set_value(min(value, bottom))

    def get_allocation(self):
        """Get a real allocation which includes the bloody x and y coordinates
        (grumble, grumble) """
        alloc = super(Terminal, self).get_allocation()
        rv = self.translate_coordinates(self.get_toplevel(), 0, 0)
        if rv:
            alloc.x, alloc.y = rv
        return alloc

    # There now begins a great list of keyboard event handlers
    def key_zoom_in(self):
        self.zoom_in()

    def key_next_profile(self):
        self.switch_to_next_profile()

    def key_previous_profile(self):
        self.switch_to_previous_profile()

    def key_zoom_out(self):
        self.zoom_out()

    def key_copy(self):
        self.vte.copy_clipboard()
        if self.config['clear_select_on_copy']:
            self.vte.unselect_all()

    def key_paste(self):
        self.paste_clipboard()

    def key_paste_selection(self):
        self.paste_clipboard(True)

    def key_toggle_scrollbar(self):
        self.do_scrollbar_toggle()

    def key_zoom_normal(self):
        self.zoom_orig ()

    def key_search(self):
        self.searchbar.start_search()

    # bindings that should be moved to Terminator as they all just call
    # a function of Terminator. It would be cleaner if TerminatorTerm
    # has absolutely no reference to Terminator.
    # N (next) - P (previous) - O (horizontal) - E (vertical) - W (close)
    def key_zoom_in_all(self):
        self.terminator.zoom_in_all()

    def key_zoom_out_all(self):
        self.terminator.zoom_out_all()
        
    def key_zoom_normal_all(self):
        self.terminator.zoom_orig_all()

    def key_cycle_next(self):
        self.key_go_next()

    def key_cycle_prev(self):
        self.key_go_prev()

    def key_go_next(self):
        self.emit('navigate', 'next')

    def key_go_prev(self):
        self.emit('navigate', 'prev')

    def key_go_up(self):
        self.emit('navigate', 'up')

    def key_go_down(self):
        self.emit('navigate', 'down')

    def key_go_left(self):
        self.emit('navigate', 'left')

    def key_go_right(self):
        self.emit('navigate', 'right')

    def key_split_auto(self):
        self.emit('split-auto', self.get_cwd())

    def key_split_horiz(self):
        self.emit('split-horiz', self.get_cwd())

    def key_split_vert(self):
        self.emit('split-vert', self.get_cwd())

    def key_rotate_cw(self):
        self.emit('rotate-cw')

    def key_rotate_ccw(self):
        self.emit('rotate-ccw')

    def key_close_term(self):
        self.close()

    def key_resize_up(self):
        self.emit('resize-term', 'up')

    def key_resize_down(self):
        self.emit('resize-term', 'down')

    def key_resize_left(self):
        self.emit('resize-term', 'left')

    def key_resize_right(self):
        self.emit('resize-term', 'right')

    def key_move_tab_right(self):
        self.emit('move-tab', 'right')

    def key_move_tab_left(self):
        self.emit('move-tab', 'left')

    def key_toggle_zoom(self):
        if self.is_zoomed():
            self.unzoom()
        else:
            self.maximise()

    def key_scaled_zoom(self):
        if self.is_zoomed():
            self.unzoom()
        else:
            self.zoom()

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

    def key_reset(self):
        self.vte.reset (True, False)

    def key_reset_clear(self):
        self.vte.reset (True, True)

    def key_create_group(self):
        self.titlebar.create_group()

    def key_group_all(self):
        self.emit('group-all')

    def key_group_all_toggle(self):
        self.emit('group-all-toggle')

    def key_ungroup_all(self):
        self.emit('ungroup-all')

    def key_group_win(self):
        dbg("Group Win")
        self.emit('group-win')

    def key_group_win_toggle(self):
        self.emit('group-win-toggle')

    def key_ungroup_win(self):
        self.emit('ungroup-win')

    def key_group_tab(self):
        self.emit('group-tab')

    def key_group_tab_toggle(self):
        self.emit('group-tab-toggle')

    def key_ungroup_tab(self):
        self.emit('ungroup-tab')

    def key_new_window(self):
        self.terminator.new_window(self.get_cwd(), self.get_profile())

    def key_new_tab(self):
        self.get_toplevel().tab_new(self)

    def key_new_terminator(self):
        spawn_new_terminator(self.origcwd, ['-u'])

    def key_broadcast_off(self):
        self.set_groupsend(None, self.terminator.groupsend_type['off'])
        self.terminator.focus_changed(self)

    def key_broadcast_group(self):
        self.set_groupsend(None, self.terminator.groupsend_type['group'])
        self.terminator.focus_changed(self)

    def key_broadcast_all(self):
        self.set_groupsend(None, self.terminator.groupsend_type['all'])
        self.terminator.focus_changed(self)

    def key_insert_number(self):
        self.emit('enumerate', False)

    def key_insert_padded(self):
        self.emit('enumerate', True)

    def key_edit_window_title(self):
        window = self.get_toplevel()
        dialog = Gtk.Dialog(_('Rename Window'), window,
                            Gtk.DialogFlags.MODAL,
                            (Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT,
                             Gtk.STOCK_OK, Gtk.ResponseType.ACCEPT))
        dialog.set_default_response(Gtk.ResponseType.ACCEPT)
        dialog.set_resizable(False)
        dialog.set_border_width(8)

        label = Gtk.Label(label=_('Enter a new title for the Terminator window...'))
        name = Gtk.Entry()
        name.set_activates_default(True)
        if window.title.text != self.vte.get_window_title():
            name.set_text(self.get_toplevel().title.text)

        dialog.vbox.pack_start(label, False, False, 6)
        dialog.vbox.pack_start(name, False, False, 6)

        dialog.show_all()
        res = dialog.run()
        if res == Gtk.ResponseType.ACCEPT:
            if name.get_text():
                window.title.force_title(None)
                window.title.force_title(name.get_text())
            else:
                window.title.force_title(None)
        dialog.destroy()
        return

    def key_edit_tab_title(self):
        window = self.get_toplevel()
        if not window.is_child_notebook():
            return

        notebook = window.get_children()[0]
        n_page = notebook.get_current_page()
        page = notebook.get_nth_page(n_page)
        label = notebook.get_tab_label(page)
        label.edit()

    def key_edit_terminal_title(self):
        self.titlebar.label.edit()

    def key_layout_launcher(self):
        LAYOUTLAUNCHER=LayoutLauncher()

    def key_page_up(self):
        self.scroll_by_page(-1)

    def key_page_down(self):
        self.scroll_by_page(1)

    def key_page_up_half(self):
        self.scroll_by_page(-0.5)

    def key_page_down_half(self):
        self.scroll_by_page(0.5)

    def key_line_up(self):
        self.scroll_by_line(-1)

    def key_line_down(self):
        self.scroll_by_line(1)

    def key_preferences(self):
        PrefsEditor(self)

    def key_preferences_keybindings(self):
        #need to have this as a config may be preferences_default
        #have a mapping rather than hardcoded page
        PrefsEditor(self, cur_page = 3)

    def key_help(self):
        manual_index_page = manual_lookup()
        if manual_index_page:
            self.open_url(manual_index_page)

# End key events


GObject.type_register(Terminal)
# vim: set expandtab ts=4 sw=4:
