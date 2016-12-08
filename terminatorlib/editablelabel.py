#!/usr/bin/env python2
# vim: tabstop=4 softtabstop=4 shiftwidth=4 expandtab
#
# Copyright (c) 2009, Emmanuel Bretelle <chantra@debuntu.org>
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, version 2 only.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 51 Franklin Street, Fifth Floor
#    , Boston, MA  02110-1301  USA

""" Editable Label class"""
from gi.repository import GLib, GObject, Gtk, Gdk

class EditableLabel(Gtk.EventBox):
    # pylint: disable-msg=W0212
    # pylint: disable-msg=R0904
    """
    An eventbox that partialy emulate a Gtk.Label
    On double-click or key binding the label is editable, entering an empty
    will revert back to automatic text
    """
    _label = None
    _ebox = None
    _autotext = None
    _custom = None
    _entry = None
    _entry_handler_id = None

    __gsignals__ = {
            'edit-done': (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, text = ""):
        """ Class initialiser"""
        GObject.GObject.__init__(self) 

        self._entry_handler_id = []
        self._label = Gtk.Label(label=text, ellipsize='end')
        self._custom = False
        self.set_visible_window (False)
        self.add (self._label)  
        self.connect ("button-press-event", self._on_click_text)

    def set_angle(self, angle ):
        """set angle of the label"""
        self._label.set_angle( angle )

    def editing(self):
        """Return if we are currently editing"""
        return(self._entry != None)

    def set_text(self, text, force=False):
        """set the text of the label"""
        self._autotext = text
        if not self._custom or force:
            self._label.set_text(text) 

    def get_text(self):
        """get the text from the label"""
        return(self._label.get_text())

    def edit(self):
        """ Start editing the widget text """
        if self._entry:
            return False
        self.remove (self._label)
        self._entry = Gtk.Entry ()
        self._entry.set_text (self._label.get_text ())
        self._entry.show ()
        self.add (self._entry)
        sig = self._entry.connect ("focus-out-event", self._entry_to_label)
        self._entry_handler_id.append(sig)
        sig = self._entry.connect ("activate", self._on_entry_activated)
        self._entry_handler_id.append(sig)
        sig = self._entry.connect ("key-press-event",
                                     self._on_entry_keypress)
        self._entry_handler_id.append(sig)
        sig = self._entry.connect("button-press-event",
                                  self._on_entry_buttonpress)
        self._entry_handler_id.append(sig)
        self._entry.grab_focus ()

    def _on_click_text(self, widget, event):
        # pylint: disable-msg=W0613
        """event handling text edition"""
        if event.button != 1:
            return False
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            self.edit()
            return(True)
        return(False)

    def _entry_to_label (self, widget, event):
        # pylint: disable-msg=W0613
        """replace Gtk.Entry by the Gtk.Label"""
        if self._entry and self._entry in self.get_children():
            #disconnect signals to avoid segfault :s
            for sig in self._entry_handler_id:
                if self._entry.handler_is_connected(sig):
                    self._entry.disconnect(sig)
            self._entry_handler_id = []
            self.remove (self._entry)
            self.add (self._label)
            self._entry = None
            self.show_all ()
            self.emit('edit-done')
            return(True)
        return(False)

    def _on_entry_activated (self, widget):
        # pylint: disable-msg=W0613
        """get the text entered in Gtk.Entry"""
        entry = self._entry.get_text ()
        label = self._label.get_text ()
        if entry == '':
            self._custom = False
            self.set_text (self._autotext)
        elif entry != label:
            self._custom = True
            self._label.set_text (entry)
        self._entry_to_label (None, None)

    def _on_entry_keypress (self, widget, event):
        # pylint: disable-msg=W0613
        """handle keypressed in Gtk.Entry"""
        key = Gdk.keyval_name (event.keyval)
        if key == 'Escape':
            self._entry_to_label (None, None)

    def _on_entry_buttonpress (self, widget, event):
        """handle button events in Gtk.Entry."""
        # Block right clicks to avoid a deadlock.
        # The correct solution here would be for _entry_to_label to trigger a
        # deferred execution handler and for that handler to check if focus is
        # in a GtkMenu. The problem being that we are unable to get a context
        # menu for the GtkEntry.
        if event.button == 3:
            return True

    def modify_fg(self, state, color):
        """Set the label foreground"""
        self._label.modify_fg(state, color)

    def is_custom(self):
        """Return whether or not we have a custom string set"""
        return(self._custom)

    def set_custom(self):
        """Set the customness of the string to True"""
        self._custom = True

    def modify_font(self, fontdesc):
        """Set the label font using a pango.FontDescription"""
        self._label.modify_font(fontdesc)

GObject.type_register(EditableLabel)
