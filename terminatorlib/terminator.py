# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""terminator.py - class for the master Terminator singleton"""

import copy
import os
import gi
gi.require_version('Vte', '2.91')
from gi.repository import Gtk, Gdk, Vte
from gi.repository.GLib import GError
import itertools
import random

from . import borg
from .borg import Borg
from .config import Config
from .keybindings import Keybindings
from .util import dbg, err, enumerate_descendants
from .factory import Factory
from .translation import _

try:
    from gi.repository import GdkX11
except ImportError:
    dbg("could not import X11 gir module")


def eventkey2gdkevent(eventkey):  # FIXME FOR GTK3: is there a simpler way of casting from specific EventKey to generic (union) GdkEvent?
    gdkevent = Gdk.Event.new(eventkey.type)
    gdkevent.key.window = eventkey.window
    gdkevent.key.send_event = eventkey.send_event
    gdkevent.key.time = eventkey.time
    gdkevent.key.state = eventkey.state
    gdkevent.key.keyval = eventkey.keyval
    gdkevent.key.length = eventkey.length
    gdkevent.key.string = eventkey.string
    gdkevent.key.hardware_keycode = eventkey.hardware_keycode
    gdkevent.key.group = eventkey.group
    gdkevent.key.is_modifier = eventkey.is_modifier
    return gdkevent

class Terminator(Borg):
    """master object for the application"""

    windows = None
    launcher_windows = None
    windowtitle = None
    terminals = None
    groups = None
    config = None
    keybindings = None
    style_providers = None
    last_focused_term = None

    origcwd = None
    dbus_path = None
    dbus_name = None
    debug_address = None

    doing_layout = None
    layoutname = None
    last_active_window = None
    prelayout_windows = None

    groupsend = None
    groupsend_type = {'all':0, 'group':1, 'off':2}

    cur_gtk_theme_name = None
    gtk_settings = None

    def __init__(self):
        """Class initialiser"""

        Borg.__init__(self, self.__class__.__name__)
        self.prepare_attributes()

    def prepare_attributes(self):
        """Initialise anything that isn't already"""

        if not self.windows:
            self.windows = []
        if not self.launcher_windows:
            self.launcher_windows = []
        if not self.terminals:
            self.terminals = []
        if not self.groups:
            self.groups = []
        if not self.config:
            self.config = Config()
        if self.groupsend == None:
            self.groupsend = self.groupsend_type[self.config['broadcast_default']]
        if not self.keybindings:
            self.keybindings = Keybindings()
            self.keybindings.configure(self.config['keybindings'])
        if not self.style_providers:
            self.style_providers = []
        if not self.doing_layout:
            self.doing_layout = False
        self.connect_signals()

    def connect_signals(self):
        """Connect all the gtk signals"""
        self.gtk_settings=Gtk.Settings().get_default()
        self.gtk_settings.connect('notify::gtk-theme-name', self.on_gtk_theme_name_notify)
        self.cur_gtk_theme_name = self.gtk_settings.get_property('gtk-theme-name')

    def set_origcwd(self, cwd):
        """Store the original cwd our process inherits"""
        if cwd == '/':
            cwd = os.path.expanduser('~')
            os.chdir(cwd)
        self.origcwd = cwd

    def set_dbus_data(self, dbus_service):
        """Store the DBus bus details, if they are available"""
        if dbus_service:
            self.dbus_name = dbus_service.bus_name.get_name()
            self.dbus_path = dbus_service.bus_path

    def get_windows(self):
        """Return a list of windows"""
        return self.windows

    def register_window(self, window):
        """Register a new window widget"""
        if window not in self.windows:
            dbg('registering %s:%s' % (id(window), type(window)))
            self.windows.append(window)

    def deregister_window(self, window):
        """de-register a window widget"""
        dbg('de-registering %s:%s' % (id(window), type(window)))
        if window in self.windows:
            self.windows.remove(window)
        else:
            err('%s is not in registered window list' % window)

        if len(self.windows) == 0:
            # We have no windows left, we should exit
            dbg('no windows remain, quitting')
            Gtk.main_quit()

        from .session import try_mark_dirty
        try_mark_dirty('deregister_window')

    def register_launcher_window(self, window):
        """Register a new launcher window widget"""
        if window not in self.launcher_windows:
            dbg('registering %s:%s' % (id(window), type(window)))
            self.launcher_windows.append(window)

    def deregister_launcher_window(self, window):
        """de-register a launcher window widget"""
        dbg('de-registering %s:%s' % (id(window), type(window)))
        if window in self.launcher_windows:
            self.launcher_windows.remove(window)
        else:
            err('%s is not in registered window list' % window)

        if len(self.launcher_windows) == 0 and len(self.windows) == 0:
            # We have no windows left, we should exit
            dbg('no windows remain, quitting')
            Gtk.main_quit()

    def register_terminal(self, terminal):
        """Register a new terminal widget"""
        if terminal not in self.terminals:
            dbg('registering %s:%s' %
                    (id(terminal), type(terminal)))
            self.terminals.append(terminal)

    def deregister_terminal(self, terminal):
        """De-register a terminal widget"""
        dbg('de-registering %s:%s' %
                (id(terminal), type(terminal)))
        self.terminals.remove(terminal)
        try:
            from .session import try_mark_dirty
            try_mark_dirty('deregister_terminal')
        except Exception:
            pass

        if len(self.terminals) == 0:
            dbg('no terminals remain, destroying all windows')
            for window in self.windows:
                window.destroy()
        else:
            dbg('%d terminals remain' % len(self.terminals))

    def find_terminal_by_uuid(self, uuid):
        """Search our terminals for one matching the supplied UUID"""
        dbg('searching self.terminals for: %s' % uuid)
        for terminal in self.terminals:
            dbg('checking: %s (%s)' % (terminal.uuid.urn, terminal))
            if terminal.uuid.urn == uuid:
                return terminal
        return None

    def find_window_by_uuid(self, uuid):
        """Search our terminals for one matching the supplied UUID"""
        dbg('searching self.terminals for: %s' % uuid)
        for window in self.windows:
            dbg('checking: %s (%s)' % (window.uuid.urn, window))
            if window.uuid.urn == uuid:
                return window
        return None

    def new_window(self, cwd=None, profile=None):
        """Create a window with a Terminal in it"""
        maker = Factory()
        window = maker.make('Window')
        terminal = maker.make('Terminal')
        if cwd:
            terminal.set_cwd(cwd)
        if profile and self.config['always_split_with_profile']:
            terminal.force_set_profile(None, profile)
        window.add(terminal)
        window.show(True)
        terminal.spawn_child()
        terminal.emit('tab-change', 0)

        return(window, terminal)

    def create_layout(self, layoutname):
        """Create all the parts necessary to satisfy the specified layout"""
        layout = None
        objects = {}

        self.doing_layout = True
        self.last_active_window = None
        self.prelayout_windows = self.windows[:]

        layout = copy.deepcopy(self.config.layout_get_config(layoutname))
        if layout:
            # Drop malformed entries (non-dict / no string type) instead of
            # crashing on layout[obj]['type'].lower() below.
            for obj in list(layout.keys()):
                node = layout[obj]
                if not isinstance(node, dict) or \
                        not isinstance(node.get('type'), str):
                    err('ignoring malformed layout entry %r' % (obj,))
                    del layout[obj]
        if layout:
            try:
                from .session import SESSION_LAYOUT_NAME, remap_layout_uuids
                if layoutname != SESSION_LAYOUT_NAME:
                    # Round-2 P1-3: a user layout is a template.  Uuids
                    # stored in it (upstream "Add/Save layout") may belong
                    # to running terminals or to cached scrollback; give
                    # every terminal a fresh one (focus refs follow).
                    remap_layout_uuids(layout)
            except Exception as ex:
                dbg('layout uuid remap failed: %s' % ex)
        if not layout:
            # User specified a non-existent layout. default to one Terminal
            err('layout %s not defined' % layout)
            self.new_window()
            return

        # Wind the flat objects into a hierarchy
        hierarchy = {}
        count = 0
        # Loop over the layout until we have consumed it, or hit 1000 loops.
        # This is a stupid artificial limit, but it's safe.
        while len(layout) > 0 and count < 1000:
            count = count + 1
            if count == 1000:
                err('hit maximum loop boundary. THIS IS VERY LIKELY A BUG')
            attached = 0
            for obj in list(layout.keys()):
                if layout[obj]['type'].lower() == 'window':
                    hierarchy[obj] = {}
                    hierarchy[obj]['type'] = 'Window'
                    hierarchy[obj]['children'] = {}

                    # Copy any additional keys
                    for objkey in list(layout[obj].keys()):
                        if layout[obj][objkey] != '' and objkey not in hierarchy[obj]:
                            hierarchy[obj][objkey] = layout[obj][objkey]

                    objects[obj] = hierarchy[obj]
                    del(layout[obj])
                    attached = attached + 1
                else:
                    # Now examine children to see if their parents exist yet
                    if 'parent' not in layout[obj]:
                        err('Invalid object: %s' % obj)
                        del(layout[obj])
                        continue
                    if layout[obj]['parent'] in objects:
                        # Our parent has been created, add ourselves
                        childobj = {}
                        childobj['type'] = layout[obj]['type']
                        childobj['children'] = {}

                        # Copy over any additional object keys
                        for objkey in list(layout[obj].keys()):
                            if objkey not in childobj:
                                childobj[objkey] = layout[obj][objkey]

                        objects[layout[obj]['parent']]['children'][obj] = childobj
                        objects[obj] = childobj
                        del(layout[obj])
                        attached = attached + 1
            # No node attached this pass: leftovers never will.
            if attached == 0:
                break

        for obj in list(layout.keys()):
            err('Unable to attach layout object %s to parent %r' % (
                obj, layout[obj].get('parent')))

        layout = hierarchy
        if not layout:
            # No Window survived. Same fallback as a missing layout.
            self.new_window()
            return

        for windef in layout:
            if layout[windef]['type'] != 'Window':
                err('invalid layout format. %s' % layout)
                raise(ValueError)
            dbg('Creating a window')
            window, terminal = self.new_window()
            # Positions only on X11. Wayland leaves placement to the
            # compositor and keeps a saved position in the file until the
            # next save. A position that misses every connected monitor
            # (an unplugged display) is moved onto the primary workarea.
            position = None
            if 'position' in layout[windef]:
                parts = str(layout[windef]['position']).split(':')
                if len(parts) == 2:
                    try:
                        position = (int(parts[0]), int(parts[1]))
                    except ValueError:
                        dbg('ignoring bad window position %r' %
                            layout[windef]['position'])
            size = None
            if 'size' in layout[windef]:
                parts = layout[windef]['size']
                try:
                    winx = int(parts[0])
                    winy = int(parts[1])
                except (IndexError, TypeError, ValueError):
                    dbg('ignoring bad window size %r' % (parts,))
                else:
                    if winx > 1 and winy > 1:
                        size = (winx, winy)
            covers = (str(layout[windef].get('maximised', '')) == 'True' or
                      str(layout[windef].get('fullscreen', '')) == 'True')
            if window.can_set_position():
                position, size = window.fit_restored_geometry(
                    position, size, shrink=not covers)
                if position:
                    window.move(position[0], position[1])
            if size:
                window.resize(size[0], size[1])
            # Only user-set titles (title_forced marker) are re-applied.
            # Legacy upstream layouts stored the dynamic focused-terminal
            # title here; forcing it would pin the window title forever.
            if layout[windef].get('title') and \
                    str(layout[windef].get('title_forced', '')) == 'True':
                window.title.force_title(layout[windef]['title'])
            if 'maximised' in layout[windef]:
                if layout[windef]['maximised'] == 'True':
                    window.ismaximised = True
                else:
                    window.ismaximised = False
                window.set_maximised(window.ismaximised)
            if 'fullscreen' in layout[windef]:
                if layout[windef]['fullscreen'] == 'True':
                    window.isfullscreen = True
                else:
                    window.isfullscreen = False
                window.set_fullscreen(window.isfullscreen)
            window.create_layout(layout[windef])

        self.layoutname = layoutname

    def layout_done(self):
        """Layout operations have finished, record that fact"""
        self.doing_layout = False
        maker = Factory()
        t = 0

        window_last_active_term_mapping = {}
        for window in self.windows:
            if window.is_child_notebook():
                source = window.get_toplevel().get_children()[0]
            else:
                source = window
            window_last_active_term_mapping[window] = copy.copy(source.last_active_term)

        for terminal in self.terminals:
            if not terminal.pid:
                terminal.spawn_child()

        for window in self.windows:
            if not window.is_child_notebook():
                # For windows without a notebook ensure Terminal is visible and focused
                if window_last_active_term_mapping[window]:
                    term = self.find_terminal_by_uuid(window_last_active_term_mapping[window].urn)
                    if term:
                        term.ensure_visible_and_focussed()

        # Build list of new windows using prelayout list
        new_win_list = []
        if self.prelayout_windows:
            for window in self.windows:
                if window not in self.prelayout_windows:
                    new_win_list.append(window)

        # Make sure all new windows get bumped to the top
        for window in new_win_list:
            window.show()
            window.grab_focus()
            t = window._server_time()  # m34: 0 off X11
            if window.get_window() is not None:
                window.get_window().focus(t)

        # Going by the docs, this should be all that's needed to ensure that the
        # last_active_window is focussed. 
        if self.last_active_window:
            window = self.find_window_by_uuid(self.last_active_window.urn)
            window.present_with_time(t)
        self.prelayout_windows = None
        try:
            from .session import SessionManager
            sess = SessionManager()
            sess.mark_dirty('layout_done')
            if sess.restored_this_run:
                sess.schedule_clear_restoring()
        except Exception:
            pass
        # Module D: restore overlay-maximised panes from session (no animation)
        try:
            seen_windows = set()
            for terminal in self.terminals:
                if not getattr(terminal, '_restore_maximised', False):
                    continue
                terminal._restore_maximised = False
                win = terminal.get_toplevel()
                if not hasattr(win, 'overlay_maximise'):
                    continue
                maker = Factory()
                top_child = win.get_child()
                if maker.isinstance(top_child, 'Notebook'):
                    page_num = top_child.page_num_descendant(terminal)
                    if page_num >= 0:
                        page = top_child.get_nth_page(page_num)
                        if not hasattr(top_child, 'last_maximised_term') or top_child.last_maximised_term is None:
                            top_child.last_maximised_term = {}
                        top_child.last_maximised_term[page] = terminal.uuid
                        if page_num != top_child.get_current_page():
                            continue
                if win in seen_windows:
                    continue
                seen_windows.add(win)
                # Deferred until the window is allocated and only for the
                # current tab (UI review P1-2)
                win._ensure_overlay().maximise_when_ready(terminal)
        except Exception as ex:
            dbg('layout_done overlay restore: %s' % ex)

    def on_gtk_theme_name_notify(self, settings, prop):
        """Reconfigure if the gtk theme name changes"""
        new_gtk_theme_name = settings.get_property(prop.name)
        if new_gtk_theme_name != self.cur_gtk_theme_name:
            self.cur_gtk_theme_name = new_gtk_theme_name
            self.reconfigure()

    def pane_accent_color(self):
        """Return a validated pane accent colour string"""
        default = '#3fb950'
        try:
            value = self.config['pane_accent_color']
        except Exception:
            return default
        rgba = Gdk.RGBA()
        if not value or not rgba.parse(str(value)):
            err('Invalid pane_accent_color %r, using %s' % (value, default))
            return default
        return str(value)

    def tab_bar_css(self):
        """Tab strip.

        The default is a light list down the left side, the same kind of
        row as Cursor's sidebar. ``tab_position = top`` keeps the dark
        chip strip.
        """
        return """
            .terminator-terminal-window notebook.terminator-notebook header.top {
                background-color: #161616;
                background-image: none;
                border: none;
                border-image: none;
                box-shadow: none;
                padding: 0 6px;
                min-height: 36px; }
            .terminator-terminal-window notebook.terminator-notebook header.top tabs {
                background-color: transparent;
                background-image: none;
                border: none; }
            .terminator-terminal-window notebook.terminator-notebook header.top tab {
                background-color: transparent;
                background-image: none;
                border-style: none;
                border-image: none;
                border-radius: 0;
                box-shadow: inset -1px 0 0 rgba(255,255,255,0.16);
                margin: 5px 2px;
                padding: 2px 12px;
                min-height: 0;
                color: #b0b0b0;
                font-weight: normal; }
            .terminator-terminal-window notebook.terminator-notebook header.top tab:hover {
                background-color: #2a2a2a;
                border-radius: 8px;
                box-shadow: none;
                color: #f2f2f2; }
            .terminator-terminal-window notebook.terminator-notebook header.top tab:checked,
            .terminator-terminal-window notebook.terminator-notebook header.top tab:checked:hover {
                background-color: #2d2d2d;
                border-radius: 8px;
                box-shadow: none;
                color: #f2f2f2; }
            .terminator-terminal-window notebook.terminator-notebook header.top tab label {
                color: #b0b0b0; }
            .terminator-terminal-window notebook.terminator-notebook header.top tab:hover label,
            .terminator-terminal-window notebook.terminator-notebook header.top tab:checked label {
                color: #f2f2f2; }
            .terminator-terminal-window notebook.terminator-notebook header.top button.terminator-tab-add {
                color: #c8c8c8; }
            .terminator-terminal-window notebook.terminator-notebook header.top button.terminator-tab-add:hover {
                background-color: #2a2a2a;
                color: #ffffff; }

            .terminator-terminal-window .terminator-tab-sidebar {
                background-color: #f3f3f3;
                background-image: none;
                border: none;
                border-image: none;
                box-shadow: none;
                /* No right padding: the scrollbar sits on the list's edge. */
                padding: 6px 0 0 6px;
                min-width: 240px; }
            .terminator-terminal-window .terminator-tab-sidebar scrolledwindow {
                border: none;
                margin: 0;
                padding: 0; }
            .terminator-terminal-window .terminator-tab-sidebar scrollbar.vertical {
                margin: 0;
                padding: 0;
                border: none; }
            /* The theme draws the bar inside a transparent border, which
               leaves a gap before the terminal. Drop the right border so
               the bar meets the edge. */
            .terminator-terminal-window .terminator-tab-sidebar scrollbar.vertical slider {
                margin: 0;
                border-style: solid;
                border-color: transparent;
                border-width: 2px 0 2px 2px;
                background-clip: padding-box;
                min-width: 6px; }
            .terminator-terminal-window .terminator-tab-sidebar tabs {
                background-color: transparent;
                background-image: none;
                border: none; }
            .terminator-terminal-window .terminator-tab-sidebar tab {
                background-color: transparent;
                background-image: none;
                border-style: none;
                border-image: none;
                border-radius: 0;
                box-shadow: none;
                margin: 0;
                padding: 0;
                min-height: 0;
                min-width: 0;
                color: transparent;
                font-weight: normal; }
            .terminator-terminal-window .terminator-tab-sidebar treeview.terminator-tab-tree,
            .terminator-terminal-window .terminator-tab-sidebar treeview.terminator-tab-tree.view {
                background-color: #f3f3f3;
                background-image: none;
                color: #1d1d1f;
                border: none; }
            .terminator-terminal-window .terminator-tab-sidebar treeview.terminator-tab-tree row {
                background-color: transparent;
                color: #1d1d1f;
                border: none;
                padding: 3px 4px; }
            .terminator-terminal-window .terminator-tab-sidebar treeview.terminator-tab-tree row:selected,
            .terminator-terminal-window .terminator-tab-sidebar treeview.terminator-tab-tree row:selected:focus,
            .terminator-terminal-window .terminator-tab-sidebar treeview.terminator-tab-tree row:selected:backdrop {
                background-color: #e4e4e6;
                background-image: none;
                color: #1d1d1f; }
            .terminator-terminal-window .terminator-tab-sidebar .terminator-tab-folder {
                color: #8e8e93;
                font-size: smaller; }
            .terminator-terminal-window .terminator-tab-sidebar tab:checked .terminator-tab-folder {
                color: #6e6e73; }
            .terminator-terminal-window .terminator-tab-sidebar tab:hover {
                background-color: #ececee; }
            .terminator-terminal-window .terminator-tab-sidebar tab:checked,
            .terminator-terminal-window .terminator-tab-sidebar tab:checked:hover {
                background-color: #e4e4e6;
                color: #1d1d1f; }
            .terminator-terminal-window .terminator-tab-sidebar tab label {
                color: #3a3a3c; }
            .terminator-terminal-window .terminator-tab-sidebar tab:checked label {
                color: #1d1d1f; }
            .terminator-terminal-window .terminator-tab-sidebar button.terminator-tab-close {
                color: #6e6e73; }
            .terminator-terminal-window .terminator-tab-sidebar box.terminator-tab-row {
                background-color: transparent;
                border-radius: 6px;
                padding: 1px 4px;
                margin-top: 1px;
                margin-bottom: 1px; }
            .terminator-terminal-window .terminator-tab-sidebar box.terminator-tab-row:hover {
                background-color: #ececee; }
            .terminator-terminal-window .terminator-tab-sidebar box.terminator-tab-row.current,
            .terminator-terminal-window .terminator-tab-sidebar box.terminator-tab-row.current:hover {
                background-color: #e4e4e6; }
            .terminator-terminal-window .terminator-tab-sidebar box.terminator-tab-row label {
                color: #1d1d1f; }
            .terminator-terminal-window .terminator-tab-sidebar button.terminator-tab-row-main {
                background-color: transparent;
                background-image: none;
                border: none;
                box-shadow: none;
                padding: 2px 4px; }
            .terminator-terminal-window .terminator-tab-sidebar button.terminator-tab-row-main:hover {
                background-color: transparent;
                background-image: none; }
            .terminator-terminal-window .terminator-tab-sidebar button.terminator-tab-row-main:active,
            .terminator-terminal-window .terminator-tab-sidebar button.terminator-tab-row-main:active:hover {
                background-color: #d8d8dc;
                background-image: none; }
            .terminator-terminal-window .terminator-tab-sidebar button.terminator-tab-action {
                background-color: transparent;
                background-image: none;
                border: none;
                box-shadow: none;
                border-radius: 6px;
                padding: 2px;
                min-width: 22px;
                min-height: 22px; }
            .terminator-terminal-window .terminator-tab-sidebar button.terminator-tab-action:hover {
                background-color: #e4e4e6; }
            .terminator-terminal-window .terminator-tab-sidebar button.terminator-tab-action:active,
            .terminator-terminal-window .terminator-tab-sidebar button.terminator-tab-action:active:hover {
                background-color: #d2d2d6; }
            .terminator-terminal-window .terminator-tab-sidebar image.terminator-tab-close-mark,
            .terminator-terminal-window .terminator-tab-sidebar image.terminator-tab-lock-mark {
                color: #1d1d1f;
                opacity: 1; }
            .terminator-terminal-window .terminator-tab-sidebar .terminator-tab-toolbar {
                min-width: 220px;
                margin: 0 2px 6px 2px; }
            .terminator-terminal-window .terminator-tab-sidebar .terminator-tab-toolbar button {
                background-color: transparent;
                background-image: none;
                border: none;
                box-shadow: none;
                color: #6e6e73;
                border-radius: 6px;
                margin: 0 2px;
                padding: 2px;
                min-width: 24px;
                min-height: 24px; }
            .terminator-terminal-window .terminator-tab-sidebar .terminator-tab-toolbar button:hover {
                background-color: #e4e4e6;
                color: #1d1d1f; }
            .terminator-terminal-window .terminator-tab-sidebar .terminator-tab-toolbar button:active,
            .terminator-terminal-window .terminator-tab-sidebar .terminator-tab-toolbar button:active:hover {
                background-color: #d8d8dc;
                color: #1d1d1f; }
            .terminator-terminal-window .terminator-tab-sidebar .terminator-tab-toolbar button:disabled {
                color: #c7c7cc;
                background-color: transparent; }

            .terminator-terminal-window notebook.terminator-notebook button.terminator-tab-close {
                background: transparent;
                background-image: none;
                border: none;
                box-shadow: none;
                padding: 0;
                margin: 0 0 0 6px;
                min-width: 14px;
                min-height: 14px; }
            .terminator-terminal-window notebook.terminator-notebook button.terminator-tab-add {
                background: transparent;
                background-image: none;
                border: none;
                box-shadow: none;
                border-radius: 8px;
                margin: 4px 2px;
                padding: 0;
                min-width: 28px;
                min-height: 28px; }
            """

    def pane_chrome_css(self):
        """CSS for the Wave-style titlebar and the focused-pane border"""
        accent = self.pane_accent_color()
        # The accent itself is stroked from Terminal._draw_focus_border.
        # A CSS border here used to stay on every pane: `transparent` has
        # nothing behind it on the terminal box, so GTK paints that 1px black.
        return """
            .terminator-terminal-window .terminator-term-focused,
            .terminator-terminal-window .terminator-term-unfocused {
                border: none; }

            .terminator-terminal-window .pane-maximised {
                border: 2px solid %(accent)s;
                border-radius: 8px;
                padding: 2px;
                box-shadow: 0 8px 24px rgba(0,0,0,0.45); }

            button.titlebar-btn {
                padding: 0px; min-height: 0px; min-width: 0px;
                margin: 0 1px;
                color: #1d1d1f; }
            button.titlebar-btn:hover { color: #000000; }
            button.titlebar-btn-close { margin-left: 1px; }
            button.titlebar-btn-close:hover { color: #f85149; }
            button.titlebar-badge {
                padding: 0px 4px; min-height: 0px; font-size: smaller;
                color: #1d1d1f; }

            .titlebar-density-standard { min-height: 24px; }
            .titlebar-density-compact { min-height: 20px; }
            .titlebar-density-standard button.titlebar-btn {
                min-width: 24px; min-height: 24px; }
            .titlebar-density-compact button.titlebar-btn {
                min-width: 20px; min-height: 20px; }
            """ % {'accent': accent}

    def reconfigure(self):
        """Update configuration for the whole application"""

        if self.style_providers != []:
            for style_provider in self.style_providers:
                Gtk.StyleContext.remove_provider_for_screen(
                    Gdk.Screen.get_default(),
                    style_provider)
        self.style_providers = []

        # Force the window background to be transparent for newer versions of
        # GTK3. We then have to fix all the widget backgrounds because the
        # widgets theming may not render it's own background.
        css = """
            .terminator-terminal-window {
                background-color: alpha(@theme_bg_color,0); }

            .terminator-terminal-window notebook header.top {
                background-color: #161616; }

            .terminator-terminal-window .pane-separator {
                background-color: @theme_bg_color; }

            .terminator-terminal-window .terminator-terminal-searchbar {
                background-color: @theme_bg_color; }
            """

        # Fix several themes that put a borders, corners, or backgrounds around
        # viewports, making the titlebar look bad.
        css += """
            .terminator-terminal-window GtkViewport,
            .terminator-terminal-window viewport {
                border-width: 0px;
                border-radius: 0px;
                background-color: transparent; }
            """

        # Pane chrome (titlebar buttons, focus border). Shared with the
        # overlay maximise module (D), which appends to this same string.
        css += self.pane_chrome_css()
        css += self.tab_bar_css()

        # Add per profile snippets for setting the background of the HBox
        template = """
            .terminator-profile-%s {
                background-color: alpha(%s, %s); }
            """
        profiles = self.config.base.profiles
        for profile in list(profiles.keys()):
            if profiles[profile]['use_theme_colors']:
                # Create a dummy window/vte and realise it so it has correct
                # values to read from
                tmp_win = Gtk.Window()
                tmp_vte = Vte.Terminal()
                tmp_win.add(tmp_vte)
                tmp_win.realize()
                bgcolor = tmp_vte.get_style_context().get_background_color(Gtk.StateType.NORMAL)
                bgcolor = "#{0:02x}{1:02x}{2:02x}".format(int(bgcolor.red  * 255),
                                                          int(bgcolor.green * 255),
                                                          int(bgcolor.blue * 255))
                tmp_win.remove(tmp_vte)
                del(tmp_vte)
                del(tmp_win)
            else:
                bgcolor = Gdk.RGBA()
                bgcolor = profiles[profile]['background_color']
            if profiles[profile]['background_type'] == 'image':
                backgound_image = profiles[profile]['background_image']
            if profiles[profile]['background_type'] == 'transparent' or profiles[profile]['background_type'] == 'image':
                bgalpha = profiles[profile]['background_darkness']
            else:
                bgalpha = "1"

            munged_profile = "".join([c if c.isalnum() else "-" for c in profile])
            css += template % (munged_profile, bgcolor, bgalpha)

        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css.encode('utf-8'))
        self.style_providers.append(style_provider)

        # Attempt to load some theme specific stylistic tweaks for appearances
        usr_theme_dir = os.path.expanduser('~/.local/share/themes')
        (head, _tail) = os.path.split(borg.__file__)
        app_theme_dir = os.path.join(head, 'themes')

        theme_name = self.gtk_settings.get_property('gtk-theme-name')

        theme_part_list = ['terminator.css']
        if self.config['extra_styling']:    # checkbox_style - needs adding to prefs
            theme_part_list.append('terminator_styling.css')
        for theme_part_file in theme_part_list:
            for theme_dir in [usr_theme_dir, app_theme_dir]:
                path_to_theme_specific_css = os.path.join(theme_dir,
                                                          theme_name,
                                                          'gtk-3.0/apps',
                                                          theme_part_file)
                if os.path.isfile(path_to_theme_specific_css):
                    style_provider = Gtk.CssProvider()
                    style_provider.connect('parsing-error', self.on_css_parsing_error)
                    try:
                        style_provider.load_from_path(path_to_theme_specific_css)
                    except GError:
                        # Hmmm. Should we try to provide GTK version specific files here on failure?
                        gtk_version_string = '.'.join([str(Gtk.get_major_version()),
                                                       str(Gtk.get_minor_version()),
                                                       str(Gtk.get_micro_version())])
                        err('Error(s) loading css from %s into Gtk %s' % (path_to_theme_specific_css,
                                                                          gtk_version_string))
                    self.style_providers.append(style_provider)
                    break

        # Flat 1px split. wide_handle used to draw a grooved gutter
        # (about 5px: two edges and a trough) between panes.
        try:
            handle = int(self.config['handle_size'])
        except (TypeError, ValueError):
            handle = 1
        if handle not in range(0, 21):
            handle = 1
        css = """
            .terminator-terminal-window separator {
                background-image: none;
                background-color: #161b22;
                border: none;
                box-shadow: none;
                margin: 0;
                padding: 0;
                min-height: %spx;
                min-width: %spx;
            }
            """ % (handle, handle)
        # White window header, same ground as the pane titlebars.
        # Titlebutton (min/max/close) is left to the theme so the
        # traffic lights keep their own colours.
        css += """
            headerbar.terminator-header-bar {
                background-color: #ffffff;
                background-image: none;
                color: #1d1d1f;
                box-shadow: none;
            }
            headerbar.terminator-header-bar .title {
                color: #1d1d1f;
            }
            headerbar.terminator-header-bar button.terminator-header-btn {
                color: #1d1d1f;
                background-color: transparent;
                background-image: none;
                border: none;
                box-shadow: none;
            }
            headerbar.terminator-header-bar button.terminator-header-btn:hover {
                color: #000000;
                background-color: rgba(0, 0, 0, 0.06);
                background-image: none;
            }
            headerbar.terminator-header-bar button.terminator-header-btn:checked,
            headerbar.terminator-header-bar button.terminator-header-btn:checked:hover {
                background-color: rgba(0, 0, 0, 0.10);
                background-image: none;
                border-radius: 8px;
                box-shadow: none;
                color: #1d1d1f;
            }
            /* The pane-split rule above matches every separator in the
               window, including the line before the traffic lights. That
               line stays the header colour. */
            headerbar.terminator-header-bar separator {
                background-color: #ffffff;
                background-image: none;
                border: none;
                box-shadow: none;
                min-width: 0;
                min-height: 0;
            }
            """
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css.encode('utf-8'))
        self.style_providers.append(style_provider)

        # Apply the providers, incrementing priority so they don't cancel out
        # each other
        for idx in range(0, len(self.style_providers)):
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(),
                self.style_providers[idx],
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+idx)

        # Cause all the terminals to reconfigure
        for terminal in self.terminals:
            titlebar = getattr(terminal, 'titlebar', None)
            # Widget.destroy() leaves the terminal registered. Its titlebar
            # is no longer packed, and Button.get_image() on those buttons
            # segfaults inside GTK.
            if titlebar is not None:
                try:
                    if titlebar.get_parent() is None:
                        continue
                except Exception:
                    continue
            terminal.reconfigure()
            if titlebar is not None and hasattr(titlebar, 'apply_chrome_config'):
                titlebar.apply_chrome_config()

        # Reparse our keybindings
        self.keybindings.configure(self.config['keybindings'])

        # Update tab position if appropriate
        maker = Factory()
        for window in self.windows:
            child = window.get_child()
            if maker.isinstance(child, 'Notebook'):
                child.configure()

        # Each window blurs only for a profile one of its terminals uses.
        for window in self.windows:
            window.sync_blur_hint()

        # Update window decoration style (handles 'auto' mode)
        decoration_style = self.config['window_decoration_style']
        for window in self.windows:
            window.apply_window_decoration_style(decoration_style)

    def on_css_parsing_error(self, provider, section, error, user_data=None):
        """Report CSS parsing issues"""
        file_path = section.get_file().get_path()
        line_no = section.get_end_line() +1
        col_no = section.get_end_position() + 1
        err('%s, at line %d, column %d, of file %s' % (error.message,
                                                       line_no, col_no,
                                                       file_path))

    def create_group(self, name):
        """Create a new group"""
        if name not in self.groups:
            dbg('registering group %s' % name)
            self.groups.append(name)

    def closegroupedterms(self, group):
        """Close all terminals in a group (process-aware confirm first)"""
        members = [t for t in self.terminals[:] if t.group == group]
        try:
            from .close_confirm import confirm_close_terminals
            if not confirm_close_terminals(members):
                dbg('closegroupedterms: user cancelled')
                return False
        except Exception as ex:
            dbg('closegroupedterms confirm failed: %s' % ex)
            try:
                from .util import gerr
                gerr('Could not confirm closing terminals: %s' % ex)
            except Exception:
                err('closegroupedterms confirm failed: %s' % ex)
            return False
        # Hidden panes of a legacy zoom are detached from the window; put
        # them back so close-term reaches a parent that is in a window.
        hidden = [t for t in members if t.get_toplevel() not in self.windows]
        if hidden:
            from .zoomguard import leave_legacy_zoom_all
            leave_legacy_zoom_all(self.windows, reason='closegroupedterms')
        if members and not [t for t in self.terminals if t not in members]:
            # Round-2 P2-7: the group covers every terminal, i.e. this quits.
            # Save the whole layout once, up front (like closing the last
            # window), instead of finalizing mid-loop with one pane left.
            try:
                from .session import SessionManager
                SessionManager().finalize()
            except Exception as ex:
                dbg('closegroupedterms finalize: %s' % ex)
        for terminal in members:
            # Same path as exit / Ctrl+Shift+W: the parent removes and
            # deregisters the terminal and then calls close() exactly once
            # (calling close() directly re-entered through close-term).
            if terminal in self.terminals:
                terminal.emit('close-term')
        return True

    def group_hoover(self):
        """Clean out unused groups"""

        if self.config['autoclean_groups']:
            inuse = []
            todestroy = []

            for terminal in self.terminals:
                if terminal.group:
                    if not terminal.group in inuse:
                        inuse.append(terminal.group)

            for group in self.groups:
                if not group in inuse:
                    todestroy.append(group)

            dbg('%d groups, hoovering %d' %
                    (len(self.groups), len(todestroy)))
            for group in todestroy:
                self.groups.remove(group)

    def group_emit(self, terminal, group, type, event):
        """Emit to each terminal in a group"""
        dbg('emitting a keystroke for group %s' % group)
        for term in self.terminals:
            if term != terminal and term.group == group:
                term.vte.emit(type, eventkey2gdkevent(event))

    def all_emit(self, terminal, type, event):
        """Emit to all terminals"""
        for term in self.terminals:
            if term != terminal:
                term.vte.emit(type, eventkey2gdkevent(event))

    def do_enumerate(self, widget, pad):
        """Insert the number of each terminal in a group, into that terminal"""
        if pad:
            numstr = '%0'+str(len(str(len(self.terminals))))+'d'
        else:
            numstr = '%d'

        terminals = []
        for window in self.windows:
            containers, win_terminals = enumerate_descendants(window)
            terminals.extend(win_terminals)

        for term in self.get_target_terms(widget):
            if term not in terminals:
                continue
            idx = terminals.index(term)
            term.feed(numstr.encode() % (idx + 1))

    def do_insert_term_name(self, widget):
        terminals = []
        for window in self.windows:
            containers, win_terminals = enumerate_descendants(window)
            terminals.extend(win_terminals)

        for term in self.get_target_terms(widget):
            name = term.titlebar.get_custom_string() or term.get_window_title()
            term.feed(name.encode())

    def get_sibling_terms(self, widget):
        termset = []
        for term in self.terminals:
            if term.group == widget.group:
                termset.append(term)
        return(termset)

    def get_target_terms(self, widget):
        """Get the terminals we should currently be broadcasting to"""
        if self.groupsend == self.groupsend_type['all']:
            return(self.terminals)
        elif self.groupsend == self.groupsend_type['group']:
            if widget.group != None:
                return(self.get_sibling_terms(widget))
        return([widget])

    def get_focussed_terminal(self):
        """iterate over all the terminals to find which, if any, has focus"""
        for terminal in self.terminals:
            if terminal.get_vte().has_focus():
                return(terminal)
        return(None)

    def focus_changed(self, widget):
        """We just moved focus to a new terminal"""
        for terminal in self.terminals:
            terminal.titlebar.update(widget)
        try:
            top = widget.get_toplevel()
            if (top is not None and hasattr(top, 'is_child_notebook')
                    and top.is_child_notebook()):
                note = top.get_child()
                if hasattr(note, 'note_pane_focus'):
                    note.note_pane_focus(widget)
        except Exception:
            pass
        return

    def focus_left(self, widget):
        self.last_focused_term=widget

    def describe_layout(self, save_cwd = False):
        """Describe our current layout"""
        layout = {}
        count = 0
        for window in self.windows:
            parent = ''
            count = window.describe_layout(count, parent, layout, 0, save_cwd)

        return(layout)

    def zoom_in_all(self):
        for term in self.terminals:
            term.zoom_in()
    
    def zoom_out_all(self):
        for term in self.terminals:
            term.zoom_out()
    
    def zoom_orig_all(self):
        for term in self.terminals:
            term.zoom_orig()

    def new_random_group(self):
        defaultmembers=[_('Alpha'),_('Beta'),_('Gamma'),_('Delta'),_('Epsilon'),_('Zeta'),_('Eta'),
                        _('Theta'),_('Iota'),_('Kappa'),_('Lambda'),_('Mu'),_('Nu'),_('Xi'),
                        _('Omicron'),_('Pi'),_('Rho'),_('Sigma'),_('Tau'),_('Upsilon'),_('Phi'),
                        _('Chi'),_('Psi'),_('Omega')]
        currentgroups=set(self.groups)
        for i in range(1,4):
            defaultgroups=set(map(''.join, list(itertools.product(defaultmembers,repeat=i))))
            freegroups = list(defaultgroups-currentgroups)
            if freegroups:
                return random.choice(freegroups)
        return ''

# vim: set expandtab ts=4 sw=4:
