# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""ipc.py - DBus server and API calls"""

import sys
import hashlib
from gi.repository import Gdk
import dbus.service
from dbus.exceptions import DBusException
import dbus.glib
from .borg import Borg
from .terminator import Terminator
from .config import Config
from .factory import Factory
from .util import dbg, err, enumerate_descendants
from .terminal import Terminal
from .container import Container
from .configjson import ConfigJson
from gi.repository import Gtk as gtk
from gi.repository import GObject as gobject

CONFIG = Config()
if not CONFIG['dbus']:
    # The config says we are not to load dbus, so pretend like we can't
    dbg('dbus disabled')
    raise ImportError

BUS_BASE = 'net.tenshu.Terminator2'
BUS_PATH = '/net/tenshu/Terminator2'
try:
    # Try and include the X11 display name in the dbus bus name
    DISPLAY = Gdk.get_display().partition('.')[0]
    # In Python 3, hash() uses a different seed on each run, so use hashlib
    DISPLAY = hashlib.md5(DISPLAY.encode('utf-8')).hexdigest()
    BUS_NAME = '%s%s' % (BUS_BASE, DISPLAY)
except:
    BUS_NAME = BUS_BASE

class DBusService(Borg, dbus.service.Object):
    """DBus Server class. This is implemented as a Borg"""
    bus_name = None
    bus_path = None
    terminator = None

    def __init__(self):
        """Class initialiser"""
        Borg.__init__(self, self.__class__.__name__)
        self.prepare_attributes()
        dbus.service.Object.__init__(self, self.bus_name, BUS_PATH)

    def prepare_attributes(self):
        """Ensure we are populated"""
        if not self.bus_name:
            dbg('Checking for bus name availability: %s' % BUS_NAME)
            try:
                bus = dbus.SessionBus()
            except Exception as e:
                err('Unable to connect to DBUS Server, proceeding as standalone')
                raise ImportError
            proxy = bus.get_object('org.freedesktop.DBus',
                                   '/org/freedesktop/DBus')
            flags = 1 | 4 # allow replacement | do not queue
            if not proxy.RequestName(BUS_NAME, dbus.UInt32(flags)) in (1, 4):
                dbg('bus name unavailable: %s' % BUS_NAME)
                raise dbus.exceptions.DBusException(
                    "Couldn't get DBus name %s: Name exists" % BUS_NAME)
            self.bus_name = dbus.service.BusName(BUS_NAME,
                                                 bus=dbus.SessionBus())
        if not self.bus_path:
            self.bus_path = BUS_PATH
        if not self.terminator:
            self.terminator = Terminator()

    @dbus.service.method(BUS_NAME, in_signature='a{ss}')
    def new_window_cmdline(self, options=dbus.Dictionary()):
        """Create a new Window"""
        dbg('dbus method called: new_window with parameters %s'%(options))
        if options['configjson']:
            dbg(options['configjson'])
            configjson = ConfigJson()
            layoutname = configjson.extend_config(options['configjson'])
            if layoutname and ((not options['layout']) or options['layout'] == 'default'):
                options['layout'] = layoutname
                if not options['profile']:
                    options['profile'] = configjson.get_profile_to_use()

        oldopts = self.terminator.config.options_get()
        oldopts.__dict__ = options
        self.terminator.config.options_set(oldopts)
        self.terminator.create_layout(oldopts.layout)
        self.terminator.layout_done()

    @dbus.service.method(BUS_NAME, in_signature='a{ss}')
    def new_tab_cmdline(self, options=dbus.Dictionary()):
        """Create a new tab"""
        dbg('dbus method called: new_tab with parameters %s'%(options))
        oldopts = self.terminator.config.options_get()
        oldopts.__dict__ = options
        self.terminator.config.options_set(oldopts)
        window = self.terminator.get_windows()[0]
        window.tab_new()

    @dbus.service.method(BUS_NAME, in_signature='a{ss}')
    def unhide_cmdline(self,options=dbus.Dictionary):
        dbg('unhide_cmdline')
        for window in self.terminator.get_windows():
            if not window.get_property('visible'):
                window.on_hide_window()

    @dbus.service.method(BUS_NAME)
    def new_window(self):
        """Create a new Window"""
        terminals_before = set(self.get_terminals())
        self.terminator.new_window()
        terminals_after = set(self.get_terminals())
        new_terminal_set = list(terminals_after - terminals_before)
        if len(new_terminal_set) != 1:
            return "ERROR: Cannot determine the UUID of the added terminal"
        else:
            return new_terminal_set[0]

    @dbus.service.method(BUS_NAME)
    def new_tab(self, uuid=None):
        """Create a new tab"""
        return self.new_terminal(uuid, 'tab')

    @dbus.service.method(BUS_NAME) 
    def bg_img_all (self,options=dbus.Dictionary()):
        for terminal in self.terminator.terminals:
            terminal.set_background_image(options.get('file')) 
            
    @dbus.service.method(BUS_NAME) 
    def bg_img(self,uuid=None,options=dbus.Dictionary()):
        self.terminator.find_terminal_by_uuid(uuid).set_background_image(options.get('file'))

    @dbus.service.method(BUS_NAME)
    def hsplit(self, uuid=None,options=None):
        """Split a terminal horizontally, by UUID"""
        if options:
            cmd = options.get('execute')
            title = options.get('title')
            return self.new_terminal_cmd(uuid=uuid, title=title, cmd=cmd, split_vert=True) 
        else:
            return self.new_terminal(uuid, 'hsplit')

    @dbus.service.method(BUS_NAME)
    def vsplit(self, uuid=None,options=None):
        """Split a terminal vertically, by UUID"""
        if options:
            cmd = options.get('execute')
            title = options.get('title')
            return self.new_terminal_cmd(uuid=uuid, title=title, cmd=cmd, split_vert=False) 
        else:
            return self.new_terminal(uuid, 'vsplit')

    def get_terminal_container(self, terminal, container=None):
        terminator = Terminator()
        if not container:
            for window in terminator.windows:
                owner = self.get_terminal_container(terminal, window)
                if owner: return owner
        else:
            for child in container.get_children():
                if isinstance(child, Terminal) and child == terminal:
                    return container
                if isinstance(child, Container):
                    owner = self.get_terminal_container(terminal, child)
                    if owner: return owner

    def new_terminal_cmd(self, uuid=None, title=None, cmd=None, split_vert=False):
        """Split a terminal by UUID and immediately runs the specified command in the new terminal"""
        if not uuid:
            return "ERROR: No UUID specified"

        terminal = self.terminator.find_terminal_by_uuid(uuid)

        terminals_before = set(self.get_terminals())
        if not terminal:
            return "ERROR: Terminal with supplied UUID not found"

        # get current working dir out of target terminal
        cwd = terminal.get_cwd()

        # get current container
        container = self.get_terminal_container(terminal)
        maker = Factory()
        sibling = maker.make('Terminal')
        sibling.set_cwd(cwd)
        if title: sibling.titlebar.set_custom_string(title)
        sibling.spawn_child(init_command=cmd)

        # split and run command in new terminal
        container.split_axis(terminal, split_vert, cwd, sibling)

        terminals_after = set(self.get_terminals())
        # Detect the new terminal UUID
        new_terminal_set = list(terminals_after - terminals_before)
        if len(new_terminal_set) != 1:
            return "ERROR: Cannot determine the UUID of the added terminal"
        else:
            return new_terminal_set[0]

    def new_terminal(self, uuid, type):
        """Split a terminal horizontally o?r vertically, by UUID"""
        dbg('dbus method called: %s' % type)
        if not uuid:
            return "ERROR: No UUID specified"
        terminal = self.terminator.find_terminal_by_uuid(uuid)
        terminals_before = set(self.get_terminals())
        if not terminal:
            return "ERROR: Terminal with supplied UUID not found"
        elif type == 'tab':
            terminal.key_new_tab()
        elif type == 'hsplit':
            terminal.key_split_horiz()
        elif type == 'vsplit':
            terminal.key_split_vert()
        else:
            return "ERROR: Unknown type \"%s\" specified" % (type)
        terminals_after = set(self.get_terminals())
        # Detect the new terminal UUID
        new_terminal_set = list(terminals_after - terminals_before)
        if len(new_terminal_set) != 1:
            return "ERROR: Cannot determine the UUID of the added terminal"
        else:
            return new_terminal_set[0]

    @dbus.service.method(BUS_NAME)
    def get_terminals(self):
        """Return a list of all the terminals"""
        return [x.uuid.urn for x in self.terminator.terminals]

    @dbus.service.method(BUS_NAME)
    def get_focused_terminal(self):
        """Returns the uuid of the currently focused terminal"""
        if self.terminator.last_focused_term:
            return self.terminator.last_focused_term.uuid.urn
        return None

    @dbus.service.method(BUS_NAME)
    def get_window(self, uuid=None):
        """Return the UUID of the parent window of a given terminal"""
        terminal = self.terminator.find_terminal_by_uuid(uuid)
        window = terminal.get_toplevel()
        return window.uuid.urn

    @dbus.service.method(BUS_NAME)
    def get_window_title(self, uuid=None):
        """Return the title of a parent window of a given terminal"""
        terminal = self.terminator.find_terminal_by_uuid(uuid)
        window = terminal.get_toplevel()
        return window.get_title()

    @dbus.service.method(BUS_NAME)
    def get_tab(self, uuid=None):
        """Return the UUID of the parent tab of a given terminal"""
        maker = Factory()
        terminal = self.terminator.find_terminal_by_uuid(uuid)
        window = terminal.get_toplevel()
        root_widget = window.get_children()[0]
        if maker.isinstance(root_widget, 'Notebook'):
            #return root_widget.uuid.urn
            for tab_child in root_widget.get_children():
                terms = [tab_child]
                if not maker.isinstance(terms[0], "Terminal"):
                    terms = enumerate_descendants(tab_child)[1]
                if terminal in terms:
                    # FIXME: There are no uuid's assigned to the the notebook, or the actual tabs!
                    # This would fail: return root_widget.uuid.urn
                    return ""

    @dbus.service.method(BUS_NAME)
    def get_tab_title(self, uuid=None):
        """Return the title of a parent tab of a given terminal"""
        maker = Factory()
        terminal = self.terminator.find_terminal_by_uuid(uuid)
        window = terminal.get_toplevel()
        root_widget = window.get_children()[0]
        if maker.isinstance(root_widget, "Notebook"):
            for tab_child in root_widget.get_children():
                terms = [tab_child]
                if not maker.isinstance(terms[0], "Terminal"):
                    terms = enumerate_descendants(tab_child)[1]
                if terminal in terms:
                    return root_widget.get_tab_label(tab_child).get_label()

    @dbus.service.method(BUS_NAME)
    def set_tab_title(self, uuid=None, options=dbus.Dictionary()):
        """Set the title of a parent tab of a given terminal"""
        tab_title = options.get('tab-title')

        maker = Factory()
        terminal = self.terminator.find_terminal_by_uuid(uuid)
        window = terminal.get_toplevel()

        if not window.is_child_notebook():
            return

        notebook = window.get_children()[0]
        n_page = notebook.get_current_page()
        page = notebook.get_nth_page(n_page)
        label = notebook.get_tab_label(page)
        label.set_custom_label(tab_title, force=True)

    @dbus.service.method(BUS_NAME)
    def switch_profile(self, uuid=None, options=dbus.Dictionary()):
        """Switch profile of a given terminal"""
        terminal = self.terminator.find_terminal_by_uuid(uuid)
        profile_name = options.get('profile')
        terminal.force_set_profile(False, profile_name)

    @dbus.service.method(BUS_NAME)
    def switch_profile_all(self, options=dbus.Dictionary()):
        """Switch profile of a given terminal"""
        for terminal in self.terminator.terminals:
            profile_name = options.get('profile')
            terminal.force_set_profile(False, profile_name)


def with_proxy(func):
    """Decorator function to connect to the session dbus bus"""
    dbg('dbus client call: %s' % func.__name__)
    def _exec(*args, **argd):
        bus = dbus.SessionBus()
        try:
            proxy = bus.get_object(BUS_NAME, BUS_PATH)

        except dbus.DBusException as e:
            sys.exit(
                "Remotinator can't connect to terminator. " +
                "May be terminator is not running.")

        return func(proxy, *args, **argd)
    return _exec

@with_proxy
def new_window_cmdline(session, options):
    """Call the dbus method to open a new window"""
    session.new_window_cmdline(options)

@with_proxy
def new_tab_cmdline(session, options):
    """Call the dbus method to open a new tab in the first window"""
    session.new_tab_cmdline(options)

@with_proxy
def unhide_cmdline(session,options):
    session.unhide_cmdline(options)

@with_proxy
def new_window(session, options):
    """Call the dbus method to open a new window"""
    print(session.new_window())

@with_proxy
def new_tab(session, uuid, options):
    """Call the dbus method to open a new tab in the first window"""
    print(session.new_tab(uuid))

@with_proxy
def hsplit(session, uuid, options):
    """Call the dbus method to horizontally split a terminal"""
    print(session.hsplit(uuid,options))

@with_proxy
def vsplit(session, uuid, options):
    """Call the dbus method to vertically split a terminal"""
    print(session.vsplit(uuid,options))

@with_proxy
def get_terminals(session, options):
    """Call the dbus method to return a list of all terminals"""
    print('\n'.join(session.get_terminals()))

@with_proxy
def get_focused_terminal(session, options):
    """Call the dbus method to return the currently focused terminal"""
    return session.get_focused_terminal()

@with_proxy
def get_window(session, uuid, options):
    """Call the dbus method to return the toplevel tab for a terminal"""
    print(session.get_window(uuid))

@with_proxy
def get_window_title(session, uuid, options):
    """Call the dbus method to return the title of a tab"""
    print(session.get_window_title(uuid))

@with_proxy
def get_tab(session, uuid, options):
    """Call the dbus method to return the toplevel tab for a terminal"""
    print(session.get_tab(uuid))

@with_proxy
def get_tab_title(session, uuid, options):
    """Call the dbus method to return the title of a tab"""
    print(session.get_tab_title(uuid))

@with_proxy
def set_tab_title(session, uuid, options):
    """Call the dbus method to set the title of a tab"""
    session.set_tab_title(uuid, options)

@with_proxy
def switch_profile(session, uuid, options):
    """Call the dbus method to return the title of a tab"""
    session.switch_profile(uuid, options)

@with_proxy
def switch_profile_all(session,options):
    """Call the dbus method to return the title of a tab"""
    session.switch_profile_all(options)

@with_proxy
def bg_img_all(session,options):
    session.bg_img_all(options)

@with_proxy
def bg_img(session,uuid,options):
    session.bg_img(uuid,options)
