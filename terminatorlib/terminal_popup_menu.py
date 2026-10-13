# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""terminal_popup_menu.py - classes necessary to provide a terminal context
menu"""

import re
from gi.repository import Gtk, Gdk

from .version import APP_NAME
from .translation import _
from .terminator import Terminator
from .util import err, dbg, spawn_new_terminator
from .config import Config
from .prefseditor import PrefsEditor
from . import plugin

class TerminalPopupMenu(object):
    """Class implementing the Terminal context menu"""
    terminal = None
    terminator = None
    config = None
    accelgrp = None

    def __init__(self, terminal):
        """Class initialiser"""
        self.terminal = terminal
        self.terminator = Terminator()
        self.config = Config()
        self.accelgrp = Gtk.AccelGroup()

    def get_menu_item_mask(self, maskstr):
        mask = 0
        if maskstr is None:
            return mask
        maskstr = maskstr.lower()
        if maskstr.find('<Shift>'.lower()) >= 0:
            mask = mask | Gdk.ModifierType.SHIFT_MASK
            dbg("adding mask <Shift> %s" % mask)

        ctrl = (maskstr.find('<Control>'.lower()) >= 0 or
                maskstr.find('<Primary>'.lower()) >= 0)
        if ctrl:
            mask = mask | Gdk.ModifierType.CONTROL_MASK
            dbg("adding mask <Control> %s" % mask)

        if maskstr.find('<Alt>'.lower()) >= 0:
            mask = mask | Gdk.ModifierType.MOD1_MASK
            dbg("adding mask <Alt> %s" % mask)

        mask = Gdk.ModifierType(mask)
        dbg("menu_item_mask :%d" % mask)
        return mask

    def menu_item(self, menutype, actstr, menustr):
        act     = self.config.base.get_item('keybindings', actstr)
        maskstr = act[actstr] if actstr in act else ""
        mask    = self.get_menu_item_mask(maskstr)

        accelchar = ""
        pos = menustr.lower().find("_")
        if (pos >= 0 and pos+1 < len(menustr)):
            accelchar = menustr.lower()[pos+1]

        #this may require tweak. what about shortcut function keys ?
        if maskstr:
            mpos = maskstr.rfind(">")
            #can't have a char at 0 position as <> is len 2
            if mpos >= 0 and mpos+1 < len(maskstr):
                configaccelchar = maskstr[mpos+1:]
                #ensure to take only 1 char else ignore
                if len(configaccelchar) == 1:
                    dbg("found accelchar in config:%s  override:%s"
                                    %  (configaccelchar, accelchar))
                    accelchar = configaccelchar

        dbg("action from config:%s for item:%s with shortcut accelchar:(%s)"
                                    % (maskstr, menustr, accelchar))
        item = menutype.new_with_mnemonic(menustr)
        item.set_name(actstr)
        if mask:
            item.add_accelerator("activate",
                                self.accelgrp,
                                Gdk.keyval_from_name(accelchar),
                                mask,
                                Gtk.AccelFlags.VISIBLE)
        return item

    def close_terminal(self, _menuitem=None):
        """Close the terminal after applying the normal close confirmation."""
        from .close_confirm import request_close_terminal
        request_close_terminal(self.terminal)

    def wants_chrome_menu(self, anchor, skip_link_check):
        """Settings belong on a titlebar, not on the terminal click.

        The window header menu, the pane titlebar and the gear pass
        skip_link_check or an anchor. The VTE menu stays short while any
        of those is available. A borderless window with no pane titlebar
        has nowhere else, so the VTE menu keeps the extra items."""
        if skip_link_check or anchor is not None:
            return True
        return not self._chrome_menu_elsewhere()

    def _pane_titlebar_visible(self):
        try:
            configured = bool(self.config['show_titlebar'])
        except Exception:
            configured = True
        if not configured:
            return False
        bar = getattr(self.terminal, 'titlebar', None)
        if bar is not None and hasattr(bar, 'get_visible'):
            try:
                return bool(bar.get_visible())
            except Exception:
                pass
        return configured

    def _window_header_menu_available(self):
        """The window title bar's menu button can carry the full menu."""
        getter = getattr(self.terminal, 'get_toplevel', None)
        if not callable(getter):
            return False
        try:
            window = getter()
        except Exception:
            return False
        if window is None or getattr(window, '_header_bar', None) is None:
            return False
        menu = getattr(window, '_header_menu', None)
        if menu is None:
            return False
        visible = getattr(menu, 'get_visible', None)
        if not callable(visible):
            return True
        try:
            return bool(visible())
        except Exception:
            return True

    def _chrome_menu_elsewhere(self):
        return (self._pane_titlebar_visible() or
                self._window_header_menu_available())

    def show(self, widget, event=None, anchor=None, skip_link_check=False):
        """Display the context menu.
        anchor: if given, attach the menu below this widget (titlebar gear).
        skip_link_check: event coordinates are not on the VTE (titlebar),
        so skip hyperlink / URL match detection."""
        terminal = self.terminal

        menu = Gtk.Menu()
        self.popup_menu = menu
        url = None
        button = None
        time = None

        self.config.set_profile(terminal.get_profile())
        chrome = self.wants_chrome_menu(anchor, skip_link_check)

        if event and skip_link_check:
            button = event.button
            time = event.time
        elif event:
            url = terminal.vte.hyperlink_check_event(event)

            if url:
                tag = None

                for pattern, tag in terminal.matches.items():
                    try:
                        if re.search(pattern, url):
                            tag = tag

                            break
                    except Exception:
                        continue

                if tag is not None:
                    url = [url, tag]
                else:
                    url = terminal.vte.match_check_event(event)
            else:
                url = terminal.vte.match_check_event(event)

            button = event.button
            time = event.time
        else:
            time = 0
            button = 3

        if url and url[0]:
            dbg("URL matches id: %d" % url[1])
            if not url[1] in list(terminal.matches.values()):
                err("Unknown URL match id: %d" % url[1])
                dbg("Available matches: %s" % terminal.matches)

            nameopen = None
            namecopy = None
            if url[1] == terminal.matches['email']:
                nameopen = _('_Send email to...')
                namecopy = _('_Copy email address')
            elif url[1] == terminal.matches['voip']:
                nameopen = _('Ca_ll VoIP address')
                namecopy = _('_Copy VoIP address')
            elif url[1] in list(terminal.matches.values()):
                # This is a plugin match
                for pluginname in terminal.matches:
                    if terminal.matches[pluginname] == url[1]:
                        break

                dbg("Found match ID (%d) in terminal.matches plugin %s" %
                        (url[1], pluginname))
                registry = plugin.PluginRegistry()
                registry.load_plugins()
                plugins = registry.get_plugins_by_capability('url_handler')
                for urlplugin in plugins:
                    if urlplugin.handler_name == pluginname:
                        dbg("Identified matching plugin: %s" %
                                urlplugin.handler_name)
                        nameopen = _(urlplugin.nameopen)
                        namecopy = _(urlplugin.namecopy)
                        break

            if not nameopen:
                nameopen = _('_Open link')
            if not namecopy:
                namecopy = _('_Copy address')

            icon = Gtk.Image.new_from_stock(Gtk.STOCK_JUMP_TO,
                                            Gtk.IconSize.MENU)
            item = Gtk.ImageMenuItem.new_with_mnemonic(nameopen)
            item.set_property('image', icon)
            item.set_tooltip_text(url[0])
            item.connect('activate', lambda x: terminal.open_url(url, True))
            menu.append(item)

            item = Gtk.MenuItem.new_with_mnemonic(namecopy)
            item.set_tooltip_text(url[0])
            item.connect('activate',
                         lambda x: terminal.clipboard.set_text(terminal.prepare_url(url), len(terminal.prepare_url(url))))
            menu.append(item)

            menu.append(Gtk.SeparatorMenuItem())

        item = self.menu_item(Gtk.ImageMenuItem, 'copy', _('_Copy'))
        item.connect('activate', lambda x: terminal.vte.copy_clipboard())
        item.set_sensitive(terminal.vte.get_has_selection())

        menu.append(item)

        item = self.menu_item(Gtk.ImageMenuItem, 'paste', _('_Paste'))
        item.connect('activate', lambda x: terminal.paste_clipboard())
        menu.append(item)

        menu.append(Gtk.SeparatorMenuItem())

        # Titles, auto-split, detach and the settings block are titlebar
        # and gear items. The VTE menu keeps copy/paste, H/V split, tab,
        # close and maximise.
        if chrome:
            item = self.menu_item(Gtk.ImageMenuItem, 'edit_window_title',
                                                     _('Set _Window Title'))
            item.connect('activate', lambda x: terminal.key_edit_window_title())
            menu.append(item)

            # D15: double-click on the titlebar now toggles maximise, so title
            # editing lives here (and on the edit_terminal_title keybinding).
            item = self.menu_item(Gtk.MenuItem, 'edit_terminal_title',
                                                _('Edit _Title'))
            item.connect('activate', lambda x: terminal.key_edit_terminal_title())
            menu.append(item)

        if not terminal.is_zoomed():
            if chrome:
                item = self.menu_item(Gtk.ImageMenuItem, 'split_auto',
                                                         _('Split _Auto'))
                item.connect('activate', lambda x: terminal.emit('split-auto',
                    self.terminal.get_cwd()))
                menu.append(item)

            item = self.menu_item(Gtk.ImageMenuItem, 'split_horiz',
                                                     _('Split H_orizontally'))
            image = Gtk.Image()
            image.set_from_icon_name(APP_NAME + '_horiz', Gtk.IconSize.MENU)
            item.set_image(image)
            if hasattr(item, 'set_always_show_image'):
                item.set_always_show_image(True)
            item.connect('activate', lambda x: terminal.emit('split-horiz',
                self.terminal.get_cwd()))
            menu.append(item)

            item = self.menu_item(Gtk.ImageMenuItem, 'split_vert',
                                                     _('Split V_ertically'))
            image = Gtk.Image()
            image.set_from_icon_name(APP_NAME + '_vert', Gtk.IconSize.MENU)
            item.set_image(image)
            if hasattr(item, 'set_always_show_image'):
                item.set_always_show_image(True)
            item.connect('activate', lambda x: terminal.emit('split-vert',
                self.terminal.get_cwd()))
            menu.append(item)

            item = self.menu_item(Gtk.MenuItem, 'new_tab', _('Open _Tab'))
            item.connect('activate', lambda x: terminal.emit('tab-new', False,
                terminal))
            menu.append(item)

            if chrome and self.terminator.debug_address is not None:
                item = Gtk.MenuItem.new_with_mnemonic(_('Open _Debug Tab'))
                item.connect('activate', lambda x:
                        terminal.emit('tab-new', True, terminal))
                menu.append(item)

            if chrome and isinstance(terminal.get_toplevel().get_child(), Gtk.Notebook):
                item = self.menu_item(Gtk.MenuItem, 'detach_tab',
                                                    _('Detach Ta_b'))
                item.connect('activate', lambda x:
                        terminal.emit('detach-tab'))
                menu.append(item)

            menu.append(Gtk.SeparatorMenuItem())

        item = self.menu_item(Gtk.ImageMenuItem, 'close_term', _('_Close'))
        item.connect('activate', self.close_terminal)
        menu.append(item)

        menu.append(Gtk.SeparatorMenuItem())

        if not terminal.is_zoomed():
            # Only the terminals of the current tab count: a single terminal
            # in a tab used to be (wrongly) sensitive.
            window = terminal.get_toplevel()
            sensitive = bool(hasattr(window, 'has_multiple_terms') and
                             window.has_multiple_terms())

            if chrome:
                item = Gtk.MenuItem.new_with_mnemonic(_('_Zoom terminal'))
                item.connect('activate', terminal.zoom)
                item.set_sensitive(sensitive)
                menu.append(item)

            item = Gtk.MenuItem.new_with_mnemonic(_('Ma_ximize pane'))
            item.connect('activate', terminal.maximise)
            item.set_sensitive(sensitive)
            menu.append(item)

            menu.append(Gtk.SeparatorMenuItem())
        else:
            item = Gtk.MenuItem.new_with_mnemonic(_('_Restore pane'))
            item.connect('activate', terminal.unzoom)
            menu.append(item)

            menu.append(Gtk.SeparatorMenuItem())

        # m36: the grouping icon is hidden by default (titlebar_show_icon),
        # so Grouping lives on the titlebar / gear menu. A hidden titlebar
        # makes the VTE menu the chrome menu, and Grouping stays there.
        if chrome and (self.config['show_titlebar'] == False or
                       not self.config['titlebar_show_icon']):
            item = Gtk.MenuItem.new_with_mnemonic(_('Grouping'))
            submenu = self.terminal.populate_group_menu()
            submenu.show_all()
            item.set_submenu(submenu)
            menu.append(item)
            menu.append(Gtk.SeparatorMenuItem())

        if terminal.is_held_open:
            item = Gtk.MenuItem.new_with_mnemonic(_('Relaunch Command'))
            item.connect('activate', lambda x: terminal.spawn_child())
            menu.append(item)
            menu.append(Gtk.SeparatorMenuItem())

        if chrome:
            item = self.menu_item(Gtk.CheckMenuItem, 'toggle_readonly', _('_Read only'))
            item.set_active(not(terminal.vte.get_input_enabled()))
            item.connect('toggled', lambda x: terminal.do_readonly_toggle())
            menu.append(item)

            self.add_font_lock_item(menu)

            item = self.menu_item(Gtk.CheckMenuItem, 'toggle_scrollbar',
                                                       _('Show _scrollbar'))
            item.set_active(terminal.scrollbar.get_property('visible'))
            item.connect('toggled', lambda x: terminal.do_scrollbar_toggle())
            menu.append(item)

            if hasattr(Gtk, 'Builder'):  # VERIFY FOR GTK3: is this ever false?
                item = self.menu_item(Gtk.MenuItem, 'preferences',
                                                    _('_Preferences'))
                item.connect('activate', lambda x: PrefsEditor(self.terminal))
                menu.append(item)

        if chrome:
            self._append_appearance_items(menu, terminal)

        try:
            menuitems = []
            registry = plugin.PluginRegistry()
            registry.load_plugins()
            plugins = registry.get_plugins_by_capability('terminal_menu')
            for menuplugin in plugins:
                menuplugin.callback(menuitems, menu, terminal)

            if len(menuitems) > 0:
                menu.append(Gtk.SeparatorMenuItem())

            for menuitem in menuitems:
                menu.append(menuitem)
        except Exception as ex:
            err('TerminalPopupMenu::show: %s' % ex)

        # A section that did not run still leaves its separator. Drop a
        # divider that would sit under the last item with nothing after it.
        children = menu.get_children()
        while children and isinstance(children[-1], Gtk.SeparatorMenuItem):
            menu.remove(children[-1])
            children = menu.get_children()

        menu.show_all()
        popped = False
        if anchor is not None:
            try:
                menu.popup_at_widget(anchor, Gdk.Gravity.SOUTH_EAST,
                                     Gdk.Gravity.NORTH_EAST, event)
                popped = True
            except Exception as ex:
                err('TerminalPopupMenu::show: popup_at_widget failed: %s' % ex)
        if not popped:
            menu.popup_at_pointer(None)

        return(True)

    def _append_appearance_items(self, menu, terminal):
        """Colors, profiles and layouts. Titlebar and gear only."""
        theme_items = [
            ('Solarized Light', '#eee8d5', '#586e75'),
            ('Solarized Dark', '#002b36', '#839496'),
            ('Monokai', '#272822', '#f8f8f2'),
            ('Dracula', '#282a36', '#f8f8f2'),
            ('Gruvbox Light', '#fbf1c7', '#3c3836'),
            ('Gruvbox Dark', '#282828', '#ebdbb2'),
            ('Nord', '#2e3440', '#d8dee9'),
            ('One Light', '#fafafa', '#383a42'),
            ('One Dark', '#1d1f21', '#c5c8c6'),
            ('Zenburn', '#3f3f3f', '#dcdccc'),
            ('Nightfox', '#1a1b26', '#c0caf5'),
            ('Taiwanese Blue', '#005695', '#ffffff'),
            ('Solarized Blue', '#073642', '#93a1a1'),
        ]
        item = Gtk.MenuItem.new_with_mnemonic(_('_Colors'))
        submenu = Gtk.Menu()
        item.set_submenu(submenu)
        menu.append(item)

        for theme_label, bg, fg in theme_items:
            item = Gtk.MenuItem(theme_label)
            item.connect('activate',
                         lambda x, b=bg, f=fg: (terminal.set_bgcolor(b),
                                                terminal.set_fgcolor(f)))
            submenu.append(item)

        submenu.append(Gtk.SeparatorMenuItem())
        custom_item = Gtk.MenuItem.new_with_mnemonic(_('_Custom...'))
        custom_item.connect('activate', lambda x: self.pick_custom_colors(terminal))
        submenu.append(custom_item)

        profilelist = sorted(self.config.list_profiles(), key=str.lower)
        if len(profilelist) > 1:
            item = Gtk.MenuItem.new_with_mnemonic(_('Profiles'))
            submenu = Gtk.Menu()
            item.set_submenu(submenu)
            menu.append(item)

            current = terminal.get_profile()
            group = None
            for profile in profilelist:
                profile_label = profile
                if profile_label == 'default':
                    profile_label = profile.capitalize()
                item = Gtk.RadioMenuItem(profile_label, group)
                if profile == current:
                    item.set_active(True)
                item.connect('activate', terminal.force_set_profile, profile)
                submenu.append(item)

        self.add_layout_launcher(menu)

    def add_font_lock_item(self, menu):
        """'Lock font size for this terminal' (hook for auto font scale, E).
        Hidden until the terminal provides set/get_auto_font_locked and
        auto_font_scale is enabled."""
        terminal = self.terminal
        if not (hasattr(terminal, 'set_auto_font_locked') and
                hasattr(terminal, 'get_auto_font_locked')):
            return None
        try:
            enabled = self.config['auto_font_scale']
        except Exception:
            enabled = False
        if not enabled:
            return None
        item = Gtk.CheckMenuItem.new_with_mnemonic(
            _('_Lock font size for this terminal'))
        item.set_active(bool(terminal.get_auto_font_locked()))
        item.connect('toggled',
                     lambda x: terminal.set_auto_font_locked(x.get_active()))
        menu.append(item)
        return item

    def pick_custom_colors(self, terminal):
        """Open a dialog to choose background and foreground colors at once"""
        dialog = Gtk.Dialog(title=_('Pick Terminal Colors'),
                            transient_for=terminal.get_toplevel(),
                            flags=Gtk.DialogFlags.MODAL)
        dialog.add_button(_('Cancel'), Gtk.ResponseType.CANCEL)
        dialog.add_button(_('Apply'), Gtk.ResponseType.OK)

        content = dialog.get_content_area()
        content.set_spacing(8)
        content.set_border_width(12)

        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(8)

        bg_label = Gtk.Label(label=_('Background:'), xalign=0)
        bg_btn = Gtk.ColorButton()
        bg_btn.set_use_alpha(True)
        if terminal.bgcolor is not None:
            bg_btn.set_rgba(terminal.bgcolor.copy())

        fg_label = Gtk.Label(label=_('Text:'), xalign=0)
        fg_btn = Gtk.ColorButton()
        if terminal.fgcolor_active is not None:
            fg_initial = terminal.fgcolor_active.copy()
            fg_initial.alpha = 1.0
            fg_btn.set_rgba(fg_initial)

        grid.attach(bg_label, 0, 0, 1, 1)
        grid.attach(bg_btn, 1, 0, 1, 1)
        grid.attach(fg_label, 0, 1, 1, 1)
        grid.attach(fg_btn, 1, 1, 1, 1)
        content.add(grid)
        dialog.show_all()

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            bg_rgba = bg_btn.get_rgba()
            fg_rgba = fg_btn.get_rgba()
            bg_hex = "#{0:02x}{1:02x}{2:02x}".format(
                int(bg_rgba.red * 255),
                int(bg_rgba.green * 255),
                int(bg_rgba.blue * 255))
            fg_hex = "#{0:02x}{1:02x}{2:02x}".format(
                int(fg_rgba.red * 255),
                int(fg_rgba.green * 255),
                int(fg_rgba.blue * 255))
            terminal.set_bgcolor(bg_hex, alpha=bg_rgba.alpha)
            terminal.set_fgcolor(fg_hex)
        dialog.destroy()

    def add_layout_launcher(self, menu):
        """Add the layout list to the menu"""
        item = self.menu_item(Gtk.MenuItem, 'layout_launcher', _('_Layouts...'))
        menu.append(item)
        submenu = Gtk.Menu()
        item.set_submenu(submenu)
        layouts = self.config.list_layouts()
        for layout in layouts:
                item = Gtk.MenuItem(layout)
                item.connect('activate', lambda x: spawn_new_terminator(self.terminator.origcwd, ['-u', '-l', x.get_label()]))
                submenu.append(item)
