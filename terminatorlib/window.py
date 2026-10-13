# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""window.py - class for the main Terminator window"""

import copy
import time
import uuid
import gi
from gi.repository import GLib, GObject
from gi.repository import Gtk, Gdk

from .zoomguard import leave_zoom
from .util import dbg, err, make_uuid, display_manager, is_x11, layout_root_widget

try:
    from gi.repository import GdkX11
except ImportError:
    dbg("could not import X11 gir module")


from . import util
from .translation import _
from .version import APP_NAME
from .container import Container
from .factory import Factory
from .terminator import Terminator
# m34: decided by the opened GdkDisplay (XWayland counts as X11; a
# native Wayland window cannot grab global keys at all).
if display_manager() == 'X11':
    try:
        gi.require_version('Keybinder', '3.0')
        from gi.repository import Keybinder
        Keybinder.init()
        Keybinder.set_use_cooked_accelerators(False)
    except (ImportError, ValueError):
        err('Unable to load Keybinder module. This means the \
hide_window shortcut will be unavailable')

# pylint: disable-msg=R0904
class Window(Container, Gtk.Window):
    """Class implementing a top-level Terminator window"""

    terminator = None
    title = None
    isfullscreen = None
    ismaximised = None
    isDestroyed = False
    hidebound = None
    hidefunc = None
    losefocus_time = 0
    position = None
    ignore_startup_show = None
    set_pos_by_ratio = None
    last_active_term = None
    preventHide = None
    # m34: the window was iconified by on_hide_window/hide-on-lose-focus
    # (no global hotkey -> hidefunc is iconify), so the next toggle must
    # bring it back instead of iconifying again.  Needed on Wayland, where
    # GDK never reports the ICONIFIED state.
    _iconified_by_hide = False

    zoom_data = None

    term_zoomed = False

    # Contract owned by module D (overlay maximise). Until D lands this is a
    # same-signature shim emitted from the legacy zoom/unzoom paths.
    #   pane-maximise-changed(terminal, maximised: bool)
    __gsignals__ = {
            'pane-maximise-changed': (GObject.SignalFlags.RUN_LAST, None,
                                      (GObject.TYPE_PYOBJECT,
                                       GObject.TYPE_BOOLEAN)),
    }

    __gproperties__ = {
            'term_zoomed': (GObject.TYPE_BOOLEAN,
                            'terminal zoomed',
                            'whether the terminal is zoomed',
                            False,
                            GObject.ParamFlags.READWRITE)
    }

    def __init__(self):
        """Class initialiser"""
        # Must be set before register_callbacks/apply_config: those can
        # trigger Terminator.reconfigure → get_child(), which reads _overlay.
        self._overlay = None  # module D OverlayController (lazy)
        self.terminator = Terminator()
        self.terminator.register_window(self)

        Container.__init__(self)
        GObject.GObject.__init__(self)
        GObject.type_register(Window)
        self.register_signals(Window)

        self.get_style_context().add_class("terminator-terminal-window")

#        self.set_property('allow-shrink', True)  # FIXME FOR GTK3, or do we need this actually?
        icon_to_apply=''

        self.register_callbacks()
        self.apply_config()

        self.title = WindowTitle(self)
        self.title.update()
        
        self.preventHide = False

        options = self.config.options_get()
        if options:
            if options.forcedtitle:
                self.title.force_title(options.forcedtitle, persist=False)

            if options.role:
                self.set_role(options.role)
            
            if options.forcedicon is not None:
                icon_to_apply = options.forcedicon

            if options.geometry:
                if not self.parse_geometry(options.geometry):
                    err('Window::__init__: Unable to parse geometry: %s' % 
                            options.geometry)

        self.apply_icon(icon_to_apply)
        self.pending_set_rough_geometry_hint = False
        # m34: register_callbacks() above already chose hidefunc (iconify
        # when the global hotkey can't be bound / on Wayland); upstream
        # overwrote that with hide() here, so the fallback never applied.
        if self.hidefunc is None:
            self.hidefunc = self.hide

    def do_get_property(self, prop):
        """Handle gobject getting a property"""
        if prop.name in ['term_zoomed', 'term-zoomed']:
            return(self.term_zoomed)
        else:
            raise AttributeError('unknown property %s' % prop.name)

    def do_set_property(self, prop, value):
        """Handle gobject setting a property"""
        if prop.name in ['term_zoomed', 'term-zoomed']:
            self.term_zoomed = value
        else:
            raise AttributeError('unknown property %s' % prop.name)

    def register_callbacks(self):
        """Connect the GTK+ signals we care about"""
        self.connect('key-press-event', self.on_key_press)
        self.connect('button-press-event', self.on_button_press)
        self.connect('delete_event', self.on_delete_event)
        self.connect('destroy', self.on_destroy_event)
        self.connect('window-state-event', self.on_window_state_changed)
        self.connect('configure-event', self.on_configure_event)
        self.connect('focus-out-event', self.on_focus_out)
        self.connect('focus-in-event', self.on_focus_in)
        # Window-title ownership: follow the focus widget inside this window
        # (fires on every grab_focus, even when the toplevel is inactive).
        self.connect('set-focus', self.on_set_focus)
        self.connect('realize', self.on_window_realize)
        self._session_last_configure = None
        try:
            self.connect('pane-maximise-changed', self.on_pane_maximise_changed)
        except TypeError:
            # Signal registered by module D; ignore until then
            pass

        # Attempt to grab a global hotkey for hiding the window.
        # If we fail, we'll never hide the window, iconifying instead.
        if self.config['keybindings']['hide_window'] not in ('', None):
            if self.can_set_position():
                try:
                    self.hidebound = Keybinder.bind(
                        self.config['keybindings']['hide_window'],
                        self.on_hide_window)
                except (KeyError, NameError):
                    pass

                if not self.hidebound:
                    err('Unable to bind hide_window key, another instance/window has it.')
                    self.hidefunc = self.iconify
                else:
                    self.hidefunc = self.hide
            else:
                # m34: no global hotkey on Wayland.  hide() would leave the
                # window unreachable except via DBus (remotinator), so
                # hide-on-lose-focus / the toggle iconify instead, like
                # the X11 path when the key is taken.
                dbg('hide_window: no global hotkey on %s; iconify instead '
                    'of hide' % display_manager(self.get_display()))
                self.hidefunc = self.iconify

    def can_set_position(self):
        """m34: True when window positions can be read and set (X11 /
        XWayland).  Wayland clients cannot place their toplevels and
        get_position() returns meaningless numbers there."""
        try:
            return is_x11(self.get_display())
        except Exception:
            return is_x11()

    def _remember_position(self):
        """Save the position for a later re-show (X11 only)."""
        if self.can_set_position():
            self.position = self.get_position()
        else:
            self.position = None

    def _server_time(self):
        """X server timestamp for focus(), 0 elsewhere (m34: Wayland)."""
        gdkwin = self.get_window()
        if gdkwin is None or not self.can_set_position():
            return 0
        try:
            return GdkX11.x11_get_server_time(gdkwin)
        except (NameError, TypeError, AttributeError):
            return 0

    def _run_hidefunc(self):
        if self.hidefunc == self.iconify:
            self._iconified_by_hide = True
        self.hidefunc()

    def apply_config(self):
        """Apply various configuration options"""
        options = self.config.options_get()
        maximise = self.config['window_state'] == 'maximise'
        fullscreen = self.config['window_state'] == 'fullscreen'
        hidden = self.config['window_state'] == 'hidden'
        borderless = self.config['borderless']
        skiptaskbar = self.config['hide_from_taskbar']
        alwaysontop = self.config['always_on_top']
        sticky = self.config['sticky']

        if options:
            if options.maximise:
                maximise = True
            if options.fullscreen:
                fullscreen = True
            if options.hidden:
                hidden = True
            if options.borderless:
                borderless = True

        self.set_fullscreen(fullscreen)
        self.set_maximised(maximise)
        self.set_borderless(borderless)
        self.set_always_on_top(alwaysontop)
        self.set_real_transparency()
        self.set_sticky(sticky)
        self.apply_window_decoration_style(self.config['window_decoration_style'])
        if self.hidebound:
            self.set_hidden(hidden)
            self.set_skip_taskbar_hint(skiptaskbar)
        else:
            self.set_iconified(hidden)

    def apply_icon(self, requested_icon):
        """Set the window icon"""
        icon_theme = Gtk.IconTheme.get_default()
        from .util import add_source_icon_path
        add_source_icon_path(icon_theme)
        icon_name_list = [APP_NAME]   # disable self.wmclass_name, n/a in GTK3

        if requested_icon:
            try:
                self.set_icon_from_file(requested_icon)
                return
            except (NameError, GObject.GError):
                dbg('Unable to load %s icon as file' % (repr(requested_icon)))

            icon_name_list.insert(0, requested_icon)

        for icon_name in icon_name_list:
            # Test if the icon is available first
            if icon_theme.lookup_icon(icon_name, 48, 0):
                self.set_icon_name(icon_name)
                return # Success! We're done.
            else:
                dbg('Unable to load %s icon' % (icon_name))

        icon = self.render_icon(Gtk.STOCK_DIALOG_INFO, Gtk.IconSize.BUTTON)
        self.set_icon(icon)

    def on_key_press(self, window, event):
        """Handle a keyboard event"""
        maker = Factory()

        self.set_urgency_hint(False)

        mapping = self.terminator.keybindings.lookup(event)

        if mapping:
            dbg('looked up %r' % mapping)
            if mapping == 'full_screen':
                self.set_fullscreen(not self.isfullscreen)
            elif mapping == 'close_window':
                if not self.on_delete_event(window,
                        Gdk.Event.new(Gdk.EventType.DELETE)):
                    self.on_destroy_event(window,
                            Gdk.Event.new(Gdk.EventType.DESTROY))
            else:
                return(False)
            return(True)

    def on_button_press(self, window, event):
        """Handle a mouse button event. Mainly this is just a clean way to
        cancel any urgency hints that are set."""
        self.set_urgency_hint(False)
        return(False)

    def on_focus_out(self, window, event):
        """Focus has left the window"""
        for terminal in self.get_visible_terminals():
            terminal.on_window_focus_out()

        self.losefocus_time = time.time()

        if self.preventHide:
            self.preventHide = False
        else:
            if self.config['hide_on_lose_focus'] and self.get_property('visible'):
                self._remember_position()
                self._run_hidefunc()

    def on_set_focus(self, _window, widget):
        """The focus widget inside this window changed. If it belongs to a
        terminal, that terminal now owns the window title. Focus on chrome
        outside any terminal (overlay frame, notebook tabs) or None keeps the
        previous owner."""
        title = getattr(self, 'title', None)
        if title is None:
            return
        terminal = terminal_for_widget(widget) if widget is not None else None
        if terminal is not None:
            title.focus_changed(terminal)
        else:
            # Focus widget unset (e.g. owner removed/detached to another
            # window): hand ownership on if the owner has left us.
            title.revalidate()

    def on_focus_in(self, window, event):
        """Focus has entered the window"""
        self.set_urgency_hint(False)
        self._iconified_by_hide = False
        if not self.terminator.doing_layout:
            self.terminator.last_active_window = self.uuid
        # Window focus-out dimmed every pane. Light only the focused one again.
        term = None
        try:
            term = self.terminator.get_focussed_terminal()
        except Exception:
            term = None
        if term is None or term.get_toplevel() is not self:
            term = getattr(self.terminator, 'last_focused_term', None)
        if term is not None and term.get_toplevel() is self:
            if hasattr(term, 'refresh_visible_focus_chrome'):
                term.refresh_visible_focus_chrome(focused=term)
            try:
                self.terminator.focus_changed(term)
            except Exception:
                pass

    def is_child_notebook(self):
        """Returns True if this Window's child is a Notebook"""
        maker = Factory()
        return(maker.isinstance(self.get_child(), 'Notebook'))

    def tab_new(self, widget=None, debugtab=False, _param1=None, _param2=None):
        """Make a new tab"""
        try:
            from .session import note_window_grown
            note_window_grown(self)
        except Exception as ex:
            dbg('note_window_grown: %s' % ex)
        if self.is_zoomed():
            leave_zoom(self, reason='window', quiet=False)

        cwd = None
        profile = None

        if widget:
            cwd = widget.get_cwd()
            profile = widget.get_profile()

        maker = Factory()
        if not self.is_child_notebook():
            dbg('Making a new Notebook')
            notebook = maker.make('Notebook', window=self)
        self.show()
        self.present()
        return self.get_child().newtab(debugtab, cwd=cwd, profile=profile)

    def on_delete_event(self, window, event, data=None):
        """Handle a window close request"""
        maker = Factory()

        # Pass the Window so D17 scope_terminals sees zoom/overlay trees
        confirm_close = self.construct_confirm_close(window, self)
        return (confirm_close != Gtk.ResponseType.ACCEPT)

    def on_destroy_event(self, widget, data=None):
        """Handle window destruction"""
        if getattr(self, '_session_destroy_handled', False) or self.isDestroyed:
            return True
        self._session_destroy_handled = True
        dbg('destroying self')
        # Round-2 P2-2: a legacy (scaled) zoom hides the other terminals from
        # get_terminals(); unzoom first so the session describe is complete
        # and every terminal is closed below (otherwise hidden ones stay
        # registered with live shells and the process never quits).
        leave_zoom(self, legacy=True, overlay=False, reason='destroy')
        # Round-2 P1-1: describe the session BEFORE the overlay teardown puts
        # the maximised terminal back in its slot, so the final save / D5
        # fragment keeps maximised_pane.  finalize() restores overlays itself
        # after saving.
        try:
            from .session import SessionManager
            sess = SessionManager()
            # Last window → finalize; otherwise D5 buffer
            remaining = [w for w in self.terminator.windows if w is not self
                         and not getattr(w, 'isDestroyed', False)
                         and not getattr(w, '_session_destroy_handled', False)]
            if len(remaining) == 0:
                sess.finalize()
            else:
                sess.note_window_closing(self)
        except Exception as ex:
            dbg('session on_destroy_event: %s' % ex)
        # UI review P2-1: stop a running maximise/restore animation (16 ms
        # tick) and drop the temporary Overlay before the tree goes away.
        overlay = getattr(self, '_overlay', None)
        if overlay is not None:
            try:
                overlay.teardown()
            except Exception as ex:
                dbg('overlay teardown on destroy: %s' % ex)
        for terminal in self.get_terminals():
            # Only for race condition, while closing a window with a single
            # terminal. Could be useful in other scenarios.
            # We can't get [[terminal1]] section using
            # terminal.describe_layout() while terminal is closing.
            # Also while receiving event on Plugins Side, if connected to term
            # we can't use close-term as it starts to close terminal, so we
            # send a pre-close-term before Example: Plugin SaveLastSessionLayout
            terminal.emit('pre-close-term')
            terminal.close()
        self.cnxids.remove_all()
        try:
            self.title.destroy()
        except Exception:
            pass
        self.terminator.deregister_window(self)
        self.isDestroyed = True
        self.destroy()
        del(self)

    def on_hide_window(self, data=None):
        """Handle a request to hide/show the window"""

        if not self.isDestroyed:
            if not self.get_property('visible'):
                #Don't show if window has just been hidden because of
                #lost focus
                if (time.time() - self.losefocus_time < 0.1) and \
                    self.config['hide_on_lose_focus']:
                    return
                if self.position and self.can_set_position():
                    self.move(self.position[0], self.position[1])
                self.show()
                self.grab_focus()
                gdkwin = self.get_window()
                if gdkwin is not None:
                    gdkwin.focus(self._server_time())
            elif self._iconified_by_hide and not self.is_active():
                # m34: toggled while iconified by us: bring it back
                self._iconified_by_hide = False
                self.deiconify()
                self.present()
            else:
                self._remember_position()
                self._run_hidefunc()

    # pylint: disable-msg=W0613
    def on_window_state_changed(self, window, event):
        """Handle the state of the window changing"""
        self.isfullscreen = bool(event.new_window_state & 
                                 Gdk.WindowState.FULLSCREEN)
        self.ismaximised = bool(event.new_window_state &
                                 Gdk.WindowState.MAXIMIZED)
        dbg('fullscreen=%s, maximised=%s' \
                % (self.isfullscreen, self.ismaximised))
        try:
            from .session import try_mark_dirty
            try_mark_dirty('window-state')
        except Exception:
            pass

        return(False)

    def on_configure_event(self, widget, event):
        """Mark session dirty when window position/size actually changes."""
        key = (int(event.x), int(event.y), int(event.width), int(event.height))
        if self._session_last_configure == key:
            return False
        self._session_last_configure = key
        try:
            from .session import try_mark_dirty
            try_mark_dirty('configure-event')
        except Exception:
            pass
        return False

    def on_pane_maximise_changed(self, window, terminal, active):
        try:
            from .session import try_mark_dirty
            try_mark_dirty('pane-maximise-changed')
        except Exception:
            pass

    def set_maximised(self, value):
        """Set the maximised state of the window from the supplied value"""
        if value == True:
            self.maximize()
        else:
            self.unmaximize()

    def set_fullscreen(self, value):
        """Set the fullscreen state of the window from the supplied value"""
        if value == True:
            self.fullscreen()
        else:
            self.unfullscreen()

    def set_borderless(self, value):
        """Set the state of the window border from the supplied value"""
        self._borderless = bool(value)
        self.set_decorated(not value)
        if value:
            self._remove_header_bar()
        else:
            self._install_header_bar()

    def _install_header_bar(self):
        """Client-side title bar, matching GNOME Terminal.

        The drop shadow and rounded corners are not drawn here. Putting a
        Gtk.HeaderBar on the window switches it to client-side decorations,
        and the compositor (Mutter on Ubuntu) paints the same shadow it
        paints around gnome-terminal. A CSS box-shadow on the contents
        cannot leave the window, so it is not a substitute. Maximised and
        fullscreen windows have no shadow; that is also the compositor.
        """
        if getattr(self, '_header_bar', None) is not None:
            return
        if getattr(self, '_borderless', False):
            return
        bar = Gtk.HeaderBar()
        bar.set_show_close_button(True)
        bar.set_has_subtitle(False)
        bar.get_style_context().add_class('terminator-header-bar')
        new_tab = self._header_button(
            ('view-left-pane-symbolic', 'sidebar-show-symbolic',
             'view-dual-symbolic'),
            _('Show or hide the tab list'),
            self._on_header_tab_panel_toggled, toggle=True)
        find = self._header_button(
            ('edit-find-symbolic', 'system-search-symbolic'),
            _('Find'), self._on_header_find)
        menu = self._header_button(
            ('open-menu-symbolic', 'view-more-symbolic'),
            _('Terminal menu'), self._on_header_menu)
        # pack_end: first packed sits next to the window buttons.
        # A slot keeps the 24px button from being stretched to the bar.
        bar.pack_start(self._header_slot(new_tab))
        bar.pack_end(self._header_slot(menu))
        bar.pack_end(self._header_slot(find))
        self._header_new_tab = new_tab
        self._header_tab_panel = new_tab
        self._header_find = find
        self._header_menu = menu
        self._header_bar = bar
        self.set_titlebar(bar)
        # Gtk.Window.show() does not map a custom titlebar on this GTK.
        # Without show_all the header stays invisible and the terminal
        # starts at the top of the window.
        bar.show_all()
        try:
            bar.set_title(self.get_title() or '')
        except Exception:
            pass
        if not getattr(self, '_header_title_bound', False):
            self.connect('notify::title', self._sync_header_title)
            self._header_title_bound = True

    def _remove_header_bar(self):
        if getattr(self, '_header_bar', None) is None:
            return
        self.set_titlebar(None)
        self._header_bar = None

    def _sync_header_title(self, window, _pspec=None):
        """Copy the window title onto the header bar.

        Gtk.HeaderBar.set_title() writes the window title back, which
        emits notify::title again. Without this guard that pair never
        returns and the process spins at startup.
        """
        if getattr(self, '_header_title_syncing', False):
            return
        bar = getattr(self, '_header_bar', None)
        if bar is None:
            return
        try:
            title = window.get_title() or ''
        except Exception:
            return
        try:
            if (bar.get_title() or '') == title:
                return
        except Exception:
            pass
        self._header_title_syncing = True
        try:
            bar.set_title(title)
        except Exception:
            pass
        finally:
            self._header_title_syncing = False

    def _header_button(self, icon_names, tooltip, callback, toggle=False):
        btn = Gtk.ToggleButton() if toggle else Gtk.Button()
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.set_focus_on_click(False)
        btn.set_can_focus(False)
        btn.get_style_context().add_class('terminator-header-btn')
        image = Gtk.Image()
        theme = Gtk.IconTheme.get_default()
        for name in icon_names:
            try:
                if theme.has_icon(name):
                    image.set_from_icon_name(name, Gtk.IconSize.MENU)
                    break
            except Exception:
                continue
        from .util import pin_icon_button
        pin_icon_button(btn, 24)
        btn.set_valign(Gtk.Align.CENTER)
        btn.set_vexpand(False)
        btn.add(image)
        btn.set_tooltip_text(tooltip)
        if toggle:
            btn.connect('toggled', callback)
        else:
            btn.connect('clicked', callback)
        return btn

    def _header_slot(self, btn):
        """Box so the header bar does not stretch a 24px button."""
        slot = Gtk.Box()
        slot.pack_start(btn, False, False, 0)
        return slot

    def _header_terminal(self):
        """The pane the header actions apply to."""
        term = None
        try:
            term = self.get_focussed_terminal()
        except Exception:
            term = None
        if term is None:
            term = getattr(self.terminator, 'last_focused_term', None)
            try:
                if term is not None and term.get_toplevel() is not self:
                    term = None
            except Exception:
                term = None
        if term is None:
            try:
                terms = self.get_terminals()
            except Exception:
                terms = []
            term = terms[0] if terms else None
        return term

    def _on_header_new_tab(self, _button):
        self.tab_new(widget=self._header_terminal())

    def _on_header_tab_panel_toggled(self, button):
        """Show or hide the tab list. The button stays down while it is open."""
        if getattr(self, '_tab_panel_syncing', False):
            return
        self._set_tab_panel_visible(button.get_active())

    def _tab_panel_visible(self):
        if not self.is_child_notebook():
            return False
        notebook = self.get_child()
        try:
            if hasattr(notebook, 'tab_list_visible'):
                return bool(notebook.tab_list_visible())
            return bool(notebook.get_show_tabs())
        except Exception:
            return False

    def _sync_tab_panel_button(self):
        btn = getattr(self, '_header_tab_panel', None)
        if btn is None or not hasattr(btn, 'get_active'):
            return
        shown = self._tab_panel_visible()
        if btn.get_active() == shown:
            return
        self._tab_panel_syncing = True
        try:
            btn.set_active(shown)
        finally:
            self._tab_panel_syncing = False

    def _set_tab_panel_visible(self, visible):
        """Open or close the tab sidebar without changing the saved preference."""
        visible = bool(visible)
        if visible and not self.is_child_notebook():
            try:
                Factory().make('Notebook', window=self)
            except Exception as ex:
                dbg('tab panel: %s' % ex)
        if not self.is_child_notebook():
            self._sync_tab_panel_button()
            return
        notebook = self.get_child()
        if visible:
            pos = 'left'
            try:
                pos = self.config['tab_position'] or 'left'
            except Exception:
                pos = 'left'
            if pos == 'hidden':
                pos = 'left'
            if pos == 'left' and hasattr(notebook, 'show_left_tab_list'):
                notebook.show_left_tab_list()
            else:
                side = getattr(notebook, '_tab_sidebar', None)
                if side is not None:
                    side.set_no_show_all(True)
                    side.hide()
                try:
                    notebook.set_tab_pos(getattr(Gtk.PositionType, pos.upper()))
                except Exception:
                    notebook.set_tab_pos(Gtk.PositionType.TOP)
                notebook.set_show_tabs(True)
                if hasattr(notebook, '_ensure_tab_add_button'):
                    notebook._ensure_tab_add_button()
        else:
            if hasattr(notebook, 'hide_tab_list'):
                notebook.hide_tab_list()
            else:
                notebook.set_show_tabs(False)
        self._sync_tab_panel_button()

    def _on_header_find(self, _button):
        term = self._header_terminal()
        if term is not None and hasattr(term, 'key_search'):
            term.key_search()

    def _on_header_menu(self, button):
        term = self._header_terminal()
        if term is not None and hasattr(term, 'popup_menu'):
            term.popup_menu(button, anchor=button, skip_link_check=True)

    def set_hidden(self, value):
        """Set the visibility of the window from the supplied value"""
        if value == True:
            self.ignore_startup_show = True
        else:
            self.ignore_startup_show = False

    def set_iconified(self, value):
        """Set the minimised state of the window from the supplied value"""
        if value == True:
            self.iconify()

    def set_always_on_top(self, value):
        """Set the always on top window hint from the supplied value"""
        self.set_keep_above(value)

    def set_sticky(self, value):
        """Set the sticky hint from the supplied value"""
        if value == True:
            self.stick()

    def apply_window_decoration_style(self, style):
        """Set the window decoration to dark or light theme variant"""
        if style == 'auto':
            style = self._detect_decoration_style()
        settings = Gtk.Settings.get_default()
        settings.set_property("gtk-application-prefer-dark-theme",
                              style == 'dark')
        current_theme = settings.get_property("gtk-theme-name")
        if style == 'dark':
            if not current_theme.endswith('-dark'):
                dark_theme = current_theme + '-dark'
                if self._theme_exists(dark_theme):
                    settings.set_property("gtk-theme-name", dark_theme)
        else:
            if current_theme.endswith('-dark'):
                light_theme = current_theme[:-5]
                if self._theme_exists(light_theme):
                    settings.set_property("gtk-theme-name", light_theme)
        self._set_theme_variant_x11(style)

    def _detect_decoration_style(self):
        """Detect dark or light based on terminal background color luminance"""
        bg_color = self.config['background_color']
        try:
            bg_color = bg_color.lstrip('#')
            r = int(bg_color[0:2], 16) / 255.0
            g = int(bg_color[2:4], 16) / 255.0
            b = int(bg_color[4:6], 16) / 255.0
            luminance = 0.299 * r + 0.587 * g + 0.114 * b
            return 'light' if luminance >= 0.5 else 'dark'
        except (ValueError, IndexError):
            return 'dark'

    def _theme_exists(self, theme_name):
        """Check if a GTK theme exists on the system"""
        import os
        search_dirs = [
            os.path.join(os.path.expanduser('~'), '.local', 'share', 'themes'),
            os.path.join(os.path.expanduser('~'), '.themes'),
            '/usr/share/themes',
            '/usr/local/share/themes',
        ]
        for d in search_dirs:
            if os.path.isdir(os.path.join(d, theme_name)):
                return True
        return False

    def _set_theme_variant_x11(self, variant):
        """Set _GTK_THEME_VARIANT X11 property for WM-drawn titlebar"""
        if display_manager() != 'X11':
            return
        if self.get_window() is None:
            return

        try:
            import ctypes
            import ctypes.util

            libx11_path = ctypes.util.find_library('X11')
            if not libx11_path:
                return
            libx11 = ctypes.cdll.LoadLibrary(libx11_path)

            libx11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
            libx11.XInternAtom.restype = ctypes.c_ulong

            libx11.XChangeProperty.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
                ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                ctypes.c_char_p, ctypes.c_int
            ]
            libx11.XChangeProperty.restype = ctypes.c_int

            libx11.XFlush.argtypes = [ctypes.c_void_p]
            libx11.XFlush.restype = ctypes.c_int

            display = ctypes.c_void_p(hash(GdkX11.x11_get_default_xdisplay()))
            xid = self.get_window().get_xid()

            variant_atom = libx11.XInternAtom(display, b'_GTK_THEME_VARIANT', 0)
            utf8_atom = libx11.XInternAtom(display, b'UTF8_STRING', 0)

            variant_bytes = variant.encode('utf-8')
            libx11.XChangeProperty(display, xid, variant_atom, utf8_atom,
                                   8, 0, variant_bytes, len(variant_bytes))
            libx11.XFlush(display)
        except Exception as e:
            dbg('_set_theme_variant_x11: failed: %s' % e)

    def set_real_transparency(self, value=True):
        """Enable RGBA if supported on the current screen"""
        if self.is_composited() == False:
            value = False

        screen = self.get_screen()
        if value:
            dbg('setting rgba visual')
            visual = screen.get_rgba_visual()
            if visual:
                self.set_visual(visual)

    def on_window_realize(self, widget):
        """Apply window hints once the window is realized"""
        profiles = self.config.base.profiles
        should_blur = False
        for profile in profiles.values():
            if (profile.get('background_blur', False) and
                    profile.get('background_type', 'solid') in ('transparent', 'image')):
                should_blur = True
                break
        self.set_blur_behind(should_blur)
        self._set_theme_variant_x11(self.config['window_decoration_style'])

    def set_blur_behind(self, enable=True):
        """Set or remove the KDE blur-behind-window hint via X11 property"""
        if display_manager() != 'X11':
            return
        if self.get_window() is None:
            return

        try:
            import ctypes
            import ctypes.util

            libx11_path = ctypes.util.find_library('X11')
            if not libx11_path:
                dbg('set_blur_behind: libX11 not found')
                return
            libx11 = ctypes.cdll.LoadLibrary(libx11_path)

            # Set explicit argtypes/restype to avoid pointer truncation on 64-bit
            libx11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
            libx11.XInternAtom.restype = ctypes.c_ulong

            libx11.XChangeProperty.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
                ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int
            ]
            libx11.XChangeProperty.restype = ctypes.c_int

            libx11.XDeleteProperty.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong]
            libx11.XDeleteProperty.restype = ctypes.c_int

            libx11.XFlush.argtypes = [ctypes.c_void_p]
            libx11.XFlush.restype = ctypes.c_int

            display = ctypes.c_void_p(hash(GdkX11.x11_get_default_xdisplay()))
            xid = self.get_window().get_xid()

            blur_atom = libx11.XInternAtom(display, b'_KDE_NET_WM_BLUR_BEHIND_REGION', 0)
            cardinal_atom = libx11.XInternAtom(display, b'CARDINAL', 0)

            if enable:
                data = (ctypes.c_ubyte * 4)(0, 0, 0, 0)
                libx11.XChangeProperty(display, xid, blur_atom, cardinal_atom,
                                       32, 0, data, 1)
                dbg('set_blur_behind: enabled blur hint on window %s' % xid)
            else:
                libx11.XDeleteProperty(display, xid, blur_atom)
                dbg('set_blur_behind: removed blur hint from window %s' % xid)

            libx11.XFlush(display)
        except Exception as e:
            dbg('set_blur_behind: failed: %s' % e)

    def show(self, startup=False):
        """Undo the startup show request if started in hidden mode"""
        #Present is necessary to grab focus when window is hidden from taskbar.
        #It is important to call present() before show(), otherwise the window
        #won't be brought to front if an another application has the focus.
        #Last note: present() will implicitly call Gtk.Window.show()
        # which does not map a custom titlebar. Show the header first.
        bar = getattr(self, '_header_bar', None)
        if bar is not None:
            bar.show_all()
        self._sync_tab_panel_button()
        self.present()

        #Window must be shown, then hidden for the hotkeys to be registered
        if (self.ignore_startup_show and startup == True):
            self._remember_position()
            self.hide()


    def add(self, widget, metadata=None):
        """Add a widget to the window by way of Gtk.Window.add()"""
        maker = Factory()
        if getattr(self, '_overlay', None) is not None and self._overlay.is_active():
            # Layout mutations while maximised: operate on the layout root
            # under the temporary Overlay (should be rare; callers restore).
            overlay = self._overlay.data['overlay']
            try:
                overlay.add(widget)
                # P0-1: the new layout root lives under the Overlay now
                self._overlay.note_main_replaced(widget)
            except Exception:
                Gtk.Window.add(self, widget)
        else:
            Gtk.Window.add(self, widget)
        if maker.isinstance(widget, 'Terminal'):
            self.connect_terminal_signals(
                widget, self.terminal_signals(widget, overlay=False))

            widget.grab_focus()

    def remove(self, widget):
        """Remove our child widget by way of Gtk.Window.remove()"""
        # The left tab list is a box beside the notebook. Removing the
        # notebook removes that box; it is the widget actually in the window.
        shell = getattr(widget, '_tab_shell', None)
        if shell is not None and widget.get_parent() is shell:
            widget = shell
        if getattr(self, '_overlay', None) is not None and self._overlay.is_active():
            overlay = self._overlay.data['overlay']
            main = self._overlay.main()
            if widget is main:
                try:
                    overlay.remove(widget)
                    self._overlay.note_main_replaced(None)
                except Exception:
                    Gtk.Window.remove(self, widget)
            else:
                Gtk.Window.remove(self, widget)
        else:
            Gtk.Window.remove(self, widget)
        self.disconnect_child(widget)
        try:
            from .session import try_mark_dirty
            try_mark_dirty('window.remove')
        except Exception:
            pass
        return(True)

    def get_child(self):
        """Return the layout root. While overlay-maximised the real Gtk child
        is a temporary Overlay — callers must still see the paned/notebook."""
        if getattr(self, '_overlay', None) is not None and self._overlay.is_active():
            # Never expose the temporary Overlay itself (None while the root
            # is being replaced, like a plain Gtk.Window between remove/add)
            return layout_root_widget(self._overlay.main())
        return layout_root_widget(Gtk.Window.get_child(self))

    def get_children(self):
        """Return a single list of our child (layout root, see get_child)"""
        child = self.get_child()
        return [child] if child is not None else []

    def hoover(self):
        """Ensure we still have a reason to exist"""
        if not self.get_child():
            self.emit('destroy')

    def closeterm(self, widget):
        """Handle a terminal closing"""
        # Overlay close path: snap-restore, then forward to the slot parent.
        # After restore the terminal is back in a Paned/Notebook — Window.remove
        # would fail because the terminal is no longer our direct child.
        was_overlay_term = (self.is_overlay_maximised() and
                            self.is_maximised_pane(widget))
        leave_zoom(self, legacy=False, overlay=True, reason='closeterm')
        if was_overlay_term:
            from .util import logical_parent
            parent = logical_parent(widget)
            if parent is not None and parent is not self:
                if hasattr(parent, 'wrapcloseterm'):
                    parent.wrapcloseterm(widget)
                elif hasattr(parent, 'closeterm'):
                    parent.closeterm(widget)
                self.hoover()
                return
        Container.closeterm(self, widget)
        self.hoover()

    def split_axis(self, widget, vertical=True, cwd=None, sibling=None, widgetfirst=True):
        """Split the window"""
        if self.is_zoomed():
            leave_zoom(self, reason='window', quiet=False)
            from .util import logical_parent
            parent = logical_parent(widget)
            parent.split_axis(widget, vertical, cwd, sibling, widgetfirst)
            return

        order = None
        maker = Factory()
        self.remove(widget)

        if vertical:
            container = maker.make('VPaned')
        else:
            container = maker.make('HPaned')
        
        self.set_pos_by_ratio = True

        if not sibling:
            sibling = maker.make('Terminal')
            sibling.set_cwd(cwd)
            if self.config['always_split_with_profile']:
                sibling.force_set_profile(None, widget.get_profile())
            sibling.spawn_child()
            if widget.group and self.config['split_to_group']:
                sibling.set_group(None, widget.group)
        elif self.config['always_split_with_profile']:
            sibling.force_set_profile(None, widget.get_profile())

        self.add(container)
        container.show_all()

        order = [widget, sibling]
        if widgetfirst is False:
            order.reverse()

        for term in order:
            container.add(term)
        container.show_all()
        
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        sibling.grab_focus()
        self.set_pos_by_ratio = False

        try:
            from .session import try_mark_dirty
            try_mark_dirty('window.split_axis')
        except Exception:
            pass

    def resizeterm(self, widget, keyname):
        """Handle a keyboard event requesting a terminal resize"""
        # if not zoomed, then ignore the signal: there is only one terminal
        if self.is_zoomed():
            leave_zoom(self, reason='window', quiet=False)
            from .util import logical_parent
            logical_parent(widget).resizeterm(widget, keyname)

    def is_zoomed(self):
        """Return True if the window has a zoomed terminal, False otherwise"""
        try:
            # 'is True' just in case we get something that is not a boolean
            return self.get_property('term_zoomed') is True
        except TypeError:
            err('failed to get "term_zoomed" property')
        return False

    def has_multiple_terms(self):
        """True if the currently visible tab holds more than one terminal.
        Used for 'Maximize pane' sensitivity only (not close-confirm scope,
        see close_confirm.scope_terminals)."""
        try:
            return len(self.get_visible_terminals()) > 1
        except Exception as ex:
            dbg('has_multiple_terms failed: %s' % ex)
            return False

    def _ensure_overlay(self):
        if self._overlay is None:
            from .paneoverlay import OverlayController
            self._overlay = OverlayController(self)
        return self._overlay

    def is_overlay_maximised(self):
        """True while the temporary Overlay maximise chrome is present."""
        overlay = getattr(self, '_overlay', None)
        return overlay is not None and overlay.is_active()

    def is_maximised_pane(self, term):
        """True iff this terminal is the one currently overlay-maximised
        (or legacy maximise without font scaling)."""
        is_ov = getattr(self, 'is_overlay_maximised', None)
        if callable(is_ov) and is_ov():
            return self._overlay.is_maximised_pane(term)
        if not self.is_zoomed() or not self.zoom_data:
            return False
        return (self.zoom_data.get('widget') is term and
                not self.zoom_data.get('font_scale'))

    def overlay_maximise(self, terminal, animate=True):
        return self._ensure_overlay().maximise(terminal, animate=animate)

    def overlay_restore(self, animate=True):
        if not self.is_overlay_maximised():
            return False
        return self._overlay.restore(animate=animate)

    def overlay_transfer(self, target, animate=True):
        if not self.is_overlay_maximised():
            return False
        return self._overlay.transfer(target, animate=animate)

    def terminal_signals(self, widget, overlay=False):
        """Signal table for a Terminal that is our direct (logical) child:
        the sole root terminal (overlay=False, no zoom: nothing to zoom
        over) or the overlay-maximised terminal in the PaneFrame
        (overlay=True: 'maximise' toggles the overlay back, 'zoom' goes
        through restore first instead of being dropped; UI review P2-3)."""
        from .container import window_terminal_signals
        signals = window_terminal_signals(self, widget, zoom=False)
        signals.update({'close-term': self.closeterm,
                        'title-change': self.title.set_title,
                        'split-auto': self.split_auto,
                        'split-horiz': self.split_horiz,
                        'split-vert': self.split_vert,
                        'resize-term': self.resizeterm,
                        'unzoom': self.unzoom})
        if overlay:
            signals['maximise'] = [self.zoom, False]
            signals['zoom'] = self._zoom_from_overlay
        return signals

    def _zoom_from_overlay(self, widget, font_scale=True):
        """Scaled (legacy) zoom requested on the overlay-maximised pane:
        leave the overlay first, then zoom from the plain tree."""
        leave_zoom(self, legacy=False, overlay=True, reason='zoom-from-overlay',
                   quiet=False)
        return self.zoom(widget, font_scale)

    def _connect_overlay_terminal_signals(self, widget):
        """Wire the same Window-level signals add() uses, after the terminal
        is reparented into PaneFrame (which does not call Window.add)."""
        self.connect_terminal_signals(
            widget, self.terminal_signals(widget, overlay=True))

    def zoom(self, widget, font_scale=True):
        """Dispatch: overlay maximise (default) or legacy reparent zoom."""
        try:
            overlay_on = bool(self.config['pane_overlay_maximise'])
        except Exception:
            overlay_on = True
        if (not font_scale) and overlay_on:
            return self.overlay_maximise(widget, animate=True)
        return self._legacy_zoom(widget, font_scale)

    def unzoom(self, widget=None):
        """Restore: overlay path or legacy reparent."""
        if self.is_overlay_maximised():
            # Public default animates; close/finalize pass animate=False
            return self.overlay_restore(animate=True)
        return self._legacy_unzoom(widget)

    def _legacy_zoom(self, widget, font_scale=True):
        """Old reparent zoom / scaled_zoom. E hooks scaled_zoom here only."""
        maker = Factory()
        children = self.get_children()

        if widget in children:
            return

        # E: pause+reset auto font BEFORE get_zoom_data so old_char_*
        # reflect the base cell, not an already-scaled size.
        if font_scale and hasattr(widget, 'pause_auto_font_scale'):
            try:
                widget.pause_auto_font_scale('scaled_zoom')
            except Exception as ex:
                dbg('legacy zoom pause font: %s' % ex)

        self.zoom_data = widget.get_zoom_data()
        self.zoom_data['widget'] = widget
        self.zoom_data['old_child'] = children[0]
        self.zoom_data['font_scale'] = font_scale

        old_parent = self.zoom_data['old_parent']
        if maker.isinstance(old_parent, 'Notebook'):
            self.zoom_data['notebook_tabnum'] = old_parent.page_num(widget)
            self.zoom_data['notebook_label'] = old_parent.get_tab_label(widget).get_label()

        self.remove(self.zoom_data['old_child'])
        old_parent.remove(widget)
        self.add(widget)
        self.set_property('term_zoomed', True)

        if font_scale:
            widget.cnxids.new(widget, 'size-allocate',
                    widget.zoom_scale, self.zoom_data)

        widget.grab_focus()
        try:
            from .session import try_mark_dirty
            try_mark_dirty('zoom')
        except Exception:
            pass
        self.emit('pane-maximise-changed', widget, not font_scale)

    def _legacy_unzoom(self, widget=None):
        """Restore from legacy reparent zoom."""
        maker = Factory()

        if not self.is_zoomed() or self.zoom_data is None:
            dbg('not legacy-zoomed, no-op')
            return

        widget = self.zoom_data['widget']
        if self.zoom_data['font_scale']:
            widget.vte.set_font(self.zoom_data['old_font'])
            if hasattr(widget, 'resume_auto_font_scale'):
                try:
                    widget.resume_auto_font_scale()
                except Exception as ex:
                    dbg('legacy unzoom resume font: %s' % ex)

        self.remove(widget)
        self.add(self.zoom_data['old_child'])
        if maker.isinstance(self.zoom_data['old_parent'], 'Notebook'):
            self.zoom_data['old_parent'].newtab(widget=widget, metadata={
                'tabnum': self.zoom_data['notebook_tabnum'],
                'label':  self.zoom_data['notebook_label']
            })
        else:
            self.zoom_data['old_parent'].add(widget)
        widget.grab_focus()
        was_maximise = not self.zoom_data.get('font_scale')
        self.zoom_data = None
        self.set_property('term_zoomed', False)
        try:
            from .session import try_mark_dirty
            try_mark_dirty('unzoom')
        except Exception:
            pass
        self.emit('pane-maximise-changed', widget, False)

    def rotate(self, widget, clockwise):
        """Rotate children in this window"""
        if self.is_zoomed():
            leave_zoom(self, reason='window', quiet=False)
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)

        self.set_pos_by_ratio = True
        maker = Factory()
        child = self.get_child()

        # If our child is a Notebook, reset to work from its visible child
        if maker.isinstance(child, 'Notebook'):
            notebook = child

            pagenum = notebook.get_current_page()
            child = notebook.get_nth_page(pagenum)

            metadata = {
                'tabnum': pagenum,
                'label': notebook.get_tab_label(child).get_label()
            }
        else:
            metadata = None

        if maker.isinstance(child, 'Paned'):
            from .util import logical_parent
            parent = logical_parent(child)
            # Need to get the allocation before we remove the child,
            # otherwise _sometimes_ we get incorrect values.
            alloc = child.get_allocation()
            parent.remove(child)
            child.rotate_recursive(parent, alloc.width, alloc.height, clockwise, metadata)

            self.show_all()
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)
            widget.grab_focus()

        self.set_pos_by_ratio = False

    def get_terminals(self):
        return(util.enumerate_descendants(self)[1])
 
    def get_visible_terminals(self):
        """Walk down the widget tree to find all of the visible terminals.
        Mostly using Container::get_visible_terminals()"""
        terminals = {}
        if not hasattr(self, 'cached_maker'):
            self.cached_maker = Factory()
        maker = self.cached_maker
        child = self.get_child()

        if not child:
            return([])

        # If our child is a Notebook, reset to work from its visible child
        if maker.isinstance(child, 'Notebook'):
            pagenum = child.get_current_page()
            child = child.get_nth_page(pagenum)

        if getattr(child, 'is_pane_placeholder', False):
            if child.terminal is not None:
                terminals[child.terminal] = child.slot_allocation()
        elif maker.isinstance(child, 'Container'):
            terminals.update(child.get_visible_terminals())
        elif maker.isinstance(child, 'Terminal'):
            terminals[child] = child.get_allocation()
        else:
            dbg('Unknown child type %s, skipping' % type(child))

        return(terminals)

    def get_focussed_terminal(self):
        """Find which terminal we want to have focus"""
        terminals = self.get_visible_terminals()
        for terminal in terminals:
            if terminal.vte.is_focus():
                return(terminal)
        return(None)

    def deferred_set_rough_geometry_hints(self):
        # no parameters are used in set_rough_geometry_hints, so we can
        # use the set_rough_geometry_hints
        if self.pending_set_rough_geometry_hint == True:
            return
        self.pending_set_rough_geometry_hint = True
        GLib.idle_add(self.do_deferred_set_rough_geometry_hints)

    def do_deferred_set_rough_geometry_hints(self):
        self.pending_set_rough_geometry_hint = False
        self.set_rough_geometry_hints()
        return False  # one-shot idle source

    def set_rough_geometry_hints(self):
        """Walk all the terminals along the top and left edges to fake up how
        many columns/rows we sort of have"""
        if self.ismaximised == True:
            return
        if not hasattr(self, 'cached_maker'):
            self.cached_maker = Factory()
        maker = self.cached_maker
        if maker.isinstance(self.get_child(), 'Notebook'):
            dbg("We don't currently support geometry hinting with tabs")
            return

        terminals = self.get_visible_terminals()
        column_sum = 0
        row_sum = 0

        for terminal in terminals:
            rect = terminal.get_allocation()
            if rect.x == 0:
                cols, rows = terminal.get_size()
                row_sum = row_sum + rows
            if rect.y == 0:
                cols, rows = terminal.get_size()
                column_sum = column_sum + cols

        if column_sum == 0 or row_sum == 0:
            dbg('column_sum=%s,row_sum=%s. No terminals found in >=1 axis' %
                (column_sum, row_sum))
            return

        # FIXME: I don't think we should just use whatever font size info is on
        # the last terminal we inspected. Looking up the default profile font
        # size and calculating its character sizes would be rather expensive
        # though.
        font_width, font_height = terminal.get_font_size()
        total_font_width = font_width * column_sum
        total_font_height = font_height * row_sum

        win_width, win_height = self.get_size()
        extra_width = win_width - total_font_width
        extra_height = win_height - total_font_height

        dbg('setting geometry hints: (ewidth:%s)(eheight:%s),\
(fwidth:%s)(fheight:%s)' % (extra_width, extra_height, 
                            font_width, font_height))
        geometry = Gdk.Geometry()
        geometry.base_width = extra_width
        geometry.base_height = extra_height
        geometry.width_inc = font_width
        geometry.height_inc = font_height
        self.set_geometry_hints(None, geometry, Gdk.WindowHints.BASE_SIZE | Gdk.WindowHints.RESIZE_INC)

    def disable_geometry_hints(self):
        self.set_geometry_hints(None, None, 0)

    def tab_change(self, widget, num=None):
        """Change to a specific tab"""
        if self.is_zoomed():
            leave_zoom(self, reason='window', quiet=False)

        if num is None:
            err('must specify a tab to change to')

        maker = Factory()
        child = self.get_child()

        if not maker.isinstance(child, 'Notebook'):
            dbg('child is not a notebook, nothing to change to')
            return

        if num == -1:
            # Go to the next tab
            cur = child.get_current_page()
            pages = child.get_n_pages()
            if cur == pages - 1:
                num = 0
            else:
                num = cur + 1
        elif num == -2:
            # Go to the previous tab
            cur = child.get_current_page()
            if cur > 0:
                num = cur - 1
            else:
                num = child.get_n_pages() - 1

        child.set_current_page(num)
        # Work around strange bug in gtk-2.12.11 and pygtk-2.12.1
        # Without it, the selection changes, but the displayed page doesn't
        # change
        child.set_current_page(child.get_current_page())

    def set_groups(self, new_group, term_list):
        """Set terminals in term_list to new_group"""
        for terminal in term_list:
            terminal.set_group(None, new_group)
        self.terminator.focus_changed(self.terminator.last_focused_term)

    def group_all(self, widget):
        """Group all terminals"""
        # FIXME: Why isn't this being done by Terminator() ?
        group = _('All')
        self.terminator.create_group(group)
        self.set_groups(group, self.terminator.terminals)

    def group_all_toggle(self, widget):
        """Toggle grouping to all"""
        if widget.group == 'All':
            self.ungroup_all(widget)
        else:
            self.group_all(widget)

    def ungroup_all(self, widget):
        """Ungroup all terminals"""
        self.set_groups(None, self.terminator.terminals)

    def group_win(self, widget):
        """Group all terminals in the current window"""
        # FIXME: Why isn't this being done by Terminator() ?
        dbg("Group Windows")
        group = _('Window group %s' % (len(self.terminator.groups) + 1))
        self.terminator.create_group(group)
        self.set_groups(group, self.get_terminals())

    def group_win_toggle(self, widget):
        """Toggle grouping to all windows in the current window"""
        if widget.group:
            self.ungroup_win(widget)
        else:
            self.group_win(widget)

    def ungroup_win(self, widget):
        """Ungroup all terminals in the current window"""
        self.set_groups(None, self.get_terminals())

    def group_tab(self, widget):
        """Group all terminals in the current tab"""
        maker = Factory()
        notebook = self.get_child()

        if not maker.isinstance(notebook, 'Notebook'):
            dbg('not in a notebook, refusing to group tab')
            return

        pagenum = notebook.get_current_page()
        while True:
            group = _('Tab %d') % pagenum
            if group not in self.terminator.groups:
                break
            pagenum += 1
        self.set_groups(group, self.get_visible_terminals())

    def group_tab_toggle(self, widget):
        """Blah"""
        if widget.group and widget.group[:4] == 'Tab ':
            self.ungroup_tab(widget)
        else:
            self.group_tab(widget)

    def ungroup_tab(self, widget):
        """Ungroup all terminals in the current tab"""
        maker = Factory()
        notebook = self.get_child()

        if not maker.isinstance(notebook, 'Notebook'):
            dbg('note in a notebook, refusing to ungroup tab')
            return
        
        self.set_groups(None, self.get_visible_terminals())

    def move_tab(self, widget, direction):
        """Handle a keyboard shortcut for moving tab positions"""
        if self.is_zoomed():
            leave_zoom(self, reason='window', quiet=False)

        maker = Factory()
        notebook = self.get_child()

        if not maker.isinstance(notebook, 'Notebook'):
            dbg('not in a notebook, refusing to move tab %s' % direction)
            return

        dbg('moving tab %s' % direction)
        numpages = notebook.get_n_pages()
        page = notebook.get_current_page()
        child = notebook.get_nth_page(page)

        if direction == 'left':
            if page == 0:
                page = numpages
            else:
                page = page - 1
        elif direction == 'right':
            if page == numpages - 1:
                page = 0
            else:
                page = page + 1
        else:
            err('unknown direction: %s' % direction)
            return
        
        notebook.reorder_child(child, page)

    def detach_tab_to_new_window(self, widget):
        """Detach the tab containing widget into a new window"""
        if self.is_zoomed():
            leave_zoom(self, reason='window', quiet=False)

        maker = Factory()
        notebook = self.get_child()

        if not maker.isinstance(notebook, 'Notebook'):
            dbg('not in a notebook, refusing to detach tab')
            return

        notebook.detach_tab_to_new_window(widget)

    def navigate_terminal(self, terminal, direction):
        """Navigate around terminals"""
        overlay_nav = (self.is_overlay_maximised() and
                       direction in ('left', 'right', 'up', 'down'))
        if self.is_zoomed() and not overlay_nav:
            # Overlay: directional keys transfer (D16); other directions /
            # legacy zoom still unzoom first.
            leave_zoom(self, reason='navigate', quiet=False)
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)

        _containers, terminals = util.enumerate_descendants(self)
        visibles = self.get_visible_terminals()
        current = terminals.index(terminal)
        length = len(terminals)
        next = None

        if length <= 1 or len(visibles) <= 1:
            return

        if direction in ['next', 'prev']:
            tmpterms = copy.copy(terminals)
            tmpterms = tmpterms[current+1:]
            tmpterms.extend(terminals[0:current])

            if direction == 'next':
                tmpterms.reverse()

            next = 0
            while len(tmpterms) > 0:
                tmpitem = tmpterms.pop()
                if tmpitem in visibles:
                    next = terminals.index(tmpitem)
                    break
        elif direction in ['left', 'right', 'up', 'down']:
            layout = self.get_visible_terminals()
            allocation = terminal.get_allocation()
            possibles = []

            # Get the coordinate of the appropriate edge for this direction
            edge, p1, p2 = util.get_edge(allocation, direction)
            cols, rows = self.get_size()
            if ((direction == 'down' and edge >= rows) or
                (direction == 'right' and edge >= cols)):
                edge =  0
            elif (direction == 'up' and edge == 0):
                edge = rows
            elif (direction == 'left' and edge == 0):
                edge = cols

            # Find all visible terminals which are, in their entirety, in the
            # direction we want to move, and are at least partially spanning
            # p1 to p2
            for term in layout:
                rect = layout[term]
                if util.get_nav_possible(edge, rect, direction, p1, p2):
                    possibles.append(term)

            if len(possibles) == 0:
                return

            # Find out how far away each of the possible terminals is, then
            # find the smallest distance. The winning terminals are all of
            # those who are that distance away.
            offsets = {}
            for term in possibles:
                rect = layout[term]
                offsets[term] = util.get_nav_offset(edge, rect, direction)
            keys = list(offsets.values())
            keys.sort()
            winners = [k for k, v in offsets.items() if v == keys[0]]
            next = terminals.index(winners[0])

            if len(winners) > 1:
                # Break an n-way tie using the cursor position
                cursor_x = allocation.x + allocation.width / 2
                cursor_y = allocation.y + allocation.height / 2

                for term in winners:
                    rect = layout[term]
                    if util.get_nav_tiebreak(direction, cursor_x, cursor_y,
                            rect):
                        next = terminals.index(term)
                        break;
        else:
            err('Unknown navigation direction: %s' % direction)

        if next is not None:
            target = terminals[next]
            if overlay_nav and target is not terminal:
                self.overlay_transfer(target, animate=True)
            else:
                target.grab_focus()

    def create_layout(self, layout):
        """Apply any config items from our layout"""
        if 'children' not in layout:
            err('layout describes no children: %s' % layout)
            return
        children = layout['children']
        if len(children) != 1:
            # We're a Window, we can only have one child
            err('incorrect number of children for Window: %s' % layout)
            return

        child = children[list(children.keys())[0]]
        terminal = self.get_children()[0]
        dbg('Making a child of type: %s' % child['type'])
        if child['type'] == 'VPaned':
            self.split_axis(terminal, True)
        elif child['type'] == 'HPaned':
            self.split_axis(terminal, False)
        elif child['type'] == 'Notebook':
            nchildren = len(child.get('children') or {})
            if nchildren == 1:
                # tab_new() wraps the current terminal and then adds another
                # page. A single kept tab has to stay one page.
                Factory().make('Notebook', window=self)
            else:
                self.tab_new()
                i = 2
                while i < nchildren:
                    self.tab_new()
                    i = i + 1
        elif child['type'] == 'Terminal':
            pass
        else:
            err('unknown child type: %s' % child['type'])
            return

        self.get_children()[0].create_layout(child)

        if 'last_active_term' in layout and layout['last_active_term'] not in ['', None]:
            self.last_active_term = make_uuid(layout['last_active_term'])

        if 'last_active_window' in layout and layout['last_active_window'] == 'True':
            self.terminator.last_active_window = self.uuid

class WindowTitle(object):
    """Own the desktop (Gtk.Window) title of one Terminator window.

    Ownership model (replaces the old ``vte.is_focus()`` guard):

    * Exactly one terminal - the *owner* - may drive the window title. The
      owner is the terminal that most recently received keyboard focus inside
      this window (tracked from Gtk.Window ``set-focus``, so it also works when
      focus later moves to a pane titlebar button, overlay chrome or the window
      itself loses toplevel focus).
    * Title changes from any other terminal are ignored for the window title
      (their pane titlebars / tab labels still update; that is handled by the
      Terminal/Notebook handlers, not here).
    * If the owner leaves the window (closed, detached), ownership falls back
      to the terminal that holds focus now.

    Coalescing: the native ``set_title`` is applied from a single pending
    GLib timeout (``DEBOUNCE_MS`` for OSC churn, ``FOCUS_DELAY_MS`` after a
    focus change so transient grab_focus chains during tab switches/layout
    ops collapse to the final pane). The latest text wins; an unchanged title
    is never re-applied.

    Config: ``window_title_mode`` = 'focused' (default) | 'fixed'; in 'fixed'
    mode the title is ``window_title_fixed``. force_title() beats both.
    """

    DEBOUNCE_MS = 300
    FOCUS_DELAY_MS = 50

    window = None
    text = None
    forced = None
    persist = False

    def __init__(self, window, config=None, timeout_add=None,
                 source_remove=None):
        """Class initialiser"""
        self.window = window
        self.forced = False
        self.persist = False
        self.owner = None
        self._config = config
        self._source = None
        self._source_is_focus = False
        self._destroyed = False
        if timeout_add is None or source_remove is None:
            from gi.repository import GLib
            timeout_add = timeout_add or GLib.timeout_add
            source_remove = source_remove or GLib.source_remove
        self._timeout_add = timeout_add
        self._source_remove = source_remove

    # -- config ---------------------------------------------------------
    def _cfg(self, key, default):
        config = self._config
        if config is None:
            config = getattr(self.window, 'config', None)
        if config is None:
            return default
        try:
            value = config[key]
        except Exception:
            return default
        return default if value is None else value

    def mode(self):
        """'focused' (follow the owner terminal) or 'fixed'"""
        mode = str(self._cfg('window_title_mode', 'focused')).strip().lower()
        return mode if mode in ('focused', 'fixed') else 'focused'

    def fixed_text(self):
        return str(self._cfg('window_title_fixed', 'Terminator') or 'Terminator')

    # -- ownership ------------------------------------------------------
    def _owns(self, terminal):
        """True if terminal currently lives in our window"""
        if terminal is None:
            return False
        try:
            return terminal.get_toplevel() is self.window
        except Exception:
            return False

    def _focus_terminal(self):
        """Terminal holding the Gtk focus widget of our window, if any"""
        get_focus = getattr(self.window, 'get_focus', None)
        if get_focus is None:
            return None
        try:
            return terminal_for_widget(get_focus())
        except Exception:
            return None

    def _ensure_owner(self, candidate=None):
        """Drop a stale owner and pick a fallback. Returns the owner."""
        if self.owner is not None and self._owns(self.owner):
            return self.owner
        self.owner = None
        last = None
        terminator = getattr(self.window, 'terminator', None)
        if terminator is not None:
            last = getattr(terminator, 'last_focused_term', None)
        for term in (self._focus_terminal(), last, candidate):
            if term is not None and self._owns(term):
                self.owner = term
                break
        return self.owner

    def focus_changed(self, terminal):
        """A terminal in our window took focus: it becomes the owner and the
        title is taken from it once (short delay to absorb transient focus
        hops)."""
        if self._destroyed or terminal is None or not self._owns(terminal):
            return
        if terminal is self.owner:
            return
        self.owner = terminal
        if self.forced or self.mode() == 'fixed':
            return
        try:
            text = terminal.get_window_title()
        except Exception:
            return
        self.text = text
        self._schedule(focus=True)

    def terminal_removed(self, terminal):
        """Forget terminal if it was the owner; fall back to the focused one"""
        if terminal is not None and terminal is self.owner:
            self.owner = None
            new = self._ensure_owner()
            if new is not None:
                self.owner = None
                self.focus_changed(new)

    def revalidate(self):
        """If the owner no longer lives in our window (closed, detached to
        another window), take the title from the fallback owner."""
        if self._destroyed or self.owner is None or self._owns(self.owner):
            return
        self.terminal_removed(self.owner)

    # -- title updates --------------------------------------------------
    def set_title(self, widget, text):
        """Title change request. widget is the emitting Terminal, or None
        for programmatic titles (force_title)."""
        if self._destroyed:
            return
        if widget is None:
            # Programmatic: apply now (a forced title still wins).
            if self.forced:
                return
            self.text = text
            self._cancel()
            self.update()
            return
        if self.forced or self.mode() == 'fixed':
            return
        owner = self._ensure_owner(widget)
        if widget is not owner:
            return
        self.text = text
        self._schedule()

    def force_title(self, newtext, persist=True):
        """Force a specific title.

        persist: save it in layouts/session (user "Set window title" or a
        restored layout).  The -T/--title CLI option passes False so a
        one-off launch title does not stick to the next plain launch."""
        was = (self.forced, self.persist, self.text)
        if newtext:
            self.forced = True
            self.persist = bool(persist)
            self.text = newtext
            self._cancel()
            self.update()
        else:
            self.forced = False
            self.persist = False
            # Back to automatic: show the owner's (or fixed) title again.
            owner = self._ensure_owner()
            if self.mode() == 'focused' and owner is not None:
                try:
                    self.text = owner.get_window_title()
                except Exception:
                    pass
            self._cancel()
            self.update()
        if (self.forced, self.persist, self.text) != was \
                and (self.persist or was[1]):
            try:
                from .session import try_mark_dirty
                try_mark_dirty('window-title')
            except Exception:
                pass

    def desired_title(self):
        """The title we want on the native window right now"""
        if self.forced:
            return self.text
        if self.mode() == 'fixed':
            return self.fixed_text()
        if self.text is None:
            return self.fixed_text()
        return "%s" % self.text

    def update(self):
        """Apply the title to the native window, skipping no-op changes"""
        if self._destroyed:
            return False
        title = self.desired_title()
        if title is None:
            return False
        get_title = getattr(self.window, 'get_title', None)
        try:
            current = get_title() if get_title is not None else None
        except Exception:
            current = None
        if current == title:
            return False
        self.window.set_title(title)
        return True

    # -- coalescing -----------------------------------------------------
    def _schedule(self, focus=False):
        """Single pending source; latest text wins when it fires.

        OSC updates do not push an already pending flush further out (so a
        pane that retitles constantly still updates ~every DEBOUNCE_MS).
        A focus change re-arms with the short FOCUS_DELAY_MS."""
        if self._source is not None:
            if not focus:
                return
            self._cancel()
        delay = self.FOCUS_DELAY_MS if focus else self.DEBOUNCE_MS
        self._source_is_focus = focus
        self._source = self._timeout_add(delay, self._flush)

    def _flush(self):
        self._source = None
        self._source_is_focus = False
        if not self._destroyed and not getattr(self.window, 'isDestroyed', False):
            self.update()
        return False

    def _cancel(self):
        if self._source is not None:
            try:
                self._source_remove(self._source)
            except Exception:
                pass
            self._source = None
            self._source_is_focus = False

    def pending(self):
        return self._source is not None

    def destroy(self):
        """Cancel any pending flush; further requests are ignored"""
        self._cancel()
        self._destroyed = True
        self.owner = None


def terminal_for_widget(widget):
    """Return the Terminal containing widget (or widget itself), else None"""
    # Duck-typed: Terminal is the only widget with both a .vte and
    # get_window_title() (VTE itself has no .vte attribute).
    while widget is not None:
        if hasattr(widget, 'vte') and hasattr(widget, 'get_window_title'):
            return widget
        try:
            widget = widget.get_parent()
        except Exception:
            return None
    return None

# vim: set expandtab ts=4 sw=4:
