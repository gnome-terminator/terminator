#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""ipc.py - DBus server and API calls"""

import gtk
import dbus.service
from dbus.exceptions import DBusException
import dbus.glib
from borg import Borg
from terminator import Terminator
from config import Config
from factory import Factory
from util import dbg

CONFIG = Config()
if not CONFIG['dbus']:
    # The config says we are not to load dbus, so pretend like we can't
    dbg('dbus disabled')
    raise ImportError

BUS_BASE = 'net.tenshu.Terminator'
BUS_PATH = '/net/tenshu/Terminator'
try:
    # Try and include the X11 display name in the dbus bus name
    DISPLAY  = hex(hash(gtk.gdk.get_display())).replace('-', '_')
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
            bus = dbus.SessionBus()
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
    def hsplit(self, uuid=None):
        """Split a terminal horizontally, by UUID"""
        return self.new_terminal(uuid, 'hsplit')

    @dbus.service.method(BUS_NAME)
    def vsplit(self, uuid=None):
        """Split a terminal vertically, by UUID"""
        return self.new_terminal(uuid, 'vsplit')

    def new_terminal(self, uuid, type):
        """Split a terminal horizontally or vertically, by UUID"""
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
    def get_terminal_tab(self, uuid):
        """Return the UUID of the parent tab of a given terminal"""
        maker = Factory()
        terminal = self.terminator.find_terminal_by_uuid(uuid)
        window = terminal.get_toplevel()
        root_widget = window.get_children()[0]
        if maker.isinstance(root_widget, 'Notebook'):
            return root_widget.uuid.urn

    @dbus.service.method(BUS_NAME)
    def get_terminal_tab_title(self, uuid):
        """Return the title of a parent tab of a given terminal"""
        maker = Factory()
        terminal = self.terminator.find_terminal_by_uuid(uuid)
        window = terminal.get_toplevel()
        root_widget = window.get_children()[0]
        if maker.isinstance(root_widget, "Notebook"):
            return root_widget.get_tab_label(terminal).get_label()

def with_proxy(func):
    """Decorator function to connect to the session dbus bus"""
    dbg('dbus client call: %s' % func.func_name)
    def _exec(*args, **argd):
        bus = dbus.SessionBus()
        proxy = bus.get_object(BUS_NAME, BUS_PATH)
        func(proxy, *args, **argd)
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
def new_window(session, options):
    """Call the dbus method to open a new window"""
    print session.new_window()

@with_proxy
def new_tab(session, uuid, options):
    """Call the dbus method to open a new tab in the first window"""
    print session.new_tab(uuid)

@with_proxy
def hsplit(session, uuid, options):
    """Call the dbus method to horizontally split a terminal"""
    print session.hsplit(uuid)

@with_proxy
def vsplit(session, uuid, options):
    """Call the dbus method to vertically split a terminal"""
    print session.vsplit(uuid)

@with_proxy
def get_terminals(session, options):
    """Call the dbus method to return a list of all terminals"""
    print '\n'.join(session.get_terminals())

@with_proxy
def get_window(session, uuid, options):
    """Call the dbus method to return the toplevel tab for a terminal"""
    print session.get_window(uuid)

@with_proxy
def get_window_title(session, uuid, options):
    """Call the dbus method to return the title of a tab"""
    print session.get_window_title(uuid)

@with_proxy
def get_tab(session, uuid, options):
    """Call the dbus method to return the toplevel tab for a terminal"""
    print session.get_tab(uuid)

@with_proxy
def get_tab_title(session, uuid, options):
    """Call the dbus method to return the title of a tab"""
    print session.get_tab_title(uuid)

