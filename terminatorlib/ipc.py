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
    def new_window(self, options=dbus.Dictionary()):
        """Create a new Window"""
        dbg('dbus method called: new_window with parameters %s'%(options))
        oldopts = self.terminator.config.options_get()
        oldopts.__dict__ = options
        self.terminator.config.options_set(oldopts)
        self.terminator.create_layout(oldopts.layout)
        self.terminator.layout_done()
            
    @dbus.service.method(BUS_NAME, in_signature='a{ss}')
    def new_tab(self, options=dbus.Dictionary()):
        """Create a new tab"""
        dbg('dbus method called: new_tab with parameters %s'%(options))
        oldopts = self.terminator.config.options_get()
        oldopts.__dict__ = options
        self.terminator.config.options_set(oldopts)
        window = self.terminator.get_windows()[0]
        window.tab_new()

    @dbus.service.method(BUS_NAME)
    def terminal_hsplit(self, uuid=None):
        """Split a terminal horizontally, by UUID"""
        return self.terminal_split(uuid, True)

    @dbus.service.method(BUS_NAME)
    def terminal_vsplit(self, uuid=None):
        """Split a terminal vertically, by UUID"""
        return self.terminal_split(uuid, False)

    def terminal_split(self, uuid, horiz):
        """Split a terminal horizontally or vertically, by UUID"""
        dbg('dbus method called: terminal_hsplit')
        if not uuid:
            return "ERROR: No UUID specified"
        terminal = self.terminator.find_terminal_by_uuid(uuid)
        if not terminal:
            return "ERROR: Terminal with supplied UUID not found"
        if horiz:
            terminal.key_split_horiz()
        else:
            terminal.key_split_vert()

    @dbus.service.method(BUS_NAME)
    def get_terminals(self, uuid):
        """Return a list of all the terminals"""
        return [x.uuid.urn for x in self.terminator.terminals]

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
def new_window(session, options):
    """Call the dbus method to open a new window"""
    session.new_window(options)

@with_proxy
def new_tab(session, options):
    """Call the dbus method to open a new tab in the first window"""
    session.new_tab(options)

@with_proxy
def terminal_hsplit(session, uuid):
    """Call the dbus method to horizontally split a terminal"""
    session.terminal_hsplit(uuid)

@with_proxy
def terminal_vsplit(session, uuid):
    """Call the dbus method to vertically split a terminal"""
    print session.terminal_vsplit(uuid)

@with_proxy
def get_terminals(session, uuid):
    """Call the dbus method to return a list of all terminals"""
    print '\n'.join(session.get_terminals(uuid))

@with_proxy
def get_terminal_tab(session, uuid):
    """Call the dbus method to return the toplevel tab for a terminal"""
    print session.get_terminal_tab(uuid)

@with_proxy
def get_terminal_tab_title(session, uuid):
    """Call the dbus method to return the title of a tab"""
    print session.get_terminal_tab_title(uuid)

