#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""Simple management of Gtk Widget signal handlers"""

from util import dbg, err

class Signalman(object):
    """Class providing glib signal tracking and management"""

    cnxids = None

    def __init__(self):
        """Class initialiser"""
        self.cnxids = {}

    def __del__(self):
        """Class destructor. This is only used to check for stray signals"""
        if len(self.cnxids.keys()) > 0:
            dbg('Remaining signals: %s' % self.cnxids)

    def new(self, widget, signal, handler, *args):
        """Register a new signal on a widget"""
        if not self.cnxids.has_key(widget):
            dbg('creating new bucket for %s' % type(widget))
            self.cnxids[widget] = {}

        if self.cnxids[widget].has_key(signal):
            err('%s already has a handler for %s' % (id(widget), signal))

        self.cnxids[widget][signal] = widget.connect(signal, handler, *args)
        dbg('connected %s::%s to %s' % (type(widget), signal, handler))
        return(self.cnxids[widget][signal])

    def remove_signal(self, widget, signal):
        """Remove a signal handler"""
        if not self.cnxids.has_key(widget):
            dbg('%s is not registered' % widget)
            return
        if not self.cnxids[widget].has_key(signal):
            dbg('%s not registered for %s' % (signal, type(widget)))
            return
        dbg('removing %s::%s' % (type(widget), signal))
        widget.disconnect(self.cnxids[widget][signal])
        del(self.cnxids[widget][signal])
        if len(self.cnxids[widget].keys()) == 0:
            dbg('no more signals for widget')
            del(self.cnxids[widget])

    def remove_widget(self, widget):
        """Remove all signal handlers for a widget"""
        if not self.cnxids.has_key(widget):
            dbg('%s not registered' % widget)
            return
        signals = self.cnxids[widget].keys()
        for signal in signals:
            self.remove_signal(widget, signal)

    def remove_all(self):
        """Remove all signal handlers for all widgets"""
        widgets = self.cnxids.keys()
        for widget in widgets:
            self.remove_widget(widget)

