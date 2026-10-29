# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""terminal.py - classes necessary to provide Terminal widgets"""


import os
import signal
import time
import gi
from gi.repository import GLib, GObject, Pango, Gtk, Gdk, GdkPixbuf, cairo
gi.require_version('Vte', '2.91')  # vte-0.38 (gnome-3.14)
from gi.repository import Vte
import subprocess
try:
    from urllib.parse import unquote as urlunquote
except ImportError:
    from urllib import unquote as urlunquote

from .util import dbg, err, spawn_new_terminator, make_uuid, manual_lookup
from . import util
from .config import Config
from .cwd import get_pid_cwd
from .factory import Factory
from .terminator import Terminator
from .titlebar import Titlebar
from .terminal_popup_menu import TerminalPopupMenu
from .prefseditor import PrefsEditor
from .searchbar import Searchbar
from .translation import _
from .signalman import Signalman
from . import plugin
from terminatorlib.layoutlauncher import LayoutLauncher
from . import regex
from .scrollback import ScrollbackCache
from . import clipboard_image
from .altscreen import (AltScreenScrollbar, adjustment_scrollable,
                       scrollbar_should_show)

_AUTOFONT_TOAST_CSS = None


def _autofont_toast_css():
    """One shared CssProvider for every auto-font toast (UI review P2-8)."""
    global _AUTOFONT_TOAST_CSS
    if _AUTOFONT_TOAST_CSS is None:
        provider = Gtk.CssProvider()
        provider.load_from_data(b"""
        .terminator-autofont-toast {
            background-color: rgba(0, 0, 0, 0.72);
            color: #ffffff;
            padding: 6px 14px;
            border-radius: 6px;
            font-weight: bold;
        }
        """)
        _AUTOFONT_TOAST_CSS = provider
    return _AUTOFONT_TOAST_CSS


def zoom_font_scale_factor(old_w, old_h, new_w, new_h):
    """Font multiplier for a scaled zoom, or None to keep waiting.

    The text grows with the axis that grew. A two-way split only grows
    one axis; scaling by the smaller one leaves the font unchanged.
    None means the size is not usable yet (the pane is mid-reparent).
    1.0 means stop without changing the font.
    """
    if old_w <= 1 or old_h <= 1 or new_w <= 1 or new_h <= 1:
        return None
    w_ratio = new_w / float(old_w)
    h_ratio = new_h / float(old_h)
    grown = max(w_ratio, h_ratio)
    shrunk = min(w_ratio, h_ratio)
    if grown < 1.02:
        # A shrink during reparent is not the final size.
        if shrunk < 0.98:
            return None
        return 1.0
    # Stay just under the fit so the cell size does not round up and
    # clip a row or a column. Cap a bogus 1px snapshot.
    return min(8.0, grown * 0.97)


# pylint: disable-msg=R0904
class Terminal(Gtk.VBox):
    """Class implementing the VTE widget and its wrappings"""

    __gsignals__ = {
        'pre-close-term': (GObject.SignalFlags.RUN_LAST, None, ()),
        'close-term': (GObject.SignalFlags.RUN_LAST, None, ()),
        'title-change': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_STRING,)),
        'insert-term-name': (GObject.SignalFlags.RUN_LAST, None, ()),
        'enumerate': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_INT,)),
        'group-tab': (GObject.SignalFlags.RUN_LAST, None, ()),
        'group-tab-toggle': (GObject.SignalFlags.RUN_LAST, None, ()),
        'ungroup-tab': (GObject.SignalFlags.RUN_LAST, None, ()),
        'ungroup-all': (GObject.SignalFlags.RUN_LAST, None, ()),
        'split-auto': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_STRING,)),
        'split-horiz': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_STRING,)),
        'split-vert': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_STRING,)),
        'rotate-cw': (GObject.SignalFlags.RUN_LAST, None, ()),
        'rotate-ccw': (GObject.SignalFlags.RUN_LAST, None, ()),
        'tab-new': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_BOOLEAN, GObject.TYPE_OBJECT)),
        'tab-top-new': (GObject.SignalFlags.RUN_LAST, None, ()),
        'focus-in': (GObject.SignalFlags.RUN_LAST, None, ()),
        'focus-out': (GObject.SignalFlags.RUN_LAST, None, ()),
        'zoom': (GObject.SignalFlags.RUN_LAST, None, ()),
        'maximise': (GObject.SignalFlags.RUN_LAST, None, ()),
        'unzoom': (GObject.SignalFlags.RUN_LAST, None, ()),
        'resize-term': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_STRING,)),
        'navigate': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_STRING,)),
        'tab-change': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_INT,)),
        'group-all': (GObject.SignalFlags.RUN_LAST, None, ()),
        'group-all-toggle': (GObject.SignalFlags.RUN_LAST, None, ()),
        'move-tab': (GObject.SignalFlags.RUN_LAST, None,
            (GObject.TYPE_STRING,)),
        'detach-tab': (GObject.SignalFlags.RUN_LAST, None, ()),
        'group-win': (GObject.SignalFlags.RUN_LAST, None, ()),
        'group-win-toggle': (GObject.SignalFlags.RUN_LAST, None, ()),
        'ungroup-win': (GObject.SignalFlags.RUN_LAST, None, ()),
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
    spawn_time = None
    child_exited = False

    matches = None
    regex_flags = None
    config = None
    custom_font_size = None
    layout_command = None
    relaunch_command = None
    directory = None
    _scrollback_restored = False

    is_held_open = False

    fgcolor_active = None
    fgcolor_inactive = None
    bgcolor = None
    bgcolor_inactive = None
    palette_active = None
    palette_inactive = None

    composite_support = None

    cnxids = None
    targets_for_new_group = None

    def __init__(self):
        """Class initialiser"""
        GObject.GObject.__init__(self)

        self.terminator = Terminator()
        self.terminator.register_terminal(self)

        # FIXME: Surely these should happen in Terminator::register_terminal()?
        self.connect('enumerate', self.terminator.do_enumerate)
        self.connect('insert-term-name', self.terminator.do_insert_term_name)
        self.connect('focus-in', self.terminator.focus_changed)
        self.connect('focus-out', self.terminator.focus_left)

        self.matches = {}
        self.match_patterns = {}
        self.cnxids = Signalman()

        self.config = Config()

        self.cwd = get_pid_cwd()
        self.origcwd = self.terminator.origcwd
        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)

        self.pending_on_vte_size_allocate = False

        self.vte = Vte.Terminal()
        self.vte.set_allow_hyperlink(True)
        self.vte._draw_data = None
        if not hasattr(self.vte, "set_opacity") or \
           not hasattr(self.vte, "is_composited"):
            self.composite_support = False
        else:
            self.composite_support = True
        dbg('composite_support: %s' % self.composite_support)

        if hasattr(self.vte, "set_enable_sixel"):
            self.vte.set_enable_sixel(True)

        self.vte.show()

        #force to load for new window/terminal use case loading plugin
        #and connecting signals, note the line update_url_matches also
        #calls load_plugins, but it won't reload since already loaded

        self.load_plugins(force = True)

        self.update_url_matches()

        self.terminalbox = self.create_terminalbox()
        # Auto-hide the scrollbar while a fullscreen TUI (alternate
        # screen) runs; see altscreen.py for the detection heuristic.
        self.altscreen = AltScreenScrollbar(self)
        self.altscreen.attach()
        # None: follow the buffer. True/False: this terminal's manual toggle.
        self._scrollbar_forced = None
        # E: Overlay around the hbox so toasts stay inside the Terminal
        # widget (D will rebuild Window overlays). close()/reconfigure keep
        # using self.terminalbox (the inner hbox).
        self._term_overlay = Gtk.Overlay()
        self._term_overlay.add(self.terminalbox)
        self._term_overlay.show()
        self._autofont_toast = None
        self._autofont_toast_timer = None
        self._scale_popover = None
        self._font_tier = 0
        self._auto_font_locked = False
        self._auto_font_mode = 'run'  # 'run' | 'freeze' | 'scaled_zoom'
        self._auto_font_timer = None
        self._auto_font_last_change_ms = 0
        self._auto_font_ever_allocated = False
        self._base_cell = None
        self._base_cell_probe_idle = None
        self._auto_font_disabled = False
        self._pane_maximise_handler = None
        self._session_custom_title = None
        self._pane_maximise_window = None

        self.titlebar = Titlebar(self)
        self.titlebar.connect_icon(self.on_group_button_press)
        self.titlebar.connect('edit-done', self.on_edit_done)
        self.connect('title-change', self.titlebar.set_terminal_title)
        self.titlebar.connect('create-group', self.really_create_group)
        self.titlebar.update('window-focus-out')
        self.titlebar.show_all()
        self.titlebar.update_visibility()
        self._ensure_scale_popover()

        self.searchbar = Searchbar(self)
        self.searchbar.connect('end-search', self.on_search_done)

        # Focus border is stroked in _draw_focus_border, on top of the
        # pane, so an unfocused pane keeps no frame and focus changes
        # do not resize the VTE.
        self.set_focus_chrome(False)
        self.connect_after('draw', self._draw_focus_border)

        self.show()
        term_area = getattr(self, '_term_overlay', None) or self.terminalbox
        if self.config['title_at_bottom']:
            self.pack_start(term_area, True, True, 0)
            self.pack_start(self.titlebar, False, True, 0)
        else:
            self.pack_start(self.titlebar, False, True, 0)
            self.pack_start(term_area, True, True, 0)

        self.connect_signals()

        os.putenv('TERM', self.config['term'])
        os.putenv('COLORTERM', self.config['colorterm'])

        env_proxy = os.getenv('http_proxy')
        if not env_proxy:
            if self.config['http_proxy'] and self.config['http_proxy'] != '':
                os.putenv('http_proxy', self.config['http_proxy'])
        self.reconfigure()
        self.vte.set_size(80, 24)

    def _export_windowid(self):
        """WINDOWID for the child (X11 only).

        m34: upstream read ``.xid``, which GdkX11Window does not have
        (the method is get_xid()), so WINDOWID was never set and a value
        inherited from the launching terminal leaked into every shell.
        Off X11 (Wayland) there is no XID: drop any inherited WINDOWID so
        tools (xdotool, w3m-img, ...) don't act on someone else's window.
        """
        xid = None
        try:
            if util.is_x11(self.vte.get_display()):
                gdkwin = self.vte.get_parent_window() or \
                    self.vte.get_toplevel().get_window()
                if gdkwin is not None and hasattr(gdkwin, 'get_xid'):
                    xid = int(gdkwin.get_xid())
        except Exception as ex:
            dbg('WINDOWID: %s' % ex)
            xid = None
        if xid:
            os.environ['WINDOWID'] = str(xid)
        else:
            os.environ.pop('WINDOWID', None)
        return xid

    def set_background_image(self,image):
        try:
            bg_pixbuf = GdkPixbuf.Pixbuf.new_from_file(image)
            self.background_image = Gdk.cairo_surface_create_from_pixbuf(bg_pixbuf, 1, None)
            self._bg_image_scale = 1
            self.cnxids.remove_signal(self.vte, 'draw')
            self.cnxids.new(self.vte, 'draw', self.background_draw)
            self.vte.set_clear_background(False)
        except Exception as e:
            self.background_image = None
            self.vte.set_clear_background(True)
            self.cnxids.remove_signal(self.vte, 'draw')
            err('error loading background image: %s, %s' % (type(e).__name__,e))

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
            self._session_mark_dirty('profile')

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
        vte_cwd = self.vte.get_current_directory_uri()
        if vte_cwd:
            # OSC7 pwd almost always gives an answer
            try:
                return(GLib.filename_from_uri(vte_cwd)[0])
            except:
                pass
        # Fall back to old gtk2 method
        if self.pid is None:
            # Child exited (m21 clears the pid) or never spawned:
            # psutil.Process(None) would report *Terminator's* own cwd.
            return getattr(self, '_last_session_cwd', None)
        dbg('calling get_pid_cwd')
        try:
            return(get_pid_cwd(self.pid))
        except Exception as ex:
            dbg('get_pid_cwd(%s) failed: %s' % (self.pid, ex))
            return getattr(self, '_last_session_cwd', None)

    def close(self):
        """Close ourselves"""
        dbg('close: called')
        # UI review P2-2: no GLib source may fire on a closed terminal
        for attr in ('_cwd_probe_timer', '_auto_font_timer',
                     '_autofont_toast_timer', '_base_cell_probe_idle'):
            sid = getattr(self, attr, None)
            if sid:
                try:
                    GLib.source_remove(sid)
                except Exception:
                    pass
            if attr in self.__dict__:
                setattr(self, attr, None)
        # Last terminal: Container.closeterm normally finalized already,
        # while this terminal was still registered (round-2 P1-2).  This is
        # the fallback for close() paths that did not go through closeterm:
        # we are deregistered by now, so pass ourselves to finalize to have
        # our output flushed before the cache stops.  The close hook below
        # is then a no-op (cache stopped) and keeps the file (A4).
        try:
            from .session import SessionManager
            # Container.closeterm() deregisters us BEFORE calling close(),
            # so "<= 1" wrongly fired when closing the second-to-last pane
            # and permanently disabled autosave (final_saving). Only
            # finalize when no OTHER terminal remains.
            others = [t for t in self.terminator.terminals if t is not self]
            if not others:
                SessionManager().finalize(closing=self)
        except Exception as ex:
            dbg('session finalize on last close: %s' % ex)
        try:
            ScrollbackCache().on_terminal_close(self)
        except Exception as ex:
            dbg('scrollback close hook failed: %s' % ex)
        self.cnxids.remove_widget(self.vte)
        adj = getattr(self, '_vadjustment', None)
        if adj is not None:
            self.cnxids.remove_widget(adj)
        window = self.get_toplevel()
        alt = getattr(self, 'altscreen', None)
        if alt is not None:
            alt.detach()
        self.emit('close-term')
        # Hand window-title ownership to the newly focused terminal.
        title = getattr(window, 'title', None)
        if title is not None and hasattr(title, 'terminal_removed'):
            try:
                title.terminal_removed(self)
            except Exception as ex:
                dbg('window title fallback on close failed: %s' % ex)
        if isinstance(self.pid, int) and self.pid > 0:
            try:
                dbg('close: killing %d' % self.pid)
                os.kill(self.pid, signal.SIGHUP)
            except Exception as ex:
                # We really don't want to care if this failed. Deep OS voodoo is
                # not what we should be doing.
                dbg('os.kill failed: %s' % ex)
                pass
            # Wait for the shell to finish exiting before we tear down the
            # PTY. This is NOT a politeness hedge — removing it resurrects a
            # real data-loss bug. The mechanism:
            #
            #   1. We've just sent SIGHUP to the shell.
            #   2. If we destroy the VTE now, the PTY master closes and the
            #      kernel delivers a SECOND SIGHUP via tty hangup to the
            #      slave's foreground process group.
            #   3. On bash 5.2 patch 14 and later (commit 6647917a, Dec 2022
            #      — "process additional terminating signals when running
            #      the EXIT trap after a terminating signal"), a second
            #      SIGHUP arriving while termsig_handler is mid-flight
            #      routes through the new kill_shell() path and terminates
            #      bash immediately, before maybe_save_shell_history() can
            #      finish writing $HISTFILE. Result: silent history
            #      loss on every window close.
            #
            # Waiting until the shell has fully exited ensures the kernel's
            # post-PTY-close SIGHUP has no recipient still trying to flush.
            # The timeout caps the wait so a shell that ignores SIGHUP can't
            # hang the window close; bash's own flush completes in well
            # under 50 ms in practice.
            self._wait_for_shell_exit()

        if self.vte:
            self.terminalbox.remove(self.vte)
            del(self.vte)

    def _wait_for_shell_exit(self, timeout=0.5, poll_interval=0.02):
        """Wait briefly for the spawned shell to exit before we tear
        down the PTY. Required to avoid silent bash history loss
        caused by bash 5.2 patch 14 reacting to the second SIGHUP that
        the kernel delivers when we close the PTY master; see the
        caller in Terminal.close() for the full mechanism.

        WNOWAIT leaves the zombie in place so VTE's GLib child-watch
        can still reap it and fire child-exited normally — we are only
        observing the exit state here, not consuming it.
        """
        deadline = time.monotonic() + timeout
        flags = os.WEXITED | os.WNOWAIT | os.WNOHANG
        while time.monotonic() < deadline:
            try:
                if os.waitid(os.P_PID, self.pid, flags):
                    return
            except OSError:
                return
            time.sleep(poll_interval)

    def create_terminalbox(self):
        """Create a GtkHBox containing the terminal and a scrollbar"""

        terminalbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 0)
        self._vadjustment = self.vte.get_vadjustment()
        self.scrollbar = Gtk.Scrollbar.new(Gtk.Orientation.VERTICAL, adjustment=self._vadjustment)
        self.scrollbar.set_no_show_all(True)
        self.cnxids.new(self._vadjustment, 'changed', self.sync_scrollbar)

        terminalbox.pack_start(self.vte, True, True, 0)
        terminalbox.pack_start(self.scrollbar, False, True, 0)
        terminalbox.show_all()

        return(terminalbox)

    def load_plugins(self, force = False):
        registry = plugin.PluginRegistry()
        registry.load_plugins(force)

    def _add_regex(self, name, re):
        dbg(f"adding regex: {re}")
        match = -1
        if regex.FLAGS_PCRE2:
            try:
                reg = Vte.Regex.new_for_match(re, len(re), self.regex_flags or regex.FLAGS_PCRE2)
                match = self.vte.match_add_regex(reg, 0)
            except GLib.Error:
                # happens when PCRE2 support is not builtin (Ubuntu < 19.10)
                pass

        # try the "old" glib regex
        if match < 0:
            reg = GLib.Regex.new(re, self.regex_flags or regex.FLAGS_GLIB, 0)
            match = self.vte.match_add_gregex(reg, 0)

        self.matches[name] = match
        self.match_patterns[name] = re
        self.vte.match_set_cursor_name(self.matches[name], 'pointer')

    def update_url_matches(self):
        """Update the regexps used to match URLs"""
        userchars = "-A-Za-z0-9"
        passchars = "-A-Za-z0-9,?;.:/!%$^*&~\"#'"
        hostchars = r"-A-Za-z0-9:\[\]"
        pathchars = "-A-Za-z0-9_$.+!*(),;:@&=?/~#%'"
        schemes   = "(news:|telnet:|nntp:|https?:|ftps?:|webcal:|ssh:)"
        user      = "[" + userchars + "]+(:[" + passchars + "]+)?"
        urlpath   = "/[" + pathchars + "]*[^]'.}>) \t\r\n,\\\"]"

        lboundry = "\\b"
        rboundry = "\\b"

        re = (lboundry + "file:/" + "//?(:[0-9]+)?(" + urlpath + ")" +
                rboundry + "/?")
        self._add_regex('file', re)

        re = (lboundry + schemes +
                "//(" + user + "@)?[" + hostchars  +".]+(:[0-9]+)?(" +
                urlpath + ")?" + rboundry + "/?")
        self._add_regex('full_uri', re)

        if self.matches['full_uri'] == -1 or self.matches['file'] == -1:
            err ('Terminal::update_url_matches: Failed adding URL matches')
        else:
            re = (lboundry +
                    '(callto:|h323:|sip:)' + "[" + userchars + "+][" +
                    userchars + ".]*(:[0-9]+)?@?[" + pathchars + "]+" +
                    rboundry)
            self._add_regex('voip', re)

            re = (lboundry +
                    "(www|ftp)[" + hostchars + r"]*\.[" + hostchars +
                    ".]+(:[0-9]+)?(" + urlpath + ")?" + rboundry + "/?")
            self._add_regex('addr_only', re)

            re = (lboundry +
                    "(mailto:)?[a-zA-Z0-9][a-zA-Z0-9.+-]*@[a-zA-Z0-9]" +
                            r"[a-zA-Z0-9-]*\.[a-zA-Z0-9][a-zA-Z0-9-]+" +
                            "[.a-zA-Z0-9-]*" + rboundry)
            self._add_regex('email', re)

            re = (lboundry +
                  r"""news:[-A-Z\^_a-z{|}~!"#$%&'()*+,./0-9;:=?`]+@""" +
                            "[-A-Za-z0-9.]+(:[0-9]+)?" + rboundry)
            self._add_regex('nntp', re)

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

                    self._add_regex(name, match)

                    dbg('added plugin URL handler for %s (%s) as %d' %
                        (name, urlplugin.__class__.__name__,
                        self.matches[name]))
            except Exception as ex:
                err('Exception occurred adding plugin URL match: %s, %s' % (type(ex).__name__, ex))

    def match_add(self, name, match):
        """Register a URL match"""
        if name in self.matches:
            err('Terminal::match_add: Refusing to create duplicate match %s' % name)
            return

        self._add_regex(name, match)

    def match_remove(self, name):
        """Remove a previously registered URL match"""
        if name not in self.matches:
            err('Terminal::match_remove: Unable to remove non-existent match %s' % name)
            return
        self.vte.match_remove(self.matches[name])
        del(self.matches[name])
        self.match_patterns.pop(name, None)

    def maybe_copy_clipboard(self):
        if self.config['copy_on_selection'] and self.vte.get_has_selection():
            self.vte.copy_clipboard()


    def _on_vte_contents_changed(self, vte, *args):
        self._on_contents_changed_cwd_probe(vte, *args)
        if self.config['scrollback_cache']:
            self._on_scrollback_contents_changed(vte)

    def _snapshot_before_input(self):
        """Save normal-screen history before input that may run a command
        (Enter, paste, programmatic feed) -- see m13."""
        try:
            ScrollbackCache().snapshot_before_command(self)
        except Exception as ex:
            dbg('scrollback pre-command snapshot failed: %s' % ex)

    def _on_scrollback_contents_changed(self, _vte):
        try:
            ScrollbackCache().mark_dirty(self)
        except Exception as ex:
            dbg('scrollback mark_dirty failed: %s' % ex)

    def connect_signals(self):
        """Connect all the gtk signals and drag-n-drop mechanics"""

        self.scrollbar.connect('button-press-event', self.on_buttonpress)

        self.cnxids.new(self.vte, 'key-press-event', self.on_keypress)
        self.cnxids.new(self.vte, 'button-press-event', self.on_buttonpress)
        self.cnxids.new(self.vte, 'scroll-event', self.on_mousewheel)
        self.cnxids.new(self.vte, 'popup-menu', self.popup_menu)

        srcvtetargets = [("vte", Gtk.TargetFlags.SAME_APP, self.TARGET_TYPE_VTE)]
        dsttargets = [("vte", Gtk.TargetFlags.SAME_APP, self.TARGET_TYPE_VTE),
                      ('text/x-moz-url', 0, self.TARGET_TYPE_MOZ),
                      ('_NETSCAPE_URL', 0, 0)]
        '''
        The following should work, but on my system it corrupts the returned
        TargetEntry's in the newdstargets with binary crap, causing "Segmentation
        fault (core dumped)" when the later drag_dest_set gets called.
        
        dsttargetlist = Gtk.TargetList.new([])
        dsttargetlist.add_text_targets(0)
        dsttargetlist.add_uri_targets(0)
        dsttargetlist.add_table(dsttargets)
        
        newdsttargets = Gtk.target_table_new_from_list(dsttargetlist)
        '''
        # FIXME: Temporary workaround for the problems with the correct way of doing things
        dsttargets.extend([('text/plain', 0, 0),
                           ('text/plain;charset=utf-8', 0, 0),
                           ('TEXT', 0, 0),
                           ('STRING', 0, 0),
                           ('UTF8_STRING', 0, 0),
                           ('COMPOUND_TEXT', 0, 0),
                           ('text/uri-list', 0, 0)])
        # Images come last: GTK picks the first destination target the
        # source offers, and an image file dragged from a file manager
        # offers both text/uri-list and image/png.  The path must win
        # there; only a drag with no URI at all is saved as a PNG.
        dsttargets.extend([('image/png', 0, 0),
                           ('image/jpeg', 0, 0),
                           ('image/bmp', 0, 0),
                           ('image/tiff', 0, 0),
                           ('image/gif', 0, 0)])
        # Convert to target entries
        srcvtetargets = [Gtk.TargetEntry.new(*tgt) for tgt in srcvtetargets]
        dsttargets = [Gtk.TargetEntry.new(*tgt) for tgt in dsttargets]

        dbg('Finalised drag targets: %s' % dsttargets)

        for (widget, mask) in [
            (self.vte, Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.BUTTON3_MASK),
            (self.titlebar, Gdk.ModifierType.BUTTON1_MASK)]:
            widget.drag_source_set(mask, srcvtetargets, Gdk.DragAction.MOVE)

        self.vte.drag_dest_set(Gtk.DestDefaults.MOTION |
                Gtk.DestDefaults.HIGHLIGHT | Gtk.DestDefaults.DROP,
                dsttargets, Gdk.DragAction.COPY | Gdk.DragAction.MOVE)

        for widget in [self.vte, self.titlebar]:
            self.cnxids.new(widget, 'drag-begin', self.on_drag_begin, self)
            self.cnxids.new(widget, 'drag-data-get', self.on_drag_data_get,
            self)

        self.cnxids.new(self.vte, 'drag-motion', self.on_drag_motion, self)
        self.cnxids.new(self.vte, 'drag-data-received',
            self.on_drag_data_received, self)

        self.cnxids.new(self.vte, 'selection-changed',
            lambda widget: self.maybe_copy_clipboard())

        if self.composite_support:
            self.cnxids.new(self.vte, 'composited-changed', self.reconfigure)

        self.cnxids.new(self.vte, 'window-title-changed', lambda x:
            self.emit('title-change', self.get_window_title()))
        # Session dirty on cwd change (OSC7); VTE 0.78+ may use termprop-changed
        try:
            from gi.repository import GObject
            if GObject.signal_lookup('current-directory-uri-changed', type(self.vte)):
                self.cnxids.new(self.vte, 'current-directory-uri-changed',
                    lambda *a: self._session_mark_dirty_cwd())
            elif GObject.signal_lookup('termprop-changed', type(self.vte)):
                self.cnxids.new(self.vte, 'termprop-changed',
                    lambda *a: self._session_mark_dirty_cwd())
        except Exception as ex:
            dbg('cwd session signal: %s' % ex)
        # Shells without OSC7 never emit cwd signals; probe /proc cwd
        # shortly after output settles so `cd` still autosaves.
        # One handler only: signalman keys by (widget, signal), so a second
        # connect() would orphan the first id (never disconnected on
        # reconfigure -> handlers pile up) and log "already has a handler".
        self.cnxids.new(self.vte, 'contents-changed',
                        self._on_vte_contents_changed)
        self.cnxids.new(self.vte, 'grab-focus', self.on_vte_focus)
        self.cnxids.new(self.vte, 'focus-in-event', self.on_vte_focus_in)
        self.cnxids.new(self.vte, 'focus-out-event', self.on_vte_focus_out)
        self.cnxids.new(self.vte, 'size-allocate', self.deferred_on_vte_size_allocate)
        # m40: Xft DPI / text-scaling / font changes re-measure the cell
        # without necessarily changing the allocation.
        if GObject.signal_lookup('char-size-changed', type(self.vte)):
            self.cnxids.new(self.vte, 'char-size-changed',
                            self._on_vte_char_size_changed)

        self.vte.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK)
        self.cnxids.new(self.vte, 'enter_notify_event',
            self.on_vte_notify_enter)

        self.cnxids.new(self.vte, 'realize', self.reconfigure)
        self.connect('hierarchy-changed', self._on_autofont_hierarchy_changed)

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
        menu.popup_at_widget(widget,Gdk.Gravity.SOUTH_WEST,Gdk.Gravity.NORTH_WEST,None)
        return(True)

    def populate_group_menu(self):
        """Fill out a group menu"""
        menu = Gtk.Menu()
        self.group_menu = menu
        groupitems = []

        item = Gtk.MenuItem.new_with_mnemonic(_('N_ew group...'))
        item.connect('activate', self.create_group)
        menu.append(item)

        if len(self.terminator.groups) > 0:
            cnxs = []
            item = Gtk.RadioMenuItem.new_with_mnemonic(groupitems, _('_None'))
            groupitems = item.get_group()
            item.set_active(self.group == None)
            cnxs.append([item, 'toggled', self.set_group, None])
            menu.append(item)

            for group in self.terminator.groups:
                item = Gtk.RadioMenuItem.new_with_label(groupitems, group)
                groupitems = item.get_group()
                item.set_active(self.group == group)
                cnxs.append([item, 'toggled', self.set_group, group])
                menu.append(item)

            for cnx in cnxs:
                cnx[0].connect(cnx[1], cnx[2], cnx[3])

        if self.group != None or len(self.terminator.groups) > 0:
            menu.append(Gtk.SeparatorMenuItem())

        if self.group != None:
            item = Gtk.MenuItem(_('Remove group %s') % self.group)
            item.connect('activate', self.ungroup, self.group)
            menu.append(item)

        if util.has_ancestor(self, Gtk.Window):
            item = Gtk.MenuItem.new_with_mnemonic(_('G_roup all in window'))
            item.connect('activate', lambda x: self.emit('group_win'))
            menu.append(item)

            if len(self.terminator.groups) > 0:
                item = Gtk.MenuItem.new_with_mnemonic(_('Ungro_up all in window'))
                item.connect('activate', lambda x: self.emit('ungroup_win'))
                menu.append(item)

        if util.has_ancestor(self, Gtk.Notebook):
            item = Gtk.MenuItem.new_with_mnemonic(_('G_roup all in tab'))
            item.connect('activate', lambda x: self.emit('group_tab'))
            menu.append(item)

            if len(self.terminator.groups) > 0:
                item = Gtk.MenuItem.new_with_mnemonic(_('Ungro_up all in tab'))
                item.connect('activate', lambda x: self.emit('ungroup_tab'))
                menu.append(item)

        if len(self.terminator.groups) > 0:
            item = Gtk.MenuItem(_('Remove all groups'))
            item.connect('activate', lambda x: self.emit('ungroup-all'))
            menu.append(item)

        if self.group != None:
            menu.append(Gtk.SeparatorMenuItem())

            item = Gtk.MenuItem(_('Close group %s') % self.group)
            item.connect('activate', lambda x:
                         self.terminator.closegroupedterms(self.group))
            menu.append(item)

        menu.append(Gtk.SeparatorMenuItem())

        groupitems = []
        cnxs = []

        for key, value in list({_('Broadcast _all'):'all',
                          _('Broadcast _group'):'group',
                          _('Broadcast _off'):'off'}.items()):
            item = Gtk.RadioMenuItem.new_with_mnemonic(groupitems, key)
            groupitems = item.get_group()
            dbg('%s active: %s' %
                    (key, self.terminator.groupsend ==
                        self.terminator.groupsend_type[value]))
            item.set_active(self.terminator.groupsend ==
                    self.terminator.groupsend_type[value])
            cnxs.append([item, 'activate', self.set_groupsend, self.terminator.groupsend_type[value]])
            menu.append(item)

        for cnx in cnxs:
            cnx[0].connect(cnx[1], cnx[2], cnx[3])

        menu.append(Gtk.SeparatorMenuItem())

        item = Gtk.CheckMenuItem.new_with_mnemonic(_('_Split to this group'))
        item.set_active(self.config['split_to_group'])
        item.connect('toggled', lambda x: self.do_splittogroup_toggle())
        menu.append(item)

        item = Gtk.CheckMenuItem.new_with_mnemonic(_('Auto_clean groups'))
        item.set_active(self.config['autoclean_groups'])
        item.connect('toggled', lambda x: self.do_autocleangroups_toggle())
        menu.append(item)

        menu.append(Gtk.SeparatorMenuItem())

        item = Gtk.MenuItem.new_with_mnemonic(_('_Insert terminal number'))
        item.connect('activate', lambda x: self.emit('enumerate', False))
        menu.append(item)

        item = Gtk.MenuItem.new_with_mnemonic(_('Insert zero _padded terminal number'))
        item.connect('activate', lambda x: self.emit('enumerate', True))
        menu.append(item)

        item = Gtk.MenuItem.new_with_mnemonic(_('Insert terminal _name'))
        item.connect('activate', lambda x: self.emit('insert-term-name'))
        menu.append(item)

        return(menu)

    def set_group(self, _item, name):
        """Set a particular group"""
        if self.group == name:
            # already in this group, no action needed
            return
        dbg('Setting group to %s' % name)
        self.group = name
        self.titlebar.set_group_label(name)
        self.terminator.group_hoover()
        self._session_mark_dirty('group')

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
        if value in list(self.terminator.groupsend_type.values()):
            dbg('setting groupsend to %s' % value)
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
        if getattr(self, 'vte', None) is None:
            return
        self.cnxids.remove_signal(self.vte, 'realize')

        # Handle child command exiting
        self.cnxids.remove_signal(self.vte, 'child-exited')

        if self.config['exit_action'] == 'restart':
            # Do NOT pass True as connect user-data: VTE emits (vte, status),
            # so user-data True became debugserver=True and status became
            # respawn. Use dedicated handlers instead.
            self.cnxids.new(self.vte, 'child-exited',
                            self._on_child_exited_restart)
        elif self.config['exit_action'] == 'hold':
            self.cnxids.new(self.vte, 'child-exited',
                            self._on_child_exited_hold)
        elif self.config['exit_action'] in ('close', 'left'):
            self.cnxids.new(self.vte, 'child-exited',
                            self._on_child_exited_close)

        # Scrollback cache: (re)bind contents-changed + reconfigure cache
        self.cnxids.remove_signal(self.vte, 'contents-changed')
        # Shells without OSC7 never emit cwd signals; probe /proc cwd
        # shortly after output settles so `cd` still autosaves.
        # One handler only: signalman keys by (widget, signal), so a second
        # connect() would orphan the first id (never disconnected on
        # reconfigure -> handlers pile up) and log "already has a handler".
        self.cnxids.new(self.vte, 'contents-changed',
                        self._on_vte_contents_changed)
        try:
            ScrollbackCache().reconfigure()
        except Exception as ex:
            dbg('scrollback reconfigure failed: %s' % ex)

        # Word char support was missing from vte 0.38, silently skip this setting
        if hasattr(self.vte, 'set_word_char_exceptions'):
            self.vte.set_word_char_exceptions(self.config['word_chars'])
        self.vte.set_mouse_autohide(self.config['mouse_autohide'])

        backspace = self.config['backspace_binding']
        delete = self.config['delete_binding']

        try:
            if backspace == 'ascii-del':
                backbind = Vte.ERASE_ASCII_DELETE
            elif backspace == 'control-h':
                backbind = Vte.ERASE_ASCII_BACKSPACE
            elif backspace == 'escape-sequence':
                backbind = Vte.ERASE_DELETE_SEQUENCE
            else:
                backbind = Vte.ERASE_AUTO
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
                delbind = Vte.ERASE_ASCII_DELETE
            elif delete == 'control-h':
                delbind = Vte.ERASE_ASCII_BACKSPACE
            elif delete == 'escape-sequence':
                delbind = Vte.ERASE_DELETE_SEQUENCE
            else:
                delbind = Vte.ERASE_AUTO
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
                self.set_font(Pango.FontDescription(font))
                self._base_cell = None
            except:
                pass
        self.vte.set_allow_bold(self.config['allow_bold'])
        if hasattr(self.vte,'set_cell_height_scale'): 
            self.vte.set_cell_height_scale(self.config['cell_height'])
        if hasattr(self.vte,'set_cell_width_scale'):
            self.vte.set_cell_width_scale(self.config['cell_width'])
        if hasattr(self.vte, 'set_bold_is_bright'):
            self.vte.set_bold_is_bright(self.config['bold_is_bright'])

        if self.config['use_theme_colors']:
            self.fgcolor_active = self.vte.get_style_context().get_color(Gtk.StateType.NORMAL)  # VERIFY FOR GTK3: do these really take the theme colors?
            self.bgcolor = self.vte.get_style_context().get_background_color(Gtk.StateType.NORMAL)
        else:
            self.fgcolor_active = Gdk.RGBA()
            self.fgcolor_active.parse(self.config['foreground_color'])
            self.bgcolor = Gdk.RGBA()
            self.bgcolor.parse(self.config['background_color'])

        if self.config['background_type'] in ('transparent', 'image'):
            self.bgcolor.alpha = float(self.config['background_darkness'])
        else:
            self.bgcolor.alpha = 1

        if self.config['background_type'] == 'image' and self.config['background_image'] != '':
            self.set_background_image(self.config['background_image'])
        else:
            self.background_image = None
            self.vte.set_clear_background(True)
            self.cnxids.remove_signal(self.vte, 'draw')

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

        bg_factor = self.config['inactive_bg_color_offset']
        if bg_factor > 1.0:
            bg_factor = 1.0
        self.bgcolor_inactive = self.bgcolor.copy()
        dbg(("bgcolor_inactive set to: RGB(%s,%s,%s)", getattr(self.bgcolor_inactive, "red"),
                                                      getattr(self.bgcolor_inactive, "green"),
                                                      getattr(self.bgcolor_inactive, "blue")))

        for bit in ['red', 'green', 'blue']:
            setattr(self.bgcolor_inactive, bit,
                    getattr(self.bgcolor_inactive, bit) * bg_factor)
        dbg(("bgcolor_inactive set to: RGB(%s,%s,%s)", getattr(self.bgcolor_inactive, "red"),
                                                      getattr(self.bgcolor_inactive, "green"),
                                                      getattr(self.bgcolor_inactive, "blue")))

        colors = self.config['palette'].split(':')
        self.palette_active = []
        for color in colors:
            if color:
                newcolor = Gdk.RGBA()
                newcolor.parse(color)
                self.palette_active.append(newcolor)
        if len(colors) == 16:
            # RGB values for indices 16..255 copied from vte source in order to dim them
            shades = [0, 95, 135, 175, 215, 255]
            for r in range(0, 6):
                for g in range(0, 6):
                    for b in range(0, 6):
                        newcolor = Gdk.RGBA()
                        setattr(newcolor, "red",   shades[r] / 255.0)
                        setattr(newcolor, "green", shades[g] / 255.0)
                        setattr(newcolor, "blue",  shades[b] / 255.0)
                        self.palette_active.append(newcolor)
            for y in range(8, 248, 10):
                newcolor = Gdk.RGBA()
                setattr(newcolor, "red",   y / 255.0)
                setattr(newcolor, "green", y / 255.0)
                setattr(newcolor, "blue",  y / 255.0)
                self.palette_active.append(newcolor)
        self.palette_inactive = []
        for color in self.palette_active:
            newcolor = Gdk.RGBA()
            for bit in ['red', 'green', 'blue']:
                setattr(newcolor, bit,
                        getattr(color, bit) * factor)
            self.palette_inactive.append(newcolor)
        if self.terminator.last_focused_term == self:
            self.vte.set_colors(self.fgcolor_active, self.bgcolor,
                                self.palette_active)
        else:
            self.vte.set_colors(self.fgcolor_inactive, self.bgcolor_inactive,
                                self.palette_inactive)
        profiles = self.config.base.profiles
        terminal_box_style_context = self.terminalbox.get_style_context()
        for profile in list(profiles.keys()):
            munged_profile = "terminator-profile-%s" % (
                "".join([c if c.isalnum() else "-" for c in profile]))
            if terminal_box_style_context.has_class(munged_profile):
                terminal_box_style_context.remove_class(munged_profile)
        munged_profile = "".join([c if c.isalnum() else "-" for c in self.get_profile()])
        css_class_name = "terminator-profile-%s" % (munged_profile)
        terminal_box_style_context.add_class(css_class_name)
        self.set_cursor_color()
        self.vte.set_cursor_shape(getattr(Vte.CursorShape,
                                          self.config['cursor_shape'].upper()));

        if self.config['cursor_blink'] == True:
            self.vte.set_cursor_blink_mode(Vte.CursorBlinkMode.ON)
        else:
            self.vte.set_cursor_blink_mode(Vte.CursorBlinkMode.OFF)

        if self.config['force_no_bell'] == True:
            self.vte.set_audible_bell(False)
            self.cnxids.remove_signal(self.vte, 'bell')
        else:
            self.vte.set_audible_bell(self.config['audible_bell'])
            self.cnxids.remove_signal(self.vte, 'bell')
            if self.config['urgent_bell'] == True or \
               self.config['icon_bell'] == True or \
               self.config['visible_bell'] == True:
                try:
                    self.cnxids.new(self.vte, 'bell', self.on_bell)
                except TypeError:
                    err('bell signal unavailable with this version of VTE')

        if self.config['scrollback_infinite'] == True:
            scrollback_lines = -1
        else:
            scrollback_lines = self.config['scrollback_lines']
        self.vte.set_scrollback_lines(scrollback_lines)
        self.vte.set_scroll_on_keystroke(self.config['scroll_on_keystroke'])
        self.vte.set_scroll_on_output(self.config['scroll_on_output'])

        # A preference change drops a manual show/hide for this terminal.
        self._scrollbar_forced = None
        self._place_scrollbar()
        self.sync_scrollbar()
        if getattr(self, 'altscreen', None) is not None:
            self.altscreen.reconfigured()

        toplevel = self.get_toplevel()
        if isinstance(toplevel, Gtk.Window) and toplevel.has_toplevel_focus():
            focused = self.terminator.get_focussed_terminal()
            if focused is None:
                focused = self.terminator.last_focused_term
            self.titlebar.update(focused or self)
        else:
            self.titlebar.update('window-focus-out')

        self.vte.queue_draw()
        self._ensure_scale_popover()
        self.schedule_auto_font_scale()
        self._sync_owning_window_blur()

    def _sync_owning_window_blur(self):
        """Recompute the blur hint of the window this terminal is in."""
        top = self.get_toplevel()
        if top is self:
            return
        sync = getattr(top, 'sync_blur_hint', None)
        if sync is None:
            return
        try:
            sync()
        except Exception as ex:
            dbg('blur hint sync failed: %s' % ex)

    def set_cursor_color(self):
        """Set the cursor color appropriately"""
        if self.config['cursor_color_default']:
            self.vte.set_color_cursor(None)
            self.vte.set_color_cursor_foreground(None)
        else:
            # foreground
            cursor_fg_color = Gdk.RGBA()
            if self.config['cursor_fg_color'] == '':
                cursor_fg_color.parse(self.config['background_color'])
            else:
                cursor_fg_color.parse(self.config['cursor_fg_color'])
            self.vte.set_color_cursor_foreground(cursor_fg_color)
            # background
            cursor_bg_color = Gdk.RGBA()
            if self.config['cursor_bg_color'] == '':
                cursor_bg_color.parse(self.config['foreground_color'])
            else:
                cursor_bg_color.parse(self.config['cursor_bg_color'])
            self.vte.set_color_cursor(cursor_bg_color)

    def set_bgcolor(self, colorstr, alpha=None):
        """Set a custom background color. If alpha is None, use the
        profile's background_darkness when transparent/image, else opaque."""
        if not colorstr:
            return
        self.bgcolor = Gdk.RGBA()
        self.bgcolor.parse(colorstr)

        if alpha is not None:
            self.bgcolor.alpha = float(alpha)
        elif self.config['background_type'] in ('transparent', 'image'):
            self.bgcolor.alpha = float(self.config['background_darkness'])
        else:
            self.bgcolor.alpha = 1.0

        bg_factor = self.config['inactive_bg_color_offset']
        if bg_factor > 1.0:
            bg_factor = 1.0
        self.bgcolor_inactive = self.bgcolor.copy()
        for bit in ['red', 'green', 'blue']:
            setattr(self.bgcolor_inactive, bit,
                    getattr(self.bgcolor_inactive, bit) * bg_factor)

        if self.terminator.last_focused_term == self:
            self.vte.set_colors(self.fgcolor_active, self.bgcolor,
                                self.palette_active)
        else:
            self.vte.set_colors(self.fgcolor_inactive, self.bgcolor_inactive,
                                self.palette_inactive)
        self.vte.queue_draw()

    def set_fgcolor(self, colorstr):
        """Set a custom foreground (text) color"""
        if not colorstr:
            return
        self.fgcolor_active = Gdk.RGBA()
        self.fgcolor_active.parse(colorstr)

        factor = self.config['inactive_color_offset']
        if factor > 1.0:
            factor = 1.0
        self.fgcolor_inactive = self.fgcolor_active.copy()
        for bit in ['red', 'green', 'blue']:
            setattr(self.fgcolor_inactive, bit,
                    getattr(self.fgcolor_inactive, bit) * factor)

        if self.terminator.last_focused_term == self:
            self.vte.set_colors(self.fgcolor_active, self.bgcolor,
                                self.palette_active)
        else:
            self.vte.set_colors(self.fgcolor_inactive, self.bgcolor_inactive,
                                self.palette_inactive)
        self.vte.queue_draw()

    def get_window_title(self):
        """Return the window title"""
        vte = getattr(self, 'vte', None)
        title = None
        if vte is not None:
            try:
                title = vte.get_window_title()
            except Exception:
                title = None
        if title:
            return title
        if self.command:
            return str(self.command)
        return self._fallback_title()

    def _fallback_title(self):
        """m26 (round2-ux P2-6): the shell set no title and there is no
        custom command: show the shell's name (e.g. 'bash') rather than the
        literal 'None' (upstream str(None)), else the cwd's basename."""
        from .altscreen import process_name
        name = None
        pid = getattr(self, 'pid', None)
        if pid:
            name = process_name(pid)
        if not name:
            shell = os.environ.get('SHELL') or ''
            name = os.path.basename(shell) if shell else None
        if name:
            return name.lstrip('-')
        try:
            cwd = self.get_cwd()
        except Exception:
            cwd = None
        if cwd:
            return os.path.basename(cwd.rstrip(os.sep)) or cwd
        return 'Terminal'

    def on_group_button_press(self, widget, event):
        """Handler for the group button"""
        if event.button == 1:
            if event.type == Gdk.EventType._2BUTTON_PRESS or \
               event.type == Gdk.EventType._3BUTTON_PRESS:
                # Ignore these, or they make the interaction bad
                return True
            # Super key applies interaction to all terms in group
            include_siblings=event.get_state() & Gdk.ModifierType.MOD4_MASK == Gdk.ModifierType.MOD4_MASK
            if include_siblings:
                targets=self.terminator.get_sibling_terms(self)
            else:
                targets=[self]
            if event.get_state() & Gdk.ModifierType.CONTROL_MASK == Gdk.ModifierType.CONTROL_MASK:
                dbg('on_group_button_press: toggle terminal to focused terminals group')
                focused=self.get_toplevel().get_focussed_terminal()
                if focused in targets: targets.remove(focused)
                if self != focused:
                    if focused.group is None and self.group is None:
                        # Create a new group and assign currently focused
                        # terminal to this group
                        new_group = self.terminator.new_random_group()
                        focused.set_group(None, new_group)
                        focused.titlebar.update()
                    elif self.group == focused.group:
                        new_group = None
                    else:
                        new_group = focused.group
                    [term.set_group(None, new_group) for term in targets]
                    [term.titlebar.update(focused) for term in targets]
                return True
            elif event.get_state() & Gdk.ModifierType.SHIFT_MASK == Gdk.ModifierType.SHIFT_MASK:
                dbg('on_group_button_press: rename of terminals group')
                self.targets_for_new_group = targets
                self.titlebar.create_group()
                return True
            elif event.type == Gdk.EventType.BUTTON_PRESS:
                # Single Click gives popup
                dbg('on_group_button_press: group menu popup')
                window = self.get_toplevel()
                window.preventHide = True
                self.create_popup_group_menu(widget, event)
                return True
            else:
                dbg('on_group_button_press: unknown group button interaction')
        return False

    def on_keypress(self, widget, event):
        """Handler for keyboard events"""
        if not event:
            dbg('Called on %s with no event' % widget)
            return False

        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            # Snapshot shell history before the command runs: if it is a
            # fullscreen TUI (vim/htop) VTE hides the normal screen until it
            # exits, so quitting meanwhile would otherwise lose it (m13).
            # Broadcast Enter reaches the other terminals through this same
            # handler (group_emit/all_emit re-emit key-press-event).
            self._snapshot_before_input()

        # FIXME: Does keybindings really want to live in Terminator()?
        mapping = self.terminator.keybindings.lookup(event)

        if mapping == "hide_window":
            return False

        if mapping and mapping not in ['close_window',
                                       'full_screen']:
            dbg('lookup found: %r' % mapping)
            # handle the case where user has re-bound copy to ctrl+<key>
            # we only copy if there is a selection otherwise let it fall through
            # to ^<key>
            if (mapping == "copy" and event.get_state() & Gdk.ModifierType.CONTROL_MASK):
                if self.vte.get_has_selection():
                    getattr(self, "key_" + mapping)()
                    return True
                elif not self.config['smart_copy']:
                    return True
            elif mapping == "restore_maximised":
                # Only consume when a pane is maximised / zoomed (D21)
                if self.is_zoomed():
                    self.key_restore_maximised()
                    return True
                return False
            else:
                getattr(self, "key_" + mapping)()
                return True

        # FIXME: This is all clearly wrong. We should be doing this better
        #         maybe we can emit the key event and let Terminator() care?
        groupsend = self.terminator.groupsend
        groupsend_type = self.terminator.groupsend_type
        toplevel = self.vte.get_toplevel()
        window_focussed = isinstance(toplevel, Gtk.Window) and toplevel.get_property('has-toplevel-focus')
        if groupsend != groupsend_type['off'] and window_focussed and self.vte.is_focus():
            if self.group and groupsend == groupsend_type['group']:
                self.terminator.group_emit(self, self.group, 'key-press-event',
                                           event)
            if groupsend == groupsend_type['all']:
                self.terminator.all_emit(self, 'key-press-event', event)

        return False

    def on_buttonpress(self, widget, event):
        """Handler for mouse events"""
        # Any button event should grab focus
        widget.grab_focus()

        if type(widget) == Gtk.VScrollbar and event.type == Gdk.EventType._2BUTTON_PRESS:
            # Suppress double-click behavior
            return True

        if self.config['putty_paste_style']:
            middle_click = [self.popup_menu, (widget, event)]
            right_click = [self.paste_clipboard, (not self.config['putty_paste_style_source_clipboard'], True)]
        else:
            middle_click = [self.paste_clipboard, (not self.config['putty_paste_style_source_clipboard'], True)]
            right_click = [self.popup_menu, (widget, event)]

        # Ctrl-click event here.
        if event.button == self.MOUSEBUTTON_LEFT:
            # Ctrl+leftclick on a URL should open it. Only the initial press
            # counts: GDK reports a double-click as BUTTON_PRESS followed by
            # _2BUTTON_PRESS, so acting on every event type would open the URL
            # once per event.
            if (event.type == Gdk.EventType.BUTTON_PRESS
                    and (self.config["link_single_click"]
                         or event.get_state() & Gdk.ModifierType.CONTROL_MASK == Gdk.ModifierType.CONTROL_MASK)):
                # Check new OSC-8 method first
                url = self.vte.hyperlink_check_event(event)
                dbg('url: %s' % url)
                if url:
                    self.open_url(url, prepare=False)
                    # Consume the event: the click we just acted on must not
                    # also be forwarded to the application underneath. Apps that
                    # enable mouse reporting and treat Ctrl+click as "open link"
                    # (e.g. TUIs) would otherwise open the same URL a second time.
                    return True
                else:
                    dbg('OSC-8 URL not detected dropping back to regex match')
                    url = self.vte.match_check_event(event)
                    if url[0]:
                        self.open_url(url, prepare=True)
                        return True
                    else:
                        dbg("No regex match, discard event.")
        elif event.button == self.MOUSEBUTTON_MIDDLE:
            # middleclick should paste the clipboard
            # try to pass it to vte widget first though
            if event.get_state() & Gdk.ModifierType.CONTROL_MASK == 0:
                if event.get_state() & Gdk.ModifierType.SHIFT_MASK == 0:
                    gtk_settings=Gtk.Settings().get_default()
                    primary_state = gtk_settings.get_property('gtk-enable-primary-paste')
                    gtk_settings.set_property('gtk-enable-primary-paste',  False)
                    if not Vte.Terminal.do_button_press_event(self.vte, event):
                        middle_click[0](*middle_click[1])
                    gtk_settings.set_property('gtk-enable-primary-paste', primary_state)
                else:
                    middle_click[0](*middle_click[1])
                return True
            return Vte.Terminal.do_button_press_event(self.vte, event)
        elif event.button == self.MOUSEBUTTON_RIGHT:
            # rightclick should display a context menu if Ctrl is not pressed,
            # plus either the app is not interested in mouse events or Shift is pressed
            if event.get_state() & Gdk.ModifierType.CONTROL_MASK == 0:
                if event.get_state() & Gdk.ModifierType.SHIFT_MASK == 0:
                    if not Vte.Terminal.do_button_press_event(self.vte, event):
                        right_click[0](*right_click[1])
                else:
                    right_click[0](*right_click[1])
                return True
        return False

    def on_mousewheel(self, widget, event):
        """Handler for modifier + mouse wheel scroll events.

        Each mask is compared in parentheses: ``==`` binds tighter than
        ``&``, so an ungrouped test treats every state as Shift.
        Smooth deltas accumulate per modifier combo and only act on a
        full step. A zero delta is not a step and does not reset that.
        """
        ctrl = ((event.state & Gdk.ModifierType.CONTROL_MASK)
                == Gdk.ModifierType.CONTROL_MASK)
        shift = ((event.state & Gdk.ModifierType.SHIFT_MASK)
                 == Gdk.ModifierType.SHIFT_MASK)
        mod4 = ((event.state & Gdk.ModifierType.MOD4_MASK)
                == Gdk.ModifierType.MOD4_MASK)
        if not ctrl and not shift:
            return False
        if ctrl and self.config['disable_mousewheel_zoom'] is True:
            return False
        direction = event.direction
        smooth = direction == Gdk.ScrollDirection.SMOOTH
        discrete_up = direction == Gdk.ScrollDirection.UP
        discrete_down = direction == Gdk.ScrollDirection.DOWN
        if not smooth and not discrete_up and not discrete_down:
            return False
        if smooth and event.delta_y == 0:
            return False
        combo = (ctrl, shift, mod4)
        if getattr(self, '_wheel_mod_combo', None) != combo:
            self._wheel_zoom_remainder = 0.0
            self._wheel_page_remainder = 0.0
            self._wheel_mod_combo = combo
        if discrete_up or discrete_down:
            steps = -1 if discrete_up else 1
        else:
            delta = event.delta_y
            attr = '_wheel_zoom_remainder' if ctrl else '_wheel_page_remainder'
            rem = float(getattr(self, attr, 0.0) or 0.0)
            if rem and ((rem > 0) != (delta > 0)):
                rem = 0.0
            rem += delta
            count = int(abs(rem))
            if count:
                sign = 1.0 if rem > 0 else -1.0
                rem -= sign * count
                steps = int(sign * count)
            else:
                steps = 0
            setattr(self, attr, rem)
            if steps == 0:
                return True
        if mod4:
            targets = self.terminator.terminals
        elif shift:
            targets = self.terminator.get_target_terms(self)
        else:
            targets = [self]
        up = steps < 0
        nsteps = abs(steps)
        if ctrl:
            for _step in range(nsteps):
                for target in targets:
                    if up:
                        target.zoom_in()
                    else:
                        target.zoom_out()
        else:
            for _step in range(nsteps):
                self.scroll_by_page(-1 if up else 1)
        return True

    def popup_menu(self, widget, event=None, anchor=None,
                   skip_link_check=False):
        """Display the context menu. Every entry point (VTE right-click,
        window header menu, titlebar right-click, titlebar gear) goes
        through here so that preventHide is always set.
        anchor: widget to attach the menu to (gear button).
        skip_link_check: the event is not on the VTE (titlebar), so do not
        run URL / hyperlink detection on its coordinates."""
        window = self.get_toplevel()
        window.preventHide = True
        menu = TerminalPopupMenu(self)
        menu.show(widget, event, anchor=anchor,
                  skip_link_check=skip_link_check)

    def set_focus_chrome(self, focused, multiple=None):
        """Toggle the focused-pane accent border.

        A single visible pane has nothing to distinguish, so the border
        stays off. ``multiple`` may be passed by a caller that already
        counted the visible panes."""
        if multiple is None:
            multiple = self._focus_border_wanted()
        context = self.get_style_context()
        if focused and multiple:
            context.remove_class('terminator-term-unfocused')
            context.add_class('terminator-term-focused')
        else:
            context.remove_class('terminator-term-focused')
            context.add_class('terminator-term-unfocused')
        redraw = getattr(self, 'queue_draw', None)
        if callable(redraw):
            redraw()

    def _draw_focus_border(self, widget, cr):
        """Stroke the focused pane in its titlebar background colour.

        Painted after the titlebar and VTE, so it does not reserve a CSS
        border. A reserved transparent border shows up black on every pane.
        """
        if not widget.get_style_context().has_class('terminator-term-focused'):
            return False
        window = self.get_toplevel()
        checker = getattr(window, 'is_maximised_pane', None)
        try:
            if callable(checker) and checker(self):
                return False
        except Exception:
            pass
        rgba = Gdk.RGBA()
        try:
            accent = self._focus_ring_color()
        except Exception:
            accent = '#ffffff'
        if not rgba.parse(str(accent)):
            return False
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        if width < 2 or height < 2:
            return False
        cr.save()
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
        cr.set_line_width(1)
        # Inset by half a pixel so the stroke stays inside the clip.
        cr.rectangle(0.5, 0.5, width - 1, height - 1)
        cr.stroke()
        cr.restore()
        return False

    def _focus_ring_color(self):
        """Colour of the focus ring: this pane's titlebar background."""
        bar = getattr(self, 'titlebar', None)
        color = getattr(bar, '_bar_bg', None) if bar is not None else None
        if color:
            return color
        try:
            return self.config['title_transmit_bg_color']
        except Exception:
            return '#ffffff'

    def _focus_border_wanted(self):
        """True when more than one pane is visible in this window."""
        window = self.get_toplevel()
        checker = getattr(window, 'has_multiple_terms', None)
        if not callable(checker):
            return True
        try:
            return bool(checker())
        except Exception:
            return True

    def refresh_visible_focus_chrome(self, focused=None):
        """Light the focus border on one visible pane and clear the rest.

        A focus-in on one VTE does not always deliver focus-out to the
        others, so every pane that was focused before can keep the accent.
        ``focused`` is that pane; when omitted, the VTE that has focus wins."""
        window = self.get_toplevel()
        if not hasattr(window, 'get_visible_terminals'):
            self.set_focus_chrome(False)
            return
        try:
            terminals = list(window.get_visible_terminals())
        except Exception:
            return
        if focused is None:
            focused = self
            for term in terminals:
                vte = getattr(term, 'vte', None)
                try:
                    if vte is not None and vte.is_focus():
                        focused = term
                        break
                except Exception:
                    pass
        multiple = len(terminals) > 1
        for term in terminals:
            if hasattr(term, 'set_focus_chrome'):
                term.set_focus_chrome(term is focused, multiple=multiple)

    def refresh_titlebars_maximise_state(self):
        """Refresh maximise button state of all visible titlebars in our
        window (after split / close / tab switch, focus moves)."""
        window = self.get_toplevel()
        if not hasattr(window, 'get_visible_terminals'):
            return
        try:
            terminals = list(window.get_visible_terminals())
        except Exception:
            return
        # m26 (round2-ux P2-1): one tree walk per refresh, not one per
        # titlebar (was O(N^2) on every focus change: ~33 ms at 64 panes).
        multiple = len(terminals) > 1
        try:
            sig = (tuple(id(t) for t in terminals), bool(window.is_zoomed()),
                   bool(getattr(window, 'is_overlay_maximised',
                                lambda: False)()),
                   id((getattr(window, 'zoom_data', None) or {}).get('widget')))
        except Exception:
            sig = None
        if sig is not None and \
                getattr(window, '_titlebar_max_sig', None) == sig:
            # Plain focus move: nothing structural changed, every button
            # is already right.
            return
        try:
            window._titlebar_max_sig = sig
        except Exception:
            pass
        for term in terminals:
            titlebar = getattr(term, 'titlebar', None)
            if titlebar is None:
                continue
            if hasattr(titlebar, 'update_visibility'):
                try:
                    titlebar.update_visibility(multiple=multiple)
                except TypeError:
                    titlebar.update_visibility()
            if hasattr(titlebar, 'refresh_maximise_state'):
                try:
                    titlebar.refresh_maximise_state(multiple=multiple)
                except TypeError:
                    titlebar.refresh_maximise_state()

    def do_readonly_toggle(self):
        self.vte.props.input_enabled = not self.vte.props.input_enabled

    def do_scrollbar_toggle(self):
        """Show or hide the terminal scrollbar"""
        alt = getattr(self, 'altscreen', None)
        in_tui = alt is not None and alt.detector.active
        if alt is not None:
            alt.user_toggled()
        self.toggle_widget_visibility(self.scrollbar)
        # During a fullscreen program the override lasts only until it
        # exits.  Otherwise the choice sticks until the next reconfigure.
        if in_tui:
            self._scrollbar_forced = None
        else:
            self._scrollbar_forced = bool(self.scrollbar.get_visible())

    def _adjustment_scrollable(self):
        adj = getattr(self, '_vadjustment', None)
        if adj is None:
            try:
                adj = self.vte.get_vadjustment()
            except Exception:
                return False
        try:
            return adjustment_scrollable(adj.get_lower(), adj.get_upper(),
                                         adj.get_page_size())
        except Exception:
            return False

    def _fullscreen_app_may_hide(self):
        """True when a fullscreen program may be about to hide the bar.

        Hiding immediately would drop the width the font scaler reserves
        for that program.  An idle shell (the prompt) is not this case.
        """
        alt = getattr(self, 'altscreen', None)
        if alt is None or alt.user_override or not alt.enabled():
            return False
        if alt.detector.active or alt.auto_hidden:
            return True
        try:
            position = self.config['scrollbar_position']
        except Exception:
            position = 'right'
        if position in ('disabled', 'hidden'):
            return False
        from .altscreen import foreground_busy, tty_raw
        fd = alt._pty_fd()
        if foreground_busy(fd, getattr(self, 'pid', None)) is not True:
            return False
        # Canonical commands (ping, make) are not fullscreen programs.
        return tty_raw(fd) is not False

    def hold_scrollbar_slot(self, width):
        """Keep ``width`` pixels where the scrollbar was.

        The fullscreen hide path does not call this. A visible slot is
        the empty strip beside a TUI; that path records
        ``altscreen.hidden_width`` and lets the VTE take the pixels.
        """
        try:
            width = int(width or 0)
        except (TypeError, ValueError):
            width = 0
        if width <= 0:
            self.release_scrollbar_slot()
            return
        box = getattr(self, 'terminalbox', None)
        if box is None:
            return
        slot = getattr(self, '_scrollbar_slot', None)
        if slot is None:
            slot = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            slot.set_no_show_all(True)
            self._scrollbar_slot = slot
            box.pack_start(slot, False, False, 0)
        slot.set_size_request(width, -1)
        try:
            position = self.config['scrollbar_position']
        except Exception:
            position = 'right'
        if position == 'left':
            box.reorder_child(slot, 0)
        else:
            kids = box.get_children()
            if slot in kids:
                box.reorder_child(slot, len(kids) - 1)
        slot.show()

    def release_scrollbar_slot(self):
        """Drop the reserved scrollbar width."""
        slot = getattr(self, '_scrollbar_slot', None)
        if slot is None:
            return
        try:
            if slot.get_visible():
                slot.hide()
        except Exception:
            pass

    def note_fullscreen_exited(self):
        """The fullscreen program left. Reconcile the font with the pane."""
        self.schedule_auto_font_scale()

    def _scrollbar_slot_held(self):
        slot = getattr(self, '_scrollbar_slot', None)
        try:
            return slot is not None and bool(slot.get_visible())
        except Exception:
            return False

    def _place_scrollbar(self):
        """Pack the scrollbar on the configured side.  Does not show it."""
        if getattr(self, 'scrollbar', None) is None:
            return
        if getattr(self, 'terminalbox', None) is None:
            return
        position = self.config['scrollbar_position']
        if position == 'left':
            self.terminalbox.reorder_child(self.scrollbar, 0)
        elif position == 'right':
            self.terminalbox.reorder_child(self.vte, 0)

    def sync_scrollbar(self, *_args):
        """Show the scrollbar only while there is something to scroll.

        ``left`` and ``right`` are where it appears.  ``hidden`` keeps it
        off.  A manual toggle is kept until preferences are applied again.
        """
        if getattr(self, '_scrollbar_syncing', False):
            # show/hide can emit adjustment "changed" again; re-read once.
            self._scrollbar_sync_again = True
            return
        self._scrollbar_syncing = True
        try:
            for _ in range(2):
                self._scrollbar_sync_again = False
                sb = getattr(self, 'scrollbar', None)
                if sb is None:
                    return
                self._sync_scrollbar(sb)
                if not self._scrollbar_sync_again:
                    break
        finally:
            self._scrollbar_syncing = False

    def _sync_scrollbar(self, sb):
        try:
            position = self.config['scrollbar_position']
        except Exception:
            position = 'right'
        alt = getattr(self, 'altscreen', None)
        alt_latched = bool(alt is not None and
                           (alt.auto_hidden or alt.pending_hidden))
        if alt is not None and alt.pending_hidden:
            alt.sync_deferred = True
        want = scrollbar_should_show(
            position,
            self._adjustment_scrollable(),
            getattr(self, '_scrollbar_forced', None),
            alt_auto_hidden=alt_latched,
            user_override=bool(alt is not None and alt.user_override))
        if want is None:
            return
        if want:
            self._place_scrollbar()
            if alt is not None and alt.auto_hidden:
                release = getattr(alt, '_release_slot', None)
                if callable(release):
                    release()
                alt.auto_hidden = False
                alt.hidden_width = 0
            sb.show()
        else:
            forced = getattr(self, '_scrollbar_forced', None)
            # A TUI can collapse the adjustment a moment before it switches
            # the PTY to raw mode, so the debounced detector has not
            # latched yet. Record this hide (with the width the VTE is
            # about to gain) before the bar goes; otherwise a later
            # apply() sees an invisible bar with no width and one
            # scrollable-looking redraw shows it again, resizing the grid
            # under the program.
            latched = False
            if forced is None and sb.get_visible() and alt is not None:
                note = getattr(alt, 'note_bar_hidden', None)
                if callable(note):
                    latched = bool(note(sb.get_allocated_width()))
            if (not latched and forced is None and sb.get_visible()
                    and self._fullscreen_app_may_hide()):
                # Not confident yet (canonical command, or no evidence of
                # content): let the debounced detector decide instead of
                # hiding on a guess.
                return
            sb.hide()

    def toggle_widget_visibility(self, widget):
        """Show or hide a widget"""
        if widget.get_property('visible'):
            widget.hide()
        else:
            widget.show()

    def on_drag_begin(self, widget, drag_context, _data):
        """Handle the start of a drag event"""
        Gtk.drag_set_icon_pixbuf(drag_context, util.widget_pixbuf(self, 512), 0, 0)

    def on_drag_data_get(self, _widget, _drag_context, selection_data, info,
                         _time, data):
        """I have no idea what this does, drag and drop is a mystery. sorry."""
        selection_data.set(Gdk.atom_intern('vte', False), info,
                           bytes(str(data.terminator.terminals.index(self)),
                                 'utf-8'))

    def on_drag_motion(self, widget, drag_context, x, y, _time, _data):
        """*shrug*"""
        if not drag_context.list_targets() == [Gdk.atom_intern('vte', False)] and \
           (Gtk.targets_include_text(drag_context.list_targets()) or
           Gtk.targets_include_uri(drag_context.list_targets()) or
           Gtk.targets_include_image(drag_context.list_targets(), False)):
            # copy text from another widget
            return
        srcwidget = Gtk.drag_get_source_widget(drag_context)
        if(isinstance(srcwidget, Gtk.EventBox) and
           srcwidget == self.titlebar) or widget == srcwidget:
            # on self
            return

        alloc = widget.get_allocation()

        if self.config['use_theme_colors']:
            color = self.vte.get_style_context().get_color(Gtk.StateType.NORMAL)  # VERIFY FOR GTK3 as above
        else:
            color = Gdk.RGBA()
            color.parse(self.config['foreground_color'])  # VERIFY FOR GTK3

        pos = self.get_location(widget, x, y)
        topleft = (0, 0)
        topright = (alloc.width, 0)
        topmiddle = (alloc.width/2, 0)
        bottomleft = (0, alloc.height)
        bottomright = (alloc.width, alloc.height)
        bottommiddle = (alloc.width/2, alloc.height)
        middleleft = (0, alloc.height/2)
        middleright = (alloc.width, alloc.height/2)

        coord = ()
        if pos == "right":
            coord = (topright, topmiddle, bottommiddle, bottomright)
        elif pos == "top":
            coord = (topleft, topright, middleright , middleleft)
        elif pos == "left":
            coord = (topleft, topmiddle, bottommiddle, bottomleft)
        elif pos == "bottom":
            coord = (bottomleft, bottomright, middleright , middleleft)

        # here, we define some widget internal values
        widget._draw_data = { 'color': color, 'coord' : coord }
        # redraw by forcing an event
        connec = widget.connect_after('draw', self.on_draw)
        widget.queue_draw_area(0, 0, alloc.width, alloc.height)
        widget.get_window().process_updates(True)
        # finally reset the values
        widget.disconnect(connec)
        widget._draw_data = None

    def _background_image_size(self, widget):
        """Logical (w, h) of the background image for widget's scale.

        m34 HiDPI: the image is shown at its native pixel resolution, i.e.
        one image pixel per device pixel, so at GDK_SCALE=2 a 3840px
        wallpaper covers 1920 logical px and 'center'/'tiling' modes stay
        sharp instead of being upscaled 2x.  Done with the cairo device
        scale, so the stretch modes keep working on logical sizes."""
        img = self.background_image
        scale = util.window_scale_factor(widget)
        if getattr(self, '_bg_image_scale', 1) != scale:
            try:
                img.set_device_scale(scale, scale)
                self._bg_image_scale = scale
            except Exception as ex:
                dbg('background image device scale: %s' % ex)
        s = getattr(self, '_bg_image_scale', 1) or 1
        return (img.get_width() / float(s), img.get_height() / float(s))

    def background_draw(self, widget, cr):
        if self.background_image is None:
            return False
        img_w, img_h = self._background_image_size(widget)
        if img_w <= 0 or img_h <= 0:
            return False

        # save cairo context
        cr.save()

        # draw background image
        image_mode = self.config['background_image_mode']
        image_align_horiz = self.config['background_image_align_horiz']
        image_align_vert = self.config['background_image_align_vert']

        rect = widget.get_allocation()
        origin_x = 0
        origin_y = 0
        if self.config['background_image_span_window']:
            toplevel = widget.get_toplevel()
            translated = widget.translate_coordinates(toplevel, 0, 0)
            if translated:
                rect = toplevel.get_allocation()
                origin_x, origin_y = translated

        xratio = float(rect.width) / float(img_w)
        yratio = float(rect.height) / float(img_h)
        if image_mode == 'stretch_and_fill':
            # keep stretched ratios
            xratio = xratio
            yratio = yratio
        elif image_mode == 'scale_and_fit':
            ratio = min(xratio, yratio)
            xratio = yratio = ratio
        elif image_mode == 'scale_and_crop':
            ratio = max(xratio, yratio)
            xratio = yratio = ratio
        else:
            xratio = yratio = 1
        cr.scale(xratio, yratio)

        xoffset = -origin_x / xratio
        yoffset = -origin_y / yratio
        if image_align_horiz == 'center':
            xoffset += (rect.width / xratio -
                        img_w) / 2
        elif image_align_horiz == 'right':
            xoffset += rect.width / xratio - img_w

        if image_align_vert == 'middle':
            yoffset += (rect.height / yratio -
                        img_h) / 2
        elif image_align_vert == 'bottom':
            yoffset += rect.height / yratio - img_h

        cr.set_source_surface(self.background_image, xoffset, yoffset)
        cr.get_source().set_filter(cairo.Filter.FAST)
        if image_mode == 'tiling':
            cr.get_source().set_extend(cairo.Extend.REPEAT)

        cr.paint()

        # draw transparent monochrome layer
        Gdk.cairo_set_source_rgba(cr, self.bgcolor)
        cr.paint()

        # restore cairo context
        cr.restore()

    def on_draw(self, widget, context):
        if not widget._draw_data:
            return False

        color = widget._draw_data['color']
        coord = widget._draw_data['coord']

        context.set_source_rgba(color.red, color.green, color.blue, 0.5)
        if len(coord) > 0:
            context.move_to(coord[len(coord)-1][0], coord[len(coord)-1][1])
            for i in coord:
                context.line_to(i[0], i[1])

        context.fill()
        return False

    def on_drag_data_received(self, widget, drag_context, x, y, selection_data,
            info, _time, data):
        """Something has been dragged into the terminal. Handle it as either a
        URL or another terminal."""
        # FIXME this code is a mess that I don't quite understand how it works.
        dbg('drag data received of type: %s' % (selection_data.get_data_type()))
        # print(selection_data.get_urls())
        if Gtk.targets_include_text(drag_context.list_targets()) or \
           Gtk.targets_include_uri(drag_context.list_targets()):
            # copy text with no modification yet to destination
            txt = selection_data.get_data()
            # https://bugs.launchpad.net/terminator/+bug/1518705
            if info == self.TARGET_TYPE_MOZ:
                 txt = txt.decode('utf-16')
                 # First line only. A title after CR or LF must not reach feed.
                 txt = txt.split('\n', 1)[0].split('\r', 1)[0]
            else:
                 txt = txt.decode()

            txt_lines = txt.split( "\r\n" )
            if txt_lines[-1] == '':
                for line in txt_lines[:-1]:
                    if line[0:7] != 'file://':
                        txt = txt.replace('\r\n','\n')
                        break
                else:
                    # It is a list of crlf terminated file:// URL. let's
                    # iterate over all elements except the last one.
                    str=''
                    for fname in txt_lines[:-1]:
                        fname = "'%s'" % urlunquote(fname[7:].replace("'",
                                                                      '\'\\\'\''))
                        str += fname + ' '
                    txt = str
            # Never send a CRLF to the terminal from here
            txt = txt.rstrip('\r\n')
            for term in self.terminator.get_target_terms(self):
                term.feed(txt)
            return

        if Gtk.targets_include_image(drag_context.list_targets(), False):
            self._drop_image(selection_data)
            return

        widgetsrc = data.terminator.terminals[int(selection_data.get_data())]
        srcvte = Gtk.drag_get_source_widget(drag_context)
        # check if computation requireds
        if (isinstance(srcvte, Gtk.EventBox) and
                srcvte == self.titlebar) or srcvte == widget:
            return

        srchbox = widgetsrc

        # The widget argument is actually a Vte.Terminal(). Turn that into a
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

        # UI review P2-11: a maximised pane (source or target) floats in the
        # overlay frame, not in its slot; snap back before re-parenting.
        for _term in (dsthbox, srchbox):
            _top = _term.get_toplevel()
            if getattr(_top, 'is_maximised_pane', None) and \
                    _top.is_maximised_pane(_term):
                from .zoomguard import leave_zoom
                leave_zoom(_top, legacy=False, overlay=True, reason='dnd')

        from .util import logical_parent as _lp
        dstpaned = _lp(dsthbox)
        srcpaned = _lp(srchbox)

        pos = self.get_location(widget, x, y)

        srcpaned.remove(widgetsrc)
        dstpaned.split_axis(dsthbox, pos in ['top', 'bottom'], None, widgetsrc, pos in ['bottom', 'right'])
        srcpaned.hoover()
        widgetsrc.ensure_visible_and_focussed()

    def _drop_image(self, selection_data):
        """Save a dropped image and feed its path to the target terminals."""
        try:
            pixbuf = selection_data.get_pixbuf()
        except Exception as ex:
            dbg('drop image: %s' % ex)
            return
        if pixbuf is None:
            return
        try:
            path = clipboard_image.save_pixbuf(pixbuf)
        except Exception as ex:
            err('Could not save the dropped image: %s' % ex)
            return
        clipboard_image.prune()
        self._paste_paths([path])

    def get_location(self, term, x, y):
        """Get our location within the terminal"""
        pos = ''
        # get the diagonals function for the receiving widget
        term_alloc = term.get_allocation()
        coef1 = float(term_alloc.height)/float(term_alloc.width)
        coef2 = -float(term_alloc.height)/float(term_alloc.width)
        b1 = 0
        b2 = term_alloc.height
        #determine position in rectangle
        #--------
        #|\    /|
        #| \  / |
        #|  \/  |
        #|  /\  |
        #| /  \ |
        #|/    \|
        #--------
        if (x*coef1 + b1 > y) and (x*coef2 + b2 < y):
            pos = "right"
        if (x*coef1 + b1 > y) and (x*coef2 + b2 > y):
            pos = "top"
        if (x*coef1 + b1 < y) and (x*coef2 + b2 > y):
            pos = "left"
        if (x*coef1 + b1 < y) and (x*coef2 + b2 < y):
            pos = "bottom"
        return pos

    def grab_focus(self):
        """Steal focus for this terminal"""
        if self.vte and not self.vte.has_focus():
            self.vte.grab_focus()

    def ensure_visible_and_focussed(self):
        """Make sure that we're visible and focused"""
        window = self.get_toplevel()
        try:
            topchild = window.get_children()[0]
        except IndexError:
            dbg('unable to get top child')    
            return
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
        self.refresh_visible_focus_chrome(focused=self)
        self.refresh_titlebars_maximise_state()
        self.emit('focus-in')

    def on_vte_focus_out(self, _widget, _event):
        """Inform other parts of the application when focus is lost"""
        self.vte.set_colors(self.fgcolor_inactive, self.bgcolor_inactive,
                            self.palette_inactive)
        self.set_cursor_color()
        self.set_focus_chrome(False)
        self.emit('focus-out')

    def on_window_focus_out(self):
        """Update our UI when the window loses focus"""
        self.titlebar.update('window-focus-out')
        self.set_focus_chrome(False)

    def scrollbar_jump(self, position):
        """Move the scrollbar to a particular row"""
        self.scrollbar.set_value(position)

    def on_search_done(self, _widget):
        """Find dialog closed: leave the viewport on the match."""
        self.vte.grab_focus()

    def on_edit_done(self, _widget):
        """A child widget is done editing a label, return focus to VTE"""
        self.vte.grab_focus()
        # Custom title is persisted in the session layout; only a real
        # change (set, edited, or cleared) should schedule a save.
        try:
            current = self.titlebar.get_custom_string()
        except Exception:
            current = None
        if current != getattr(self, '_session_custom_title', None):
            self._session_custom_title = current
            self._session_mark_dirty('title')

    def deferred_on_vte_size_allocate(self, widget, allocation):
        # widget & allocation are not used in on_vte_size_allocate, so we
        # can use the on_vte_size_allocate instead of duplicating the code
        if self.pending_on_vte_size_allocate:
            return
        self.pending_on_vte_size_allocate = True
        GLib.idle_add(self.do_deferred_on_vte_size_allocate, widget, allocation)

    def do_deferred_on_vte_size_allocate(self, widget, allocation):
        self.pending_on_vte_size_allocate = False
        self.on_vte_size_allocate(widget, allocation)
        return False  # one-shot idle source

    def on_vte_size_allocate(self, widget, allocation):
        self.titlebar.update_terminal_size(self.vte.get_column_count(),
                self.vte.get_row_count())
        # m39: auto font size must run even if geometry hinting fails, and
        # the toplevel may not be a Terminator Window (e.g. mid-reparent).
        try:
            window = self.get_toplevel()
            # Character-cell resize increments are meaningless (and can
            # fight the WM) while auto font size keeps changing the cell.
            if self.config['geometry_hinting'] and \
                    not self._auto_font_enabled():
                hint = getattr(window, 'deferred_set_rough_geometry_hints', None)
            else:
                hint = getattr(window, 'disable_geometry_hints', None)
            if hint is not None:
                hint()
        finally:
            self._auto_font_on_size_allocate()

    def _on_vte_char_size_changed(self, _vte=None, cw=0, ch=0):
        """m40: VTE re-measured its character cell (font zoom, Xft DPI or
        GNOME text-scaling change, our own font_scale tier).  Refresh the
        size readout and geometry hints, and drop a base cell that no
        longer matches so auto font size stops using stale metrics."""
        try:
            self.titlebar.update_terminal_size(self.vte.get_column_count(),
                                               self.vte.get_row_count())
        except Exception:
            pass
        try:
            if self.config['geometry_hinting'] and \
                    not self._auto_font_enabled():
                hint = getattr(self.get_toplevel(),
                               'deferred_set_rough_geometry_hints', None)
                if hint is not None:
                    hint()
        except Exception as ex:
            dbg('char-size-changed hint refresh failed: %s' % ex)
        if self._base_cell is None:
            return
        from .autofont import base_cell_stale
        try:
            scale = float(self.vte.get_font_scale())
            measured = (int(self.vte.get_char_width()),
                        int(self.vte.get_char_height()))
        except Exception:
            return
        # Signal from an older font state (VTE may defer the font update):
        # wait for the emission that matches the live metrics, so a stale
        # emission can never bounce us into a probe/invalidate loop.
        if cw and ch and (int(cw), int(ch)) != measured:
            return
        if not base_cell_stale(self._base_cell, measured, scale):
            return
        dbg('base cell %s stale (now %s at scale %.3f)' %
            (self._base_cell, measured, scale))
        # Scaled zoom swaps in a temporary FontDescription and puts
        # font_scale back to 1. That cell is not the base font; recording
        # it makes the next automatic tier treat the pane as huge type.
        if getattr(self, '_auto_font_mode', None) == 'scaled_zoom':
            return
        if abs(scale - 1.0) < 1e-6:
            self._base_cell = measured
        else:
            self._base_cell = None
        self.schedule_auto_font_scale()

    def on_vte_notify_enter(self, term, event):
        """Handle the mouse entering this terminal"""
        # FIXME: This shouldn't be looking up all these values every time
        sloppy = False
        if self.config['focus'] == 'system':
            sloppy = self.config.get_system_focus() in ['sloppy', 'mouse']
        elif self.config['focus'] in ['sloppy', 'mouse']:
            sloppy = True
        if sloppy and self.titlebar.editing() == False:
            term.grab_focus()
            return False

    def get_zoom_data(self):
        """Return a dict of information for Window"""
        from .util import logical_parent
        alloc = self.vte.get_allocation()
        data = {'old_font': self.vte.get_font().copy(),
                'old_char_height': self.vte.get_char_height(),
                'old_char_width': self.vte.get_char_width(),
                'old_allocation': alloc,
                # Integers, not the rectangle: get_allocation() can hand
                # back storage that later resizes in place.
                'old_alloc_width': int(alloc.width),
                'old_alloc_height': int(alloc.height),
                'old_columns': self.vte.get_column_count(),
                'old_rows': self.vte.get_row_count(),
                'old_parent': logical_parent(self) or self.get_parent()}

        return data

    def cancel_zoom_scale(self):
        """Drop the one-shot font scaler, if it is still connected."""
        self.cnxids.remove_signal(self, 'size-allocate')
        # FIXME: Is a zoom signal actually used anywhere?
        self.cnxids.remove_signal(self, 'zoom')

    def zoom_scale(self, widget, allocation, old_data):
        """Enlarge the font to match the axis this pane grew on.

        A two-way split only grows one side. The previous formula took
        the smaller side and gave up when either side was unchanged, so
        the usual split filled the window and left the text the same size.
        """
        try:
            alloc = self.vte.get_allocation()
            new_w, new_h = int(alloc.width), int(alloc.height)
        except Exception:
            return
        old_w = old_data.get('old_alloc_width')
        old_h = old_data.get('old_alloc_height')
        if not old_w or not old_h:
            old = old_data.get('old_allocation')
            if old is None:
                return
            old_w, old_h = int(old.width), int(old.height)
        factor = zoom_font_scale_factor(old_w, old_h, new_w, new_h)
        if factor is None:
            dbg('zoom scale waiting: %sx%s -> %sx%s' % (
                old_w, old_h, new_w, new_h))
            return
        # Disconnect before set_font: that allocates again, and a second
        # pass would measure the already-scaled grid.
        self.cancel_zoom_scale()
        if factor <= 1.02:
            dbg('zoom scale unchanged: %sx%s -> %sx%s' % (
                old_w, old_h, new_w, new_h))
            return
        new_size = int(old_data['old_font'].get_size() * factor)
        if new_size <= 0:
            err('refusing to set a zero sized font')
            return
        new_font = self.vte.get_font()
        new_font.set_size(new_size)
        dbg('zoom scale %sx%s -> %sx%s factor %.3f font %s' % (
            old_w, old_h, new_w, new_h, factor, new_font))
        self.set_font(new_font)

    def is_zoomed(self):
        """Determine if we are a zoomed terminal"""
        window = self.get_toplevel()
        return window.is_zoomed()

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
            self.cwd = os.path.expanduser(cwd)

    def held_open(self, widget=None, respawn=False, debugserver=False):
        self.is_held_open = True
        self.titlebar.update()

    def spawn_child(self, widget=None, respawn=False, debugserver=False, init_command=None):
        args = []
        shell = None
        command = init_command
        debug_local = False

        if self.terminator.doing_layout:
            dbg('still laying out, refusing to spawn a child')
            return

        # Scrollback restore once per terminal (do not trust respawn — it is
        # often the child-exited status code, not a boolean; see B §3.2).
        if not self._scrollback_restored:
            self._scrollback_restored = True
            try:
                ScrollbackCache().restore_into(self)
            except Exception as ex:
                dbg('scrollback restore failed: %s' % ex)

        if respawn is False:
            self.vte.grab_focus()

        self.is_held_open = False

        options = self.config.options_get()
        if options and options.command:
            command = options.command
            self.relaunch_command = command
            options.command = None
        elif options and options.execute:
            command = options.execute
            self.relaunch_command = command
            options.execute = None
        elif self.relaunch_command:
            command = self.relaunch_command
        elif self.config['use_custom_command']:
            command = self.config['custom_command']
        elif self.layout_command:
            command = self.layout_command
        elif debugserver is True:
            details = self.terminator.debug_address
            if isinstance(details, str) and details:
                from terminatorlib.debugserver import debug_connect_argv
                command = debug_connect_argv(details)
                debug_local = True

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
                args.insert(0, "-l")
            else:
                args.insert(0, shell)

            if command is not None:
                args += ['-c', command]

        if shell is None:
            self.vte.feed(_('Unable to find a shell').encode('utf-8'))
            return -1

        self._export_windowid()

        envv = ['TERM=%s' % self.config['term'],
                'COLORTERM=%s' % self.config['colorterm'], 'PWD=%s' % self.cwd,
                'TERMINATOR_UUID=%s' % self.uuid.urn]
        if self.terminator.dbus_name:
            envv.append('TERMINATOR_DBUS_NAME=%s' % self.terminator.dbus_name)
        if self.terminator.dbus_path:
            envv.append('TERMINATOR_DBUS_PATH=%s' % self.terminator.dbus_path)

        dbg('Forking shell: "%s" with args: %s' % (shell, args))
        args.insert(0, shell)

        if util.is_flatpak():
            if not debug_local:
                dbg('Flatpak detected')
                args = util.get_flatpak_args(args, envv, self.cwd)
                dbg('Forking shell: "%s" with args: %s via flatpak-spawn' % (shell, args))
            # spawn_async is void. The pid arrives in the callback, and a
            # failure must not look like os.kill(-1).
            self.command = shell
            self.vte.spawn_async(
                Vte.PtyFlags.NO_CTTY,
                self.cwd,
                args,
                envv,
                0,
                None,
                None,
                -1,
                None,
                self._on_flatpak_spawned,
                None,
            )
        else:
            result, self.pid = self.vte.spawn_sync(
                    Vte.PtyFlags.DEFAULT,
                    self.cwd,
                    args,
                    envv,
                    GLib.SpawnFlags.FILE_AND_ARGV_ZERO,
                    None,
                    None,
                    None
                    )

        self.command = shell
        self.spawn_time = time.time()
        self.child_exited = False

        self.titlebar.update()

        if self.pid == -1 and not getattr(self, '_flatpak_spawn_reported', False):
            self.vte.feed((_('Unable to start shell:') + shell).encode('utf-8'))
            return -1

    def _on_flatpak_spawned(self, _vte, pid, error, _user_data=None):
        """Flatpak spawn_async callback. VTE gives us the wrapper pid here."""
        if error is not None or not isinstance(pid, int) or pid <= 0:
            self.pid = -1
            if not getattr(self, '_flatpak_spawn_reported', False):
                self._flatpak_spawn_reported = True
                self.vte.feed((_('Unable to start shell:') +
                               (self.command or '')).encode('utf-8'))
        else:
            self.pid = pid

    def prepare_url(self, urlmatch):
        """Prepare a URL from a VTE match"""
        url = urlmatch[0]
        match = urlmatch[1]

        if match == self.matches['addr_only'] and url[0:3] == 'ftp':
            url = 'ftp://' + url
        elif match == self.matches['addr_only']:
            url = 'http://' + url
        elif match in list(self.matches.values()):
            # We have a match, but it's not a hard coded one, so it's a plugin
            try:
                registry = plugin.PluginRegistry()
                registry.load_plugins()
                plugins = registry.get_plugins_by_capability('url_handler')
                dbg("URL handler plugins: {}".format(plugins))

                for urlplugin in plugins:
                    if match == self.matches[urlplugin.handler_name]:
                        try:
                            newurl = urlplugin.callback(url, terminal=self)
                        except TypeError:
                            newurl = urlplugin.callback(url)
                        if newurl: # If the plugin returns None, it's a false match.
                            dbg('URL prepared by %s plugin' \
                                    % urlplugin.handler_name)
                            url = newurl
                        break
            except Exception as ex:
                err('Exception occurred preparing URL: %s, %s' % (type(ex).__name__, ex))

        return url

    def open_url(self, url, prepare=False):
        """Open a given URL, conditionally unpacking it from a VTE match"""
        if prepare:
            url = self.prepare_url(url)
        dbg('URL: %s (prepared: %s)' % (url, prepare))

        # If the URL opening is managed by the plugin: do nothing.
        # (plugins can indicate they manage the URL opening by returning a "terminator://" URI).
        if url.split(":")[0] == "terminator":
            dbg("URL opening is managed by the plugin, do nothing more.")
            return

        # Else, call the URL handler.
        if self.config['use_custom_url_handler']:
            dbg("Using custom URL handler: %s" %
                self.config['custom_url_handler'])
            try:
                subprocess.Popen([self.config['custom_url_handler'], url])
                return
            except:
                dbg('custom url handler did not work, falling back to defaults')

        try:
            Gtk.show_uri(None, url, Gdk.CURRENT_TIME)
            return
        except:
            dbg('Gtk.show_uri did not work, falling through to xdg-open')

        try:
            subprocess.Popen(["xdg-open", url])
        except:
            dbg('xdg-open did not work, falling back to webbrowser.open')
            import webbrowser
            webbrowser.open(url)


    def paste_clipboard(self, primary=False, mouse=False):
        """Paste one of the two clipboards.

        VTE 0.68 only requests text, so an image-only clipboard (a
        screenshot, "Copy image") would paste nothing.  Ask for the
        targets first and, when there is no text but there is an image,
        save it as a PNG and paste its path instead.
        """
        if mouse and self.config['disable_mouse_paste']:
            return

        clipboard = getattr(self, 'clipboard', None)
        # The primary selection is text by convention, and asking for its
        # targets first would add a round trip to middle-click paste (and
        # may never answer where primary selection is unsupported).
        if primary or clipboard is None:
            self._paste_text(primary)
        else:
            clipboard.request_targets(self._on_paste_targets, (primary,))
        if getattr(self, 'vte', None):
            self.vte.grab_focus()

    def _on_paste_targets(self, clipboard, targets, _n_targets, data):
        """Pick the text or image path once the clipboard answers."""
        if not getattr(self, 'vte', None):
            return
        primary, = data
        if targets and Gtk.targets_include_text(targets):
            self._paste_text(primary)
        elif targets and Gtk.targets_include_image(targets, False):
            clipboard.request_image(self._on_paste_image, data)
        else:
            # No text and no image: let VTE try anyway, as before.
            self._paste_text(primary)

    def _on_paste_image(self, _clipboard, pixbuf, data):
        """Save a clipboard image and paste its path."""
        if pixbuf is None or not getattr(self, 'vte', None):
            return
        try:
            path = clipboard_image.save_pixbuf(pixbuf)
        except Exception as ex:
            err('Could not save the clipboard image: %s' % ex)
            return
        clipboard_image.prune()
        self._paste_paths([path])

    def _paste_text(self, primary=False):
        """Paste the clipboard's text into every target terminal."""
        for term in self.terminator.get_target_terms(self):
            if not getattr(term, 'vte', None):
                continue
            # Pasted text may contain a newline that runs a command.
            term._snapshot_before_input()
            if primary:
                term.vte.paste_primary()
            else:
                term.vte.paste_clipboard()

    def _paste_paths(self, paths):
        """Paste shell-quoted paths into every target terminal."""
        text = clipboard_image.paste_text(paths)
        for term in self.terminator.get_target_terms(self):
            vte = getattr(term, 'vte', None)
            if vte is None:
                continue
            if hasattr(vte, 'paste_text'):
                vte.paste_text(text)
            else:
                term.feed(text)

    def feed(self, text):
        """Feed the supplied text to VTE"""
        # Ensure text is bytes for feed_child
        if isinstance(text, str):
            text = text.encode()
        if b'\r' in text or b'\n' in text:
            self._snapshot_before_input()
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

        if fontsize > Pango.SCALE and not zoom_in:
            fontsize -= Pango.SCALE
        elif zoom_in:
            fontsize += Pango.SCALE

        pangodesc.set_size(fontsize)
        self.set_font(pangodesc)
        self.custom_font_size = fontsize
        self._base_cell = None
        self.schedule_auto_font_scale()

    def zoom_orig(self):
        """Restore original font size"""
        if self.config['use_system_font']:
            font = self.config.get_system_mono_font()
        else:
            font = self.config['font']
        dbg("restoring font to: %s" % font)
        self.set_font(Pango.FontDescription(font))
        self.custom_font_size = None
        # D19: Ctrl+0 resets base font only; keep auto tier / do not lock
        self._base_cell = None
        self.schedule_auto_font_scale()

    def set_font(self, fontdesc):
        """Set the font we want in VTE"""
        self.vte.set_font(fontdesc)

    # ---- Auto font scale (M2b / E) ---------------------------------------

    def _auto_font_enabled(self):
        """True when config says on, VTE supports it, and tiers validate."""
        if self._auto_font_disabled:
            return False
        try:
            if not self.config['auto_font_scale']:
                return False
        except Exception:
            return False
        if not hasattr(self.vte, 'set_font_scale') or \
           not hasattr(self.vte, 'get_font_scale'):
            return False
        return True

    def _auto_font_load_params(self):
        """Return (tiers, min_cols, min_rows, hyst, ideal) or None if bad."""
        from .autofont import parse_tiers, validate_auto_font_config
        try:
            raw_tiers = self.config['auto_font_scale_tiers']
            min_cols = int(self.config['reading_measure_min_cols'])
            min_rows = int(self.config['auto_font_scale_min_rows'])
            hyst = float(self.config['auto_font_scale_hysteresis'])
            ideal = int(self.config['reading_measure_ideal_cols'] or 0)
        except Exception as ex:
            dbg('auto_font config read failed: %s' % ex)
            self._auto_font_disabled = True
            return None
        ok, reason = validate_auto_font_config(
            raw_tiers, min_cols, min_rows, hyst, ideal)
        if not ok:
            dbg('auto_font config invalid (%s); disabling' % reason)
            self._auto_font_disabled = True
            return None
        try:
            tiers = parse_tiers(raw_tiers)
        except ValueError as ex:
            dbg('auto_font tiers invalid: %s' % ex)
            self._auto_font_disabled = True
            return None
        return tiers, min_cols, min_rows, hyst, ideal

    def _auto_font_on_size_allocate(self):
        if not self._auto_font_enabled():
            return
        try:
            w = self.vte.get_allocated_width()
            h = self.vte.get_allocated_height()
        except Exception:
            return
        if w <= 0 or h <= 0:
            return
        self._auto_font_ever_allocated = True
        if self._auto_font_mode in ('freeze', 'scaled_zoom'):
            return
        self.schedule_auto_font_scale()

    def schedule_auto_font_scale(self):
        """Debounced recompute. Existing timer is kept (at-most delay)."""
        if not self._auto_font_enabled():
            return
        if self._auto_font_mode != 'run':
            return
        if self._auto_font_timer is not None:
            return
        try:
            delay = int(self.config['auto_font_scale_delay_ms'])
        except Exception:
            delay = 150
        if delay < 0:
            delay = 0
        self._auto_font_timer = GLib.timeout_add(
            delay, self._auto_font_flush_timer)

    def _auto_font_flush_timer(self):
        self._auto_font_timer = None
        self.update_auto_font_scale()
        return False

    def _cancel_auto_font_timer(self):
        if self._auto_font_timer is not None:
            try:
                GLib.source_remove(self._auto_font_timer)
            except Exception:
                pass
            self._auto_font_timer = None

    def _monotonic_ms(self):
        return int(time.monotonic() * 1000)

    def ensure_base_cell(self):
        """Cache (cw, ch) at font_scale==1.0.

        Recover it from the live cell. Flipping the scale to 1.0 to
        measure changes the grid under a TUI, which then draws for a
        column count the pane no longer has.
        """
        if self._base_cell is not None:
            return True
        if not hasattr(self.vte, 'get_font_scale'):
            return False
        try:
            scale = float(self.vte.get_font_scale())
            cw = int(self.vte.get_char_width())
            ch = int(self.vte.get_char_height())
        except Exception:
            return False
        from .autofont import base_cell_from_measured
        cell = base_cell_from_measured((cw, ch), scale)
        if cell is None:
            return False
        self._base_cell = cell
        return True

    def update_auto_font_scale(self, force=False, avail=None):
        """Recompute and maybe apply a tier. avail=(w,h) for D sync path."""
        from .autofont import cols_rows_from_base, select_font_tier
        if not self._auto_font_enabled():
            return
        if self._auto_font_mode != 'run' and not force:
            return
        if self._auto_font_locked:
            if self._font_tier != 0 or force:
                self.apply_tier(0, reason='locked', toast=False)
            else:
                self.refresh_badge()
            return
        # Font used to stay frozen for the whole TUI. After a split drag
        # the narrow pane kept 100% and clipped the program, while the
        # wide pane stayed at a smaller tier. Follow the current size.
        # An idle TUI whose tier is already right never calls set_font_scale.
        if not self._auto_font_ever_allocated and avail is None:
            return
        params = self._auto_font_load_params()
        if not params:
            return
        tiers, min_cols, min_rows, hyst, ideal = params
        if not self.ensure_base_cell():
            return
        if avail is not None:
            w, h = avail
        else:
            try:
                w = self.vte.get_allocated_width()
                h = self.vte.get_allocated_height()
            except Exception:
                return
            # Fullscreen hide gives the bar's width to the VTE and does
            # not reserve a slot.  Subtract it so the font tier does not
            # flip for the duration of the program.  A held slot already
            # keeps the VTE the same size, so subtracting again would
            # shrink it.
            alt = getattr(self, 'altscreen', None)
            hidden = 0
            if alt is not None and not self._scrollbar_slot_held():
                effective = getattr(alt, 'effective_hidden_width', None)
                if callable(effective):
                    hidden = effective()
                elif getattr(alt, 'auto_hidden', False):
                    hidden = getattr(alt, 'hidden_width', 0)
            if hidden > 0:
                w = max(1, w - hidden)
        cols0, rows0 = cols_rows_from_base(w, h, *self._base_cell)
        if cols0 <= 0 or rows0 <= 0:
            return
        if avail is not None:
            pane = avail
        else:
            try:
                pane = (self.get_allocated_width(),
                        self.get_allocated_height())
            except Exception:
                pane = (w, h)
        if self._auto_font_keeps_full_size(*pane):
            new = 0
        else:
            # Same-sized panes share the tier a fresh pane would pick.
            # Hysteresis would otherwise leave one at 90% and one at 100%.
            # avail= is a destination rect, not the live split: don't look
            # for a peer of the current allocation.
            cur = self._font_tier
            if avail is None and self._same_size_font_peer(w, h) is not None:
                cur = 0
            new = select_font_tier(
                cols0, rows0, cur, tiers,
                min_cols, min_rows, hyst, ideal)
        if new == self._font_tier and not force:
            self.refresh_badge()
            return
        if not force and (self._monotonic_ms() - self._auto_font_last_change_ms) < 500:
            self.schedule_auto_font_scale()
            return
        self.apply_tier(new, reason='update', toast=not force)

    def _same_size_font_peer(self, w, h):
        """Another visible terminal whose content box matches (w, h)."""
        from .autofont import same_content_size
        try:
            terms = self.get_toplevel().get_visible_terminals()
        except Exception:
            return None
        for term in terms:
            if term is self or not hasattr(term, 'vte'):
                continue
            try:
                tw = term.vte.get_allocated_width()
                th = term.vte.get_allocated_height()
            except Exception:
                continue
            if same_content_size((w, h), (tw, th)):
                return term
        return None

    def _auto_font_page_size(self):
        """(w, h) of the area this pane shares: the current tab page or the
        window content (the direct child of the Notebook / Window above
        us).  (0, 0) when unknown."""
        node = self
        parent = self.get_parent()
        while parent is not None:
            kind = type(parent).__name__
            if kind in ('Notebook', 'Window') or isinstance(parent, Gtk.Window):
                break
            node = parent
            parent = parent.get_parent()
        if parent is None:
            return (0, 0)   # not in a window yet
        try:
            return node.get_allocated_width(), node.get_allocated_height()
        except Exception:
            return (0, 0)

    def _auto_font_keeps_full_size(self, pane_w, pane_h):
        """m26 P1-3: panes taking >= ~45% of their page (any 2-pane split)
        stay at 100% whatever the reading measure says."""
        from .autofont import keeps_full_size
        try:
            page_w, page_h = self._auto_font_page_size()
        except Exception:
            return False
        return keeps_full_size(pane_w, pane_h, page_w, page_h)

    def apply_tier(self, index, reason='', toast=True):
        """Apply a tier index to VTE and refresh the badge."""
        params = self._auto_font_load_params()
        if not params:
            return
        tiers = params[0]
        index = max(0, min(int(index), len(tiers) - 1))
        scale = tiers[index]
        self._font_tier = index
        if hasattr(self.vte, 'set_font_scale'):
            try:
                self.vte.set_font_scale(scale)
            except Exception as ex:
                dbg('set_font_scale failed: %s' % ex)
                return
        self._auto_font_last_change_ms = self._monotonic_ms()
        self.refresh_badge()
        show_badge = True
        try:
            show_badge = bool(self.config['auto_font_scale_show_badge'])
        except Exception:
            pass
        if (toast and show_badge and scale < 0.999 and
                reason not in ('init', 'd-sync', 'locked') and
                self._autofont_toast_wanted()):
            from .autofont import tier_label
            self.show_center_toast(tier_label(scale))

    def _autofont_toast_wanted(self):
        """UI review P2-7: a window resize crossing a threshold changes the
        tier in every pane at once; only the focused pane (or, while the
        window is unfocused, the last focused one) toasts. The badges
        already show the others' state."""
        try:
            if self.vte.has_focus():
                return True
            return getattr(self.terminator, 'last_focused_term', None) is self
        except Exception:
            return True

    def refresh_badge(self):
        """Push current scale/lock state to the titlebar badge."""
        if not hasattr(self, 'titlebar') or self.titlebar is None:
            return
        if not hasattr(self.titlebar, 'set_scale_badge'):
            return
        show_badge = True
        try:
            show_badge = bool(self.config['auto_font_scale_show_badge'])
        except Exception:
            pass
        if not show_badge or not self._auto_font_enabled():
            self.titlebar.set_scale_badge(None, False)
            return
        locked = bool(self._auto_font_locked)
        scale = 1.0
        params = self._auto_font_load_params()
        if params and 0 <= self._font_tier < len(params[0]):
            scale = params[0][self._font_tier]
        if locked:
            scale = 1.0
        # C API: None or (~1 and not locked) → hide; locked shows lock icon
        badge_scale = None if (scale >= 0.999 and not locked) else scale
        self.titlebar.set_scale_badge(badge_scale, locked)

    def get_auto_font_locked(self):
        return bool(self._auto_font_locked)

    def set_auto_font_locked(self, locked):
        locked = bool(locked)
        if locked == self._auto_font_locked:
            self.refresh_badge()
            return
        self._auto_font_locked = locked
        if locked:
            self.apply_tier(0, reason='locked', toast=False)
        else:
            self.update_auto_font_scale(force=True)
        self.refresh_badge()

    def pause_auto_font_scale(self, mode='freeze'):
        """Pause auto scaling. mode: 'freeze' | 'scaled_zoom'."""
        if mode not in ('freeze', 'scaled_zoom'):
            mode = 'freeze'
        self._cancel_auto_font_timer()
        self._auto_font_mode = mode
        if mode == 'scaled_zoom' and hasattr(self.vte, 'set_font_scale'):
            try:
                self.vte.set_font_scale(1.0)
            except Exception as ex:
                dbg('pause scaled_zoom reset failed: %s' % ex)
            self._font_tier = 0
            self.refresh_badge()

    def resume_auto_font_scale(self, avail=None):
        """Leave pause mode and force a recompute.

        avail=(w, h) is the content size to use instead of the live VTE
        allocation. Overlay arrival passes the landed rect: a resize during
        the animation has already updated that rect, while the VTE
        allocation can still be the size from when the flight started.
        """
        self._auto_font_mode = 'run'
        self.update_auto_font_scale(force=True, avail=avail)

    def compute_tier_for_size(self, w, h):
        """Return the scale D should apply for destination pixels (no VTE write)."""
        from .autofont import cols_rows_from_base, select_font_tier
        if not self._auto_font_enabled():
            return 1.0
        if self._auto_font_locked:
            return 1.0
        params = self._auto_font_load_params()
        if not params:
            return 1.0
        tiers, min_cols, min_rows, hyst, ideal = params
        if not self.ensure_base_cell():
            # Fall back: if we have no cell yet, keep current / 1.0
            return tiers[self._font_tier] if self._font_tier < len(tiers) else 1.0
        cols0, rows0 = cols_rows_from_base(w, h, *self._base_cell)
        if cols0 <= 0 or rows0 <= 0:
            return tiers[self._font_tier] if self._font_tier < len(tiers) else 1.0
        if self._auto_font_keeps_full_size(w, h):
            return tiers[0]
        idx = select_font_tier(
            cols0, rows0, self._font_tier, tiers,
            min_cols, min_rows, hyst, ideal)
        return tiers[idx]

    def apply_font_tier_scale(self, scale, toast=False):
        """D sync path: set VTE scale + tier index in one frame (no debounce)."""
        params = self._auto_font_load_params()
        if not params:
            return
        tiers = params[0]
        try:
            scale = float(scale)
        except (TypeError, ValueError):
            return
        # Snap to nearest configured tier
        best = 0
        best_diff = abs(tiers[0] - scale)
        for i, t in enumerate(tiers):
            d = abs(t - scale)
            if d < best_diff:
                best = i
                best_diff = d
        self.apply_tier(best, reason='d-sync', toast=bool(toast))

    def get_auto_font_scale(self):
        params = self._auto_font_load_params()
        if not params:
            return 1.0
        tiers = params[0]
        if self._auto_font_locked:
            return 1.0
        if 0 <= self._font_tier < len(tiers):
            return tiers[self._font_tier]
        return 1.0

    def show_center_toast(self, text):
        """Brief centered toast inside the Terminal overlay (not Window)."""
        overlay = getattr(self, '_term_overlay', None)
        if overlay is None:
            return
        if self._autofont_toast_timer is not None:
            try:
                GLib.source_remove(self._autofont_toast_timer)
            except Exception:
                pass
            self._autofont_toast_timer = None
        if self._autofont_toast is not None:
            try:
                overlay.remove(self._autofont_toast)
            except Exception:
                pass
            self._autofont_toast = None
        label = Gtk.Label(label=str(text))
        label.set_halign(Gtk.Align.CENTER)
        label.set_valign(Gtk.Align.CENTER)
        label.set_sensitive(False)
        label.set_can_focus(False)
        try:
            label.set_margin_bottom(24)
        except Exception:
            pass
        try:
            label.get_style_context().add_provider(
                _autofont_toast_css(), Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            label.get_style_context().add_class('terminator-autofont-toast')
        except Exception as ex:
            dbg('autofont toast css: %s' % ex)
        label.show()
        overlay.add_overlay(label)
        try:
            overlay.set_overlay_pass_through(label, True)
        except Exception:
            pass
        self._autofont_toast = label

        def _hide():
            self._autofont_toast_timer = None
            if self._autofont_toast is label:
                try:
                    overlay.remove(label)
                except Exception:
                    pass
                self._autofont_toast = None
            return False

        self._autofont_toast_timer = GLib.timeout_add(800, _hide)

    def _ensure_scale_popover(self):
        """Build the badge popover once (C owns the button, E owns content)."""
        if self._scale_popover is not None:
            return
        if not hasattr(self, 'titlebar') or self.titlebar is None:
            return
        if not hasattr(self.titlebar, 'scale_badge'):
            return
        btn = self.titlebar.scale_badge
        try:
            pop = Gtk.Popover.new(btn)
        except Exception as ex:
            dbg('scale popover create failed: %s' % ex)
            return
        box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 6)
        box.set_border_width(10)
        blurb = Gtk.Label(label=_('Auto font size follows reading measure.'))
        blurb.set_line_wrap(True)
        blurb.set_max_width_chars(32)
        blurb.set_halign(Gtk.Align.START)
        box.pack_start(blurb, False, False, 0)

        lock = Gtk.CheckButton.new_with_mnemonic(
            _('_Lock font size for this terminal'))
        lock.set_active(bool(self._auto_font_locked))

        def _on_lock_toggled(button):
            self.set_auto_font_locked(button.get_active())

        lock_handler = lock.connect('toggled', _on_lock_toggled)
        box.pack_start(lock, False, False, 0)

        disable = Gtk.Button.new_with_mnemonic(_('_Disable auto font size'))

        def _on_disable(_button):
            try:
                self.config['auto_font_scale'] = False
                self.config.save()
            except Exception as ex:
                dbg('disable auto_font_scale save: %s' % ex)
            for term in list(self.terminator.terminals):
                if hasattr(term, 'on_auto_font_globally_disabled'):
                    term.on_auto_font_globally_disabled()
            try:
                pop.popdown()
            except Exception:
                pass

        disable.connect('clicked', _on_disable)
        box.pack_start(disable, False, False, 0)

        prefs = Gtk.Button.new_with_mnemonic(_('_Preferences…'))

        def _on_prefs(_button):
            try:
                PrefsEditor(self)
            except Exception as ex:
                dbg('PrefsEditor from scale popover: %s' % ex)
            try:
                pop.popdown()
            except Exception:
                pass

        prefs.connect('clicked', _on_prefs)
        box.pack_start(prefs, False, False, 0)

        box.show_all()
        pop.add(box)

        def _on_badge_clicked(*_a):
            # Refresh lock toggle without re-entrancy
            lock.handler_block(lock_handler)
            try:
                lock.set_active(bool(self._auto_font_locked))
            finally:
                lock.handler_unblock(lock_handler)
            pop.popup()
            return True

        btn.connect('clicked', _on_badge_clicked)
        self._scale_popover = pop
        self._scale_popover_lock = lock

    def on_auto_font_config_changed(self):
        """Re-apply auto font after prefs changed (toggle/badge/measure)."""
        try:
            enabled = bool(self.config['auto_font_scale'])
        except Exception:
            enabled = False
        if not enabled:
            self.on_auto_font_globally_disabled()
            return
        # Clear an earlier invalid-config latch; params are re-validated.
        self._auto_font_disabled = False
        self.refresh_badge()
        self.update_auto_font_scale(force=True)

    def on_auto_font_globally_disabled(self):
        """Reset this terminal after config auto_font_scale was turned off."""
        self._cancel_auto_font_timer()
        self._auto_font_locked = False
        self._font_tier = 0
        if hasattr(self.vte, 'set_font_scale'):
            try:
                self.vte.set_font_scale(1.0)
            except Exception:
                pass
        self.refresh_badge()

    def _on_autofont_hierarchy_changed(self, *_args):
        self._connect_pane_maximise_signal()

    def _connect_pane_maximise_signal(self):
        """Listen for Window.pane-maximise-changed (refresh badge; D drives pause)."""
        win = self.get_toplevel()
        if win is self._pane_maximise_window:
            return
        if self._pane_maximise_handler is not None and \
           self._pane_maximise_window is not None:
            try:
                self._pane_maximise_window.disconnect(self._pane_maximise_handler)
            except Exception:
                pass
            self._pane_maximise_handler = None
            self._pane_maximise_window = None
        if not isinstance(win, Gtk.Window):
            return
        if not hasattr(win, 'connect'):
            return
        # Signal may be missing on older Window; guard with lookup
        try:
            from gi.repository import GObject as _GObject
            if not _GObject.signal_lookup('pane-maximise-changed', type(win)):
                return
        except Exception:
            return
        try:
            handler = win.connect('pane-maximise-changed',
                                  self._on_pane_maximise_changed)
        except Exception as ex:
            dbg('pane-maximise-changed connect: %s' % ex)
            return
        self._pane_maximise_handler = handler
        self._pane_maximise_window = win

    def _on_pane_maximise_changed(self, window, terminal, maximised):
        if terminal is not self:
            return
        # D owns pause/apply; E only refreshes chrome here.
        self.refresh_badge()


    def get_cursor_position(self):
        """Return the coordinates of our cursor"""
        # FIXME: THIS METHOD IS DEPRECATED AND UNUSED
        col, row = self.vte.get_cursor_position()
        width = self.vte.get_char_width()
        height = self.vte.get_char_height()
        return col * width, row * height

    def get_font_size(self):
        """Return the width/height of our font"""
        return self.vte.get_char_width(), self.vte.get_char_height()

    def get_size(self):
        """Return the column/rows of the terminal"""
        return self.vte.get_column_count(), self.vte.get_row_count()

    def on_bell(self, widget):
        """Set the urgency hint/icon/flash for our window"""
        if self.config['urgent_bell']:
            window = self.get_toplevel()
            if window.is_toplevel():
                window.set_urgency_hint(True)
        if self.config['icon_bell']:
            self.titlebar.icon_bell()
        if self.config['visible_bell']:
            # Repurposed the code used for drag and drop overlay to provide a visual terminal flash
            alloc = widget.get_allocation()

            if self.config['use_theme_colors']:
                color = self.vte.get_style_context().get_color(Gtk.StateType.NORMAL)  # VERIFY FOR GTK3 as above
            else:
                color = Gdk.RGBA()
                color.parse(self.config['foreground_color'])  # VERIFY FOR GTK3

            coord = ((0, 0), (alloc.width, 0), (alloc.width, alloc.height), (0, alloc.height))

            # here, we define some widget internal values
            widget._draw_data = { 'color': color, 'coord' : coord }
            # redraw by forcing an event
            connec = widget.connect_after('draw', self.on_draw)
            widget.queue_draw_area(0, 0, alloc.width, alloc.height)
            widget.get_window().process_updates(True)
            # finally reset the values
            widget.disconnect(connec)
            widget._draw_data = None

            # Add timeout to clean up display
            GLib.timeout_add(100, self.on_bell_cleanup, widget, alloc)

    def on_bell_cleanup(self, widget, alloc):
        """Queue a redraw to clear the visual flash overlay"""
        widget.queue_draw_area(0, 0, alloc.width, alloc.height)
        widget.get_window().process_updates(True)
        return False

    def describe_layout(self, count, parent, global_layout, child_order, save_cwd = False):
        """Describe our layout"""
        layout = {'type': 'Terminal', 'parent': parent, 'order': child_order}
        if self.group:
            layout['group'] = self.group
        profile = self.get_profile()
        if profile != "default":
            # There's no point explicitly noting default profiles
            layout['profile'] = profile
        title = self.titlebar.get_custom_string()
        if title:
            layout['title'] = title
        layout['uuid'] = self.uuid
        if save_cwd:
            cwd = self.get_cwd()
            if cwd:
                layout['directory'] = cwd
        # m25: per-terminal font state, only when user changed it
        if self.custom_font_size:
            layout['font_size'] = str(int(self.custom_font_size))
        if self._auto_font_locked:
            layout['auto_font_locked'] = 'True'
        name = 'terminal%d' % count
        count = count + 1
        global_layout[name] = layout
        return count

    def create_layout(self, layout):
        """Apply our layout"""
        dbg('Setting layout')
        if 'command' in layout and layout['command'] != '':
            self.layout_command = layout['command']
        if 'profile' in layout and layout['profile'] != '':
            if layout['profile'] in self.config.list_profiles():
                self.set_profile(self, layout['profile'])
        if 'group' in layout and layout['group'] != '':
            # This doesn't need/use self.titlebar, but it's safer than sending
            # None
            self.really_create_group(self.titlebar, layout['group'])
        if 'title' in layout and layout['title'] != '':
            self.titlebar.set_custom_string(layout['title'])
            self._session_custom_title = layout['title']
        if 'directory' in layout and layout['directory'] != '':
            self.directory = layout['directory']
        if 'uuid' in layout and layout['uuid'] != '':
            wanted = make_uuid(layout['uuid'])
            # Round-2 P1-3: never take the uuid of another live terminal
            # (shared scrollback cache file, wrong DBus/focus lookups).
            if any(t is not self and getattr(t, 'uuid', None) == wanted
                   for t in self.terminator.terminals):
                dbg('layout uuid %s already in use, keeping fresh %s' %
                    (wanted, self.uuid))
            else:
                self.uuid = wanted
        if layout.get('maximised_pane') == 'True':
            self._restore_maximised = True
        self._restore_font_state(layout)

    # Pango units; 1pt..512pt keeps corrupt sessions from wrecking the UI
    _FONT_SIZE_MIN = Pango.SCALE
    _FONT_SIZE_MAX = 512 * Pango.SCALE

    def _restore_font_state(self, layout):
        """m25: apply saved font_size / auto_font_locked (both optional;
        older sessions lack them). Runs before the first auto-font pass."""
        raw = layout.get('font_size')
        if raw not in (None, ''):
            try:
                size = int(str(raw).strip())
            except (TypeError, ValueError):
                size = None
            if size is not None and \
                    self._FONT_SIZE_MIN <= size <= self._FONT_SIZE_MAX:
                try:
                    desc = self.vte.get_font()
                    if desc is not None:
                        desc = desc.copy()
                        desc.set_size(size)
                        self.set_font(desc)
                    self.custom_font_size = size
                    self._base_cell = None
                except Exception as ex:
                    dbg('font_size restore failed: %s' % ex)
            else:
                dbg('ignoring invalid saved font_size %r' % (raw,))
        locked = layout.get('auto_font_locked')
        if str(locked).strip().lower() == 'true':
            # Set the flag directly: set_auto_font_locked() would trigger
            # apply_tier; at restore time tier is still 0 anyway.
            self._auto_font_locked = True
            try:
                self.refresh_badge()
            except Exception:
                pass

    def scroll_by_page(self, pages):
        """Scroll up or down in pages"""
        amount = pages * self.vte.get_vadjustment().get_page_increment()
        self.scroll_by(int(amount))

    def scroll_by_line(self, lines):
        """Scroll up or down in lines"""
        amount = lines * self.vte.get_vadjustment().get_step_increment()
        self.scroll_by(int(amount))

    def scroll_by(self, amount):
        """Scroll up or down by an amount of lines"""
        adjustment = self.vte.get_vadjustment()
        bottom = adjustment.get_upper() - adjustment.get_page_size()
        value = adjustment.get_value() + amount
        adjustment.set_value(min(value, bottom))

    def get_allocation(self):
        """Get a real allocation which includes the bloody x and y coordinates
        (grumble, grumble) """
        alloc = super(Terminal, self).get_allocation()
        rv = self.translate_coordinates(self.get_toplevel(), 0, 0)
        if rv:
            alloc.x, alloc.y = rv
        return alloc

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
        if self.config['clear_select_on_copy']:
            self.vte.unselect_all()

    def key_paste(self):
        self.paste_clipboard()

    def key_paste_selection(self):
        self.paste_clipboard(True)

    def key_send_newline(self):
        self.feed('\n')

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
    def key_zoom_in_all(self):
        self.terminator.zoom_in_all()

    def key_zoom_out_all(self):
        self.terminator.zoom_out_all()
        
    def key_zoom_normal_all(self):
        self.terminator.zoom_orig_all()

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

    def key_split_auto(self):
        self.emit('split-auto', self.get_cwd())

    def key_split_horiz(self):
        self.emit('split-horiz', self.get_cwd())

    def key_split_vert(self):
        self.emit('split-vert', self.get_cwd())

    def key_rotate_cw(self):
        self.emit('rotate-cw')

    def key_rotate_ccw(self):
        self.emit('rotate-ccw')

    def key_close_term(self):
        from .close_confirm import request_close_terminal
        btn = getattr(getattr(self, 'titlebar', None), 'btn_close', None)
        anchor = btn if (btn is not None and getattr(btn, 'get_visible', lambda: False)()) else None
        try:
            request_close_terminal(self, anchor_widget=anchor)
        except TypeError:
            request_close_terminal(self)

    def _session_mark_dirty(self, reason='cwd'):
        try:
            from .session import try_mark_dirty
            try_mark_dirty(reason)
        except Exception:
            pass

    def _session_mark_dirty_cwd(self):
        self._session_mark_dirty('cwd')

    CWD_PROBE_DELAY_MS = 800

    def _on_contents_changed_cwd_probe(self, *_args):
        """Throttled: at most one pending cwd probe per terminal."""
        if getattr(self, '_cwd_probe_timer', None):
            return
        try:
            self._cwd_probe_timer = GLib.timeout_add(
                self.CWD_PROBE_DELAY_MS, self._cwd_probe_fire)
        except Exception:
            self._cwd_probe_timer = None

    def _cwd_probe_fire(self):
        self._cwd_probe_timer = None
        self.cwd_probe_check()
        return False

    def cwd_probe_check(self):
        """Mark session dirty if the shell's cwd changed since last probe."""
        try:
            if self.pid is None:
                return False
            # m26 (round2-ux P2-2): a fullscreen TUI (top, vim, ...) has the
            # shell waiting in the background: its cwd cannot change, and
            # the TUI's redraws would probe every 800 ms for nothing.  The
            # first contents change after the TUI exits probes again.
            alt = getattr(self, 'altscreen', None)
            if alt is not None and getattr(alt.detector, 'active', False):
                return False
            cwd = get_pid_cwd(self.pid)
        except Exception:
            return False
        if not cwd:
            return False
        last = getattr(self, '_last_session_cwd', None)
        self._last_session_cwd = cwd
        if last is not None and last != cwd:
            self._session_mark_dirty('cwd-probe')
            # The tab name follows this directory. The shell title often
            # lags a cd, so refresh it from here too. A half-built
            # terminal has no signal table; the dirty mark still stands.
            try:
                self.emit('title-change', self.get_window_title())
            except Exception:
                pass
            return True
        return False

    def _note_child_exited(self):
        """Forget the dead child's pid: close confirmation must not report
        it as '<unknown>' (or an unrelated process if the pid is reused),
        and close() must not SIGHUP a recycled pid."""
        self.pid = None
        self.child_exited = True

    def _on_child_exited_restart(self, _vte, _status):
        """child-exited → respawn shell (exit_action=restart)."""
        self._note_child_exited()
        self.spawn_child(respawn=True)

    def _on_child_exited_hold(self, _vte, _status):
        """child-exited → keep VTE open (exit_action=hold)."""
        self._note_child_exited()
        self.held_open(respawn=True)

    def _on_child_exited_close(self, _vte, _status):
        """child-exited → close the terminal (exit_action=close/left)."""
        self._note_child_exited()
        self.emit('close-term')

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

    def key_detach_tab(self):
        self.emit('detach-tab')

    def key_toggle_zoom(self):
        if self.is_zoomed():
            self.unzoom()
        else:
            self.maximise()

    def key_maximise(self):
        """Default maximise shortcut: toggle single-pane overlay maximise."""
        self.key_toggle_zoom()

    def key_zoom(self):
        if not self.is_zoomed():
            self.zoom()

    def key_unzoom(self):
        if self.is_zoomed():
            self.unzoom()

    def key_restore_maximised(self):
        """Shift+Esc: restore overlay/legacy maximise only when zoomed."""
        if self.is_zoomed():
            self.unzoom()

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
        try:
            if self.uuid is not None:
                ScrollbackCache().delete_uuid(str(self.uuid))
        except Exception as ex:
            dbg('scrollback reset_clear failed: %s' % ex)

    def key_create_group(self):
        self.titlebar.create_group()

    def key_group_all(self):
        self.emit('group-all')

    def key_group_all_toggle(self):
        self.emit('group-all-toggle')

    def key_ungroup_all(self):
        self.emit('ungroup-all')

    def key_group_win(self):
        dbg("Group Win")
        self.emit('group-win')

    def key_group_win_toggle(self):
        self.emit('group-win-toggle')

    def key_ungroup_win(self):
        self.emit('ungroup-win')

    def key_group_tab(self):
        self.emit('group-tab')

    def key_group_tab_toggle(self):
        self.emit('group-tab-toggle')

    def key_ungroup_tab(self):
        self.emit('ungroup-tab')

    def key_new_window(self):
        self.terminator.new_window(self.get_cwd(), self.get_profile())

    def key_new_tab(self, init_command=None):
        self.get_toplevel().tab_new(self, init_command=init_command)

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
        dialog = Gtk.Dialog(_('Rename Window'), window,
                            Gtk.DialogFlags.MODAL,
                            (Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT,
                             Gtk.STOCK_OK, Gtk.ResponseType.ACCEPT))
        dialog.set_default_response(Gtk.ResponseType.ACCEPT)
        dialog.set_resizable(False)
        dialog.set_border_width(8)

        label = Gtk.Label(label=_('Enter a new title for the Terminator window...'))
        name = Gtk.Entry()
        name.set_activates_default(True)
        if window.title.text != self.vte.get_window_title():
            name.set_text(self.get_toplevel().title.text)

        dialog.vbox.pack_start(label, False, False, 6)
        dialog.vbox.pack_start(name, False, False, 6)

        dialog.show_all()
        res = dialog.run()
        if res == Gtk.ResponseType.ACCEPT:
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

    def key_preferences(self):
        PrefsEditor(self)

    def key_preferences_keybindings(self):
        PrefsEditor(self, cur_page='keybindings')

    def key_help(self):
        manual_index_page = manual_lookup()
        if manual_index_page:
            self.open_url(manual_index_page)

# End key events


GObject.type_register(Terminal)
# vim: set expandtab ts=4 sw=4:
