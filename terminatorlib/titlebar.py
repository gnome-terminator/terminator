# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""titlebar.py - classes necessary to provide a terminal title bar"""

from gi.repository import Gtk, Gdk
from gi.repository import GObject
from gi.repository import GLib
from gi.repository import Pango

from .version import APP_NAME
from .util import dbg, err
from .terminator import Terminator
from .editablelabel import EditableLabel
from .translation import _

_BTN_FG_PROVIDERS = {}


def _button_fg_provider(color):
    """Cached CssProvider colouring titlebar buttons/badge with the
    titlebar's own fg colour (UI review P2-9: a fixed light #c9d1d9 was
    unreadable on light title_*_bg_color). Hover keeps the global rules."""
    provider = _BTN_FG_PROVIDERS.get(color)
    if provider is None:
        rgba = Gdk.RGBA()
        if not rgba.parse(str(color)):
            return None
        provider = Gtk.CssProvider()
        try:
            provider.load_from_data((
                'button:not(:hover) { color: %s; }' % rgba.to_string()
            ).encode())
        except Exception as ex:
            dbg('titlebar button css: %s' % ex)
            return None
        _BTN_FG_PROVIDERS[color] = provider
    return provider

# pylint: disable-msg=R0904
# pylint: disable-msg=W0613
# m26 (round2-ux P2-5): text glyphs used when no icon can be rendered
_BUTTON_FALLBACK_TEXT = {
    'gear': '\u2699',      # ⚙
    'maximise': '\u2922',  # ⤢
    'restore': '\u2921',   # ⤡
    'close': '\u2715',     # ✕
}
_ICON_LOADABLE = {}


class Titlebar(Gtk.EventBox):
    """Class implementing the Titlebar widget"""

    terminator = None
    terminal = None
    config = None
    oldtitle = None
    termtext = None
    sizetext = None
    label = None
    ebox = None
    groupicon = None
    grouplabel = None
    groupentry = None
    bellicon = None
    termicon = None
    btn_gear = None
    btn_max = None
    btn_close = None
    scale_badge = None
    _badge_label = None
    _badge_lock = None
    _badge_wanted = False
    _win_sig = None
    _sizetext_timer = None
    _collapse_level = 0
    _collapse_idle = None
    _pressed_btn = None
    _maximise_icon_state = None
    # m36: the left-hand terminal/grouping icons are hidden by default
    # (titlebar_show_icon).  Grouping stays reachable through the group
    # name (clickable), the context menu "Grouping" submenu and the group
    # shortcuts; broadcast state is shown as text on the sending pane.
    _show_icon = False
    _icon_name_current = None
    broadcastlabel = None

    # Width thresholds (px) for progressively collapsing optional parts.
    # Order: size text -> group name -> scale badge -> gear -> maximise.
    # m26 (round2-ux P2-3): the title keeps at least TITLE_MIN_CHARS
    # before buttons do; gear and maximise stay reachable through the
    # context menu, double-click and their shortcuts.  Close never hides.
    COLLAPSE_SIZETEXT_PX = 320
    COLLAPSE_GROUP_PX = 280
    COLLAPSE_BADGE_PX = 240
    COLLAPSE_GEAR_PX = 200
    COLLAPSE_MAX_PX = 150
    TITLE_MIN_CHARS = 6
    _show_buttons = True

    __gsignals__ = {
            'clicked': (GObject.SignalFlags.RUN_LAST, None, ()),
            'edit-done': (GObject.SignalFlags.RUN_LAST, None, ()),
            'create-group': (GObject.SignalFlags.RUN_LAST, None,
                (GObject.TYPE_STRING,)),
    }

    def __init__(self, terminal):
        """Class initialiser"""
        GObject.GObject.__init__(self)

        self.terminator = Terminator()
        self.terminal = terminal
        self.config = self.terminal.config

        # D15: double-click toggles pane maximise; editing the title moves
        # to the context menu / edit_terminal_title keybinding.
        self.label = EditableLabel(double_click_edit=False)
        self.label.connect('edit-done', self.on_edit_done)
        self.label.connect('double-clicked',
                           lambda *_: self._toggle_pane_maximise())
        self.ebox = Gtk.EventBox()
        grouphbox = Gtk.HBox()
        self.grouplabel = Gtk.Label(ellipsize='end')
        self.groupicon = Gtk.Image()
        self.groupicon.set_no_show_all(True)
        self.broadcastlabel = Gtk.Label()
        self.broadcastlabel.set_no_show_all(True)
        self.broadcastlabel.get_style_context().add_class(
            'titlebar-broadcast')
        self.bellicon = Gtk.Image()
        self.bellicon.set_no_show_all(True)

        self.groupentry = Gtk.Entry()
        self.groupentry.set_no_show_all(True)
        self.groupentry.connect('focus-out-event', self.groupentry_cancel)
        self.groupentry.connect('activate', self.groupentry_activate)
        self.groupentry.connect('key-press-event', self.groupentry_keypress)

        groupsend_type = self.terminator.groupsend_type
        if self.terminator.groupsend == groupsend_type['all']:
            icon_name = 'all'
        elif self.terminator.groupsend == groupsend_type['group']:
            icon_name = 'group'
        elif self.terminator.groupsend == groupsend_type['off']:
            icon_name = 'off'
        self.set_from_icon_name('_active_broadcast_%s' % icon_name, 
                Gtk.IconSize.MENU)

        grouphbox.pack_start(self.groupicon, False, True, 2)
        grouphbox.pack_start(self.broadcastlabel, False, True, 2)
        grouphbox.pack_start(self.grouplabel, False, True, 2)
        grouphbox.pack_start(self.groupentry, False, True, 2)

        self.ebox.add(grouphbox)
        self.ebox.show_all()

        self.bellicon.set_from_icon_name('terminal-bell', Gtk.IconSize.MENU)

        viewport = Gtk.Viewport(hscroll_policy='natural')
        viewport.add(self.label)
        self._title_viewport = viewport
        self._apply_title_min_width()

        self.termicon = Gtk.Image()
        _termicon = self._loadable_icon('utilities-terminal-symbolic',
                                        'utilities-terminal', 'terminal')
        if _termicon is not None:
            self.termicon.set_from_icon_name(_termicon, Gtk.IconSize.MENU)
        else:
            # nothing renderable: no image-missing placeholder
            self._termicon_ok = False
        self.termicon.set_no_show_all(True)

        # Right-hand buttons (Wave style): [badge] gear  maximise  close
        self.btn_close = self._make_button(
            ('window-close-symbolic', 'window-close'), 'close',
            ['titlebar-btn', 'titlebar-btn-close'])
        self.btn_max = self._make_button(
            ('view-fullscreen-symbolic', 'view-fullscreen'), 'maximise',
            ['titlebar-btn'])
        self.btn_gear = self._make_button(
            ('emblem-system-symbolic', 'preferences-system-symbolic',
             'open-menu-symbolic', 'emblem-system'), 'gear',
            ['titlebar-btn'])

        self.scale_badge = Gtk.Button()
        self.scale_badge.set_relief(Gtk.ReliefStyle.NONE)
        self.scale_badge.set_focus_on_click(False)
        self.scale_badge.get_style_context().add_class('titlebar-badge')
        badgebox = Gtk.HBox(spacing=2)
        self._badge_lock = Gtk.Image()
        self._badge_lock.set_from_icon_name(
            self._icon_name('changes-prevent-symbolic', 'changes-prevent',
                            'system-lock-screen-symbolic'),
            Gtk.IconSize.MENU)
        self._badge_lock.set_no_show_all(True)
        self._badge_label = Gtk.Label(label='')
        badgebox.pack_start(self._badge_lock, False, False, 0)
        badgebox.pack_start(self._badge_label, False, False, 0)
        self._badge_label.show()
        badgebox.show()
        self.scale_badge.add(badgebox)
        self.scale_badge.set_no_show_all(True)
        # Clicks on the badge must not start a DnD of the terminal; E
        # connects 'clicked' to show its popover.
        self.scale_badge.connect('button-press-event',
                                 self._on_badge_button_press)

        hbox = Gtk.HBox()
        hbox.pack_start(self.termicon, False, False, 4)
        hbox.pack_start(self.ebox, False, True, 0)
        self._group_sep = Gtk.VSeparator()
        self._group_sep.set_no_show_all(True)
        hbox.pack_start(self._group_sep, False, True, 0)
        hbox.pack_start(viewport, True, True, 0)
        # pack_end: first packed is right-most
        hbox.pack_end(self.btn_close, False, False, 0)
        hbox.pack_end(self.btn_max, False, False, 0)
        hbox.pack_end(self.btn_gear, False, False, 0)
        hbox.pack_end(self.scale_badge, False, False, 2)
        hbox.pack_end(self.bellicon, False, False, 2)

        self.add(hbox)
        hbox.show_all()
        self.set_no_show_all(True)
        self.show()

        self.connect('button-press-event', self.on_button_press)
        self.connect('hierarchy-changed', self._on_hierarchy_changed)
        self.connect('size-allocate', self._on_size_allocate)
        self.connect('destroy', self._on_destroy)

        self.apply_chrome_config()

    _termicon_ok = True

    def connect_icon(self, func):
        """Connect the supplied function to clicking on the group icon
        (the whole group box: icon, broadcast text and group name)"""
        self.ebox.connect('button-press-event', func)

    def update(self, other=None):
        """Update our contents"""
        default_bg = False

        temp_heldtext_str = ''
        temp_sizetext_str = ''

        if self.terminal.is_held_open:
            temp_heldtext_str = _('[INACTIVE: Right-Click for Relaunch option] ')
        if (not self.config['title_hide_sizetext'] and self.sizetext
                and self._sizetext_timer is not None
                and self._collapse_level < 1):
            temp_sizetext_str = " %s" % (self.sizetext)
        self.label.set_text("%s%s%s" % (temp_heldtext_str, self.termtext, temp_sizetext_str))

        if (not self.config['title_use_system_font']) and self.config['title_font']:
            title_font = Pango.FontDescription(self.config['title_font'])
        else:
            title_font = Pango.FontDescription(self.config.get_system_prop_font())
        self.label.modify_font(title_font)
        self.grouplabel.modify_font(title_font)

        if other:
            term = self.terminal
            terminator = self.terminator
            if other == 'window-focus-out':
                title_fg = self.config['title_inactive_fg_color']
                title_bg = self.config['title_inactive_bg_color']
                icon = '_receive_off'
                default_bg = True
                group_fg = self.config['title_inactive_fg_color']
                group_bg = self.config['title_inactive_bg_color']
            elif term != other and term.group and term.group == other.group:
                if terminator.groupsend == terminator.groupsend_type['off']:
                    title_fg = self.config['title_inactive_fg_color']
                    title_bg = self.config['title_inactive_bg_color']
                    icon = '_receive_off'
                    default_bg = True
                else:
                    title_fg = self.config['title_receive_fg_color']
                    title_bg = self.config['title_receive_bg_color']
                    icon = '_receive_on'
                group_fg = self.config['title_receive_fg_color']
                group_bg = self.config['title_receive_bg_color']
            elif term != other and not term.group or term.group != other.group:
                if terminator.groupsend == terminator.groupsend_type['all']:
                    title_fg = self.config['title_receive_fg_color']
                    title_bg = self.config['title_receive_bg_color']
                    icon = '_receive_on'
                else:
                    title_fg = self.config['title_inactive_fg_color']
                    title_bg = self.config['title_inactive_bg_color']
                    icon = '_receive_off'
                    default_bg = True
                group_fg = self.config['title_inactive_fg_color']
                group_bg = self.config['title_inactive_bg_color']
            else:
                # We're the active terminal
                title_fg = self.config['title_transmit_fg_color']
                title_bg = self.config['title_transmit_bg_color']
                if terminator.groupsend == terminator.groupsend_type['all']:
                    icon = '_active_broadcast_all'
                elif terminator.groupsend == terminator.groupsend_type['group']:
                    icon = '_active_broadcast_group'
                else:
                    icon = '_active_broadcast_off'
                group_fg = self.config['title_transmit_fg_color']
                group_bg = self.config['title_transmit_bg_color']

            self.label.modify_fg(Gtk.StateType.NORMAL,
                    Gdk.color_parse(title_fg))
            self._set_button_fg(title_fg)
            self.grouplabel.modify_fg(Gtk.StateType.NORMAL,
                    Gdk.color_parse(group_fg))
            self.modify_bg(Gtk.StateType.NORMAL, 
                    Gdk.color_parse(title_bg))
            if not self.get_desired_visibility():
                if default_bg == True:
                    color = term.get_style_context().get_background_color(Gtk.StateType.NORMAL)  # VERIFY FOR GTK3
                else:
                    color = Gdk.color_parse(title_bg)
            self.update_visibility()
            self.ebox.modify_bg(Gtk.StateType.NORMAL,
                    Gdk.color_parse(group_bg))
            self.set_from_icon_name(icon, Gtk.IconSize.MENU)
            self._update_broadcast_label(icon)

    def update_visibility(self):
        """Make the titlebar be visible or not"""
        if not self.get_desired_visibility():
            dbg('hiding titlebar')
            self.hide()
            self.label.hide()
        else:
            dbg('showing titlebar')
            self.show()
            self.label.show()

    def get_desired_visibility(self):
        """Returns True if the titlebar is supposed to be visible. False if
        not"""
        if self.editing() == True or self.terminal.group:
            dbg('implicit desired visibility')
            return(True)
        else:
            dbg('configured visibility: %s' % self.config['show_titlebar'])
            return(self.config['show_titlebar'])

    def set_from_icon_name(self, name, size = Gtk.IconSize.MENU):
        """Set an icon for the group label"""
        self._icon_name_current = name
        if not name:
            self.groupicon.hide()
            return

        self.groupicon.set_from_icon_name(APP_NAME + name, size)
        if self._show_icon:
            self.groupicon.show()
        else:
            self.groupicon.hide()

    def _apply_icon_visibility(self):
        """m36: show/hide the terminal and grouping icons"""
        try:
            show = bool(self.config['titlebar_show_icon'])
        except Exception:
            show = False
        self._show_icon = show
        if show and self._termicon_ok:
            self.termicon.show()
        else:
            self.termicon.hide()
        if show and self._icon_name_current:
            self.groupicon.show()
        else:
            self.groupicon.hide()
        self._update_broadcast_label(self._icon_name_current)

    def _update_broadcast_label(self, icon):
        """Text replacement for the broadcast state icon on the sending
        pane when icons are hidden (receivers already get the receive
        colours)."""
        label = self.broadcastlabel
        if label is None:
            return
        text = ''
        if not self._show_icon:
            if icon == '_active_broadcast_all':
                text = _('Broadcast: all')
            elif icon == '_active_broadcast_group' and \
                    getattr(self.terminal, 'group', None):
                text = _('Broadcast: group')
        label.set_text(text)
        if text:
            label.set_tooltip_text(_('Click for the grouping menu'))
        self._apply_collapse()

    def update_terminal_size(self, width, height):
        """Update the displayed terminal size. The size is only shown for
        about a second after a resize instead of permanently."""
        sizetext = "%sx%s" % (width, height)
        if sizetext == self.sizetext and self._sizetext_timer is None:
            # Unchanged size (e.g. re-allocation without resize): do not
            # flash the size again.
            return
        self.sizetext = sizetext
        if self._sizetext_timer is not None:
            GLib.source_remove(self._sizetext_timer)
        self._sizetext_timer = GLib.timeout_add(1000, self._clear_sizetext)
        self.update()

    def _clear_sizetext(self):
        """Timeout: stop displaying the terminal size"""
        self._sizetext_timer = None
        self.update_label_only()
        return False

    def update_label_only(self):
        """Refresh the label text without touching colours"""
        temp_heldtext_str = ''
        if self.terminal.is_held_open:
            temp_heldtext_str = _('[INACTIVE: Right-Click for Relaunch option] ')
        sizetext = ''
        if (self._sizetext_timer is not None and self.sizetext
                and not self.config['title_hide_sizetext']
                and self._collapse_level < 1):
            sizetext = " %s" % self.sizetext
        self.label.set_text("%s%s%s" % (temp_heldtext_str, self.termtext,
                                        sizetext))

    def set_terminal_title(self, widget, title):
        """Update the terminal title"""
        self.termtext = title
        self.update()
        # Return False so we don't interrupt any chains of signal handling
        return False

    def set_group_label(self, name):
        """Set the name of the group"""
        if name:
            self.grouplabel.set_text(name)
            self.grouplabel.show()
        else:
            self.grouplabel.set_text('')
            self.grouplabel.hide()
        self._apply_collapse()
        self.update_visibility()

    def on_button_press(self, widget, event):
        """Handle mouse presses anywhere on the titlebar.

        Right-click opens the terminal context menu (useful when the
        terminal application, e.g. tmux with mouse on, swallows right
        clicks). It must return True so nothing else sees the event.
        Double-click toggles pane maximise (D15). Single left clicks are
        not consumed so DnD still works."""
        if event.button == 3 and event.type == Gdk.EventType.BUTTON_PRESS:
            self.terminal.grab_focus()
            self.terminal.popup_menu(self, event, skip_link_check=True)
            return True
        if event.button == 1 and event.type == Gdk.EventType._2BUTTON_PRESS:
            if not self.editing():
                self._toggle_pane_maximise()
            return True
        if event.button == 1 and event.type == Gdk.EventType.BUTTON_PRESS:
            self.show()
            self.label.show()
            self.emit('clicked')
        return False

    # Backwards compatible name
    on_clicked = on_button_press

    # ---- Buttons -------------------------------------------------------

    @staticmethod
    def _icon_name(*names):
        """Return the first icon name the current theme provides"""
        return Titlebar._loadable_icon(*names) or names[0]

    @staticmethod
    def _loadable_icon(*names):
        """First icon name the theme has AND can actually render, or None.

        m26 (round2-ux P2-5): has_icon() is True for symbolic SVG icons
        even without the gdk-pixbuf SVG loader (minimal installs), which
        then render as image-missing.  Results are cached per name."""
        try:
            theme = Gtk.IconTheme.get_default()
        except Exception:
            theme = None
        if theme is None:
            return None
        for name in names:
            ok = _ICON_LOADABLE.get(name)
            if ok is None:
                ok = False
                if theme.has_icon(name):
                    try:
                        ok = theme.load_icon(name, 16, 0) is not None
                    except Exception as ex:
                        dbg('icon %s not loadable: %s' % (name, ex))
                        ok = False
                _ICON_LOADABLE[name] = ok
            if ok:
                return name
        return None

    def _set_button_glyph(self, btn, icon_names, fallback_text):
        """Icon if one can be rendered, else a short text glyph."""
        name = self._loadable_icon(*icon_names)
        if name is not None:
            image = btn.get_image()
            if image is None:
                image = Gtk.Image()
                btn.set_image(image)
            image.set_from_icon_name(name, Gtk.IconSize.MENU)
            btn.set_always_show_image(True)
        else:
            btn.set_label(fallback_text)
            btn.get_style_context().add_class('titlebar-btn-text')

    def _set_button_fg(self, color):
        """Icon colour of ⚙/maximise/✕ and the badge follows title fg."""
        if getattr(self, '_btn_fg', None) == color:
            return
        provider = _button_fg_provider(color)
        if provider is None:
            return
        old = _BTN_FG_PROVIDERS.get(getattr(self, '_btn_fg', None))
        for btn in (getattr(self, 'btn_close', None),
                    getattr(self, 'btn_max', None),
                    getattr(self, 'btn_gear', None),
                    getattr(self, 'scale_badge', None)):
            if btn is None:
                continue
            ctx = btn.get_style_context()
            if old is not None:
                ctx.remove_provider(old)
            ctx.add_provider(provider,
                             Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
        self._btn_fg = color

    def _make_button(self, icon_names, action, classes):
        """Create a flat titlebar button"""
        btn = Gtk.Button()
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.set_focus_on_click(False)
        btn.set_can_focus(True)
        self._set_button_glyph(btn, icon_names,
                               _BUTTON_FALLBACK_TEXT.get(action, '?'))
        context = btn.get_style_context()
        for klass in classes:
            context.add_class(klass)
        btn.connect('button-press-event', self._on_btn_press, action)
        btn.connect('button-release-event', self._on_btn_release, action)
        # Keyboard activation (Enter/Space) arrives as 'clicked'
        btn.connect('clicked', self._on_btn_clicked, action)
        return btn

    def _on_btn_press(self, btn, event, action):
        """Handle presses on our own buttons. Returning True stops the
        event from reaching the titlebar (no DnD, no double-click toggle)."""
        if event.button == 3:
            # Let a right-click bubble up to the titlebar menu handler
            return False
        if event.button != 1:
            return True
        if event.type != Gdk.EventType.BUTTON_PRESS:
            # Swallow double/triple clicks on buttons
            return True
        if action == 'gear':
            self._pressed_btn = None
            self._do_action(action, btn, event)
            return True
        self._pressed_btn = btn
        return True

    def _on_btn_release(self, btn, event, action):
        """Activate max/close on release inside the button"""
        if event.button != 1:
            return False
        pressed = self._pressed_btn
        self._pressed_btn = None
        if pressed is not btn:
            return True
        alloc = btn.get_allocation()
        if 0 <= event.x < alloc.width and 0 <= event.y < alloc.height:
            self._do_action(action, btn, event)
        return True

    def _on_btn_clicked(self, btn, action):
        """Keyboard activation of a button"""
        current = Gtk.get_current_event()
        if current is not None and current.type in (
                Gdk.EventType.BUTTON_PRESS, Gdk.EventType.BUTTON_RELEASE,
                Gdk.EventType._2BUTTON_PRESS, Gdk.EventType._3BUTTON_PRESS):
            # Mouse activation is handled by press/release above
            return
        self._do_action(action, btn, None)

    def _do_action(self, action, btn, event):
        """Run a titlebar button action"""
        if action == 'gear':
            self.terminal.grab_focus()
            self.terminal.popup_menu(btn, event, anchor=btn,
                                     skip_link_check=True)
        elif action == 'maximise':
            self._toggle_pane_maximise()
        elif action == 'close':
            self.on_close_clicked()

    def _on_badge_button_press(self, btn, event):
        """Do not let badge clicks start a DnD or toggle maximise"""
        if event.button == 3:
            return False
        if event.type != Gdk.EventType.BUTTON_PRESS:
            return True
        return False

    def on_close_clicked(self, *_args):
        """Close via the single confirmed close path (D17)"""
        from .close_confirm import request_close_terminal
        request_close_terminal(self.terminal)

    # ---- Chrome config / tooltips ---------------------------------------

    def apply_chrome_config(self):
        """Apply titlebar_buttons / titlebar_density"""
        try:
            show_buttons = bool(self.config['titlebar_buttons'])
        except Exception:
            show_buttons = True
        try:
            density = self.config['titlebar_density']
        except Exception:
            density = 'standard'
        if density not in ('standard', 'compact'):
            if density:
                err('Invalid titlebar_density %r, using standard' % density)
            density = 'standard'

        context = self.get_style_context()
        for name in ('standard', 'compact'):
            klass = 'titlebar-density-%s' % name
            if name == density:
                context.add_class(klass)
            else:
                context.remove_class(klass)

        self._show_buttons = show_buttons
        self._apply_icon_visibility()
        for btn in (self.btn_gear, self.btn_max, self.btn_close):
            btn.set_no_show_all(not show_buttons)
            if show_buttons:
                btn.show()
            else:
                btn.hide()
        self._apply_collapse()
        self._update_button_tooltips()
        self.refresh_maximise_state()

    def _accel_label(self, *actions):
        """Human readable accelerator for the first of `actions` that has a
        working shortcut, or ''.

        m26 (round2-ux P2-4): built from the resolved key lookup, so a
        default shortcut that lost to a user binding of another action is
        not advertised."""
        for action in actions:
            label = self._accel_label_one(action)
            if label:
                return label
        return ''

    def _accel_label_one(self, action):
        try:
            value = self.config['keybindings'][action]
        except Exception:
            return ''
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ''
        kb = getattr(self.terminator, 'keybindings', None)
        if kb is not None and hasattr(kb, 'resolved_bindings') and \
                getattr(kb, 'keys', None):
            try:
                resolved = kb.resolved_bindings(action)
                value = resolved[0] if resolved else ''
            except Exception:
                pass
        if not value:
            return ''
        try:
            key, mods = Gtk.accelerator_parse(value)
            if not key and not mods:
                return ''
            return Gtk.accelerator_get_label(key, mods)
        except Exception:
            return ''

    @staticmethod
    def _with_accel(text, accel):
        if accel:
            return '%s (%s)' % (text, accel)
        return text

    def _set_button_text(self, btn, name, tooltip):
        btn.set_tooltip_text(tooltip)
        acc = btn.get_accessible()
        if acc is not None:
            acc.set_name(name)

    def _update_button_tooltips(self):
        """(Re)build tooltips / accessible names, honouring rebinds"""
        self._set_button_text(self.btn_gear, _('Terminal menu'),
                              _('Terminal menu (right-click the titlebar too)'))
        self._set_button_text(
            self.btn_close, _('Close terminal'),
            self._with_accel(_('Close terminal'), self._accel_label('close_term')))
        self._maximise_icon_state = None
        self.refresh_maximise_state()

    # ---- Pane maximise state (driven by Window 'pane-maximise-changed') --

    def _pane_maximise_state(self, multiple=None):
        """Return (window, restorable, multiple) for our terminal.

        multiple: precomputed Window.has_multiple_terms() (m26 P2-1: the
        caller refreshing every titlebar of a window walks the tree once
        instead of once per titlebar)."""
        win = self.get_toplevel()
        if win is None or not hasattr(win, 'has_multiple_terms'):
            return (None, False, False)
        restorable = False
        try:
            if hasattr(win, 'is_maximised_pane') and \
                    win.is_maximised_pane(self.terminal):
                restorable = True
            elif win.is_zoomed():
                # Legacy (font-scaled) zoom of this terminal: allow restore
                zoom_data = getattr(win, 'zoom_data', None) or {}
                restorable = zoom_data.get('widget') is self.terminal
        except Exception as ex:
            dbg('pane maximise state failed: %s' % ex)
        if multiple is None:
            try:
                multiple = bool(win.has_multiple_terms())
            except Exception:
                multiple = False
        return (win, restorable, bool(multiple))

    def refresh_maximise_state(self, *_args, multiple=None):
        """Update maximise button icon, tooltip and sensitivity.
        Never called optimistically from the click handler: the state is
        only trusted after the Window says it changed."""
        if self.btn_max is None:
            return
        _win, restorable, multiple = self._pane_maximise_state(multiple)
        self.btn_max.set_sensitive(restorable or multiple)
        if self._maximise_icon_state == restorable:
            return
        self._maximise_icon_state = restorable
        accel = self._accel_label('maximise', 'toggle_zoom')
        if restorable:
            icons = ('view-restore-symbolic', 'view-restore')
            glyph = _BUTTON_FALLBACK_TEXT['restore']
            name = _('Restore pane')
        else:
            icons = ('view-fullscreen-symbolic', 'view-fullscreen')
            glyph = _BUTTON_FALLBACK_TEXT['maximise']
            name = _('Maximize pane')
        self._set_button_glyph(self.btn_max, icons, glyph)
        self._set_button_text(self.btn_max, name, self._with_accel(name, accel))

    def _disconnect_window_signal(self):
        if self._win_sig is not None:
            win, handler = self._win_sig
            self._win_sig = None
            try:
                if win.handler_is_connected(handler):
                    win.disconnect(handler)
            except Exception:
                pass

    def _on_hierarchy_changed(self, widget, prev_toplevel):
        """Terminal may move between windows (DnD / detach tab)"""
        win = self.get_toplevel()
        if self._win_sig is not None and self._win_sig[0] is win:
            self.refresh_maximise_state()
            return
        self._disconnect_window_signal()
        if win is not None and hasattr(win, 'is_maximised_pane'):
            try:
                handler = win.connect('pane-maximise-changed',
                                      self._on_pane_maximise_changed)
                self._win_sig = (win, handler)
            except TypeError:
                pass
        self.refresh_maximise_state()

    def _on_pane_maximise_changed(self, window, terminal, maximised):
        self.refresh_maximise_state()

    def _toggle_pane_maximise(self):
        """Maximise this pane, or restore if it is the maximised one"""
        win, restorable, multiple = self._pane_maximise_state()
        if win is None:
            return
        if restorable:
            self.terminal.unzoom()
        elif multiple:
            self.terminal.maximise()

    def _on_destroy(self, *_args):
        self._disconnect_window_signal()
        if self._sizetext_timer is not None:
            GLib.source_remove(self._sizetext_timer)
            self._sizetext_timer = None
        if self._collapse_idle is not None:
            GLib.source_remove(self._collapse_idle)
            self._collapse_idle = None

    # ---- Scale badge (E owns the popover and decides when to call) -------

    def set_scale_badge(self, scale, locked):
        """Show the auto font scale badge.
        scale: float or None; locked: bool.
        Hidden when scale is None, or scale ~1.0 and not locked."""
        locked = bool(locked)
        if scale is None or (scale >= 0.999 and not locked):
            self._badge_wanted = False
            self.scale_badge.hide()
            return
        percent = int(round(float(scale) * 100))
        self._badge_label.set_text('%d%%' % percent)
        if locked:
            self._badge_lock.show()
            tooltip = _('Font size locked')
        else:
            self._badge_lock.hide()
            tooltip = _('Auto font size %d%% (click for details)') % percent
        self.scale_badge.set_tooltip_text(tooltip)
        acc = self.scale_badge.get_accessible()
        if acc is not None:
            acc.set_name(_('Auto font size %d%%') % percent)
        self._badge_wanted = True
        self._apply_collapse()

    # ---- Narrow-width collapsing -----------------------------------------

    def _apply_title_min_width(self):
        """Reserve ~TITLE_MIN_CHARS characters for the title."""
        viewport = getattr(self, '_title_viewport', None)
        if viewport is None:
            return
        try:
            metrics = self.get_pango_context().get_metrics(None, None)
            char_w = metrics.get_approximate_char_width() / Pango.SCALE
        except Exception:
            char_w = 8
        viewport.set_size_request(
            int(round(max(4, char_w) * self.TITLE_MIN_CHARS)), -1)

    def _collapse_level_for(self, width):
        if width < self.COLLAPSE_MAX_PX:
            return 5
        if width < self.COLLAPSE_GEAR_PX:
            return 4
        if width < self.COLLAPSE_BADGE_PX:
            return 3
        if width < self.COLLAPSE_GROUP_PX:
            return 2
        if width < self.COLLAPSE_SIZETEXT_PX:
            return 1
        return 0

    def _on_size_allocate(self, widget, allocation):
        level = self._collapse_level_for(allocation.width)
        if level == self._collapse_level:
            return
        self._collapse_level = level
        if self._collapse_idle is None:
            # Changing visibility inside size-allocate re-queues layout;
            # defer to idle to avoid allocation loops.
            self._collapse_idle = GLib.idle_add(self._collapse_idle_cb)

    def _collapse_idle_cb(self):
        self._collapse_idle = None
        self._apply_collapse()
        self.update_label_only()
        return False

    def _apply_collapse(self):
        level = self._collapse_level
        group_wanted = bool(self.grouplabel.get_text()) and \
            not self.groupentry.get_property('visible')
        if group_wanted and level < 2:
            self.grouplabel.show()
        elif level >= 2:
            self.grouplabel.hide()
        blabel = self.broadcastlabel
        if blabel is not None:
            # Same narrow-width step as the group name
            blabel.set_visible(bool(blabel.get_text()) and level < 2)
        sep = getattr(self, '_group_sep', None)
        if sep is not None:
            # m36: no dangling separator when the group box is empty
            sep.set_visible(bool(
                self.groupicon.get_visible() or
                (self.grouplabel.get_visible() and
                 bool(self.grouplabel.get_text())) or
                self.groupentry.get_visible() or
                (blabel is not None and blabel.get_visible()) or
                self.termicon.get_visible()))
        if self._badge_wanted and level < 3:
            self.scale_badge.show()
        else:
            self.scale_badge.hide()
        if self._show_buttons:
            for btn, hide_at in ((self.btn_gear, 4), (self.btn_max, 5)):
                if btn is not None:
                    btn.set_visible(level < hide_at)

    def on_edit_done(self, widget):
        """Re-emit an edit-done signal from an EditableLabel"""
        self.emit('edit-done')

    def editing(self):
        """Determine if we're currently editing a group name or title"""
        return(self.groupentry.get_property('visible') or self.label.editing())

    def create_group(self):
        """Create a new group"""
        if self.terminal.group:
            self.groupentry.set_text(self.terminal.group)
        else:
            self.groupentry.set_text(self.terminator.new_random_group())
        self.groupentry.show()
        self.grouplabel.hide()
        self._apply_collapse()
        self.groupentry.grab_focus()
        self.update_visibility()

    def groupentry_cancel(self, widget, event):
        """Hide the group name entry"""
        self.groupentry.set_text('')
        self.groupentry.hide()
        self.grouplabel.show()
        self._apply_collapse()
        self.get_parent().grab_focus()

    def groupentry_activate(self, widget):
        """Actually cause a group to be created"""
        groupname = self.groupentry.get_text() or None
        dbg('creating group: %s' % groupname)
        self.groupentry_cancel(None, None)
        last_focused_term=self.terminator.last_focused_term
        if self.terminal.targets_for_new_group:
            [term.titlebar.emit('create-group', groupname) for term in self.terminal.targets_for_new_group]
            self.terminal.targets_for_new_group = None
        else:
            self.emit('create-group', groupname)
        last_focused_term.grab_focus()
        self.terminator.focus_changed(last_focused_term)

    def groupentry_keypress(self, widget, event):
        """Handle keypresses on the entry widget"""
        key = Gdk.keyval_name(event.keyval)
        if key == 'Escape':
            self.groupentry_cancel(None, None)

    def icon_bell(self):
        """A bell signal requires we display our bell icon"""
        self.bellicon.show()
        GLib.timeout_add(1000, self.icon_bell_hide)

    def icon_bell_hide(self):
        """Handle a timeout which means we now hide the bell icon"""
        self.bellicon.hide()
        return(False)

    def get_custom_string(self):
        """If we have a custom string set, return it, otherwise None"""
        if self.label.is_custom():
            return(self.label.get_text())
        else:
            return(None)

    def set_custom_string(self, string):
        """Set a custom string"""
        self.label.set_text(string)
        self.label.set_custom()

GObject.type_register(Titlebar)
