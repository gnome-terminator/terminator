#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""terminal.py - classes necessary to provide Terminal widgets"""

from __future__ import division
import sys
import os
import signal
import pygtk
pygtk.require('2.0')
import gtk
import gobject
import pango
import subprocess
import urllib

from util import dbg, err, gerr, spawn_new_terminator, make_uuid,  manual_lookup
import util
from config import Config
from cwd import get_default_cwd
from factory import Factory
from terminator import Terminator
from titlebar import Titlebar
from terminal_popup_menu import TerminalPopupMenu
from searchbar import Searchbar
from translation import _
from signalman import Signalman
import plugin
from terminatorlib.layoutlauncher import LayoutLauncher

try:
    import vte
except ImportError:
    gerr('You need to install python bindings for libvte')
    sys.exit(1)

# pylint: disable-msg=R0904
class Terminal(gtk.VBox):
    """Class implementing the VTE widget and its wrappings"""

    __gsignals__ = {
        'close-term': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        'title-change': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
            (gobject.TYPE_STRING,)),
        'enumerate': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
            (gobject.TYPE_INT,)),
        'group-tab': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        'group-tab-toggle': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        'ungroup-tab': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        'ungroup-all': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        'split-horiz': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
            (gobject.TYPE_STRING,)),
        'split-vert': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
            (gobject.TYPE_STRING,)),
        'rotate-cw': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        'rotate-ccw': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        'tab-new': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
            (gobject.TYPE_BOOLEAN, gobject.TYPE_OBJECT)),
        'tab-top-new': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        'focus-in': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        'focus-out': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        'zoom': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        'maximise': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        'unzoom': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        'resize-term': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
            (gobject.TYPE_STRING,)),
        'navigate': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
            (gobject.TYPE_STRING,)),
        'tab-change': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
            (gobject.TYPE_INT,)),
        'group-all': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        'group-all-toggle': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        'move-tab': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, 
            (gobject.TYPE_STRING,)),
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
    config = None
    default_encoding = None
    custom_encoding = None
    custom_font_size = None
    layout_command = None
    directory = None

    fgcolor_active = None
    fgcolor_inactive = None
    bgcolor = None
    palette_active = None
    palette_inactive = None

    composite_support = None

    cnxids = None
    targets_for_new_group = None

    def __init__(self):
        """Class initialiser"""
        gtk.VBox.__init__(self)
        self.__gobject_init__()

        self.terminator = Terminator()
        self.terminator.register_terminal(self)

        # FIXME: Surely these should happen in Terminator::register_terminal()?
        self.connect('enumerate', self.terminator.do_enumerate)
        self.connect('focus-in', self.terminator.focus_changed)
        self.connect('focus-out', self.terminator.focus_left)

        self.matches = {}
        self.cnxids = Signalman()

        self.config = Config()

        self.cwd = get_default_cwd()
        self.origcwd = self.terminator.origcwd
        self.clipboard = gtk.clipboard_get(gtk.gdk.SELECTION_CLIPBOARD)

        self.pending_on_vte_size_allocate = False

        self.vte = vte.Terminal()
        self.vte._expose_data = None
        if not hasattr(self.vte, "set_opacity") or \
           not hasattr(self.vte, "is_composited"):
            self.composite_support = False
        else:
            self.composite_support = True
        dbg('composite_support: %s' % self.composite_support)

        self.vte.show()

        self.default_encoding = self.vte.get_encoding()
        self.update_url_matches(self.config['try_posix_regexp'])

        self.terminalbox = self.create_terminalbox()

        self.titlebar = Titlebar(self)
        self.titlebar.connect_icon(self.on_group_button_press)
        self.titlebar.connect('edit-done', self.on_edit_done)
        self.connect('title-change', self.titlebar.set_terminal_title)
        self.titlebar.connect('create-group', self.really_create_group)
        self.titlebar.show_all()

        self.searchbar = Searchbar()
        self.searchbar.connect('end-search', self.on_search_done)

        self.show()
        self.pack_start(self.titlebar, False)
        self.pack_start(self.terminalbox)
        self.pack_end(self.searchbar)

        self.connect_signals()

        os.putenv('TERM', self.config['term'])
        os.putenv('COLORTERM', self.config['colorterm'])

        env_proxy = os.getenv('http_proxy')
        if not env_proxy:
            if self.config['http_proxy'] and self.config['http_proxy'] != '':
                os.putenv('http_proxy', self.config['http_proxy'])
        self.reconfigure()
        self.vte.set_size(80, 24)

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
        return(self.terminator.pid_cwd(self.pid))

    def close(self):
        """Close ourselves"""
        dbg('close: called')
        self.cnxids.remove_signal(self.vte, 'child-exited')
        self.emit('close-term')
        try:
            dbg('close: killing %d' % self.pid)
            os.kill(self.pid, signal.SIGHUP)
        except Exception, ex:
            # We really don't want to care if this failed. Deep OS voodoo is
            # not what we should be doing.
            dbg('os.kill failed: %s' % ex)
            pass

    def create_terminalbox(self):
        """Create a GtkHBox containing the terminal and a scrollbar"""

        terminalbox = gtk.HBox()
        self.scrollbar = gtk.VScrollbar(self.vte.get_adjustment())

        terminalbox.pack_start(self.vte, True, True, 0)
        terminalbox.pack_start(self.scrollbar, False, True, 0)
        terminalbox.show_all()

        return(terminalbox)

    def update_url_matches(self, posix = True):
        """Update the regexps used to match URLs"""
        userchars = "-A-Za-z0-9"
        passchars = "-A-Za-z0-9,?;.:/!%$^*&~\"#'"
        hostchars = "-A-Za-z0-9"
        pathchars = "-A-Za-z0-9_$.+!*(),;:@&=?/~#%'"
        schemes   = "(news:|telnet:|nntp:|file:/|https?:|ftps?:|webcal:)"
        user      = "[" + userchars + "]+(:[" + passchars + "]+)?"
        urlpath   = "/[" + pathchars + "]*[^]'.}>) \t\r\n,\\\"]"

        if posix:
            dbg ('Terminal::update_url_matches: Trying POSIX URL regexps')
            lboundry = "[[:<:]]"
            rboundry = "[[:>:]]"
        else: # GNU
            dbg ('Terminal::update_url_matches: Trying GNU URL regexps')
            lboundry = "\\<"
            rboundry = "\\>"

        self.matches['full_uri'] = self.vte.match_add(lboundry + schemes + 
                "//(" + user + "@)?[" + hostchars  +".]+(:[0-9]+)?(" + 
                urlpath + ")?" + rboundry + "/?")

        if self.matches['full_uri'] == -1:
            if posix:
                err ('Terminal::update_url_matches: POSIX failed, trying GNU')
                self.update_url_matches(posix = False)
            else:
                err ('Terminal::update_url_matches: Failed adding URL matches')
        else:
            self.matches['voip'] = self.vte.match_add(lboundry + 
                    '(callto:|h323:|sip:)' + "[" + userchars + "+][" + 
                    userchars + ".]*(:[0-9]+)?@?[" + pathchars + "]+" + 
                    rboundry)
            self.matches['addr_only'] = self.vte.match_add (lboundry + 
                    "(www|ftp)[" + hostchars + "]*\.[" + hostchars + 
                    ".]+(:[0-9]+)?(" + urlpath + ")?" + rboundry + "/?")
            self.matches['email'] = self.vte.match_add (lboundry + 
                    "(mailto:)?[a-zA-Z0-9][a-zA-Z0-9.+-]*@[a-zA-Z0-9]" +
                            "[a-zA-Z0-9-]*\.[a-zA-Z0-9][a-zA-Z0-9-]+" +
                            "[.a-zA-Z0-9-]*" + rboundry)
            self.matches['nntp'] = self.vte.match_add (lboundry + 
                  """news:[-A-Z\^_a-z{|}~!"#$%&'()*+,./0-9;:=?`]+@""" +
                            "[-A-Za-z0-9.]+(:[0-9]+)?" + rboundry)

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
                    self.matches[name] = self.vte.match_add(match)
                    dbg('added plugin URL handler for %s (%s) as %d' % 
                        (name, urlplugin.__class__.__name__,
                        self.matches[name]))
            except Exception, ex:
                err('Exception occurred adding plugin URL match: %s' % ex)

    def match_add(self, name, match):
        """Register a URL match"""
        if name in self.matches:
            err('Terminal::match_add: Refusing to create duplicate match %s' % name)
            return
        self.matches[name] = self.vte.match_add(match)

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

        self.vte.connect('key-press-event', self.on_keypress)
        self.vte.connect('button-press-event', self.on_buttonpress)
        self.vte.connect('scroll-event', self.on_mousewheel)
        self.vte.connect('popup-menu', self.popup_menu)

        srcvtetargets = [("vte", gtk.TARGET_SAME_APP, self.TARGET_TYPE_VTE)]
        dsttargets = [("vte", gtk.TARGET_SAME_APP, self.TARGET_TYPE_VTE), 
                      ('text/x-moz-url', 0, self.TARGET_TYPE_MOZ), 
                      ('_NETSCAPE_URL', 0, 0)]
        dsttargets = gtk.target_list_add_text_targets(dsttargets)
        dsttargets = gtk.target_list_add_uri_targets(dsttargets)
        dbg('Finalised drag targets: %s' % dsttargets)

        for (widget, mask) in [
            (self.vte, gtk.gdk.CONTROL_MASK | gtk.gdk.BUTTON3_MASK), 
            (self.titlebar, gtk.gdk.BUTTON1_MASK)]:
            widget.drag_source_set(mask, srcvtetargets, gtk.gdk.ACTION_MOVE)

        self.vte.drag_dest_set(gtk.DEST_DEFAULT_MOTION |
                gtk.DEST_DEFAULT_HIGHLIGHT | gtk.DEST_DEFAULT_DROP,
                dsttargets, gtk.gdk.ACTION_COPY | gtk.gdk.ACTION_MOVE)

        for widget in [self.vte, self.titlebar]:
            widget.connect('drag-begin', self.on_drag_begin, self)
            widget.connect('drag-data-get', self.on_drag_data_get,
            self)

        self.vte.connect('drag-motion', self.on_drag_motion, self)
        self.vte.connect('drag-data-received',
            self.on_drag_data_received, self)

        self.cnxids.new(self.vte, 'selection-changed', 
            lambda widget: self.maybe_copy_clipboard())

        if self.composite_support:
            self.vte.connect('composited-changed', self.reconfigure)

        self.vte.connect('window-title-changed', lambda x:
            self.emit('title-change', self.get_window_title()))
        self.vte.connect('grab-focus', self.on_vte_focus)
        self.vte.connect('focus-in-event', self.on_vte_focus_in)
        self.vte.connect('focus-out-event', self.on_vte_focus_out)
        self.vte.connect('size-allocate', self.deferred_on_vte_size_allocate)

        self.vte.add_events(gtk.gdk.ENTER_NOTIFY_MASK)
        self.vte.connect('enter_notify_event',
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
        menu.popup(None, None, self.position_popup_group_menu, button, time,
                widget)
        return(True)

    def populate_group_menu(self):
        """Fill out a group menu"""
        menu = gtk.Menu()
        groupitem = None

        item = gtk.MenuItem(_('N_ew group...'))
        item.connect('activate', self.create_group)
        menu.append(item)

        if len(self.terminator.groups) > 0:
            groupitem = gtk.RadioMenuItem(groupitem, _('_None'))
            groupitem.set_active(self.group == None)
            groupitem.connect('activate', self.set_group, None)
            menu.append(groupitem)

            for group in self.terminator.groups:
                item = gtk.RadioMenuItem(groupitem, group, False)
                item.set_active(self.group == group)
                item.connect('toggled', self.set_group, group)
                menu.append(item)
                groupitem = item

        if self.group != None or len(self.terminator.groups) > 0:
            menu.append(gtk.MenuItem())

        if self.group != None:
            item = gtk.MenuItem(_('Remove group %s') % self.group)
            item.connect('activate', self.ungroup, self.group)
            menu.append(item)

        if util.has_ancestor(self, gtk.Notebook):
            item = gtk.MenuItem(_('G_roup all in tab'))
            item.connect('activate', lambda x: self.emit('group_tab'))
            menu.append(item)

            if len(self.terminator.groups) > 0:
                item = gtk.MenuItem(_('Ungro_up all in tab'))
                item.connect('activate', lambda x: self.emit('ungroup_tab'))
                menu.append(item)

        if len(self.terminator.groups) > 0:
            item = gtk.MenuItem(_('Remove all groups'))
            item.connect('activate', lambda x: self.emit('ungroup-all'))
            menu.append(item)

        if self.group != None:
            menu.append(gtk.MenuItem())

            item = gtk.MenuItem(_('Close group %s') % self.group)
            item.connect('activate', lambda x:
                         self.terminator.closegroupedterms(self.group))
            menu.append(item)

        menu.append(gtk.MenuItem())

        groupitem = None

        for key, value in {_('Broadcast _all'):'all', 
                          _('Broadcast _group'):'group',
                          _('Broadcast _off'):'off'}.items():
            groupitem = gtk.RadioMenuItem(groupitem, key)
            dbg('Terminal::populate_group_menu: %s active: %s' %
                    (key, self.terminator.groupsend ==
                        self.terminator.groupsend_type[value]))
            groupitem.set_active(self.terminator.groupsend ==
                    self.terminator.groupsend_type[value])
            groupitem.connect('activate', self.set_groupsend,
                    self.terminator.groupsend_type[value])
            menu.append(groupitem)

        menu.append(gtk.MenuItem())

        item = gtk.CheckMenuItem(_('_Split to this group'))
        item.set_active(self.config['split_to_group'])
        item.connect('toggled', lambda x: self.do_splittogroup_toggle())
        menu.append(item)

        item = gtk.CheckMenuItem(_('Auto_clean groups'))
        item.set_active(self.config['autoclean_groups'])
        item.connect('toggled', lambda x: self.do_autocleangroups_toggle())
        menu.append(item)

        menu.append(gtk.MenuItem())

        item = gtk.MenuItem(_('_Insert terminal number'))
        item.connect('activate', lambda x: self.emit('enumerate', False))
        menu.append(item)

        item = gtk.MenuItem(_('Insert _padded terminal number'))
        item.connect('activate', lambda x: self.emit('enumerate', True))
        menu.append(item)

        return(menu)

    def position_popup_group_menu(self, menu, widget):
        """Calculate the position of the group popup menu"""
        _screen_w = gtk.gdk.screen_width()
        screen_h = gtk.gdk.screen_height()

        if gtk.gtk_version >= (2, 14):
            widget_win = widget.get_window()
        else:
            widget_win = widget.window
        widget_x, widget_y = widget_win.get_origin()
        _widget_w, widget_h = widget_win.get_size()

        _menu_w, menu_h = menu.size_request()

        if widget_y + widget_h + menu_h > screen_h:
            menu_y = max(widget_y - menu_h, 0)
        else:
            menu_y = widget_y + widget_h

        return(widget_x, menu_y, 1)

    def set_group(self, _item, name):
        """Set a particular group"""
        if self.group == name:
            # already in this group, no action needed
            return
        dbg('Terminal::set_group: Setting group to %s' % name)
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
        if value in self.terminator.groupsend_type.values():
            dbg('Terminal::set_groupsend: setting groupsend to %s' % value)
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
        elif self.config['exit_action'] in ('close', 'left'):
            self.cnxids.new(self.vte, 'child-exited', 
                                            lambda x: self.emit('close-term'))

        self.vte.set_emulation(self.config['emulation'])
        if self.custom_encoding != True:
            self.vte.set_encoding(self.config['encoding'])
        self.vte.set_word_chars(self.config['word_chars'])
        self.vte.set_mouse_autohide(self.config['mouse_autohide'])

        backspace = self.config['backspace_binding']
        delete = self.config['delete_binding']

        try:
            if backspace == 'ascii-del':
                backbind = vte.ERASE_ASCII_DELETE
            elif backspace == 'control-h':
                backbind = vte.ERASE_ASCII_BACKSPACE
            elif backspace == 'escape-sequence':
                backbind = vte.ERASE_DELETE_SEQUENCE
            else:
                backbind = vte.ERASE_AUTO
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
                delbind = vte.ERASE_ASCII_DELETE
            elif delete == 'control-h':
                delbind = vte.ERASE_ASCII_BACKSPACE
            elif delete == 'escape-sequence':
                delbind = vte.ERASE_DELETE_SEQUENCE
            else:
                delbind = vte.ERASE_AUTO
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
                self.set_font(pango.FontDescription(font))
            except:
                pass
        self.vte.set_allow_bold(self.config['allow_bold'])
        if self.config['use_theme_colors']:
            self.fgcolor_active = self.vte.get_style().text[gtk.STATE_NORMAL]
            self.bgcolor = self.vte.get_style().base[gtk.STATE_NORMAL]
        else:
            self.fgcolor_active = gtk.gdk.color_parse(self.config['foreground_color'])
            self.bgcolor = gtk.gdk.color_parse(self.config['background_color'])

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
        colors = self.config['palette'].split(':')
        self.palette_active = []
        for color in colors:
            if color:
                newcolor = gtk.gdk.color_parse(color)
                self.palette_active.append(newcolor)
        if len(colors) == 16:
            # RGB values for indices 16..255 copied from vte source in order to dim them
            shades = [0, 95, 135, 175, 215, 255]
            for r in xrange(0, 6):
                for g in xrange(0, 6):
                    for b in xrange(0, 6):
                        newcolor = gtk.gdk.Color(shades[r] / 255.0,
                                                 shades[g] / 255.0,
                                                 shades[b] / 255.0)
                        self.palette_active.append(newcolor)
            for y in xrange(8, 248, 10):
                newcolor = gtk.gdk.Color(y / 255.0,
                                         y / 255.0,
                                         y / 255.0)
                self.palette_active.append(newcolor)
        self.palette_active = self.palette_active[:255]
        self.palette_inactive = []
        for color in self.palette_active:
            newcolor = gtk.gdk.Color()
            for bit in ['red', 'green', 'blue']:
                setattr(newcolor, bit,
                        getattr(color, bit) * factor)
            self.palette_inactive.append(newcolor)
        if self.terminator.last_focused_term == self:
            self.vte.set_colors(self.fgcolor_active, self.bgcolor,
                                self.palette_active)
        else:
            self.vte.set_colors(self.fgcolor_inactive, self.bgcolor,
                                self.palette_inactive)
        self.set_cursor_color()
        if hasattr(self.vte, 'set_cursor_shape'):
            self.vte.set_cursor_shape(getattr(vte, 'CURSOR_SHAPE_' +
                self.config['cursor_shape'].upper()))

        background_type = self.config['background_type']
        dbg('background_type=%s' % background_type)
        if background_type == 'image' and \
           self.config['background_image'] is not None and \
           self.config['background_image'] != '':
            self.vte.set_background_image_file(self.config['background_image'])
            self.vte.set_scroll_background(self.config['scroll_background'])
        else:
            try:
                self.vte.set_background_image(None)
            except TypeError:
                # FIXME: I think this is only necessary because of
                # https://bugzilla.gnome.org/show_bug.cgi?id=614910
                pass
            self.vte.set_scroll_background(False)

        if background_type in ('image', 'transparent'):
            self.vte.set_background_tint_color(gtk.gdk.color_parse(
                                               self.config['background_color']))
            opacity = int(self.config['background_darkness'] * 65536)
            saturation = 1.0 - float(self.config['background_darkness'])
            dbg('setting background saturation: %f' % saturation)
            self.vte.set_background_saturation(saturation)
        else:
            dbg('setting background_saturation: 1')
            opacity = 65535
            self.vte.set_background_saturation(1)

        if self.composite_support:
            dbg('setting opacity: %d' % opacity)
            self.vte.set_opacity(opacity)

        # This is quite hairy, but the basic explanation is that we should
        # set_background_transparent(True) when we have no compositing and want
        # fake background transparency, otherwise it should be False.
        if not self.composite_support or self.config['disable_real_transparency']:
            # We have no compositing support, fake background only
            background_transparent = True
        else:
            if self.vte.is_composited() == False:
                # We have compositing and it's enabled. no fake background.
                background_transparent = True
            else:
                # We have compositing, but it's not enabled. fake background
                background_transparent = False

        if self.config['background_type'] == 'transparent':
            dbg('setting background_transparent=%s' % background_transparent)
            self.vte.set_background_transparent(background_transparent)
        else:
            dbg('setting background_transparent=False')
            self.vte.set_background_transparent(False)

        if hasattr(vte, 'VVVVTE_CURSOR_BLINK_ON'):
            if self.config['cursor_blink'] == True:
                self.vte.set_cursor_blink_mode('VTE_CURSOR_BLINK_ON')
            else:
                self.vte.set_cursor_blink_mode('VTE_CURSOR_BLINK_OFF')
        else:
            self.vte.set_cursor_blinks(self.config['cursor_blink'])

        if self.config['force_no_bell'] == True:
            self.vte.set_audible_bell(False)
            self.vte.set_visible_bell(False)
            self.cnxids.remove_signal(self.vte, 'beep')
        else:
            self.vte.set_audible_bell(self.config['audible_bell'])
            self.vte.set_visible_bell(self.config['visible_bell'])
            self.cnxids.remove_signal(self.vte, 'beep')
            if self.config['urgent_bell'] == True or \
               self.config['icon_bell'] == True:
                try:
                    self.cnxids.new(self.vte, 'beep', self.on_beep)
                except TypeError:
                    err('beep signal unavailable with this version of VTE')

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

        if hasattr(self.vte, 'set_alternate_screen_scroll'):
            self.vte.set_alternate_screen_scroll(
                                        self.config['alternate_screen_scroll'])

        self.titlebar.update()
        self.vte.queue_draw()

    def set_cursor_color(self):
        """Set the cursor color appropriately"""
        if self.config['cursor_color_fg']:
            try:
                self.vte.set_color_cursor(None) 
            except TypeError:
                # FIXME: I think this is only necessary because of
                # https://bugzilla.gnome.org/show_bug.cgi?id=614910
                pass
        elif self.config['cursor_color'] != '':
            self.vte.set_color_cursor(gtk.gdk.color_parse(
                                        self.config['cursor_color']))
 
    def get_window_title(self):
        """Return the window title"""
        return(self.vte.get_window_title() or str(self.command))

    def on_group_button_press(self, widget, event):
        """Handler for the group button"""
        if event.button == 1:
            if event.type == gtk.gdk._2BUTTON_PRESS or \
               event.type == gtk.gdk._3BUTTON_PRESS:
                # Ignore these, or they make the interaction bad
                return True
            # Super key applies interaction to all terms in group
            include_siblings=event.state & gtk.gdk.MOD4_MASK == gtk.gdk.MOD4_MASK
            if include_siblings:
                targets=self.terminator.get_sibling_terms(self)
            else:
                targets=[self]
            if event.state & gtk.gdk.CONTROL_MASK == gtk.gdk.CONTROL_MASK:
                dbg('on_group_button_press: toggle terminal to focused terminals group')
                focused=self.get_toplevel().get_focussed_terminal()
                if focused in targets: targets.remove(focused)
                if self != focused:
                    if self.group==focused.group:
                        new_group=None
                    else:
                        new_group=focused.group
                    [term.set_group(None, new_group) for term in targets]
                    [term.titlebar.update(focused) for term in targets]
                return True
            elif event.state & gtk.gdk.SHIFT_MASK == gtk.gdk.SHIFT_MASK:
                dbg('on_group_button_press: rename of terminals group')
                self.targets_for_new_group = targets
                self.titlebar.create_group()
                return True
            elif event.type == gtk.gdk.BUTTON_PRESS:
                # Single Click gives popup
                dbg('on_group_button_press: group menu popup')
                self.create_popup_group_menu(widget, event)
                return True
            else:
                dbg('on_group_button_press: unknown group button interaction')
        return(False)

    def on_keypress(self, widget, event):
        """Handler for keyboard events"""
        if not event:
            dbg('Terminal::on_keypress: Called on %s with no event' % widget)
            return(False)

        # Workaround for IBus interfering with broadcast when using dead keys
        # Environment also needs IBUS_DISABLE_SNOOPER=1, or double chars appear
        # in the receivers.
        if self.terminator.ibus_running:
            if (event.state | gtk.gdk.MODIFIER_MASK ) ^ gtk.gdk.MODIFIER_MASK != 0:
                dbg('Terminal::on_keypress: Ignore processed event with event.state %d' % event.state)
                return(False)
        
        # FIXME: Does keybindings really want to live in Terminator()?
        mapping = self.terminator.keybindings.lookup(event)

        if mapping == "hide_window":
            return(False)

        if mapping and mapping not in ['close_window', 
                                       'full_screen']:
            dbg('Terminal::on_keypress: lookup found: %r' % mapping)
            # handle the case where user has re-bound copy to ctrl+<key>
            # we only copy if there is a selection otherwise let it fall through
            # to ^<key>
            if (mapping == "copy" and event.state & gtk.gdk.CONTROL_MASK):
                if self.vte.get_has_selection ():
                    getattr(self, "key_" + mapping)()
                    return(True)
                elif not self.config['smart_copy']:
                    return(True)
            else:
                getattr(self, "key_" + mapping)()
                return(True)

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

        return(False)

    def on_buttonpress(self, widget, event):
        """Handler for mouse events"""
        # Any button event should grab focus
        widget.grab_focus()

        if type(widget) == gtk.VScrollbar and event.type == gtk.gdk._2BUTTON_PRESS:
            # Suppress double-click behavior
            return True

        if self.config['putty_paste_style']:
            middle_click = [self.popup_menu, (widget, event)]
            right_click = [self.paste_clipboard, (True, )]
        else:
            middle_click = [self.paste_clipboard, (True, )]
            right_click = [self.popup_menu, (widget, event)]

        if event.button == self.MOUSEBUTTON_LEFT:
            # Ctrl+leftclick on a URL should open it
            if event.state & gtk.gdk.CONTROL_MASK == gtk.gdk.CONTROL_MASK:
                url = self.check_for_url(event)
                if url:
                    self.open_url(url, prepare=True)
        elif event.button == self.MOUSEBUTTON_MIDDLE:
            # middleclick should paste the clipboard
            middle_click[0](*middle_click[1])
            return(True)
        elif event.button == self.MOUSEBUTTON_RIGHT:
            # rightclick should display a context menu if Ctrl is not pressed
            if event.state & gtk.gdk.CONTROL_MASK == 0:
                right_click[0](*right_click[1])
                return(True)

        return(False)
    
    def on_mousewheel(self, widget, event):
        """Handler for modifier + mouse wheel scroll events"""
        if event.state & gtk.gdk.CONTROL_MASK == gtk.gdk.CONTROL_MASK:
            # Ctrl + mouse wheel up/down with Shift and Super additions
            if event.state & gtk.gdk.MOD4_MASK == gtk.gdk.MOD4_MASK:
                targets=self.terminator.terminals
            elif event.state & gtk.gdk.SHIFT_MASK == gtk.gdk.SHIFT_MASK:
                targets=self.terminator.get_target_terms(self)
            else:
                targets=[self]
            if event.direction == gtk.gdk.SCROLL_UP:
                for target in targets:
                    target.zoom_in()
                return (True)
            elif event.direction == gtk.gdk.SCROLL_DOWN:
                for target in targets:
                    target.zoom_out()
                return (True)
        if event.state & gtk.gdk.SHIFT_MASK == gtk.gdk.SHIFT_MASK:
            # Shift + mouse wheel up/down
            if event.direction == gtk.gdk.SCROLL_UP:
                self.scroll_by_page(-1)
                return (True)
            elif event.direction == gtk.gdk.SCROLL_DOWN:
                self.scroll_by_page(1)
                return (True)
        return(False)

    def popup_menu(self, widget, event=None):
        """Display the context menu"""
        menu = TerminalPopupMenu(self)
        menu.show(widget, event)

    def do_scrollbar_toggle(self):
        """Show or hide the terminal scrollbar"""
        self.toggle_widget_visibility(self.scrollbar)

    def toggle_widget_visibility(self, widget):
        """Show or hide a widget"""
        if widget.get_property('visible'):
            widget.hide()
        else:
            widget.show()

    def on_encoding_change(self, _widget, encoding):
        """Handle the encoding changing"""
        current = self.vte.get_encoding()
        if current != encoding:
            dbg('on_encoding_change: setting encoding to: %s' % encoding)
            self.custom_encoding = not (encoding == self.config['encoding'])
            self.vte.set_encoding(encoding)

    def on_drag_begin(self, widget, drag_context, _data):
        """Handle the start of a drag event"""
        widget.drag_source_set_icon_pixbuf(util.widget_pixbuf(self, 512))

    def on_drag_data_get(self, _widget, _drag_context, selection_data, info, 
            _time, data):
        """I have no idea what this does, drag and drop is a mystery. sorry."""
        selection_data.set('vte', info,
                str(data.terminator.terminals.index(self)))

    def on_drag_motion(self, widget, drag_context, x, y, _time, _data):
        """*shrug*"""
        if not drag_context.targets == ['vte'] and \
           (gtk.targets_include_text(drag_context.targets) or \
           gtk.targets_include_uri(drag_context.targets)):
            # copy text from another widget
            return
        srcwidget = drag_context.get_source_widget()
        if(isinstance(srcwidget, gtk.EventBox) and 
           srcwidget == self.titlebar) or widget == srcwidget:
            # on self
            return

        alloc = widget.allocation
        rect = gtk.gdk.Rectangle(0, 0, alloc.width, alloc.height)

        if self.config['use_theme_colors']:
            color = self.vte.get_style().text[gtk.STATE_NORMAL]
        else:
            color = gtk.gdk.color_parse(self.config['foreground_color'])

        pos = self.get_location(widget, x, y)
        topleft = (0, 0)
        topright = (alloc.width, 0)
        topmiddle = (alloc.width/2, 0)
        bottomleft = (0, alloc.height)
        bottomright = (alloc.width, alloc.height)
        bottommiddle = (alloc.width/2, alloc.height)
        middleleft = (0, alloc.height/2)
        middleright = (alloc.width, alloc.height/2)
        #print "%f %f %d %d" %(coef1, coef2, b1,b2)
        coord = ()
        if pos == "right":
            coord = (topright, topmiddle, bottommiddle, bottomright)
        elif pos == "top":
            coord = (topleft, topright, middleright , middleleft)
        elif pos == "left":
            coord = (topleft, topmiddle, bottommiddle, bottomleft)
        elif pos == "bottom":
            coord = (bottomleft, bottomright, middleright , middleleft) 

        #here, we define some widget internal values
        widget._expose_data = { 'color': color, 'coord' : coord }
        #redraw by forcing an event
        connec = widget.connect_after('expose-event', self.on_expose_event)
        widget.window.invalidate_rect(rect, True)
        widget.window.process_updates(True)
        #finaly reset the values
        widget.disconnect(connec)
        widget._expose_data = None

    def on_expose_event(self, widget, _event):
        """Handle an expose event while dragging"""
        if not widget._expose_data:
            return(False)

        color = widget._expose_data['color']
        coord = widget._expose_data['coord']

        context = widget.window.cairo_create()
        context.set_source_rgba(color.red, color.green, color.blue, 0.5)
        if len(coord) > 0 :
            context.move_to(coord[len(coord)-1][0], coord[len(coord)-1][1])
            for i in coord:
                context.line_to(i[0], i[1])

        context.fill()
        return(False)

    def on_drag_data_received(self, widget, drag_context, x, y, selection_data,
            info, _time, data):
        """Something has been dragged into the terminal. Handle it as either a
        URL or another terminal."""
        dbg('drag data received of type: %s' % selection_data.type)
        if gtk.targets_include_text(drag_context.targets) or \
           gtk.targets_include_uri(drag_context.targets):
            # copy text with no modification yet to destination
            txt = selection_data.data

            # https://bugs.launchpad.net/terminator/+bug/1518705
            if info == self.TARGET_TYPE_MOZ:
                 txt = txt.decode('utf-16').encode('utf-8')
                 txt = txt.split('\n')[0]

            txt_lines = txt.split( "\r\n" )
            if txt_lines[-1] == '':
                for line in txt_lines[:-1]:
                    if line[0:7] != 'file://':
                        break
                else:
                    # It is a list of crlf terminated file:// URL. let's
                    # iterate over all elements except the last one.
                    str=''
                    for fname in txt_lines[:-1]:
                        dbg('drag data fname: %s' % fname)
                        fname = "'%s'" % urllib.unquote(fname[7:].replace("'",
                                                                    '\'\\\'\''))
                        str += fname + ' '
                    txt=str
            for term in self.terminator.get_target_terms(self):
                term.feed(txt)
            return
        
        widgetsrc = data.terminator.terminals[int(selection_data.data)]
        srcvte = drag_context.get_source_widget()
        #check if computation requireds
        if (isinstance(srcvte, gtk.EventBox) and 
                srcvte == self.titlebar) or srcvte == widget:
            return

        srchbox = widgetsrc

        # The widget argument is actually a vte.Terminal(). Turn that into a
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
        #get the diagonales function for the receiving widget
        coef1 = float(term.allocation.height)/float(term.allocation.width)
        coef2 = -float(term.allocation.height)/float(term.allocation.width)
        b1 = 0
        b2 = term.allocation.height
        #determine position in rectangle
        #--------
        #|\    /|
        #| \  / |
        #|  \/  |
        #|  /\  |
        #| /  \ |
        #|/    \|
        #--------
        if (x*coef1 + b1 > y ) and (x*coef2 + b2 < y ):
            pos =  "right"
        if (x*coef1 + b1 > y ) and (x*coef2 + b2 > y ):
            pos = "top"
        if (x*coef1 + b1 < y ) and (x*coef2 + b2 > y ):
            pos = "left"
        if (x*coef1 + b1 < y ) and (x*coef2 + b2 < y ):
            pos = "bottom"
        return pos

    def grab_focus(self):
        """Steal focus for this terminal"""
        if not self.vte.flags()&gtk.HAS_FOCUS:
            self.vte.grab_focus()

    def ensure_visible_and_focussed(self):
        """Make sure that we're visible and focussed"""
        window = self.get_toplevel()
        topchild = window.get_child()
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
        if self.config['inactive_color_offset'] < 1.0:
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
        if self.config['inactive_color_offset'] < 1.0:
            self.vte.set_colors(self.fgcolor_inactive, self.bgcolor,
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
        if self.pending_on_vte_size_allocate == True:
            return
        self.pending_on_vte_size_allocate = True
        gobject.idle_add(self.do_deferred_on_vte_size_allocate, widget, allocation)

    def do_deferred_on_vte_size_allocate(self, widget, allocation):
        self.pending_on_vte_size_allocate = False
        self.on_vte_size_allocate(widget, allocation)

    def on_vte_size_allocate(self, widget, allocation):
        self.titlebar.update_terminal_size(self.vte.get_column_count(),
                self.vte.get_row_count())
        if self.vte.window and self.config['geometry_hinting']:
            window = self.get_toplevel()
            window.deferred_set_rough_geometry_hints()

    def on_vte_notify_enter(self, term, event):
        """Handle the mouse entering this terminal"""
        # FIXME: This shouldn't be looking up all these values every time
        sloppy = False
        if self.config['focus'] == 'system':
            sloppy = self.config.get_system_focus() in ['sloppy', 'mouse']
        elif self.config['focus'] in ['sloppy', 'mouse']:
            sloppy = True
        if sloppy == True and self.titlebar.editing() == False:
            term.grab_focus()
            return(False)

    def get_zoom_data(self):
        """Return a dict of information for Window"""
        data = {}
        data['old_font'] = self.vte.get_font()
        data['old_char_height'] = self.vte.get_char_height()
        data['old_char_width'] = self.vte.get_char_width()
        data['old_allocation'] = self.vte.get_allocation()
        data['old_columns'] = self.vte.get_column_count()
        data['old_rows'] = self.vte.get_row_count()
        data['old_parent'] = self.get_parent()

        return(data)

    def zoom_scale(self, widget, allocation, old_data):
        """Scale our font correctly based on how big we are not vs before"""
        self.cnxids.remove_signal(self, 'size-allocate')
        # FIXME: Is a zoom signal actualy used anywhere?
        self.cnxids.remove_signal(self, 'zoom')

        new_columns = self.vte.get_column_count()
        new_rows = self.vte.get_row_count()
        new_font = self.vte.get_font()

        dbg('Terminal::zoom_scale: Resized from %dx%d to %dx%d' % (
             old_data['old_columns'],
             old_data['old_rows'],
             new_columns,
             new_rows))

        if new_rows == old_data['old_rows'] or \
           new_columns == old_data['old_columns']:
            dbg('Terminal::zoom_scale: One axis unchanged, not scaling')
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
        prop = None
        window = self.get_toplevel()

        try:
            prop = window.get_property('term-zoomed')
        except TypeError:
            prop = False

        return(prop)

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

    def spawn_child(self, widget=None, respawn=False, debugserver=False):
        update_records = self.config['update_records']
        login = self.config['login_shell']
        args = []
        shell = None
        command = None

        if self.terminator.doing_layout == True:
            dbg('still laying out, refusing to spawn a child')
            return

        if respawn == False:
            self.vte.grab_focus()

        options = self.config.options_get()
        if options and options.command:
            command = options.command
            options.command = None
        elif options and options.execute:
            command = options.execute
            options.execute = None
        elif self.config['use_custom_command']:
            command = self.config['custom_command']
        elif self.layout_command:
            command = self.layout_command
        elif debugserver is True:
            details = self.terminator.debug_address
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
                args.insert(0, "-%s" % shell)
            else:
                args.insert(0, shell)

            if command is not None:
                args += ['-c', command]

        if shell is None:
            self.vte.feed(_('Unable to find a shell'))
            return(-1)

        try:
            os.putenv('WINDOWID', '%s' % self.vte.get_parent_window().xid)
        except AttributeError:
            pass

        envv = []
        envv.append('TERM=%s' % self.config['term'])
        envv.append('COLORTERM=%s' % self.config['colorterm'])
        envv.append('PWD=%s' % self.cwd)
        envv.append('TERMINATOR_UUID=%s' % self.uuid.urn)
        if self.terminator.dbus_name:
            envv.append('TERMINATOR_DBUS_NAME=%s' % self.terminator.dbus_name)
        if self.terminator.dbus_path:
            envv.append('TERMINATOR_DBUS_PATH=%s' % self.terminator.dbus_path)

        dbg('Forking shell: "%s" with args: %s' % (shell, args))
        self.pid = self.vte.fork_command(command=shell, argv=args, envv=envv,
                                         loglastlog=login, 
                                         logwtmp=update_records,
                                         logutmp=update_records, 
                                         directory=self.cwd)
        self.command = shell

        self.titlebar.update()

        if self.pid == -1:
            self.vte.feed(_('Unable to start shell:') + shell)
            return(-1)

    def check_for_url(self, event):
        """Check if the mouse is over a URL"""
        return (self.vte.match_check(int(event.x / self.vte.get_char_width()),
            int(event.y / self.vte.get_char_height())))

    def prepare_url(self, urlmatch):
        """Prepare a URL from a VTE match"""
        url = urlmatch[0]
        match = urlmatch[1]

        if match == self.matches['email'] and url[0:7] != 'mailto:':
            url = 'mailto:' + url
        elif match == self.matches['addr_only'] and url[0:3] == 'ftp':
            url = 'ftp://' + url
        elif match == self.matches['addr_only']:
            url = 'http://' + url
        elif match in self.matches.values():
            # We have a match, but it's not a hard coded one, so it's a plugin
            try:
                registry = plugin.PluginRegistry()
                registry.load_plugins()
                plugins = registry.get_plugins_by_capability('url_handler')

                for urlplugin in plugins:
                    if match == self.matches[urlplugin.handler_name]:
                        newurl = urlplugin.callback(url)
                        if newurl is not None:
                            dbg('Terminal::prepare_url: URL prepared by \
%s plugin' % urlplugin.handler_name)
                            url = newurl
                        break
            except Exception, ex:
                err('Exception occurred preparing URL: %s' % ex)

        return(url)

    def open_url(self, url, prepare=False):
        """Open a given URL, conditionally unpacking it from a VTE match"""
        oldstyle = False

        if prepare == True:
            url = self.prepare_url(url)
        dbg('open_url: URL: %s (prepared: %s)' % (url, prepare))

        if self.config['use_custom_url_handler']:
            dbg("Using custom URL handler: %s" %
                self.config['custom_url_handler'])
            try:
                subprocess.Popen([self.config['custom_url_handler'], url])
                return
            except:
                dbg('custom url handler did not work, falling back to defaults')

        if gtk.gtk_version < (2, 14, 0) or \
           not hasattr(gtk, 'show_uri') or \
           not hasattr(gtk.gdk, 'CURRENT_TIME'):
            oldstyle = True

        if oldstyle == False:
            try:
                gtk.show_uri(None, url, gtk.gdk.CURRENT_TIME)
            except:
                oldstyle = True

        if oldstyle == True:
            dbg('Old gtk (%s,%s,%s), calling xdg-open' % gtk.gtk_version)
            try:
                subprocess.Popen(["xdg-open", url])
            except:
                dbg('xdg-open did not work, falling back to webbrowser.open')
                import webbrowser
                webbrowser.open(url)

    def paste_clipboard(self, primary=False):
        """Paste one of the two clipboards"""
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

        if fontsize > pango.SCALE and not zoom_in:
            fontsize -= pango.SCALE
        elif zoom_in:
            fontsize += pango.SCALE

        pangodesc.set_size(fontsize)
        self.set_font(pangodesc)
        self.custom_font_size = fontsize

    def zoom_orig(self):
        """Restore original font size"""
        if self.config['use_system_font'] == True:
            font = self.config.get_system_mono_font()
        else:
            font = self.config['font']
        dbg("Terminal::zoom_orig: restoring font to: %s" % font)
        self.set_font(pango.FontDescription(font))
        self.custom_font_size = None

    def set_font(self, fontdesc):
        """Set the font we want in VTE"""
        antialias = self.config['antialias']
        if antialias:
            try:
                antialias = vte.ANTI_ALIAS_FORCE_ENABLE
            except AttributeError:
                antialias = 1
        else:
            try:
                antialias = vte.ANTI_ALIAS_FORCE_DISABLE
            except AttributeError:
                antialias = 2
        self.vte.set_font_full(fontdesc, antialias)

    def get_cursor_position(self):
        """Return the co-ordinates of our cursor"""
        # FIXME: THIS METHOD IS DEPRECATED AND UNUSED
        col, row = self.vte.get_cursor_position()
        width = self.vte.get_char_width()
        height = self.vte.get_char_height()
        return((col * width, row * height))

    def get_font_size(self):
        """Return the width/height of our font"""
        return((self.vte.get_char_width(), self.vte.get_char_height()))

    def get_size(self):
        """Return the column/rows of the terminal"""
        return((self.vte.get_column_count(), self.vte.get_row_count()))

    def on_beep(self, widget):
        """Set the urgency hint for our window"""
        if self.config['urgent_bell'] == True:
            window = self.get_toplevel()
            if window.flags() & gtk.TOPLEVEL:
                window.set_urgency_hint(True)
        if self.config['icon_bell'] == True:
            self.titlebar.icon_bell()

    def describe_layout(self, count, parent, global_layout, child_order):
        """Describe our layout"""
        layout = {}
        layout['type'] = 'Terminal'
        layout['parent'] = parent
        layout['order'] = child_order
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
        name = 'terminal%d' % count
        count = count + 1
        global_layout[name] = layout
        return(count)

    def create_layout(self, layout):
        """Apply our layout"""
        dbg('Setting layout')
        if layout.has_key('command') and layout['command'] != '':
            self.layout_command = layout['command']
        if layout.has_key('profile') and layout['profile'] != '':
            if layout['profile'] in self.config.list_profiles():
                self.set_profile(self, layout['profile'])
        if layout.has_key('group') and layout['group'] != '':
            # This doesn't need/use self.titlebar, but it's safer than sending
            # None
            self.really_create_group(self.titlebar, layout['group'])
        if layout.has_key('title') and layout['title'] != '':
            self.titlebar.set_custom_string(layout['title'])
        if layout.has_key('directory') and layout['directory'] != '':
            self.directory = layout['directory']
        if layout.has_key('uuid') and layout['uuid'] != '':
            self.uuid = make_uuid(layout['uuid'])

    def scroll_by_page(self, pages):
        """Scroll up or down in pages"""
        amount = pages * self.vte.get_adjustment().get_page_increment()
        self.scroll_by(int(amount))

    def scroll_by_line(self, lines):
        """Scroll up or down in lines"""
        amount = lines * self.vte.get_adjustment().get_step_increment()
        self.scroll_by(int(amount))

    def scroll_by(self, amount):
        """Scroll up or down by an amount of lines"""
        adjustment = self.vte.get_adjustment()
        bottom = adjustment.upper - adjustment.page_size
        value = adjustment.get_value() + amount
        adjustment.set_value(min(value, bottom))

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

    def key_paste(self):
        self.paste_clipboard()

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

    def key_split_horiz(self):
        self.emit('split-horiz', self.terminator.pid_cwd(self.pid))

    def key_split_vert(self):
        self.emit('split-vert', self.terminator.pid_cwd(self.pid))

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

    def key_group_all(self):
        self.emit('group-all')

    def key_group_all_toggle(self):
        self.emit('group-all-toggle')

    def key_ungroup_all(self):
        self.emit('ungroup-all')

    def key_group_tab(self):
        self.emit('group-tab')

    def key_group_tab_toggle(self):
        self.emit('group-tab-toggle')

    def key_ungroup_tab(self):
        self.emit('ungroup-tab')

    def key_new_window(self):
        self.terminator.new_window(self.terminator.pid_cwd(self.pid), self.get_profile())

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
        dialog = gtk.Dialog(_('Rename Window'), window,
                        gtk.DIALOG_MODAL,
                        ( gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT,
                          gtk.STOCK_OK, gtk.RESPONSE_ACCEPT ))
        dialog.set_default_response(gtk.RESPONSE_ACCEPT)
        dialog.set_has_separator(False)
        dialog.set_resizable(False)
        dialog.set_border_width(8)
        
        label = gtk.Label(_('Enter a new title for the Terminator window...'))
        name = gtk.Entry()
        name.set_activates_default(True)
        if window.title.text != self.vte.get_window_title():
            name.set_text(self.get_toplevel().title.text)
        
        dialog.vbox.pack_start(label, False, False, 6)
        dialog.vbox.pack_start(name, False, False, 6)

        dialog.show_all()
        res = dialog.run()
        if res == gtk.RESPONSE_ACCEPT:
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

    def key_help(self):
        manual_index_page = manual_lookup()
        if manual_index_page:
            self.open_url('file://%s' % (manual_index_page))

# End key events

gobject.type_register(Terminal)
# vim: set expandtab ts=4 sw=4:
