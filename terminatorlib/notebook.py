# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""notebook.py - classes for the notebook widget"""

import os
from functools import cmp_to_key
from gi.repository import GObject
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GLib
from gi.repository import Pango

from .terminator import Terminator
from .config import Config
from .factory import Factory
from .container import Container
from .editablelabel import EditableLabel
from .translation import _
from .util import err, dbg, enumerate_descendants, make_uuid, logical_parent


def folder_basename(path):
    """Directory name used as a tab's default title.

    The home directory is ``~``. Anything else is the last path segment.
    """
    if not path:
        return ''
    path = os.path.abspath(os.path.expanduser(path))
    home = os.path.abspath(os.path.expanduser('~'))
    if path == home:
        return '~'
    name = os.path.basename(path.rstrip(os.sep))
    return name or path


def folder_subtitle(path):
    """Folder path shown under the tab name, with ``~`` for home."""
    if not path:
        return ''
    path = os.path.abspath(os.path.expanduser(path))
    home = os.path.abspath(os.path.expanduser('~'))
    if path == home:
        return '~'
    prefix = home + os.sep
    if path.startswith(prefix):
        return '~' + os.sep + path[len(prefix):]
    return path


def choose_naming_terminal(terminals, focused):
    """Which pane names the tab. The focused pane wins; else the first."""
    terms = [term for term in (terminals or []) if term is not None]
    if focused is not None and focused in terms:
        return focused
    if terms:
        return terms[0]
    return None


def pane_row_title(cwd, fallback=''):
    """Name of one pane in the sidebar tree. The directory wins."""
    name = folder_basename(cwd)
    if name:
        return name
    return fallback or ''


def sidebar_tree_rows(pages):
    """Turn tabs into a two-level tree.

    ``pages`` is a list of ``(title, pane_titles)``. A tab with one pane is
    a single row. A tab with several panes keeps that title as the parent
    and lists each pane underneath it.
    """
    rows = []
    for page, item in enumerate(pages or []):
        title = item[0] or ''
        panes = list(item[1] or [])
        rows.append({'title': title, 'page': page, 'pane': None, 'depth': 0})
        if len(panes) >= 2:
            for index, pane_title in enumerate(panes):
                rows.append({
                    'title': pane_title or title,
                    'page': page,
                    'pane': index,
                    'depth': 1,
                })
    return rows


def tab_nav_sensitive(index, count):
    """Back and forward in the sidebar. They do not wrap."""
    if count < 1 or index < 0 or index >= count:
        return {'back': False, 'forward': False}
    return {
        'back': index > 0,
        'forward': index < count - 1,
    }


# Shared stroke icons. Same ink box, so they sit at the same size.
TAB_CLOSE_ICON = 'terminator-tab-close-symbolic'
TAB_LOCK_ICON = 'terminator-tab-lock-symbolic'
TAB_UNLOCK_ICON = 'terminator-tab-unlock-symbolic'
SIDEBAR_MARK_PX = 12
# The SVG tile. Drawn at this size so the stroke is not resampled.
SIDEBAR_ICON_PX = 16


def sidebar_mark(name, css_class, fallback):
    """A sidebar glyph drawn from our SVG, or a theme icon if it is missing."""
    from .util import scale_image_to_ink, svg_icon_surface
    image = Gtk.Image()
    image.get_style_context().add_class(css_class)
    image.set_halign(Gtk.Align.CENTER)
    image.set_valign(Gtk.Align.CENTER)

    def _paint(*_args):
        scale = image.get_scale_factor() or 1
        if getattr(image, '_mark_scale', None) == scale:
            return False
        try:
            surface = svg_icon_surface(name, SIDEBAR_ICON_PX, scale)
        except Exception:
            surface = None
        if surface is not None:
            image._mark_scale = scale
            image.set_from_surface(surface)
            return False
        if getattr(image, '_mark_fallback', False):
            return False
        image._mark_fallback = True
        image.set_from_icon_name(fallback, Gtk.IconSize.MENU)
        scale_image_to_ink(
            image, fallback, target_px=SIDEBAR_MARK_PX, button_px=24)
        return False

    image.connect('realize', _paint)
    image.connect('notify::scale-factor', _paint)
    _paint()
    return image


def sidebar_icon_button(image):
    """A real button around a sidebar glyph.

    The row used to be one button, with the lock and close painted on it
    and chosen by pointer position. A press on that row ran the action
    immediately. A separate button highlights while it is held and runs
    its action only if the pointer is still on it when released.
    """
    button = Gtk.Button()
    button.set_relief(Gtk.ReliefStyle.NONE)
    button.set_focus_on_click(False)
    button.set_can_focus(False)
    button.get_style_context().add_class('terminator-tab-action')
    button.add(image)
    return button


def tree_drop_target(rows, x, y, promote_x=36):
    """Where a dragged tab or child pane lands.

    ``rows`` are ``depth``, ``page``, ``pane``, ``top`` and ``bottom``.
    A tab row's middle nests the drop inside that tab. Its top and bottom
    edges insert a tab. A child row reorders panes; dropping it in the
    left gutter makes it a tab.
    """
    if not rows:
        return ('tab', 0)
    hit = None
    for row in rows:
        if row['top'] <= y < row['bottom']:
            hit = row
            break
    if hit is None:
        if y < rows[0]['top']:
            return ('tab', 0)
        last = rows[-1]
        if last['depth'] == 1 and x >= promote_x:
            return ('pane', last['page'], last['pane'] + 1)
        return ('tab', last['page'] + 1)
    height = max(1.0, float(hit['bottom'] - hit['top']))
    rel = (y - hit['top']) / height
    if hit['depth'] == 0:
        if rel < 0.25:
            return ('tab', hit['page'])
        if rel > 0.75:
            return ('tab', hit['page'] + 1)
        return ('into', hit['page'])
    if x < promote_x:
        if rel < 0.5:
            return ('tab', hit['page'])
        return ('tab', hit['page'] + 1)
    if rel < 0.5:
        return ('pane', hit['page'], hit['pane'])
    return ('pane', hit['page'], hit['pane'] + 1)


def tab_drop_index(spans, y):
    """Where a dragged tab lands.

    ``spans`` is ``(top, bottom)`` for each page, top to bottom. ``y`` is
    the pointer. The result is an insertion index from 0 through
    ``len(spans)``: before the first page whose midpoint is below ``y``.
    """
    for index, (top, bottom) in enumerate(spans):
        if y < (top + bottom) / 2.0:
            return index
    return len(spans)


def reorder_to_index(current, insert_at, count):
    """``reorder_child`` index for a page that is already in the notebook.

    ``insert_at`` is the slot it would take if it were lifted out first.
    ``None`` means the page would not move.
    """
    if count <= 1 or current < 0 or current >= count:
        return None
    if insert_at > current:
        insert_at -= 1
    if insert_at < 0:
        insert_at = 0
    if insert_at > count - 1:
        insert_at = count - 1
    if insert_at == current:
        return None
    return insert_at


def pane_menu_sensitive(index, count):
    """Which items of a child-pane menu can run.

    Up and down do not wrap. Making the pane its own tab needs a sibling
    to leave behind. Close always can.
    """
    if count < 1 or index < 0 or index >= count:
        return {'up': False, 'down': False, 'promote': False, 'close': False}
    return {
        'up': index > 0,
        'down': index < count - 1,
        'promote': count > 1,
        'close': True,
    }


def tab_menu_sensitive(index, count):
    """Which items of the tab context menu can run.

    Moves do not wrap: the first tab cannot move left, the last cannot
    move right. Detach needs another tab to leave behind. Close always
    can.
    """
    if count < 1 or index < 0 or index >= count:
        return {'left': False, 'right': False, 'detach': False,
                'close': False}
    return {
        'left': index > 0,
        'right': index < count - 1,
        'detach': count > 1,
        'close': True,
    }


_TAB_DRAG_PAYLOADS = {}


def _tab_dnd_targets():
    """Drag type shared by every window's tab list. Same application only."""
    cached = getattr(_tab_dnd_targets, '_cached', None)
    if cached is None:
        cached = [Gtk.TargetEntry.new(
            'application/x-terminator-tab', Gtk.TargetFlags.SAME_APP, 1)]
        _tab_dnd_targets._cached = cached
    return cached


class Notebook(Container, Gtk.Notebook):
    """Class implementing a Gtk.Notebook container"""
    window = None
    last_active_term = None
    last_maximised_term = None
    _tab_switching = False
    _maximise_changed_handler = None
    pending_on_tab_switch = None
    pending_on_tab_switch_args = None

    def __init__(self, window):
        """Class initialiser"""
        if isinstance(window.get_child(), Gtk.Notebook):
            err('There is already a Notebook at the top of this window')
            raise(ValueError)

        Container.__init__(self)
        GObject.GObject.__init__(self)
        self.terminator = Terminator()
        self.window = window
        GObject.type_register(Notebook)
        self.register_signals(Notebook)
        self.connect('switch-page', self.deferred_on_tab_switch)
        self.connect('scroll-event', self.on_scroll_event)
        self.connect('create-window', self.create_window_detach)
        self.connect_after('drag-failed', self.on_tab_drag_failed)
        self.configure()

        self.set_can_focus(False)
        self.get_style_context().add_class('terminator-notebook')
        self.set_show_border(False)

        child = window.get_child()
        window.remove(child)
        window.add(self)
        window_last_active_term = window.last_active_term
        window_last_maximised_term = getattr(window, 'last_maximised_term', None)
        self.newtab(widget=child)
        if window_last_active_term:
            self.set_last_active_term(window_last_active_term)
            window.last_active_term = None
        if window_last_maximised_term:
            self.last_maximised_term[child] = window_last_maximised_term
            window.last_maximised_term = None
        self.connect('page-removed', self._on_page_removed)
        self._wire_window_maximise_signals()

        self.show_all()
        # configure() built the list before this notebook had a parent.
        side = getattr(self, '_tab_sidebar', None)
        if side is not None and getattr(self, '_tab_shell', None) is None:
            self._attach_tab_shell(side)
        # The notebook itself has no GdkWindow. Tab-strip hits land on the
        # window, which does not start out with a scroll mask.
        self._select_tab_scroll()

    def configure(self):
        """Apply widget-wide settings"""
        # FIXME: The old reordered handler updated Terminator.terminals with
        # the new order of terminals. We probably need to preserve this for
        # navigation to next/prev terminals.
        #self.connect('page-reordered', self.on_page_reordered)
        self.connect('page-reordered', self.on_page_reordered_dirty)
        self.set_scrollable(self.config['scroll_tabbar'])

        if self.config['tab_position'] == 'hidden':
            self.set_show_tabs(False)
        elif self.config['tab_position'] == 'left':
            # The list is a sibling of this notebook, not its header.
            # Showing the native tabs would put that header back.
            self.set_tab_pos(Gtk.PositionType.LEFT)
            self.set_show_tabs(False)
        else:
            self.set_show_tabs(True)
            pos = getattr(Gtk.PositionType, self.config['tab_position'].upper())
            self.set_tab_pos(pos)

        for tab in range(0, self.get_n_pages()):
            page = self.get_nth_page(tab)
            label = self.get_tab_label(page)
            label.update_angle()
            self._pack_tab(page)
        self._ensure_tab_add_button()

#        style = Gtk.RcStyle()  # FIXME FOR GTK3 how to do it there? actually do we really want to override the theme?
#        style.xthickness = 0
#        style.ythickness = 0
#        self.modify_style(style)
        self.last_active_term = {}
        if not hasattr(self, 'last_maximised_term') or self.last_maximised_term is None:
            self.last_maximised_term = {}
        self._scroll_acc = 0.0
        self._select_tab_scroll()

    def create_window_detach(self, notebook, widget, x, y):
        """Defer detaching a dropped tab until the drag has ended"""
        dbg('deferring detach of dropped tab: %s' % widget)
        GLib.idle_add(self.detach_tab_to_new_window, widget, x, y)

    def detach_tab_to_new_window(self, widget, x=None, y=None):
        """Detach the tab containing widget into a newly created window"""
        child = self.find_tab_root(widget)
        if self.page_num(child) == -1:
            err('could not find tab to detach for %s' % widget)
            return False

        dbg('detaching tab into new window: %s' % child)
        keep_list = self.tab_list_visible()
        custom = None
        locked = False
        label = self.get_tab_label(child)
        if label is not None and hasattr(label, 'get_custom_label'):
            custom = label.get_custom_label()
        if label is not None and hasattr(label, 'get_locked'):
            locked = bool(label.get_locked())
        maker = Factory()
        window = maker.make('Window')
        if x is not None and y is not None and window.can_set_position():
            window.move(x, y)
        size = self.window.get_size()
        window.resize(size.width, size.height)

        self.detach_tab(child)
        self.disconnect_child(child)
        # One tab left used to throw the notebook away. That closes the
        # tab list. Leave the list up, and open it on the new window too.
        self._drop_empty_pages()
        if self.get_n_pages() == 0:
            top = self.get_toplevel()
            self._unparent_from_window()
            if top is not None and hasattr(top, 'hoover'):
                top.hoover()
        else:
            self._sidebar_sig = None
            self._hide_native_tab_labels()
            self._queue_sidebar_refresh()
        window.add(child)
        window.show_all()
        if keep_list and hasattr(window, '_set_tab_panel_visible'):
            window._set_tab_panel_visible(True)
        notebook = window.get_child()
        if maker.isinstance(notebook, 'Notebook'):
            page = notebook.get_nth_page(0)
            moved = notebook.get_tab_label(page) if page is not None else None
            if custom and moved is not None and hasattr(moved, 'set_custom_label'):
                moved.set_custom_label(custom)
            if locked and moved is not None and hasattr(moved, 'set_locked'):
                moved.set_locked(True)
            if page is not None and not maker.isinstance(page, 'Terminal'):
                notebook._rewire_moved_terminals(page)
            notebook._hide_native_tab_labels()
        return False

    def page_num_of_label(self, label):
        """Index of the page whose tab label is `label`, or None."""
        for i in range(self.get_n_pages()):
            page = self.get_nth_page(i)
            if page is not None and self.get_tab_label(page) is label:
                return i
        return None

    def move_labeled_tab(self, label, direction):
        """Move one tab left or right. Does not wrap."""
        win = getattr(self, 'window', None)
        if win is not None and getattr(win, 'is_zoomed', lambda: False)():
            from .zoomguard import leave_zoom
            leave_zoom(win, reason='window', quiet=False)
        page = self.page_num_of_label(label)
        if page is None:
            return
        count = self.get_n_pages()
        if not tab_menu_sensitive(page, count).get(direction):
            return
        child = self.get_nth_page(page)
        new = page - 1 if direction == 'left' else page + 1
        self.reorder_child(child, new)
        try:
            from .session import try_mark_dirty
            try_mark_dirty('notebook.move_tab')
        except Exception:
            pass

    def detach_labeled_tab(self, label):
        """Tear the tab with this label out into its own window."""
        page = self.page_num_of_label(label)
        if page is None:
            return
        if not tab_menu_sensitive(page, self.get_n_pages())['detach']:
            return
        child = self.get_nth_page(page)
        win = getattr(self, 'window', None)
        if win is not None and hasattr(win, 'detach_tab_to_new_window'):
            win.detach_tab_to_new_window(child)
        else:
            self.detach_tab_to_new_window(child)

    def on_tab_drag_failed(self, notebook, context, result):
        """Re-allocate after a failed tab drag so the label repaints"""
        GLib.idle_add(self.queue_resize)
        return False

    def create_layout(self, layout):
        """Apply layout configuration"""
        def child_compare(a, b):
            order_a = int(children[a]['order'])
            order_b = int(children[b]['order'])

            if (order_a == order_b):
                return 0
            if (order_a < order_b):
                return -1
            if (order_a > order_b):
                return 1

        if 'children' not in layout:
            err('layout specifies no children: %s' % layout)
            return

        children = layout['children']
        if len(children) < 1:
            err('incorrect number of children for Notebook: %s' % layout)
            return

        num = 0
        keys = list(children.keys())
        keys = sorted(keys, key=cmp_to_key(child_compare))

        for child_key in keys:
            child = children[child_key]
            dbg('Making a child of type: %s' % child['type'])
            if child['type'] == 'Terminal':
                pass
            elif child['type'] == 'VPaned':
                page = self.get_nth_page(num)
                self.split_axis(page, True)
            elif child['type'] == 'HPaned':
                page = self.get_nth_page(num)
                self.split_axis(page, False)
            num = num + 1

        num = 0
        for child_key in keys:
            page = self.get_nth_page(num)
            if not page:
                # This page does not yet exist, so make it
                self.newtab(children[child_key])
                page = self.get_nth_page(num)
            if 'labels' in layout:
                labeltext = layout['labels'][num]
                if labeltext and labeltext != "None":
                    label = self.get_tab_label(page)
                    label.set_custom_label(labeltext)
            flags = layout.get('locked') or []
            if (num < len(flags) and
                    str(flags[num]).strip().lower() == 'true'):
                label = self.get_tab_label(page)
                if label is not None and hasattr(label, 'set_locked'):
                    label.set_locked(True)
            page.create_layout(children[child_key])

            if  layout.get('last_active_term',  None):
                self.last_active_term[page] = make_uuid(layout['last_active_term'][num])
            if layout.get('last_maximised_term', None):
                raw_lmt = layout['last_maximised_term']
                if isinstance(raw_lmt, (list, tuple)) and num < len(raw_lmt) and raw_lmt[num]:
                    self.last_maximised_term[page] = make_uuid(raw_lmt[num])
            self._wire_window_maximise_signals()
            num = num + 1

        if 'active_page' in layout:
            # Need to do it later, or layout changes result
            GLib.idle_add(self.set_current_page, int(layout['active_page']))
        else:
            self.set_current_page(0)
        self._sidebar_sig = None
        self._queue_sidebar_refresh()

    def split_axis(self, widget, vertical=True, cwd=None, sibling=None, widgetfirst=True):
        """Split the axis of a terminal inside us"""
        dbg('called for widget: %s' % widget)
        order = None
        page_num = self.page_num(widget)
        if page_num == -1:
            err('Notebook::split_axis: %s not found in Notebook' % widget)
            return

        label = self.get_tab_label(widget)
        lat = None
        if hasattr(self, 'last_active_term') and self.last_active_term is not None:
            lat = self.last_active_term.pop(widget, None)
        lmt = None
        if hasattr(self, 'last_maximised_term') and self.last_maximised_term is not None:
            lmt = self.last_maximised_term.pop(widget, None)
        self.remove(widget)

        maker = Factory()
        if vertical:
            container = maker.make('vpaned')
        else:
            container = maker.make('hpaned')

        self.get_toplevel().set_pos_by_ratio = True

        if not sibling:
            sibling = maker.make('terminal')
            sibling.set_cwd(cwd)
            if self.config['always_split_with_profile']:
                sibling.force_set_profile(None, widget.get_profile())
            sibling.spawn_child()
            if widget.group and self.config['split_to_group']:
                sibling.set_group(None, widget.group)
        elif (self.config['always_split_with_profile'] and
              hasattr(sibling, 'force_set_profile') and
              hasattr(widget, 'get_profile')):
            sibling.force_set_profile(None, widget.get_profile())

        self.insert_page(container, None, page_num)
        if hasattr(self, 'last_active_term') and self.last_active_term is not None:
            if lat is not None:
                self.last_active_term[container] = lat
            elif hasattr(widget, 'uuid'):
                self.last_active_term[container] = widget.uuid
        if hasattr(self, 'last_maximised_term') and self.last_maximised_term is not None and lmt is not None:
            self.last_maximised_term[container] = lmt
        self.set_tab_detachable(container, self.config['detachable_tabs'])
        self._pack_tab(container)
        self.set_tab_reorderable(container, True)
        self.set_tab_label(container, label)
        self.show_all()

        order = [widget, sibling]
        if widgetfirst is False:
            order.reverse()

        for terminal in order:
            container.add(terminal)
        self.set_current_page(page_num)

        self.show_all()

        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        self.get_toplevel().set_pos_by_ratio = False

        if hasattr(terminal, 'ensure_visible_and_focussed'):
            GLib.idle_add(terminal.ensure_visible_and_focussed)
        self._hide_native_tab_labels()
        self._queue_sidebar_refresh()
        try:
            from .session import try_mark_dirty
            try_mark_dirty('notebook.split_axis')
        except Exception:
            pass

    def add(self, widget, metadata=None):
        """Add a widget to the container"""
        dbg('adding a new tab')
        self.newtab(widget=widget, metadata=metadata)

    def remove(self, widget):
        """Remove a widget from the container"""
        page_num = self.page_num(widget)
        if page_num == -1:
            err('%s not found in Notebook. Actual parent is: %s' %
                    (widget, widget.get_parent()))
            return(False)
        self.remove_page(page_num)
        self.disconnect_child(widget)
        try:
            from .session import try_mark_dirty
            try_mark_dirty('notebook.remove')
        except Exception:
            pass
        return(True)

    def replace(self, oldwidget, newwidget):
        """Replace a tab's contents with a new widget"""
        page_num = self.page_num(oldwidget)
        self.remove(oldwidget)
        self.add(newwidget)
        self.reorder_child(newwidget, page_num)

    def swap_child(self, old_widget, new_widget):
        """Replace page contents in-place; keep tab label and page number.

        Placeholder pages are not wired with Terminal signals (module D).
        """
        page_num = self.page_num(old_widget)
        if page_num == -1:
            raise ValueError('swap_child: %s not in Notebook' % old_widget)
        label = self.get_tab_label(old_widget)
        lat = None
        if hasattr(self, 'last_active_term'):
            lat = self.last_active_term.pop(old_widget, None)
        lmt = None
        if hasattr(self, 'last_maximised_term') and self.last_maximised_term is not None:
            lmt = self.last_maximised_term.pop(old_widget, None)

        self.disconnect_child(old_widget)
        # Keep the label widget; detach page without destroying the label
        self.detach_tab(old_widget)

        maker = Factory()
        if maker.isinstance(new_widget, 'Terminal'):
            # Re-insert via newtab so signals + TabLabel stay consistent
            metadata = {'tabnum': page_num}
            if label is not None and hasattr(label, 'get_custom_label'):
                custom = label.get_custom_label()
                if custom:
                    metadata['label'] = custom
            locked = False
            if label is not None and hasattr(label, 'get_locked'):
                try:
                    locked = bool(label.get_locked())
                except Exception:
                    locked = False
            self.newtab(widget=new_widget, metadata=metadata)
            if lat is not None:
                self.last_active_term[new_widget] = lat
            if lmt is not None and hasattr(self, 'last_maximised_term') and self.last_maximised_term is not None:
                self.last_maximised_term[new_widget] = lmt
            if locked:
                new_label = self.get_tab_label(new_widget)
                if new_label is not None and hasattr(new_label, 'set_locked'):
                    new_label.set_locked(True)
        else:
            self.insert_page(new_widget, label, page_num)
            self._pack_tab(new_widget)
            self.set_tab_reorderable(new_widget, True)
            if hasattr(self, 'last_active_term'):
                term = getattr(new_widget, 'terminal', None)
                self.last_active_term[new_widget] = (
                    lat if lat is not None else getattr(term, 'uuid', None))
            if hasattr(self, 'last_maximised_term') and self.last_maximised_term is not None and lmt is not None:
                self.last_maximised_term[new_widget] = lmt
            self.set_current_page(page_num)
            new_widget.show_all()
        try:
            from .session import try_mark_dirty
            try_mark_dirty('notebook.swap_child')
        except Exception:
            pass
        return True

    def get_child_metadata(self, widget):
        """Fetch the relevant metadata for a widget which we'd need
        to recreate it when it's re-added"""
        metadata = {}
        metadata['tabnum'] = self.page_num(widget)
        label = self.get_tab_label(widget)
        if not label:
            dbg('unable to find label for widget: %s' % widget)
        elif label.get_custom_label():
            metadata['label'] = label.get_custom_label()
        else:
            dbg('don\'t grab the label as it was not customised')
        return metadata

    def _pack_tab(self, widget):
        """Rows in the left list fill the sidebar; top tabs hug their label."""
        left = self.get_tab_pos() == Gtk.PositionType.LEFT
        self.child_set_property(widget, 'tab-expand', False)
        self.child_set_property(widget, 'tab-fill',
                                left and getattr(self, '_tab_tree', None) is None)

    def _icon_button(self, icon_names, tooltip, css_class):
        """Flat icon button used in the tab toolbar."""
        btn = Gtk.Button()
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.set_focus_on_click(False)
        btn.set_can_focus(False)
        btn.get_style_context().add_class(css_class)
        image = Gtk.Image()
        theme = Gtk.IconTheme.get_default()
        for name in icon_names:
            try:
                if theme is not None and theme.has_icon(name):
                    image.set_from_icon_name(name, Gtk.IconSize.MENU)
                    break
            except Exception:
                continue
        # Same 24px box as a pane titlebar button. MENU is 16px and
        # fits without the 20px enlargement that made these too big.
        from .util import pin_icon_button
        pin_icon_button(btn, 24)
        btn.add(image)
        btn.set_tooltip_text(tooltip)
        return btn

    def _ensure_tab_add_button(self):
        """Sidebar toolbar: plus (new tab) on the left, back and forward on the right.

        The header's sidebar icon is the show/hide toggle, so this button
        stays a plus.

        A top strip keeps a single plus after the chips.
        """
        if getattr(self, '_new_tab_btn', None) is not None:
            return
        if self.config['tab_position'] == 'hidden':
            return
        left = self.config['tab_position'] == 'left'
        if left:
            bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
            bar.get_style_context().add_class('terminator-tab-toolbar')
            bar.set_hexpand(True)
            # Wide enough that back and forward sit on the right edge.
            bar.set_size_request(220, -1)
            new_btn = self._icon_button(
                ('list-add-symbolic', 'tab-new-symbolic'),
                _('Open a new tab'), 'terminator-tab-add')
            prev_btn = self._icon_button(
                ('go-previous-symbolic', 'pan-start-symbolic'),
                _('Switch to the previous tab'), 'terminator-tab-nav')
            next_btn = self._icon_button(
                ('go-next-symbolic', 'pan-end-symbolic'),
                _('Switch to the next tab'), 'terminator-tab-nav')
            new_btn.connect('clicked', lambda *_a: self._on_tab_toolbar('new'))
            prev_btn.connect('clicked', lambda *_a: self._on_tab_toolbar('back'))
            next_btn.connect('clicked', lambda *_a: self._on_tab_toolbar('forward'))
            bar.pack_start(new_btn, False, False, 0)
            bar.pack_end(next_btn, False, False, 0)
            bar.pack_end(prev_btn, False, False, 0)
            side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            side.get_style_context().add_class('terminator-tab-sidebar')
            side.set_vexpand(True)
            side.pack_start(bar, False, False, 0)
            side.pack_start(self._build_tab_tree(), True, True, 0)
            self._enable_tab_drop(side)
            side.show_all()
            self._new_tab_btn = new_btn
            self._tab_prev_btn = prev_btn
            self._tab_next_btn = next_btn
            self._tab_toolbar = bar
            self._tab_sidebar = side
            # Not an action widget. The notebook header splits its height
            # with the native tab strip, and measuring that strip shows the
            # labels again. The list is a sibling and takes the full height.
            self._attach_tab_shell(side)
            self.connect('switch-page', self._on_tab_nav_switch)
            self.connect('page-added', lambda *_a: self._queue_sidebar_refresh())
            self.connect('page-removed', lambda *_a: self._queue_sidebar_refresh())
            self.connect('page-reordered', lambda *_a: self._queue_sidebar_refresh())
            self._refresh_tab_nav()
            self._queue_sidebar_refresh()
            return
        btn = self._icon_button(
            ('list-add-symbolic', 'tab-new-symbolic'),
            _('Open a new tab'), 'terminator-tab-add')
        btn.connect('clicked', lambda *_a: self.newtab())
        btn.show_all()
        self._new_tab_btn = btn
        self.set_action_widget(btn, Gtk.PackType.END)
        self.connect('size-allocate', self._place_tab_add_beside_tabs)

    def tab_list_visible(self):
        """True when the left list, or the native tab strip, is on screen."""
        side = getattr(self, '_tab_sidebar', None)
        if side is not None:
            try:
                return bool(side.get_visible() and side.get_parent() is not None)
            except Exception:
                return False
        try:
            return bool(self.get_show_tabs())
        except Exception:
            return False

    def show_left_tab_list(self):
        """Open the left list. The native tab strip stays hidden."""
        self._ensure_tab_add_button()
        side = getattr(self, '_tab_sidebar', None)
        if side is None:
            return
        if getattr(self, '_tab_shell', None) is None:
            self._attach_tab_shell(side)
        side.set_no_show_all(False)
        side.show_all()
        self.set_show_tabs(False)
        self._hide_native_tab_labels()
        self._queue_sidebar_refresh()

    def hide_tab_list(self):
        """Close the left list, or the native strip when that is what is showing."""
        side = getattr(self, '_tab_sidebar', None)
        if side is not None:
            side.set_no_show_all(True)
            side.hide()
        self.set_show_tabs(False)

    def _attach_tab_shell(self, sidebar):
        """Put the list and this notebook side by side in the window."""
        if getattr(self, '_tab_shell', None) is not None:
            return
        parent = self.get_parent()
        if parent is None:
            return
        shell = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        shell.get_style_context().add_class('terminator-tab-shell')
        shell._tab_shell_notebook = self
        window = self.get_toplevel()
        if parent is window:
            Gtk.Window.remove(window, self)
        else:
            parent.remove(self)
        sidebar.set_vexpand(True)
        sidebar.set_valign(Gtk.Align.FILL)
        sidebar.set_hexpand(False)
        self.set_hexpand(True)
        shell.pack_start(sidebar, False, False, 0)
        shell.pack_start(self, True, True, 0)
        self._tab_shell = shell
        self._tab_sidebar = sidebar
        shell.show_all()
        self.set_show_tabs(False)
        if parent is window:
            Gtk.Window.add(window, shell)
        else:
            parent.add(shell)

    def _unparent_from_window(self):
        """Leave the window, taking the tab-list shell with this notebook."""
        holder = logical_parent(self)
        if holder is not None:
            holder.remove(self)
        else:
            parent = self.get_parent()
            if parent is not None:
                parent.remove(self)
        shell = getattr(self, '_tab_shell', None)
        self._tab_shell = None
        if shell is None:
            return
        try:
            shell._tab_shell_notebook = None
            if self.get_parent() is shell:
                shell.remove(self)
        except Exception:
            pass

    def _on_tab_toolbar(self, which):
        """New, back and forward in the sidebar. Back and forward do not wrap."""
        if which == 'new':
            self.newtab()
        elif which == 'back':
            self.prev_page()
        elif which == 'forward':
            self.next_page()
        self._refresh_tab_nav()

    def _on_tab_nav_switch(self, _notebook, _page, page_num):
        self._refresh_tab_nav(page_num)
        return False

    def _refresh_tab_nav(self, page_num=None):
        """Grey out back or forward when that direction has no tab."""
        prev = getattr(self, '_tab_prev_btn', None)
        nxt = getattr(self, '_tab_next_btn', None)
        if prev is None or nxt is None:
            return False
        if page_num is None:
            page_num = self.get_current_page()
        state = tab_nav_sensitive(page_num, self.get_n_pages())
        prev.set_sensitive(state['back'])
        nxt.set_sensitive(state['forward'])
        return False

    def _build_tab_tree(self):
        """Sidebar tree: a tab, then its panes when the tab is split.

        Rows are ordinary widgets, not a Gtk.TreeView. The theme paints
        over a tree selection, and these rows use the same styling as the
        old tab list.
        """
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        box.get_style_context().add_class('terminator-tab-tree')
        box.set_vexpand(True)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_shadow_type(Gtk.ShadowType.NONE)
        scroll.set_vexpand(True)
        # Do not request the current allocation. That grows the window
        # on every size pass.
        scroll.set_propagate_natural_height(False)
        scroll.set_size_request(228, -1)
        scroll.add(box)
        self._enable_tab_drop(box)
        self._enable_tab_drop(scroll)
        self._tab_rows = box
        self._tab_tree = box
        self._tab_tree_scroll = scroll
        self._sidebar_sig = None
        self._sidebar_target = None
        self._sidebar_collapsed = set()
        return scroll

    def _current_sidebar_target(self):
        """Page and pane index that should look selected. Pane -1 is the tab."""
        page = self.get_current_page()
        panes = self._ordered_panes(self.get_nth_page(page)) if page >= 0 else []
        focused = self._focused_terminal(panes)
        if len(panes) >= 2 and focused in panes:
            return page, panes.index(focused)
        return page, -1

    def _ordered_panes(self, page):
        return self._terminals_in_page(page)

    def _pane_cwd(self, term):
        cwd = None
        try:
            cwd = term.get_cwd()
        except Exception:
            cwd = None
        if not cwd:
            cwd = getattr(term, 'cwd', None)
        return cwd

    def _sidebar_pages(self):
        """(tab title, [pane title, ...]) for every notebook page."""
        pages = []
        for index in range(self.get_n_pages()):
            page = self.get_nth_page(index)
            label = self.get_tab_label(page)
            panes = self._ordered_panes(page)
            pane_titles = []
            for term in panes:
                fallback = ''
                try:
                    fallback = term.get_window_title() or ''
                except Exception:
                    fallback = ''
                pane_titles.append(pane_row_title(self._pane_cwd(term), fallback))
            title = ''
            if hasattr(label, 'get_label'):
                title = label.get_label() or ''
            if not title and pane_titles:
                title = pane_titles[0]
            pages.append((title, pane_titles))
        return pages

    def _queue_sidebar_refresh(self):
        if getattr(self, '_tab_tree', None) is None:
            return False
        if getattr(self, '_sidebar_refresh_queued', False):
            return False
        self._sidebar_refresh_queued = True
        GLib.idle_add(self._refresh_sidebar_tree)
        return False

    def note_pane_focus(self, _widget):
        """The focused pane changed. Move the tree highlight."""
        self._queue_sidebar_refresh()

    def _refresh_sidebar_tree(self):
        """Rebuild the tree when tabs, panes, or focus changed."""
        self._sidebar_refresh_queued = False
        if (getattr(self, '_tab_drag_page', None) is not None or
                getattr(self, '_sidebar_pressed', False)):
            # Rebuilding now would destroy the row under the pointer.
            self._sidebar_refresh_after_drag = True
            return False
        box = getattr(self, '_tab_rows', None)
        if box is None:
            return False
        pages = self._sidebar_pages()
        signature = tuple((title, tuple(panes)) for title, panes in pages)
        target = self._current_sidebar_target()
        collapsed = tuple(sorted(getattr(self, '_sidebar_collapsed', set())))
        locks = tuple(self._page_is_locked(i) for i in range(self.get_n_pages()))
        state = (signature, target, collapsed, locks)
        if state != getattr(self, '_sidebar_sig', None):
            self._fill_sidebar_rows(pages, target)
            self._sidebar_sig = state
        self._hide_native_tab_labels()
        return False

    def _fill_sidebar_rows(self, pages, target):
        box = self._tab_rows
        for child in list(box.get_children()):
            box.remove(child)
        rows = sidebar_tree_rows(pages)
        parents = {row['page'] for row in rows if row['depth'] == 1}
        current_page, current_pane = target
        collapsed = getattr(self, '_sidebar_collapsed', set())
        for row in rows:
            if row['depth'] == 1 and row['page'] in collapsed:
                continue
            box.pack_start(
                self._make_sidebar_row(row, row['page'] in parents,
                                        current_page, current_pane),
                False, False, 0)
        box.show_all()

    def _make_sidebar_row(self, row, has_children, current_page, current_pane):
        """One sidebar row. Children sit in from the tab row."""
        pane = -1 if row['pane'] is None else row['pane']
        page = row['page']
        frame = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        frame.set_hexpand(True)
        frame.get_style_context().add_class('terminator-tab-row')
        if row['depth'] == 1:
            frame.get_style_context().add_class('terminator-tab-child')
            # CSS margin would wipe this. Children sit in under the tab.
            frame.set_margin_start(36)
        if page == current_page and pane == current_pane:
            frame.get_style_context().add_class('current')
        if row['depth'] == 0:
            if has_children:
                open_row = page not in self._sidebar_collapsed
                icon = 'pan-down-symbolic' if open_row else 'pan-end-symbolic'
                disclose = sidebar_icon_button(
                    Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.MENU))
                disclose.connect(
                    'clicked', lambda *_a, page=page:
                    self._toggle_sidebar_page(page))
                self._bind_sidebar_pointer(disclose, page, pane, has_children)
                frame.pack_start(disclose, False, False, 0)
            else:
                gap = Gtk.Box()
                gap.set_size_request(22, -1)
                frame.pack_start(gap, False, False, 0)
        title = Gtk.Label(label=row['title'] or '', xalign=0,
                           halign=Gtk.Align.START)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title.set_hexpand(True)
        main = Gtk.Button()
        main.set_relief(Gtk.ReliefStyle.NONE)
        main.set_focus_on_click(False)
        main.set_can_focus(False)
        main.set_hexpand(True)
        main.get_style_context().add_class('terminator-tab-row-main')
        main.add(title)
        main.connect(
            'clicked', lambda *_a, page=page, pane=pane:
            self._activate_sidebar_row(page, pane))
        self._bind_sidebar_pointer(main, page, pane, has_children)
        frame.pack_start(main, True, True, 0)
        locked = False
        if row['depth'] == 0:
            locked = self._page_is_locked(page)
            if locked:
                frame.get_style_context().add_class('locked')
            # First pack_end sits on the right. Close is packed first,
            # so the lock ends up just to its left.
            if page == current_page:
                close = sidebar_icon_button(sidebar_mark(
                    TAB_CLOSE_ICON, 'terminator-tab-close-mark',
                    'window-close-symbolic'))
                close.set_tooltip_text(_('Close Tab'))
                close.connect(
                    'clicked', lambda *_a, page=page:
                    self._close_sidebar_page(page))
                self._bind_sidebar_pointer(close, page, pane, has_children)
                frame.pack_end(close, False, False, 0)
            lock = sidebar_icon_button(self._lock_mark(locked))
            lock.set_tooltip_text(
                _('Kept for the next launch') if locked else
                _('One-time — forgotten on a normal exit'))
            lock.connect(
                'clicked', lambda *_a, page=page:
                self._toggle_page_lock(page))
            self._bind_sidebar_pointer(lock, page, pane, has_children)
            frame.pack_end(lock, False, False, 0)
        if row['depth'] == 1 and page == current_page and pane == current_pane:
            close = sidebar_icon_button(sidebar_mark(
                TAB_CLOSE_ICON, 'terminator-tab-close-mark',
                'window-close-symbolic'))
            tip = _('_Close Pane').replace('_', '')
            if tip.endswith('(_C)'):
                tip = tip[:-4]
            elif tip.endswith('(C)'):
                tip = tip[:-3]
            close.set_tooltip_text(tip)
            close.connect(
                'clicked', lambda *_a, page=page, pane=pane:
                self._close_sidebar_pane(page, pane))
            self._bind_sidebar_pointer(close, page, pane, has_children)
            frame.pack_end(close, False, False, 0)
            frame._close_btn = close
        frame._sidebar_page = page
        frame._sidebar_depth = row['depth']
        frame._sidebar_pane = None if row['pane'] is None else row['pane']
        page_widget = self.get_nth_page(page)
        terminal = None
        if row['depth'] == 1 and page_widget is not None:
            panes = self._ordered_panes(page_widget)
            if row['pane'] is not None and row['pane'] < len(panes):
                terminal = panes[row['pane']]
        if page_widget is not None:
            self._make_tab_drag_source(main, page_widget, terminal)
        # The pointer is over the row, so the row itself has to accept the drop.
        # The list behind it only sees drops in the gaps.
        self._enable_tab_drop(frame)
        tip = self._sidebar_tip(page, pane)
        if tip:
            main.set_tooltip_text(tip)
        return frame

    def _lock_mark(self, locked):
        """Padlock for a tab root row. Closed when the tab is kept."""
        if locked:
            return sidebar_mark(
                TAB_LOCK_ICON, 'terminator-tab-lock-mark',
                'changes-prevent-symbolic')
        return sidebar_mark(
            TAB_UNLOCK_ICON, 'terminator-tab-lock-mark',
            'changes-allow-symbolic')

    def _page_label(self, page):
        widget = self.get_nth_page(page) if page >= 0 else None
        if widget is None:
            return None
        return self.get_tab_label(widget)

    def _page_is_locked(self, page):
        label = self._page_label(page)
        getter = getattr(label, 'get_locked', None)
        if not callable(getter):
            return False
        try:
            return bool(getter())
        except Exception:
            return False

    def _toggle_page_lock(self, page):
        """Keep this tab across a normal exit, or make it one-time."""
        label = self._page_label(page)
        if label is None or not hasattr(label, 'set_locked'):
            return
        label.set_locked(not label.get_locked())
        self.note_tab_lock()

    def note_tab_lock(self):
        """The lock on a tab changed. Redraw the row and save the session."""
        self._sidebar_sig = None
        self._queue_sidebar_refresh()
        try:
            from .session import try_mark_dirty
            try_mark_dirty('notebook.tab_lock')
        except Exception:
            pass

    def _toggle_sidebar_page(self, page):
        collapsed = self._sidebar_collapsed
        if page in collapsed:
            collapsed.discard(page)
        else:
            collapsed.add(page)
        self._sidebar_sig = None
        self._queue_sidebar_refresh()

    def _sidebar_pane_terminal(self, page, pane):
        panes = self._ordered_panes(self.get_nth_page(page))
        if pane < 0 or pane >= len(panes):
            return None
        return panes[pane]

    def popup_pane_menu(self, event, page, pane):
        """Child-pane menu: move up or down, make it a tab, or close it."""
        term = self._sidebar_pane_terminal(page, pane)
        if term is None:
            return False
        self._activate_sidebar_row(page, pane)
        count = len(self._ordered_panes(self.get_nth_page(page)))
        state = pane_menu_sensitive(pane, count)
        menu = Gtk.Menu()

        def add(text, enabled, callback):
            item = Gtk.MenuItem.new_with_mnemonic(_(text))
            item.set_sensitive(enabled)
            item.connect('activate', lambda *_a: callback())
            menu.append(item)

        add('Move Pane _Up', state['up'],
            lambda: self._move_sidebar_pane(page, pane, 'up'))
        add('Move Pane _Down', state['down'],
            lambda: self._move_sidebar_pane(page, pane, 'down'))
        menu.append(Gtk.SeparatorMenuItem())
        add('Detach as _Tab', state['promote'],
            lambda: self._promote_sidebar_pane(page, pane))
        menu.append(Gtk.SeparatorMenuItem())
        add('_Close Pane', state['close'],
            lambda: self._close_sidebar_pane(page, pane))
        menu.show_all()
        self._pane_menu = menu
        menu.popup_at_pointer(event)
        return True

    def _move_sidebar_pane(self, page, pane, direction):
        """Move a child pane one step up or down inside its tab."""
        term = self._sidebar_pane_terminal(page, pane)
        if term is None:
            return
        count = len(self._ordered_panes(self.get_nth_page(page)))
        if direction == 'up' and pane > 0:
            insert_at = pane - 1
        elif direction == 'down' and pane < count - 1:
            insert_at = pane + 2
        else:
            return
        self._move_terminal_into_page(self, term, page, insert_at)

    def _promote_sidebar_pane(self, page, pane):
        """Make this child pane a tab of its own, just after its old tab."""
        term = self._sidebar_pane_terminal(page, pane)
        if term is None:
            return
        self._promote_terminal(self, term, page + 1)

    def _sidebar_row_widget(self, page, pane):
        """Return the sidebar row widget for (page, pane), or None."""
        box = getattr(self, '_tab_rows', None)
        if box is None:
            return None
        target_pane = None if pane is None or pane < 0 else pane
        for child in box.get_children():
            if getattr(child, '_sidebar_page', None) == page and \
                    getattr(child, '_sidebar_pane', None) == target_pane:
                return child
        return None

    def _close_sidebar_pane(self, page, pane):
        """Close one child pane, asking first when a program is running."""
        term = self._sidebar_pane_terminal(page, pane)
        if term is None:
            return
        row = self._sidebar_row_widget(page, pane)
        anchor = getattr(row, '_close_btn', row)
        from .close_confirm import request_close_terminal
        try:
            request_close_terminal(term, anchor_widget=anchor)
        except TypeError:
            request_close_terminal(term)

    def _close_sidebar_page(self, page):
        label = self.get_tab_label(self.get_nth_page(page))
        if label is not None:
            label.emit('close-clicked', label)

    def _enable_tab_drop(self, widget):
        """Accept a tab dragged from this or another window's list."""
        if widget is None or getattr(widget, '_tab_drop_ready', False):
            return
        widget.drag_dest_set(
            Gtk.DestDefaults.MOTION | Gtk.DestDefaults.HIGHLIGHT |
            Gtk.DestDefaults.DROP,
            _tab_dnd_targets(), Gdk.DragAction.MOVE)
        widget.connect('drag-data-received', self._on_tab_drop)
        widget._tab_drop_ready = True

    def _make_tab_drag_source(self, frame, page_widget, terminal=None):
        """A tab or a child pane can be dragged to reorder or change level."""
        frame.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK, _tab_dnd_targets(),
            Gdk.DragAction.MOVE)
        frame.connect('drag-begin', self._on_tab_drag_begin, page_widget)
        frame.connect('drag-data-get', self._on_tab_drag_data_get,
                      page_widget, terminal)
        frame.connect('drag-end', self._on_tab_drag_end)
        frame.connect('drag-data-delete', self._on_tab_drag_delete)

    def _on_tab_drag_begin(self, _widget, _context, page):
        self._tab_drag_page = page

    def _on_tab_drag_data_get(self, _widget, _context, selection, _info,
                              _time, page, terminal):
        token = '%s:%s:%s' % (id(self), id(page), id(terminal))
        _TAB_DRAG_PAYLOADS[token] = (self, page, terminal)
        selection.set(selection.get_target(), 8, token.encode('ascii'))

    def _on_tab_drag_delete(self, _widget, _context):
        """The page was reparented in the drop handler. Nothing to delete."""
        return True

    def _on_tab_drag_end(self, _widget, _context):
        self._tab_drag_page = None
        stale = [key for key, value in _TAB_DRAG_PAYLOADS.items()
                 if value[0] is self]
        for key in stale:
            _TAB_DRAG_PAYLOADS.pop(key, None)
        self._sidebar_pressed = False
        self._flush_sidebar_after_pointer()

    def _on_tab_drop(self, widget, context, x, y, selection, _info, time):
        raw = selection.get_data()
        token = raw.decode('ascii', 'replace') if raw else ''
        payload = _TAB_DRAG_PAYLOADS.pop(token, None)
        if not payload:
            Gtk.drag_finish(context, False, False, time)
            return
        source, page, terminal = payload
        action = self._tree_drop_action(widget, x, y)
        ok = False
        try:
            ok = self._take_dropped_node(source, page, terminal, action)
        except Exception as ex:
            import traceback
            err('tab drop failed: %s\n%s' % (ex, traceback.format_exc()))
        Gtk.drag_finish(context, bool(ok), False, time)

    def _tab_drop_index(self, dest, y):
        """Insertion index under the pointer, from the tab rows' spans."""
        tree = getattr(self, '_tab_rows', None)
        if tree is None:
            return self.get_n_pages()
        translated = None
        try:
            translated = dest.translate_coordinates(tree, 0, int(y))
        except Exception:
            translated = None
        pointer = y if not translated else translated[1]
        spans = []
        current = None
        for child in tree.get_children():
            alloc = child.get_allocation()
            depth = getattr(child, '_sidebar_depth', 0)
            if depth == 0:
                if current is not None:
                    spans.append(tuple(current))
                current = [alloc.y, alloc.y + alloc.height]
            elif current is not None:
                current[1] = alloc.y + alloc.height
        if current is not None:
            spans.append(tuple(current))
        return tab_drop_index(spans, pointer)

    def _tree_drop_action(self, dest, x, y):
        """Tab insert, nest into a tab, or pane insert under the pointer."""
        tree = getattr(self, '_tab_rows', None)
        if tree is None:
            return ('tab', self.get_n_pages())
        translated = None
        try:
            translated = dest.translate_coordinates(tree, int(x), int(y))
        except Exception:
            translated = None
        pointer_x = x if not translated else translated[0]
        pointer_y = y if not translated else translated[1]
        rows = []
        for child in tree.get_children():
            alloc = child.get_allocation()
            rows.append({
                'depth': getattr(child, '_sidebar_depth', 0),
                'page': getattr(child, '_sidebar_page', 0),
                'pane': getattr(child, '_sidebar_pane', None),
                'top': alloc.y,
                'bottom': alloc.y + alloc.height,
            })
        return tree_drop_target(rows, pointer_x, pointer_y)

    def _take_dropped_node(self, source, page, terminal, action):
        """Reorder a tab or pane, or move it up or down a level."""
        if source is None or page is None or not action:
            return False
        if source is not self:
            try:
                allowed = bool(source.config['detachable_tabs'])
            except Exception:
                allowed = True
            if not allowed:
                return False
        kind = action[0]
        if terminal is None:
            if kind == 'tab':
                return self._take_dropped_tab(source, page, action[1])
            pane_at = None if kind == 'into' or len(action) < 3 else action[2]
            return self._demote_page_into(source, page, action[1], pane_at)
        if kind == 'tab':
            return self._promote_terminal(source, terminal, action[1])
        if kind == 'into':
            return self._move_terminal_into_page(source, terminal, action[1], None)
        return self._move_terminal_into_page(
            source, terminal, action[1], action[2])

    def _leave_zoom_for(self, *notebooks):
        from .zoomguard import leave_zoom
        for notebook in notebooks:
            win = getattr(notebook, 'window', None)
            if win is not None and getattr(win, 'is_zoomed', lambda: False)():
                leave_zoom(win, reason='tab-drop', quiet=False)

    def _lift_terminal(self, term):
        """Take a pane out of its split without closing it."""
        parent = term.get_parent() if term is not None else None
        if parent is None or not hasattr(parent, 'children'):
            return term
        self._sync_paned_slots(parent)
        if term not in parent.children:
            return term
        # The Python wrapper keeps the widget alive across the unparent.
        parent.remove(term)
        if len(parent.children) == 1:
            self._collapse_single_child_paned(parent)
        return term

    def _collapse_single_child_paned(self, paned):
        """Replace a split that has one child left with that child."""
        self._sync_paned_slots(paned)
        if len(getattr(paned, 'children', [])) != 1:
            return
        child = paned.children[0]
        parent = logical_parent(paned)
        if parent is None:
            return
        maker = Factory()
        paned.remove(child)
        if maker.isinstance(parent, 'Notebook'):
            page_num = parent.page_num(paned)
            label = parent.get_tab_label(paned)
            lat = None
            if hasattr(parent, 'last_active_term'):
                lat = parent.last_active_term.pop(paned, None)
            lmt = None
            if hasattr(parent, 'last_maximised_term') and parent.last_maximised_term is not None:
                lmt = parent.last_maximised_term.pop(paned, None)
            parent.detach_tab(paned)
            if page_num < 0:
                page_num = parent.get_n_pages()
            parent.insert_page(child, label, page_num)
            parent.set_tab_detachable(
                child, parent.config['detachable_tabs'])
            parent.set_tab_reorderable(child, True)
            parent._pack_tab(child)
            if maker.isinstance(child, 'Terminal'):
                parent.last_active_term[child] = getattr(child, 'uuid', None)
            elif lat is not None:
                parent.last_active_term[child] = lat
            if lmt is not None and hasattr(parent, 'last_maximised_term') and parent.last_maximised_term is not None:
                if not maker.isinstance(child, 'Terminal'):
                    parent.last_maximised_term[child] = lmt
            if maker.isinstance(child, 'Terminal'):
                parent._bind_notebook_terminal(child)
            child.show_all()
            parent._hide_native_tab_labels()
        elif hasattr(parent, 'swap_child'):
            parent.swap_child(paned, child)
            self._sync_paned_slots(parent)
        try:
            paned.cnxids.remove_all()
        except Exception:
            pass

    def _is_vertical(self, widget):
        get_orientation = getattr(widget, 'get_orientation', None)
        if not callable(get_orientation):
            return False
        try:
            return get_orientation() == Gtk.Orientation.VERTICAL
        except Exception:
            return False

    def _sync_paned_slots(self, paned):
        """Make a paned's child list follow the visible slots."""
        if paned is None or not hasattr(paned, 'get_child1'):
            return
        if not hasattr(paned, 'children'):
            return
        paned.children[:] = [child for child in (paned.get_child1(),
                                                 paned.get_child2())
                             if child is not None]

    def _ensure_parented(self, widget):
        """A move that fails must not leave a terminal with no parent."""
        if widget is None:
            return
        try:
            parent = widget.get_parent()
        except Exception:
            return
        if parent is None:
            self.newtab(widget=widget)

    def _promote_terminal(self, source, term, index):
        """Make a child pane its own tab."""
        if term is None:
            return False
        self._leave_zoom_for(source, self)
        page = source.find_tab_root(term) if hasattr(source, 'find_tab_root') else None
        panes = source._ordered_panes(page) if page is not None else []
        if len(panes) < 2:
            if page is not None:
                return self._take_dropped_tab(source, page, index)
            return False
        try:
            self._lift_terminal(term)
            if term.get_parent() is not None:
                return False
            if index < 0:
                index = 0
            if index > self.get_n_pages():
                index = self.get_n_pages()
            self.newtab(widget=term, metadata={'tabnum': index})
        except Exception:
            self._ensure_parented(term)
            raise
        self._sidebar_sig = None
        if source is not self:
            source._sidebar_sig = None
            source._queue_sidebar_refresh()
            GLib.idle_add(self._release_source_after_drop, source)
        self._queue_sidebar_refresh()
        return True

    def _move_terminal_into_page(self, source, term, page_index, pane_index):
        """Move a pane into ``page_index``, at ``pane_index`` or at the end."""
        if term is None:
            return False
        self._leave_zoom_for(source, self)
        if page_index < 0 or page_index >= self.get_n_pages():
            return False
        target = self.get_nth_page(page_index)
        if target is None:
            return False
        panes = list(self._ordered_panes(target))
        same_page = term in panes
        vertical = self._is_vertical(term.get_parent()) if same_page else False
        if same_page:
            src = panes.index(term)
            insert_at = len(panes) if pane_index is None else pane_index
            dest = reorder_to_index(src, insert_at, len(panes))
            if dest is None:
                return True
            pane_index = dest
        try:
            self._lift_terminal(term)
            if term.get_parent() is not None:
                return False
            target = self.get_nth_page(page_index)
            if target is None:
                self._ensure_parented(term)
                return False
            self._insert_widget_beside(target, term, pane_index, vertical)
        except Exception:
            self._ensure_parented(term)
            raise
        self._sidebar_sig = None
        self._queue_sidebar_refresh()
        if source is not self:
            source._sidebar_sig = None
            source._queue_sidebar_refresh()
            GLib.idle_add(self._release_source_after_drop, source)
        try:
            from .session import try_mark_dirty
            try_mark_dirty('notebook.move_pane')
        except Exception:
            pass
        return True

    def _insert_widget_beside(self, page_widget, widget, pane_index,
                              vertical=False):
        """Split ``page_widget`` so ``widget`` sits at ``pane_index``."""
        panes = [item for item in self._ordered_panes(page_widget)
                 if item is not widget]
        if not panes:
            anchor = page_widget
            before = False
        elif pane_index is None or pane_index >= len(panes):
            anchor = panes[-1]
            before = False
        elif pane_index <= 0:
            anchor = panes[0]
            before = True
        else:
            anchor = panes[pane_index]
            before = True
        if anchor is widget:
            return
        self._split_beside(anchor, widget, before, vertical)

    def _split_beside(self, anchor, sibling, before, vertical=False):
        """Put ``sibling`` on one side of ``anchor``, keeping a stack's axis."""
        parent = anchor.get_parent() if anchor is not None else None
        if parent is not None and hasattr(parent, 'get_orientation'):
            vertical = self._is_vertical(parent)
        widgetfirst = not before
        maker = Factory()
        if parent is self or maker.isinstance(parent, 'Notebook'):
            self.split_axis(anchor, vertical=vertical, sibling=sibling,
                            widgetfirst=widgetfirst)
            return
        if parent is not None and hasattr(parent, 'split_axis'):
            parent.split_axis(anchor, vertical=vertical, sibling=sibling,
                              widgetfirst=widgetfirst)
            self._sync_paned_slots(parent)
            for child in (parent.get_child1(), parent.get_child2()):
                if child is not None and child is not anchor:
                    self._sync_paned_slots(child)
            return
        self.split_axis(anchor, vertical=vertical, sibling=sibling,
                        widgetfirst=widgetfirst)

    def _demote_page_into(self, source, page, page_index, pane_index=None):
        """Make a whole tab a split inside another tab."""
        if source.page_num(page) < 0:
            return False
        if page_index < 0 or page_index >= self.get_n_pages():
            return False
        target = self.get_nth_page(page_index)
        if target is None or target is page:
            return False
        self._leave_zoom_for(source, self)
        src_index = source.page_num(page)
        if source is self and src_index < page_index:
            page_index -= 1
        maker = Factory()
        terminal_page = maker.isinstance(page, 'Terminal')
        if terminal_page:
            source.disconnect_child(page)
        try:
            source.detach_tab(page)
            target = self.get_nth_page(page_index)
            if target is None:
                self.newtab(widget=page)
            else:
                self._insert_widget_beside(target, page, pane_index, False)
            if not terminal_page:
                self._rewire_moved_terminals(page)
        except Exception:
            self._ensure_parented(page)
            raise
        self._sidebar_sig = None
        self._hide_native_tab_labels()
        self._queue_sidebar_refresh()
        if source is not self:
            source._sidebar_sig = None
            GLib.idle_add(self._release_source_after_drop, source)
        try:
            from .session import try_mark_dirty
            try_mark_dirty('notebook.nest_tab')
        except Exception:
            pass
        return True

    def _take_dropped_tab(self, source, page, index):
        """Move ``page`` into this notebook at ``index``. Same list reorders."""
        if source is None or page is None:
            return False
        if source.page_num(page) < 0:
            return False
        from .zoomguard import leave_zoom
        for notebook in (source, self):
            win = getattr(notebook, 'window', None)
            if win is not None and getattr(win, 'is_zoomed', lambda: False)():
                leave_zoom(win, reason='tab-drop', quiet=False)
        if source is self:
            current = self.page_num(page)
            dest = reorder_to_index(current, index, self.get_n_pages())
            if dest is not None:
                self.reorder_child(page, dest)
            self._queue_sidebar_refresh()
            return True

        label = source.get_tab_label(page)
        lat = None
        if hasattr(source, 'last_active_term'):
            lat = source.last_active_term.pop(page, None)
        lmt = None
        if hasattr(source, 'last_maximised_term') and source.last_maximised_term is not None:
            lmt = source.last_maximised_term.pop(page, None)
        maker = Factory()
        if maker.isinstance(page, 'Terminal'):
            source.disconnect_child(page)
        try:
            source.detach_tab(page)
            if index < 0 or index > self.get_n_pages():
                index = self.get_n_pages()
            self.insert_page(page, label, index)
            if label is not None:
                try:
                    label.disconnect_by_func(source.closetab)
                except Exception:
                    pass
                label.notebook = self
                label.connect('close-clicked', self.closetab)
            self.set_tab_detachable(page, self.config['detachable_tabs'])
            self.set_tab_reorderable(page, True)
            self._pack_tab(page)
            if lat is not None:
                self.last_active_term[page] = lat
            if lmt is not None and hasattr(self, 'last_maximised_term') and self.last_maximised_term is not None:
                self.last_maximised_term[page] = lmt
            self._rewire_moved_terminals(page)
            self.set_current_page(index)
            page.show_all()
        except Exception:
            self._ensure_parented(page)
            raise
        self._hide_native_tab_labels()
        self._queue_sidebar_refresh()
        # Destroying the source window inside the drop handler aborts the drag.
        GLib.idle_add(self._release_source_after_drop, source)
        try:
            from .session import try_mark_dirty
            try_mark_dirty('notebook.drop_tab')
        except Exception:
            pass
        return True

    def _bind_notebook_terminal(self, widget):
        """Window and notebook handlers for a terminal that is the whole tab."""
        from .container import window_terminal_signals
        signals = window_terminal_signals(
            self.get_toplevel(), widget, rotate=False)
        signals.update({'close-term': self.wrapcloseterm,
                        'split-auto': self.split_auto,
                        'split-horiz': self.split_horiz,
                        'split-vert': self.split_vert,
                        'title-change': self.propagate_title_change})
        self.connect_terminal_signals(widget, signals)

    def _rewire_moved_terminals(self, page):
        """Point split panes at this window. A lone terminal binds here."""
        maker = Factory()
        if maker.isinstance(page, 'Terminal'):
            self._bind_notebook_terminal(page)
            return
        window = self.get_toplevel()
        _containers, terminals = enumerate_descendants(page)
        for term in terminals:
            parent = term.get_parent()
            while parent is not None and parent is not self:
                if (hasattr(parent, 'terminal_signals') and
                        hasattr(parent, 'disconnect_child')):
                    parent.disconnect_child(term)
                    parent.connect_terminal_signals(
                        term, parent.terminal_signals(window, term))
                    break
                parent = parent.get_parent()

    def _release_source_after_drop(self, source):
        """Close a window whose last tab was dragged away."""
        try:
            remaining = source.get_n_pages()
        except Exception:
            return False
        if remaining > 0:
            source._queue_sidebar_refresh()
            return False
        win = source.get_toplevel()
        source._unparent_from_window()
        if win is not None and hasattr(win, 'hoover'):
            win.hoover()
        return False

    def _bind_sidebar_pointer(self, widget, page, pane, has_children):
        """Right-click opens the menu. Release may rebuild the list."""
        widget.connect('button-press-event', self._on_sidebar_row_press,
                       page, pane, has_children)
        widget.connect_after('button-release-event',
                             self._on_sidebar_row_release)

    def _on_sidebar_row_release(self, _widget, _event):
        """The pointer is up. The list may rebuild again."""
        self._sidebar_pressed = False
        self._flush_sidebar_after_pointer()
        return False

    def _flush_sidebar_after_pointer(self):
        if (getattr(self, '_tab_drag_page', None) is not None or
                getattr(self, '_sidebar_pressed', False)):
            return
        if getattr(self, '_sidebar_refresh_after_drag', False):
            self._sidebar_refresh_after_drag = False
            self._queue_sidebar_refresh()

    def _on_sidebar_row_press(self, _widget, event, page, pane, _has_children):
        if event.button == 3 and pane < 0:
            label = self.get_tab_label(self.get_nth_page(page))
            if hasattr(label, 'popup_tab_menu'):
                self.set_current_page(page)
                label.popup_tab_menu(event)
            return True
        if event.button == 3 and pane >= 0:
            self.popup_pane_menu(event, page, pane)
            return True
        if event.button != 1:
            return False
        # Hold the row still until release. A refresh on press deletes the
        # widget before the drag can start. Lock and close are their own
        # buttons: they highlight while held and act on release.
        self._sidebar_pressed = True
        return False

    def _sidebar_tip(self, page, pane):
        page_widget = self.get_nth_page(page)
        panes = self._ordered_panes(page_widget)
        if pane >= 0 and pane < len(panes):
            term = panes[pane]
        else:
            term = choose_naming_terminal(panes, self._focused_terminal(panes))
        return folder_subtitle(self._pane_cwd(term)) if term is not None else ''

    def _hide_native_tab_labels(self):
        """The tree is the sidebar. The notebook's own rows stay out of it."""
        if getattr(self, '_tab_tree', None) is None:
            return
        for index in range(self.get_n_pages()):
            label = self.get_tab_label(self.get_nth_page(index))
            if label is None:
                continue
            label.set_no_show_all(True)
            label.set_size_request(0, 0)
            label.hide()

    def _activate_sidebar_row(self, page, pane):
        if page < 0 or page >= self.get_n_pages():
            return
        if self.get_current_page() != page:
            self.set_current_page(page)
        GLib.idle_add(self._focus_sidebar_pane, page, pane)

    def _focus_sidebar_pane(self, page, pane):
        page_widget = self.get_nth_page(page)
        panes = self._ordered_panes(page_widget)
        if pane >= 0 and pane < len(panes):
            term = panes[pane]
        else:
            term = choose_naming_terminal(
                panes, self._focused_terminal(panes))
        if term is not None and hasattr(term, 'grab_focus'):
            term.grab_focus()
        return False

    def _place_tab_add_beside_tabs(self, *_args):
        """Keep the plus next to the last tab, not at the far edge.

        Gtk packs the action widget at the end of the header. A right margin
        pulls it back until it sits just after the last label. The rest of
        the header stays the same dark colour.
        """
        btn = getattr(self, '_new_tab_btn', None)
        if btn is None or not btn.get_mapped():
            return False
        right = 0
        for i in range(self.get_n_pages()):
            label = self.get_tab_label(self.get_nth_page(i))
            if label is None:
                continue
            alloc = label.get_allocation()
            right = max(right, alloc.x + alloc.width)
        btn_alloc = btn.get_allocation()
        if right <= 0 or btn_alloc.width <= 1 or btn_alloc.x < 0:
            return False
        old = btn.get_margin_end()
        new = max(0, old + btn_alloc.x - (right + 8))
        if new != old:
            btn.set_margin_end(new)
        return False

    def get_children(self):
        """Return an ordered list of our children"""
        children = []
        for page in range(0,self.get_n_pages()):
            children.append(self.get_nth_page(page))
        return(children)

    def newtab(self, debugtab=False, widget=None, cwd=None, metadata=None,
               profile=None, init_command=None):
        """Add a new tab, optionally supplying a child widget"""
        dbg('making a new tab')
        maker = Factory()
        top_window = self.get_toplevel()

        if not widget:
            widget = maker.make('Terminal')
            if cwd:
                widget.set_cwd(cwd)
            if profile and self.config['always_split_with_profile']:
                widget.force_set_profile(None, profile)
            widget.spawn_child(debugserver=debugtab, init_command=init_command)
        elif profile and self.config['always_split_with_profile']:
            widget.force_set_profile(None, profile)

        # Shared table (UI review P2-3); a tab has no rotate/resize/unzoom
        from .container import window_terminal_signals
        signals = window_terminal_signals(top_window, widget, rotate=False)
        signals.update({'close-term': self.wrapcloseterm,
                        'split-auto': self.split_auto,
                        'split-horiz': self.split_horiz,
                        'split-vert': self.split_vert,
                        'title-change': self.propagate_title_change})

        if maker.isinstance(widget, 'Terminal'):
            self.connect_terminal_signals(widget, signals)

        if metadata and 'tabnum' in metadata:
            tabpos = metadata['tabnum']
        elif self.config['new_tab_after_current_tab'] == True:
            tabpos = self.get_current_page() + 1
        else:
            tabpos = -1

        label = TabLabel('', self)
        try:
            initial_cwd = widget.get_cwd() if hasattr(widget, 'get_cwd') else None
        except Exception:
            initial_cwd = None
        if not initial_cwd:
            initial_cwd = getattr(widget, 'cwd', None)
        label.set_folder_name(initial_cwd)
        if metadata and 'label' in metadata:
            dbg('creating TabLabel with text: %s' % metadata['label'])
            label.set_custom_label(metadata['label'])
        label.connect('close-clicked', self.closetab)

        label.show_all()
        widget.show_all()

        dbg('inserting page at position: %s' % tabpos)
        self.insert_page(widget, None, tabpos)
        self.set_tab_detachable(widget, self.config['detachable_tabs'])

        if maker.isinstance(widget, 'Terminal'):
            containers, objects = ([], [widget])
        else:
            containers, objects = enumerate_descendants(widget)

        term_widget = None
        for term_widget in objects:
            if maker.isinstance(term_widget, 'Terminal'):
                self.set_last_active_term(term_widget.uuid)
                break

        self.set_tab_label(widget, label)
        self._pack_tab(widget)

        self.set_tab_reorderable(widget, True)
        self.set_current_page(tabpos)
        self.show_all()
        self._hide_native_tab_labels()
        self._queue_sidebar_refresh()
        if maker.isinstance(term_widget, 'Terminal'):
            widget.grab_focus()
        try:
            from .session import try_mark_dirty
            try_mark_dirty('notebook.newtab')
        except Exception:
            pass

    def wrapcloseterm(self, widget):
        """A child terminal has closed"""
        dbg('called on %s' % widget)
        if self.closeterm(widget):
            dbg('closeterm succeeded')
            self.hoover()
        else:
            dbg('closeterm failed')

    def closetab(self, widget, label):
        """Close a tab"""
        tabnum = None
        try:
            nb = widget.notebook
        except AttributeError:
            err('TabLabel::closetab: called on non-Notebook: %s' % widget)
            return

        for i in range(0, nb.get_n_pages() + 1):
            if label == nb.get_tab_label(nb.get_nth_page(i)):
                tabnum = i
                break

        if tabnum is None:
            err('TabLabel::closetab: %s not in %s. Bailing.' % (label, nb))
            return

        maker = Factory()
        child = nb.get_nth_page(tabnum)
        if getattr(child, 'is_pane_placeholder', False):
            # UI review P2-12: a single-terminal tab whose terminal floats in
            # the overlay frame; put it back so the Terminal branch applies.
            from .zoomguard import leave_zoom
            leave_zoom(self.window, legacy=False, overlay=True,
                       reason='closetab')
            child = nb.get_nth_page(tabnum)

        confirm_close = self.construct_confirm_close(self.window, child)
        if confirm_close != Gtk.ResponseType.ACCEPT:
            dbg('user cancelled request')
            return

        if maker.isinstance(child, 'Terminal'):
            dbg('child is a single Terminal')

            nb.last_active_term.pop(child, None)
            if hasattr(nb, 'last_maximised_term') and nb.last_maximised_term is not None:
                nb.last_maximised_term.pop(child, None)
            child.close()
            # FIXME: We only do this del and return here to avoid removing the
            # page below, which child.close() implicitly does
            del(label)
        elif maker.isinstance(child, 'Container'):
            dbg('child is a Container')

            containers = None
            objects = None
            containers, objects = enumerate_descendants(child)

            while len(objects) > 0:
                descendant = objects.pop()
                descendant.close()
                while Gtk.events_pending():
                    Gtk.main_iteration()
        else:
            err('Notebook::closetab: child is unknown type %s' % child)
        try:
            from .session import try_mark_dirty
            try_mark_dirty('notebook.closetab')
        except Exception:
            pass


    def resizeterm(self, widget, keyname):
        """Handle a keyboard event requesting a terminal resize"""
        raise NotImplementedError('resizeterm')

    def zoom(self, widget, fontscale = False):
        """Zoom a terminal"""
        raise NotImplementedError('zoom')

    def unzoom(self, widget):
        """Unzoom a terminal"""
        raise NotImplementedError('unzoom')

    def find_tab_root(self, widget):
        """Look for the tab child which is or ultimately contains the supplied
        widget"""
        parent = widget.get_parent()
        previous = parent

        while parent is not None and parent is not self:
            previous = parent
            parent = parent.get_parent()

        if previous == self:
            return(widget)
        else:
            return(previous)

    def _terminals_in_page(self, page):
        """Terminals shown in this tab."""
        if page is None:
            return []
        if hasattr(page, 'get_visible_terminals'):
            try:
                found = list(page.get_visible_terminals().keys())
            except Exception:
                found = []
            if found:
                return found
        if hasattr(page, 'get_cwd') and hasattr(page, 'vte'):
            return [page]
        return []

    def _focused_terminal(self, terminals):
        for term in terminals:
            vte = getattr(term, 'vte', None)
            try:
                if vte is not None and vte.is_focus():
                    return term
            except Exception:
                pass
        last = getattr(self.terminator, 'last_focused_term', None)
        if last in terminals:
            return last
        return None

    def update_tab_label_text(self, widget, text):
        """Name the tab from the focused pane's folder.

        A user-edited title stays on the first line. The shell's window
        title is not the tab name. A pane that does not have the focus
        does not rename the tab.
        """
        page = self.find_tab_root(widget)
        label = self.get_tab_label(page)
        if not label:
            err('Notebook::update_tab_label_text: %s not found' % widget)
            return
        terminals = self._terminals_in_page(page)
        focused = self._focused_terminal(terminals)
        if focused is not None and widget is not focused:
            self._queue_sidebar_refresh()
            return
        source = choose_naming_terminal(terminals, focused)
        if source is None:
            source = widget if hasattr(widget, 'get_cwd') else None
        cwd = None
        if source is not None:
            try:
                cwd = source.get_cwd()
            except Exception:
                cwd = None
            if not cwd:
                cwd = getattr(source, 'cwd', None)
        if hasattr(label, 'set_folder_name'):
            label.set_folder_name(cwd)
        else:
            label.set_label(text)
        self._queue_sidebar_refresh()

    def _drop_empty_pages(self):
        """Remove notebook pages that no longer have a child."""
        numpages = self.get_n_pages()
        while numpages > 0:
            numpages = numpages - 1
            page = self.get_nth_page(numpages)
            if not page:
                dbg('Removing empty page: %d' % numpages)
                self.remove_page(numpages)

    def hoover(self):
        """Clean up any empty tabs and if we only have one tab left, die"""
        self._drop_empty_pages()

        if self.get_n_pages() == 1:
            dbg('Last page, removing self')
            child = self.get_nth_page(0)
            self.remove_page(0)
            parent = logical_parent(self)
            self._unparent_from_window()
            self.cnxids.remove_all()
            parent.add(child)
            del(self)
            # Find the last terminal in the new parent and give it focus
            terms = parent.get_visible_terminals()
            list(terms.keys())[-1].grab_focus()

    def page_num_descendant(self, widget):
        """Find the tabnum of the tab containing a widget at any level"""
        if widget is None:
            return -1
        placeholder = getattr(widget, '_overlay_placeholder', None)
        if placeholder is not None and placeholder.get_parent() is not None:
            widget = placeholder
        tabnum = self.page_num(widget)
        dbg("widget is direct child if not equal -1 - tabnum: %d" % tabnum)
        while tabnum == -1 and widget.get_parent():
            widget = widget.get_parent()
            tabnum = self.page_num(widget)
        dbg("found tabnum containing widget: %d" % tabnum)
        return tabnum

    def set_last_active_term(self, uuid):
        """Set the last active term for uuid"""
        widget = self.terminator.find_terminal_by_uuid(uuid.urn)
        if not widget:
            err("Cannot find terminal with uuid: %s, so cannot make it active" % (uuid.urn))
            return
        tabnum = self.page_num_descendant(widget)
        if tabnum == -1:
            err("No tabnum found for terminal with uuid: %s" % (uuid.urn))
            return
        nth_page = self.get_nth_page(tabnum)
        self.last_active_term[nth_page] = uuid

    def clean_last_active_term(self):
        """Clean up old entries in last_active_term"""
        if self.terminator.doing_layout == True:
            return
        last_active_term = {}
        for tabnum in range(0, self.get_n_pages()):
            nth_page = self.get_nth_page(tabnum)
            if nth_page in self.last_active_term:
                last_active_term[nth_page] = self.last_active_term[nth_page]
        self.last_active_term = last_active_term

    def clean_last_maximised_term(self):
        """Clean up old entries in last_maximised_term"""
        if self.terminator.doing_layout == True:
            return
        if not hasattr(self, 'last_maximised_term') or self.last_maximised_term is None:
            self.last_maximised_term = {}
            return
        last_maximised_term = {}
        for tabnum in range(0, self.get_n_pages()):
            nth_page = self.get_nth_page(tabnum)
            if nth_page in self.last_maximised_term:
                last_maximised_term[nth_page] = self.last_maximised_term[nth_page]
        self.last_maximised_term = last_maximised_term

    def _on_page_removed(self, notebook, child, page_num):
        if hasattr(self, 'last_active_term') and self.last_active_term is not None:
            self.last_active_term.pop(child, None)
        if hasattr(self, 'last_maximised_term') and self.last_maximised_term is not None:
            self.last_maximised_term.pop(child, None)
        self.clean_last_active_term()
        self.clean_last_maximised_term()

    def _wire_window_maximise_signals(self):
        win = getattr(self, 'window', None)
        if win is not None and getattr(self, '_maximise_changed_handler', None) is None:
            try:
                self._maximise_changed_handler = win.connect(
                    'pane-maximise-changed', self._on_pane_maximise_changed)
            except Exception as ex:
                dbg('notebook connect pane-maximise-changed: %s' % ex)

    def _on_pane_maximise_changed(self, window, terminal, active):
        if not hasattr(self, 'last_maximised_term') or self.last_maximised_term is None:
            self.last_maximised_term = {}
        if active:
            if terminal is not None:
                tabnum = self.page_num_descendant(terminal)
                if tabnum != -1:
                    page = self.get_nth_page(tabnum)
                    self.last_maximised_term[page] = getattr(terminal, 'uuid', None)
        else:
            if not getattr(self, '_tab_switching', False):
                if terminal is not None:
                    tabnum = self.page_num_descendant(terminal)
                    if tabnum != -1:
                        page = self.get_nth_page(tabnum)
                        self.last_maximised_term.pop(page, None)
                        return
                    term_uuid = getattr(terminal, 'uuid', None)
                    if term_uuid is not None:
                        to_del = [p for p, u in self.last_maximised_term.items() if u == term_uuid]
                        for p in to_del:
                            self.last_maximised_term.pop(p, None)
                cur_page_num = self.get_current_page()
                if 0 <= cur_page_num < self.get_n_pages():
                    self.last_maximised_term.pop(self.get_nth_page(cur_page_num), None)

    def on_page_reordered_dirty(self, *args):
        try:
            from .session import try_mark_dirty
            try_mark_dirty('page-reordered')
        except Exception:
            pass

    def deferred_on_tab_switch(self, notebook, page,  page_num,  data=None):
        """Prime a single idle tab switch signal, using the most recent set of params"""
        self._tab_switching = True
        win = self.get_toplevel()
        old_page_num = self.get_current_page()
        if 0 <= old_page_num < self.get_n_pages():
            old_page = self.get_nth_page(old_page_num)
            is_ov = getattr(win, 'is_overlay_maximised', None)
            if callable(is_ov) and is_ov():
                overlay_data = getattr(getattr(win, '_overlay', None), 'data', None)
                if overlay_data and overlay_data.get('terminal'):
                    if not hasattr(self, 'last_maximised_term') or self.last_maximised_term is None:
                        self.last_maximised_term = {}
                    self.last_maximised_term[old_page] = overlay_data['terminal'].uuid
        # Module D: leaving a tab while overlay-maximised must snap-restore
        from .zoomguard import leave_zoom
        leave_zoom(self.get_toplevel(), legacy=False, overlay=True,
                   reason='tab-switch')
        tabs_last_active_term = self.last_active_term.get(self.get_nth_page(page_num),  None)
        data = {'tabs_last_active_term':tabs_last_active_term}

        self.pending_on_tab_switch_args = (notebook, page,  page_num,  data)
        if self.pending_on_tab_switch == True:
            return
        GLib.idle_add(self.do_deferred_on_tab_switch)
        self.pending_on_tab_switch = True

    def do_deferred_on_tab_switch(self):
        """Perform the latest tab switch signal, and resetting the pending flag"""
        # try/finally: an exception in on_tab_switch must not leave the
        # pending flag stuck at True, which would swallow every later switch.
        try:
            args = self.pending_on_tab_switch_args
            if args is not None:
                self.on_tab_switch(*args)
        finally:
            self.pending_on_tab_switch = False
            self.pending_on_tab_switch_args = None
            self._tab_switching = False
        return False

    def on_tab_switch(self, notebook, page,  page_num,  data=None):
        """Do the real work for a tab switch"""
        try:
            from .session import try_mark_dirty
            try_mark_dirty('switch-page')
        except Exception:
            pass
        target_page = self.get_nth_page(page_num) if hasattr(self, 'get_nth_page') else None
        lmt = getattr(self, 'last_maximised_term', None) or {}
        max_uuid = lmt.get(target_page, None) if target_page is not None else None
        max_term = None
        if max_uuid and hasattr(self, 'terminator'):
            max_term = self.terminator.find_terminal_by_uuid(
                max_uuid.urn if hasattr(max_uuid, 'urn') else str(max_uuid))
            if max_term is not None and hasattr(self, 'page_num_descendant') and self.page_num_descendant(max_term) == page_num:
                win = self.get_toplevel() if hasattr(self, 'get_toplevel') else None
                if win is not None and hasattr(win, 'overlay_maximise'):
                    term_count = 0
                    for t in getattr(self.terminator, 'terminals', []):
                        if hasattr(self, 'page_num_descendant') and self.page_num_descendant(t) == page_num:
                            term_count += 1
                            if term_count > 1:
                                break
                    if term_count > 1:
                        if not win.overlay_maximise(max_term, animate=False):
                            if hasattr(self, 'last_maximised_term') and self.last_maximised_term:
                                self.last_maximised_term.pop(target_page, None)
                            max_term = None
                    else:
                        if hasattr(self, 'last_maximised_term') and self.last_maximised_term:
                            self.last_maximised_term.pop(target_page, None)
                        max_term = None
            else:
                if hasattr(self, 'last_maximised_term') and self.last_maximised_term:
                    self.last_maximised_term.pop(target_page, None)
                max_term = None
        if max_term is not None:
            GLib.idle_add(max_term.ensure_visible_and_focussed)
        else:
            tabs_last_active_term = data.get('tabs_last_active_term') if isinstance(data, dict) else None
            if tabs_last_active_term:
                term = self.terminator.find_terminal_by_uuid(tabs_last_active_term.urn)
                # if we can't find a last active term we must be starting up
                if term is not None:
                    GLib.idle_add(term.ensure_visible_and_focussed)
        # Return False (GLib.SOURCE_REMOVE) so that, should this ever be
        # scheduled directly via GLib.idle_add/timeout_add, it runs once
        # instead of repeating forever.  As a switch-page handler (or via
        # do_deferred_on_tab_switch) the return value is ignored.
        return False

    def _select_tab_scroll(self):
        """Let tab-strip wheel events reach this window.

        Notebook.get_has_window() is false, so the strip is drawn on the
        toplevel GdkWindow. add_events only updates the widget mask.
        OR the bits on; replacing the mask would drop the window's other
        events. VTE and the sidebar have their own child windows.
        """
        win = self.get_window()
        if win is None:
            return
        win.set_events(win.get_events()
                       | Gdk.EventMask.SCROLL_MASK
                       | Gdk.EventMask.SMOOTH_SCROLL_MASK)

    def _child_at_window_coords(self, widget, x, y):
        """Deepest mapped widget with no GdkWindow of its own at x, y.

        Coordinates are relative to the toplevel. Children that own a
        different GdkWindow (VTE, sidebar) are skipped so a wheel there
        is not treated as a tab-strip click.
        """
        if widget is None or not widget.get_mapped():
            return None
        top = widget.get_toplevel()
        origin = widget.translate_coordinates(top, 0, 0)
        if origin is None:
            return None
        ox, oy = origin
        alloc = widget.get_allocation()
        if not (ox <= x < ox + alloc.width and oy <= y < oy + alloc.height):
            return None
        top_win = top.get_window()
        if hasattr(widget, 'get_children'):
            for child in reversed(list(widget.get_children())):
                child_win = child.get_window()
                if child.get_has_window() and child_win not in (None, top_win):
                    continue
                hit = self._child_at_window_coords(child, x, y)
                if hit is not None:
                    return hit
        return widget

    def on_scroll_event(self, notebook, event):
        '''Handle scroll events for scrolling through tabs'''
        #print "self: %s" % self
        #print "event: %s" % event
        child = self.get_nth_page(self.get_current_page())
        if child == None:
            print("Child = None,  return false")
            return False

        event_widget = Gtk.get_event_widget(event)
        # A wheel on the toplevel window reports the window, not the
        # windowless tab label under the pointer.
        ev_win = getattr(event, 'window', None)
        if (ev_win is not None and ev_win is self.get_window()
                and event_widget is self.get_toplevel()
                and hasattr(event, 'x')):
            hit = self._child_at_window_coords(
                self.get_toplevel(), event.x, event.y)
            if hit is None:
                return False
            event_widget = hit

        if event_widget == None or \
           event_widget == child or \
           event_widget.is_ancestor(child):
            print("event_widget is wrong one,  return false")
            return False

        # Not sure if we need these. I don't think wehave any action widgets
        # at this point.
        action_widget = self.get_action_widget(Gtk.PackType.START)
        if event_widget == action_widget or \
           (action_widget != None and event_widget.is_ancestor(action_widget)):
            return False
        action_widget = self.get_action_widget(Gtk.PackType.END)
        if event_widget == action_widget or \
           (action_widget != None and event_widget.is_ancestor(action_widget)):
            return False

        if event.direction in [Gdk.ScrollDirection.RIGHT,
                               Gdk.ScrollDirection.DOWN]:
            self.next_page()
        elif event.direction in [Gdk.ScrollDirection.LEFT,
                                 Gdk.ScrollDirection.UP]:
            self.prev_page()
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            # Same mapping as a discrete wheel, on every tab edge: positive
            # delta_y is down, positive delta_x is right, and both move to
            # the next page. Small deltas accumulate; a direction change
            # drops the unused remainder so a wiggle does not switch twice.
            dx = float(getattr(event, 'delta_x', 0.0) or 0.0)
            dy = float(getattr(event, 'delta_y', 0.0) or 0.0)
            delta = dy if abs(dy) >= abs(dx) else dx
            if delta != 0.0:
                acc = getattr(self, '_scroll_acc', 0.0)
                if acc != 0.0 and (acc > 0.0) != (delta > 0.0):
                    acc = 0.0
                acc += delta
                while acc >= 1.0:
                    self.next_page()
                    acc -= 1.0
                while acc <= -1.0:
                    self.prev_page()
                    acc += 1.0
                self._scroll_acc = acc
        return True

class TabLabel(Gtk.HBox):
    """Class implementing a label widget for Notebook tabs"""
    notebook = None
    terminator = None
    config = None
    label = None
    icon = None
    button = None

    __gsignals__ = {
            'close-clicked': (GObject.SignalFlags.RUN_LAST, None,
                (GObject.TYPE_OBJECT,)),
    }

    def __init__(self, title, notebook):
        """Class initialiser"""
        GObject.GObject.__init__(self)

        self.notebook = notebook
        self.terminator = Terminator()
        self.config = Config()
        self._locked = False

        self.connect("button-press-event", self.on_button_pressed)

        self.label = EditableLabel(title)
        # Two lines, like Cursor's two-level row: the name, then the folder.
        self._lines = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.folder_label = Gtk.Label(xalign=0, halign=Gtk.Align.START)
        self.folder_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.folder_label.get_style_context().add_class('terminator-tab-folder')
        self.folder_label.set_no_show_all(True)
        self._lines.pack_start(self.label, False, False, 0)
        self._lines.pack_start(self.folder_label, False, False, 0)
        self.update_angle()

        self.pack_start(self._lines, True, True, 0)

        self.update_button()
        self.show_all()
        if self.button is not None:
            self.button.hide()
        self.connect('enter-notify-event', self._on_pointer_enter)
        self.connect('leave-notify-event', self._on_pointer_leave)

    def set_label(self, text):
        """Update the text of our label"""
        self.label.set_text(text)
        self._fit_label_width()

    def set_folder_name(self, cwd):
        """First line is the folder name, unless the user renamed the tab.

        The second line is the folder path. A custom title never gets
        replaced; clearing it falls back to the folder name.
        """
        if not cwd:
            return
        self._cwd = cwd
        name = folder_basename(cwd)
        subtitle = folder_subtitle(cwd)
        # set_text updates the automatic title even while a custom one shows.
        self.label.set_text(name or subtitle)
        same = (not self.label.is_custom()) and subtitle == (name or subtitle)
        if same or self.notebook.get_tab_pos() != Gtk.PositionType.LEFT:
            self.folder_label.hide()
        else:
            self.folder_label.set_text(subtitle)
            self.folder_label.show()
        self._fit_label_width()

    def _fit_label_width(self):
        """Sidebar rows ellipsize inside a fixed width. Top tabs use the title."""
        label = self.label._label
        label.set_halign(Gtk.Align.START)
        if self.notebook.get_tab_pos() == Gtk.PositionType.LEFT:
            if getattr(self.notebook, '_tab_tree', None) is not None:
                self.set_no_show_all(True)
                self.set_size_request(0, 0)
                self.hide()
                return
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_xalign(0)
            label.set_max_width_chars(26)
            self.folder_label.set_max_width_chars(32)
            self.set_size_request(220, 44)
            return
        self.folder_label.hide()
        text = label.get_text() or ''
        layout = label.create_pango_layout(text)
        width, _height = layout.get_pixel_size()
        cap = 420
        if width > cap:
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_size_request(cap, -1)
        else:
            label.set_ellipsize(Pango.EllipsizeMode.NONE)
            label.set_size_request(-1, -1)
        self.set_size_request(-1, -1)

    def get_label(self):
        return self.label.get_text()

    def set_custom_label(self, text, force=False):
        """Set a permanent label as if the user had edited it"""
        self.label.set_text(text, force=force)
        self.label.set_custom()

    def get_custom_label(self):
        """Return a custom label if we have one, otherwise None"""
        if self.label.is_custom():
            return(self.label.get_text())
        else:
            return(None)

    def get_locked(self):
        """True when a normal exit should open this tab again."""
        return bool(getattr(self, '_locked', False))

    def set_locked(self, locked):
        self._locked = bool(locked)

    def edit(self):
        self.label.edit()

    def update_button(self):
        """Update the state of our close button"""
        if not self.config['close_button_on_tab']:
            if self.button:
                self.button.remove(self.icon)
                self.remove(self.button)
                del(self.button)
                del(self.icon)
                self.button = None
                self.icon = None
            return

        if not self.button:
            self.button = Gtk.Button()
            # Right-click on the close mark uses the same tab menu.
            self.button.connect('button-press-event', self.on_button_pressed)
            self.button.connect('clicked', self.on_close)
        if not self.icon:
            self.icon = Gtk.Label(label='\u00d7')
            self.icon.get_style_context().add_class('terminator-tab-close-mark')

        self.button.set_focus_on_click(False)
        self.button.set_relief(Gtk.ReliefStyle.NONE)
        self.button.set_can_focus(False)
        if self.icon.get_parent() is None:
            self.button.add(self.icon)
        self.button.get_style_context().add_class('terminator-tab-close')
        self.button.set_name('terminator-tab-close-button')
        if hasattr(self.button, 'set_tooltip_text'):
            self.button.set_tooltip_text(_('Close Tab'))
        if self.button.get_parent() is None:
            self.pack_start(self.button, False, False, 0)
        # Wave shows the mark only while the pointer is on the tab.
        self.button.set_no_show_all(True)
        self.icon.show()
        self.show_all()
        self.button.hide()

    def update_angle(self):
        """Update the angle of a label.

        The left-hand list keeps horizontal text, the same as a sidebar
        row. Only a tab strip on the right is turned on its side.
        """
        position = self.notebook.get_tab_pos()
        if position == Gtk.PositionType.RIGHT:
            if hasattr(self, 'set_orientation'):
                self.set_orientation(Gtk.Orientation.VERTICAL)
            self.label.set_angle(270)
        else:
            if hasattr(self, 'set_orientation'):
                self.set_orientation(Gtk.Orientation.HORIZONTAL)
            self.label.set_angle(0)
        self._fit_label_width()

    def _on_pointer_enter(self, _widget, _event):
        if self.button is not None:
            self.button.show()
        return False

    def _on_pointer_leave(self, _widget, event):
        if getattr(event, 'detail', None) == Gdk.NotifyType.INFERIOR:
            return False
        if self.button is not None:
            self.button.hide()
        return False

    def on_close(self, _widget):
        """The close button has been clicked. Destroy the tab"""
        self.emit('close-clicked', self)

    def on_button_pressed(self, _widget, event):
        if event.button == 2:
            self.on_close(_widget)
            return True
        if event.button == 3:
            # A right-click in the rename entry belongs to the entry.
            if self.label.editing():
                return False
            self.popup_tab_menu(event)
            return True
        return False

    def popup_tab_menu(self, event):
        """Tab context menu: move, detach, close. Same set as GNOME Terminal."""
        nb = self.notebook
        page = nb.page_num_of_label(self)
        if page is None:
            return False
        try:
            nb.set_current_page(page)
        except Exception:
            pass
        state = tab_menu_sensitive(page, nb.get_n_pages())
        menu = Gtk.Menu()
        keep = Gtk.CheckMenuItem.new_with_mnemonic(_('_Keep for next launch'))
        keep.set_active(self.get_locked())

        def on_keep(item):
            self.set_locked(item.get_active())
            if hasattr(nb, 'note_tab_lock'):
                nb.note_tab_lock()

        keep.connect('toggled', on_keep)
        menu.append(keep)
        menu.append(Gtk.SeparatorMenuItem())

        def add(text, enabled, callback):
            item = Gtk.MenuItem.new_with_mnemonic(_(text))
            item.set_sensitive(enabled)
            item.connect('activate', lambda *_a: callback())
            menu.append(item)

        add('Move Terminal _Left', state['left'],
            lambda: nb.move_labeled_tab(self, 'left'))
        add('Move Terminal _Right', state['right'],
            lambda: nb.move_labeled_tab(self, 'right'))
        menu.append(Gtk.SeparatorMenuItem())
        add('_Detach Terminal', state['detach'],
            lambda: nb.detach_labeled_tab(self))
        menu.append(Gtk.SeparatorMenuItem())
        add('_Close Terminal', state['close'],
            lambda: self.on_close(None))
        menu.show_all()
        # Keep the menu alive until it pops down.
        self._tab_menu = menu
        menu.popup_at_pointer(event)
        return True

# vim: set expandtab ts=4 sw=4:
