#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""terminal.py - classes necessary to provide Terminal widgets"""

import pwd
import sys
import os
import pygtk
pygtk.require('2.0')
import gtk
import gobject

from util import dbg, err, gerr
from config import Config
from cwd import get_default_cwd
from newterminator import Terminator
from titlebar import Titlebar
from searchbar import Searchbar
from translation import _

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
    }

    TARGET_TYPE_VTE = 8

    terminator = None
    vte = None
    terminalbox = None
    titlebar = None
    searchbar = None

    group = None
    cwd = None
    command = None
    clipboard = None

    matches = None
    config = None
    default_encoding = None

    composite_support = None

    def __init__(self):
        """Class initialiser"""
        gtk.VBox.__init__(self)
        self.__gobject_init__()

        self.terminator = Terminator()
        self.connect('enumerate', self.terminator.do_enumerate)

        self.matches = {}

        self.config = Config()

        self.cwd = get_default_cwd()
        self.clipboard = gtk.clipboard_get(gtk.gdk.SELECTION_CLIPBOARD)

        self.vte = vte.Terminal()
        self.vte.set_size(80, 24)
        self.vte._expose_data = None
        if not hasattr(self.vte, "set_opacity") or not hasattr(self.vte,
                "is_composited"):
            self.composite_support = False
        self.vte.show()

        self.default_encoding = self.vte.get_encoding()
        self.update_url_matches(self.config['try_posix_regexp'])

        self.terminalbox = self.create_terminalbox()

        self.titlebar = Titlebar()
        self.titlebar.connect_icon(self.on_group_button_press)
        self.titlebar.connect('edit-done', self.on_edit_done)
        self.connect('title-change', self.titlebar.set_terminal_title)

        self.searchbar = Searchbar()

        self.show()
        self.pack_start(self.titlebar, False)
        self.pack_start(self.terminalbox)
        self.pack_end(self.searchbar)

        self.connect_signals()

        os.putenv('COLORTERM', 'gnome-terminal')

        env_proxy = os.getenv('http_proxy')
        if not env_proxy:
            if self.config['http_proxy'] and self.config['http_proxy'] != '':
                os.putenv('http_proxy', self.config['http_proxy'])

    def create_terminalbox(self):
        """Create a GtkHBox containing the terminal and a scrollbar"""

        terminalbox = gtk.HBox()
        scrollbar = gtk.VScrollbar(self.vte.get_adjustment())
        position = self.config['scrollbar_position']

        if position not in ('hidden', 'disabled'):
            scrollbar.show()

        if position == 'left':
            func = terminalbox.pack_end
        else:
            func = terminalbox.pack_start

        func(self.vte)
        func(scrollbar, False)
        terminalbox.show()

        return(terminalbox)

    def update_url_matches(self, posix = True):
        """Update the regexps used to match URLs"""
        userchars = "-A-Za-z0-9"
        passchars = "-A-Za-z0-9,?;.:/!%$^*&~\"#'"
        hostchars = "-A-Za-z0-9"
        pathchars = "-A-Za-z0-9_$.+!*(),;:@&=?/~#%'\""
        schemes   = "(news:|telnet:|nntp:|file:/|https?:|ftps?:|webcal:)"
        user      = "[" + userchars + "]+(:[" + passchars + "]+)?"
        urlpath   = "/[" + pathchars + "]*[^]'.}>) \t\r\n,\\\"]"

        if posix:
            dbg ('update_url_matches: Trying POSIX URL regexps')
            lboundry = "[[:<:]]"
            rboundry = "[[:>:]]"
        else: # GNU
            dbg ('update_url_matches: Trying GNU URL regexps')
            lboundry = "\\<"
            rboundry = "\\>"

        self.matches['full_uri'] = self.vte.match_add(lboundry + schemes + 
                "//(" + user + "@)?[" + hostchars  +".]+(:[0-9]+)?(" + 
                urlpath + ")?" + rboundry + "/?")

        if self.matches['full_uri'] == -1:
            if posix:
                err ('update_url_matches: POSIX match failed, trying GNU')
                self.update_url_matches(posix = False)
            else:
                err ('update_url_matches: Failed adding URL match patterns')
        else:
            self.matches['voip'] = self.vte.match_add(lboundry + 
                    '(callto:|h323:|sip:)' + "[" + userchars + "+][" + 
                    userchars + ".]*(:[0-9]+)?@?[" + pathchars + "]+" + 
                    rboundry)
            self.matches['addr_only'] = self.vte.match_add (lboundry + 
                    "(www|ftp)[" + hostchars + "]*\.[" + hostchars + 
                    ".]+(:[0-9]+)?(" + urlpath + ")?" + rboundry + "/?")
            self.matches['email'] = self.vte.match_add (lboundry + 
                    "(mailto:)?[a-zA-Z0-9][a-zA-Z0-9.+-]*@[a-zA-Z0-9]\
                            [a-zA-Z0-9-]*\.[a-zA-Z0-9][a-zA-Z0-9-]+\
                            [.a-zA-Z0-9-]*" + rboundry)
            self.matches['nntp'] = self.vte.match_add (lboundry + 
                    '''news:[-A-Z\^_a-z{|}~!"#$%&'()*+,./0-9;:=?`]+@\
                            [-A-Za-z0-9.]+(:[0-9]+)?''' + rboundry)
            # if the url looks like a Launchpad changelog closure entry 
            # LP: #92953 - make it a url to http://bugs.launchpad.net
            self.matches['launchpad'] = self.vte.match_add (
                    '\\bLP:? #?[0-9]+\\b')

    def connect_signals(self):
        """Connect all the gtk signals and drag-n-drop mechanics"""

        self.vte.connect('key-press-event', self.on_keypress)
        self.vte.connect('button-press-event', self.on_buttonpress)
        self.vte.connect('popup-menu', self.popup_menu)

        srcvtetargets = [("vte", gtk.TARGET_SAME_APP, self.TARGET_TYPE_VTE)]
        dsttargets = [("vte", gtk.TARGET_SAME_APP, self.TARGET_TYPE_VTE), 
                ('text/plain', 0, 0), ('STRING', 0, 0), ('COMPOUND_TEXT', 0, 0)]

        for (widget, mask) in [
            (self.vte, gtk.gdk.CONTROL_MASK | gtk.gdk.BUTTON3_MASK), 
            (self.titlebar, gtk.gdk.CONTROL_MASK)]:
            widget.drag_source_set(mask, srcvtetargets, gtk.gdk.ACTION_MOVE)

        self.vte.drag_dest_set(gtk.DEST_DEFAULT_MOTION |
                gtk.DEST_DEFAULT_HIGHLIGHT | gtk.DEST_DEFAULT_DROP,
                dsttargets, gtk.gdk.ACTION_MOVE)

        for widget in [self.vte, self.titlebar]:
            widget.connect('drag-begin', self.on_drag_begin, self)
            widget.connect('drag-data-get', self.on_drag_data_get,
            self)

        self.vte.connect('drag-motion', self.on_drag_motion, self)
        self.vte.connect('drag-data-received',
            self.on_drag_data_received, self)

        if self.config['copy_on_selection']:
            self.vte.connect('selection-changed', lambda widget:
                self.vte.copy_clipboard())

        if self.composite_support:
            self.vte.connect('composited-changed',
                self.on_composited_changed)

        self.vte.connect('window-title-changed',
            self.on_vte_title_change)
        self.vte.connect('grab-focus', self.on_vte_focus)
        self.vte.connect('focus-out-event', self.on_vte_focus_out)
        self.vte.connect('focus-in-event', self.on_vte_focus_in)
        self.vte.connect('resize-window', self.on_resize_window)
        self.vte.connect('size-allocate', self.on_vte_size_allocate)

        if self.config['exit_action'] == 'restart':
            self.vte.connect('child-exited', self.spawn_child)
        elif self.config['exit_action'] in ('close', 'left'):
            self.vte.connect('child-exited', self.close_term)

        self.vte.add_events(gtk.gdk.ENTER_NOTIFY_MASK)
        self.vte.connect('enter_notify_event',
            self.on_vte_notify_enter)

        self.vte.connect_after('realize', self.reconfigure)
        self.vte.connect_after('realize', self.spawn_child)

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

        item = gtk.MenuItem(_('Assign to group...'))
        item.connect('activate', self.create_group)
        menu.append(item)
       
        if len(self.terminator.groups) > 0:
            groupitem = gtk.RadioMenuItem(groupitem, _('None'))
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

        # FIXME: Functions to group/ungroup all terms in current tab

        if len(self.terminator.groups) > 0:
            item = gtk.MenuItem(_('Remove all groups'))
            item.connect('activate', self.ungroup_all) # FIXME: ungroup_all should be in Terminator() ?
            menu.append(item)

        if self.group != None:
            menu.append(gtk.MenuItem())

            item = gtk.MenuItem(_('Close group %s') % self.group)
            item.connect('activate', lambda menu_item:
                    self.terminator.closegroupedterms(self))
            menu.append(item)

        menu.append(gtk.MenuItem())

        groupitem = None

        for key,value in {_('Broadcast off'):'off', 
                          _('Broadcast group'):'group',
                          _('Broadcast all'):'all'}.items():
            groupitem = gtk.RadioMenuItem(groupitem, key)
            groupitem.set_active(self.terminator.groupsend ==
                    self.terminator.groupsend_type[value])
            groupitem.connect('activate', self.set_groupsend,
                    self.terminator.groupsend_type[value])
            menu.append(groupitem)

        menu.append(gtk.MenuItem())

        item = gtk.CheckMenuItem(_('Split to this group'))
        item.set_active(self.terminator.splittogroup)
        item.connect('toggled', lambda menu_item: self.do_splittogroup_toggle())
        menu.append(item)

        item = gtk.CheckMenuItem(_('Autoclean groups'))
        item.set_active(self.terminator.autocleangroups)
        item.connect('toggled', lambda menu_item:
                self.do_autocleangroups_toggle())
        menu.append(item)

        menu.append(gtk.MenuItem())

        item = gtk.MenuItem(_('Insert terminal number'))
        item.connect('activate', lambda menu_item: self.emit('enumerate', False))
        menu.append(item)

        item = gtk.MenuItem(_('Insert padded terminal number'))
        item.connect('activate', lambda menu_item: self.emit('enumerate', True))
        menu.append(item)

        return(menu)

    def position_popup_group_menu(self, menu, widget):
        """Calculate the position of the group popup menu"""
        screen_w = gtk.gdk.screen_width()
        screen_h = gtk.gdk.screen_height()

        widget_win = widget.get_window()
        widget_x, widget_y = widget_win.get_origin()
        widget_w, widget_h = widget_win.get_size()

        menu_w, menu_h = menu.size_request()

        if widget_y + widget_h + menu_h > screen_h:
            menu_y = max(widget_y - menu_h, 0)
        else:
            menu_y = widget_y + widget_h

        return(widget_x, menu_y, 1)

    def create_group(self, item):
        """Create a new group"""
        pass

    def set_groupsend(self, widget, value):
        """Set the groupsend mode"""
        # FIXME: Can we think of a smarter way of doing this than poking?
        self.terminator.groupsend = value

    def do_splittogroup_toggle(self):
        """Toggle the splittogroup mode"""
        # FIXME: Can we think of a smarter way of doing this than poking?
        self.terminator.splittogroup = not self.terminator.splittogroup

    def do_autocleangroups_toggle(self):
        """Toggle the autocleangroups mode"""
        # FIXME: Can we think of a smarter way of doing this than poking?
        self.terminator.autocleangroups = not self.terminator.autocleangroups

    def reconfigure(self, widget=None):
        """Reconfigure our settings"""
        pass

    def get_window_title(self):
        """Return the window title"""
        return(self.vte.get_window_title() or str(self.command))

    def on_group_button_press(self, widget, event):
        """Handler for the group button"""
        if event.button == 1:
            self.create_popup_group_menu(widget, event)
        return(False)

    def on_keypress(self, vte, event):
        """Handler for keyboard events"""
        pass

    def on_buttonpress(self, vte, event):
        """Handler for mouse events"""
        # Any button event should grab focus
        self.vte.grab_focus()

        if event.button == 1:
            # Ctrl+leftclick on a URL should open it
            if event.state & gtk.gdk.CONTROL_MASK == gtk.gdk.CONTROL_MASK:
                url = self.check_for_url(event)
                if url:
                    self.open_url(url, prepare=True)
        elif event.button == 2:
            # middleclick should paste the clipboard
            self.paste_clipboard(True)
            return(True)
        elif event.button == 3:
            # rightclick should display a context menu if Ctrl is not pressed
            if event.state & gtk.gdk.CONTROL_MASK == 0:
                self.popup_menu(self.vte, event)
                return(True)

        return(False)
    
    def popup_menu(self, widget, event=None):
        """Display the context menu"""

        pass

    def on_drag_begin(self, widget, drag_context, data):
        pass

    def on_drag_data_get(self, widget, drag_context, selection_data, info, time,
            data):
        pass

    def on_drag_motion(self, widget, drag_context, x, y, time, data):
        pass

    def on_drag_data_received(self, widget, drag_context, x, y, selection_data,
            info, time, data):
        pass

    def on_vte_title_change(self, vte):
        self.emit('title-change', self.get_window_title())

    def on_vte_focus(self, vte):
        pass

    def on_vte_focus_out(self, vte, event):
        pass

    def on_vte_focus_in(self, vte, event):
        pass

    def on_edit_done(self, widget):
        """A child widget is done editing a label, return focus to VTE"""
        self.vte.grab_focus()

    def on_resize_window(self):
        pass

    def on_vte_size_allocate(self, widget, allocation):
        self.titlebar.update_terminal_size(self.vte.get_column_count(),
                self.vte.get_row_count())
        pass

    def on_vte_notify_enter(self, term, event):
        pass

    def close_term(self, widget):
        self.emit('close-term')

    def hide_titlebar(self):
        self.titlebar.hide()

    def show_titlebar(self):
        self.titlebar.show()

    def spawn_child(self, widget=None):
        update_records = self.config['update_records']
        login = self.config['login_shell']
        args = []
        shell = None
        command = None

        if self.config['use_custom_command']:
            command = self.config['custom_command']

        shell = self.shell_lookup()

        if self.config['login_shell']:
            args.insert(0, "-%s" % shell)
        else:
            args.insert(0, shell)

        if command is not None:
            args += ['-c', command]

        if shell is None:
            self.vte.feed(_('Unable to find a shell'))
            return(-1)

        os.putenv('WINDOWID', '%s' % self.vte.get_parent_window().xid)

        self.pid = self.vte.fork_command(command=shell, argv=args, envv=[],
                loglastlog=login, logwtmp=update_records,
                logutmp=update_records, directory=self.cwd)
        self.command = shell

        self.on_vte_title_change(self.vte)
        self.titlebar.update()

        if self.pid == -1:
            self.vte.feed(_('Unable to start shell:') + shell)
            return(-1)

    def shell_lookup(self):
        """Find an appropriate shell for the user"""
        shells = [os.getenv('SHELL'), pwd.getpwuid(os.getuid())[6], 'bash',
                'zsh', 'tcsh', 'ksh', 'csh', 'sh']

        for shell in shells:
            if shell is None: continue
            elif os.path.isfile(shell):
                return(shell)
            else:
                rshell = self.path_lookup(shell)
                if rshell is not None:
                    dbg('shell_lookup: Found %s at %s' % (shell, rshell))
                    return(rshell)
        dbg('shell_lookup: Unable to locate a shell')

    def path_lookup(self, command):
        if os.path.isabs(command):
            if os.path.isfile(command):
                return(command)
            else:
                return(None)
        elif command[:2] == './' and os.path.isfile(command):
            dbg('path_lookup: Relative filename %s found in cwd' % command)
            return(command)

        try:
            paths = os.environ['PATH'].split(':')
            if len(paths[0]) == 0: raise(ValueError)
        except (ValueError, NameError):
            dbg('path_lookup: PATH not set in environment, using fallbacks')
            paths = ['/usr/local/bin', '/usr/bin', '/bin']

        dbg('path_lookup: Using %d paths: %s', (len(paths), paths))

        for path in paths:
            target = os.path.join(path, command)
            if os.path.isfile(target):
                dbg('path_lookup: found %s' % target)
                return(target)

        dbg('path_lookup: Unable to locate %s' % command)

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
        elif match == self.matches['launchpad']:
            for item in re.findall(r'[0-9]+', url):
                url = 'https://bugs.launchpad.net/bugs/%s' % item
                return(url)
        else:
            return(url)

    def open_url(self, url, prepare=False):
        """Open a given URL, conditionally unpacking it from a VTE match"""
        if prepare == True:
            url = self.prepare_url(url)
        dbg('open_url: URL: %s (prepared: %s)' % (url, prepare))
        try:
            subprocess.Popen(['xdg-open', url])
        except OSError:
            dbg('open_url: xdg-open failed')
            try:
                self.terminator.url_show(url)
            except:
                dbg('open_url: url_show failed. Giving up')
                pass

    def paste_clipboard(self, primary=False):
        """Paste one of the two clipboards"""
        for term in self.terminator.get_target_terms():
            if primary:
                term.vte.paste_primary()
            else:
                term.vte.paste_clipboard()
        self.vte.grab_focus()

    def feed(self, text):
        """Feed the supplied text to VTE"""
        self.vte.feed_child(text)

gobject.type_register(Terminal)
# vim: set expandtab ts=4 sw=4:
