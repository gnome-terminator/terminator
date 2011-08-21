#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""activitywatch.py - Terminator Plugin to watch a terminal for activity"""

import time
import gtk
import gobject

import terminatorlib.plugin as plugin
from terminatorlib.translation import _
from terminatorlib.util import err, dbg
from terminatorlib.version import APP_NAME

try:
    import pynotify
    # Every plugin you want Terminator to load *must* be listed in 'AVAILABLE'
    # This is inside this try so we only make the plugin available if pynotify
    #  is present on this computer.
    AVAILABLE = ['ActivityWatch', 'InactivityWatch']
except ImportError:
    err(_('ActivityWatch plugin unavailable: please install python-notify'))

class ActivityWatch(plugin.MenuItem):
    """Add custom commands to the terminal menu"""
    capabilities = ['terminal_menu']
    watches = None
    last_notifies = None
    timers = None

    def __init__(self):
        plugin.MenuItem.__init__(self)
        if not self.watches:
            self.watches = {}
        if not self.last_notifies:
            self.last_notifies = {}
        if not self.timers:
            self.timers = {}

        pynotify.init(APP_NAME.capitalize())

    def callback(self, menuitems, menu, terminal):
        """Add our menu items to the menu"""
        if not self.watches.has_key(terminal):
            item = gtk.MenuItem(_('Watch for activity'))
            item.connect("activate", self.watch, terminal)
        else:
            item = gtk.MenuItem(_('Stop watching for activity'))
            item.connect("activate", self.unwatch, terminal)
        menuitems.append(item)

    def watch(self, _widget, terminal):
        """Watch a terminal"""
        vte = terminal.get_vte()
        self.watches[terminal] = vte.connect('contents-changed', 
                                             self.notify, terminal)

    def unwatch(self, _widget, terminal):
        """Stop watching a terminal"""
        vte = terminal.get_vte()
        vte.disconnect(self.watches[terminal])
        del(self.watches[terminal])

    def notify(self, _vte, terminal):
        """Notify that a terminal did something"""
        show_notify = False

        # Don't notify if the user is already looking at this terminal.
        if terminal.vte.flags() & gtk.HAS_FOCUS:
            return True

        note = pynotify.Notification('Terminator', 'Activity in: %s' % 
                                  terminal.get_window_title(), 'terminator')

        this_time = time.mktime(time.gmtime())
        if not self.last_notifies.has_key(terminal):
            show_notify = True
        else:
            last_time = self.last_notifies[terminal]
            if this_time - last_time > 10:
                show_notify = True

        if show_notify == True:
            note.show()
            self.last_notifies[terminal] = this_time

        return True

class InactivityWatch(plugin.MenuItem):
    """Add custom commands to notify when a terminal goes inactive"""
    capabilities = ['terminal_menu']
    watches = None
    last_activities = None
    timers = None

    def __init__(self):
        plugin.MenuItem.__init__(self)
        if not self.watches:
            self.watches = {}
        if not self.last_activities:
            self.last_activities = {}
        if not self.timers:
            self.timers = {}

        pynotify.init(APP_NAME.capitalize())

    def callback(self, menuitems, menu, terminal):
        """Add our menu items to the menu"""
        if not self.watches.has_key(terminal):
            item = gtk.MenuItem(_("Watch for silence"))
            item.connect("activate", self.watch, terminal)
        else:
            item = gtk.MenuItem(_("Stop watching for silence"))
            item.connect("activate", self.unwatch, terminal)
        menuitems.append(item)
        dbg('Menu items appended')

    def watch(self, _widget, terminal):
        """Watch a terminal"""
        vte = terminal.get_vte()
        self.watches[terminal] = vte.connect('contents-changed',
                                             self.reset_timer, terminal)
        timeout_id = gobject.timeout_add(5000, self.check_times, terminal)
        self.timers[terminal] = timeout_id
        dbg('timer %s added for %s' %(timeout_id, terminal))

    def unwatch(self, _vte, terminal):
        """Unwatch a terminal"""
        vte = terminal.get_vte()
        vte.disconnect(self.watches[terminal])
        del(self.watches[terminal])
        gobject.source_remove(self.timers[terminal])
        del(self.timers[terminal])

    def reset_timer(self, _vte, terminal):
        """Reset the last-changed time for a terminal"""
        time_now = time.mktime(time.gmtime())
        self.last_activities[terminal] = time_now
        dbg('reset activity time for %s' % terminal)

    def check_times(self, terminal):
        """Check if this terminal has gone silent"""
        time_now = time.mktime(time.gmtime())
        if not self.last_activities.has_key(terminal):
            dbg('Terminal %s has no last activity' % terminal)
            return True

        dbg('seconds since last activity: %f (%s)' % (time_now - self.last_activities[terminal], terminal))
        if time_now - self.last_activities[terminal] >= 10.0:
            del(self.last_activities[terminal])
            note = pynotify.Notification('Terminator', 'Silence in: %s' % 
                                         terminal.get_window_title(), 'terminator')
            note.show()

        return True
