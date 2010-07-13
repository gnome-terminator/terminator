#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""activitywatch.py - Terminator Plugin to watch a terminal for activity"""

import time
import gtk

import terminatorlib.plugin as plugin
from terminatorlib.translation import _
from terminatorlib.util import err
from terminatorlib.version import APP_NAME

try:
    import pynotify
    # Every plugin you want Terminator to load *must* be listed in 'AVAILABLE'
    # This is inside this try so we only make the plugin available if pynotify
    #  is present on this computer.
    AVAILABLE = ['ActivityWatch']
except ImportError:
    err(_('ActivityWatch plugin unavailable: please install python-notify'))

class ActivityWatch(plugin.MenuItem):
    """Add custom commands to the terminal menu"""
    capabilities = ['terminal_menu']
    watches = None
    last_notifies = None

    def __init__(self):
        plugin.MenuItem.__init__(self)
        if not self.watches:
            self.watches = {}
        if not self.last_notifies:
            self.last_notifies = {}

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

        return(True)
