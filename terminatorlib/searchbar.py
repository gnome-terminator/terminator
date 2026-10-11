# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""searchbar.py - Find dialog for a terminal's scrollback"""

import re

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')  # vte-0.38 (gnome-3.14)
from gi.repository import Gtk, Gdk, Vte, GObject, GLib

from .translation import _
from .config import Config
from . import regex
from .util import dbg


def build_search_pattern(text, whole_word, as_regex):
    """Turn the Find entry into a VTE search pattern.

    With *as_regex* off the text is matched literally. *whole_word* adds
    a word boundary on each side. An empty entry is not a pattern.
    """
    if not text:
        return None
    if as_regex:
        body = text
    else:
        body = re.escape(text)
    if whole_word:
        return '\\b(?:%s)\\b' % body
    return body


class Searchbar(GObject.GObject):
    """Find dialog. Ctrl+Shift+F opens it; Escape or the close button ends it."""

    __gsignals__ = {
        'end-search': (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, terminal):
        GObject.GObject.__init__(self)
        self.terminal = terminal
        self.vte = None
        self.dialog = None
        self.config = Config()
        self._last = ''
        self._closing = False
        self.regex_flags_pcre2 = regex.FLAGS_PCRE2
        self.regex_flags_glib = regex.FLAGS_GLIB

    def hide(self):
        if self.dialog is not None:
            self.dialog.hide()

    def start_search(self):
        """Present the Find dialog for this terminal."""
        if self.vte is None:
            self.vte = self.terminal.vte
        self._ensure_dialog()
        parent = self.terminal.get_toplevel()
        if isinstance(parent, Gtk.Window):
            self.dialog.set_transient_for(parent)
        self.dialog.present()
        self.entry.grab_focus()
        self.entry.select_region(0, -1)

    def end_search(self, widget=None):
        """Hide the dialog, drop the highlight, and tell the terminal."""
        if self._closing:
            return
        self._closing = True
        try:
            self._clear_highlight()
            self.hide()
            self._last = ''
            self.emit('end-search')
        finally:
            self._closing = False

    def _ensure_dialog(self):
        if self.dialog is not None:
            return
        dialog = Gtk.Dialog(title=_('Find'), use_header_bar=True)
        dialog.set_destroy_with_parent(True)
        dialog.set_modal(False)
        dialog.set_resizable(False)
        dialog.set_default_size(380, -1)
        dialog.connect('delete-event', self._on_delete)
        dialog.connect('key-press-event', self._on_dialog_key)

        area = dialog.get_content_area()
        area.set_border_width(18)
        area.set_spacing(10)

        self.entry = Gtk.Entry()
        self.entry.set_activates_default(True)
        try:
            self.entry.set_icon_from_icon_name(
                Gtk.EntryIconPosition.PRIMARY, 'edit-find-symbolic')
        except Exception:
            pass
        self.entry.connect('changed', self._on_changed)
        self.entry.connect('activate', self._on_activate)
        self.entry.connect('key-press-event', self._on_entry_key)

        self.prev = self._arrow_button(
            'go-up-symbolic', _('Find previous'))
        self.next = self._arrow_button(
            'go-down-symbolic', _('Find next'))
        self.prev.connect('clicked', self.prev_search)
        self.next.connect('clicked', self.next_search)
        self.prev.set_sensitive(False)
        self.next.set_sensitive(False)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        row.get_style_context().add_class('linked')
        row.pack_start(self.entry, True, True, 0)
        row.pack_start(self.prev, False, False, 0)
        row.pack_start(self.next, False, False, 0)
        area.pack_start(row, False, False, 0)

        self.match_case = Gtk.CheckButton.new_with_mnemonic(_('_Match case'))
        self.whole_word = Gtk.CheckButton.new_with_mnemonic(
            _('Match _entire word'))
        self.as_regex = Gtk.CheckButton.new_with_mnemonic(
            _('Match as _regular expression'))
        self.wrap = Gtk.CheckButton.new_with_mnemonic(_('_Wrap around'))

        self.match_case.set_active(
            bool(self.config.base.get_item('case_sensitive')))
        self.whole_word.set_active(
            bool(self.config.base.get_item('search_whole_word')))
        self.as_regex.set_active(
            bool(self.config.base.get_item('search_regex')))
        wrap = self.config.base.get_item('search_wrap')
        self.wrap.set_active(True if wrap is None else bool(wrap))

        for box in (self.match_case, self.whole_word, self.as_regex, self.wrap):
            box.connect('toggled', self._on_option)
            area.pack_start(box, False, False, 0)

        area.show_all()
        self.dialog = dialog

    def _arrow_button(self, icon_name, tooltip):
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.set_focus_on_click(False)
        image = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
        button.add(image)
        button.set_tooltip_text(tooltip)
        return button

    def _on_delete(self, _dialog, _event):
        self.end_search()
        return True

    def _on_dialog_key(self, _dialog, event):
        if Gdk.keyval_name(event.keyval) == 'Escape':
            self.end_search()
            return True
        return False

    def _on_entry_key(self, _widget, event):
        if (event.state & Gdk.ModifierType.SHIFT_MASK) and \
                event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.prev_search()
            return True
        return False

    def _on_changed(self, _entry):
        self._apply(jump=False)

    def _on_activate(self, _entry):
        if self._inverted():
            self.prev_search()
        else:
            self.next_search()

    def _on_option(self, _button):
        self._save_options()
        self._last = ''
        self._apply(jump=False)

    def _save_options(self):
        base = self.config.base
        base.set_item('case_sensitive', self.match_case.get_active())
        base.set_item('search_whole_word', self.whole_word.get_active())
        base.set_item('search_regex', self.as_regex.get_active())
        base.set_item('search_wrap', self.wrap.get_active())
        self.config.save()

    def _inverted(self):
        try:
            return bool(self.config.base.get_item('invert_search'))
        except Exception:
            return False

    def _apply(self, jump):
        """Install the pattern. Jump to a hit unless the text only grew."""
        if self.vte is None:
            return
        text = self.entry.get_text()
        pattern = build_search_pattern(
            text, self.whole_word.get_active(), self.as_regex.get_active())
        try:
            self.vte.search_set_wrap_around(self.wrap.get_active())
        except Exception:
            pass
        if not pattern:
            self._clear_highlight()
            self._set_nav(False)
            self._mark_entry(False)
            self._last = ''
            return
        if not self._install_pattern(pattern):
            self._clear_highlight()
            self._set_nav(False)
            self._mark_entry(True)
            return
        self._mark_entry(False)
        self._set_nav(True)
        extended = bool(self._last) and text.startswith(self._last)
        self._last = text
        if jump or not extended:
            if self._inverted():
                self.prev_search()
            else:
                self.next_search()

    def _install_pattern(self, pattern):
        caseless = not self.match_case.get_active()
        self.searchre = None
        if regex.FLAGS_PCRE2:
            flags = regex.FLAGS_PCRE2
            if caseless:
                flags |= regex.PCRE2_CASELESS
            try:
                compiled = Vte.Regex.new_for_search(pattern, len(pattern), flags)
                self.vte.search_set_regex(compiled, 0)
                self.searchre = compiled
                return True
            except GLib.Error as error:
                dbg('PCRE2 regex error: %s' % error)
        flags = regex.FLAGS_GLIB
        if caseless:
            flags |= regex.GLIB_CASELESS
        try:
            compiled = GLib.Regex(pattern, flags, 0)
            self.vte.search_set_gregex(compiled, 0)
            self.searchre = compiled
            return True
        except GLib.Error as error:
            dbg('GLib regex error: %s' % error)
            return False

    def _mark_entry(self, invalid):
        context = self.entry.get_style_context()
        if invalid:
            context.add_class('error')
        else:
            context.remove_class('error')

    def _set_nav(self, enabled):
        self.next.set_sensitive(enabled)
        self.prev.set_sensitive(enabled)

    def _clear_highlight(self):
        if self.vte is None:
            return
        try:
            self.vte.search_set_regex(None, 0)
        except Exception:
            try:
                self.vte.search_set_gregex(None, 0)
            except Exception:
                pass

    def next_search(self, widget=None):
        if self.vte is None or self.entry.get_text() == '':
            return
        found = self.vte.search_find_next()
        if not self.wrap.get_active():
            self.next.set_sensitive(bool(found))
        else:
            self.next.set_sensitive(True)
        self.prev.set_sensitive(True)

    def prev_search(self, widget=None):
        if self.vte is None or self.entry.get_text() == '':
            return
        found = self.vte.search_find_previous()
        if not self.wrap.get_active():
            self.prev.set_sensitive(bool(found))
        else:
            self.prev.set_sensitive(True)
        self.next.set_sensitive(True)

    def get_search_term(self):
        if self.dialog is None:
            return ''
        return self.entry.get_text()


GObject.type_register(Searchbar)
