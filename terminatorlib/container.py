# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""container.py - classes necessary to contain Terminal widgets"""

from gi.repository import GObject
from gi.repository import Gtk

from .factory import Factory
from .config import Config
from .util import dbg, err
from .translation import _
from .signalman import Signalman

def window_terminal_signals(top_window, widget, rotate=True, zoom=True):
    """Window-level Terminal signal handlers shared by every container
    (Window, Window overlay frame, Paned, Notebook). Single source of truth
    so the copies cannot drift (UI review P2-3); callers add their own
    container-specific entries (close-term, split-*, title-change, ...)."""
    signals = {'tab-change': top_window.tab_change,
               'group-all': top_window.group_all,
               'group-all-toggle': top_window.group_all_toggle,
               'ungroup-all': top_window.ungroup_all,
               'group-win': top_window.group_win,
               'group-win-toggle': top_window.group_win_toggle,
               'ungroup-win': top_window.ungroup_win,
               'group-tab': top_window.group_tab,
               'group-tab-toggle': top_window.group_tab_toggle,
               'ungroup-tab': top_window.ungroup_tab,
               'move-tab': top_window.move_tab,
               'detach-tab': top_window.detach_tab_to_new_window,
               'tab-new': [top_window.tab_new, widget],
               'navigate': top_window.navigate_terminal}
    if rotate:
        signals['rotate-cw'] = [top_window.rotate, True]
        signals['rotate-ccw'] = [top_window.rotate, False]
    if zoom:
        signals['zoom'] = top_window.zoom
        signals['maximise'] = [top_window.zoom, False]
    return signals


# pylint: disable-msg=R0921
class Container(object):
    """Base class for Terminator Containers"""

    terminator = None
    immutable = None
    children = None
    config = None
    signals = None
    signalman = None

    def __init__(self):
        """Class initialiser"""
        self.children = []
        self.signals = []
        self.cnxids = Signalman()
        self.config = Config()

    def register_signals(self, widget):
        """Register gobject signals in a way that avoids multiple inheritance"""
        existing = GObject.signal_list_names(widget)
        for signal in self.signals:
            if signal['name'] in existing:
                dbg('Container:: skipping signal %s for %s, already exists' % (
                        signal['name'], widget))
            else:
                dbg('Container:: registering signal for %s on %s' % 
                        (signal['name'], widget))
                try:
                    GObject.signal_new(signal['name'],
                                       widget,
                                       signal['flags'],
                                       signal['return_type'],
                                        signal['param_types'])
                except RuntimeError:
                    err('Container:: registering signal for %s on %s failed' %
                            (signal['name'], widget))

    def connect_child(self, widget, signal, handler, *args):
        """Register the requested signal and record its connection ID"""
        self.cnxids.new(widget, signal, handler, *args)
        return

    def connect_terminal_signals(self, widget, signals):
        """Connect a {signal: handler | [handler, *args]} table to widget."""
        for signal, handler in signals.items():
            args = []
            if isinstance(handler, list):
                args = handler[1:]
                handler = handler[0]
            self.connect_child(widget, signal, handler, *args)

    def disconnect_child(self, widget):
        """De-register the signals for a child"""
        self.cnxids.remove_widget(widget)

    def get_offspring(self):
        """Return a list of direct child widgets, if any"""
        return(self.children)

    def get_child_metadata(self, widget):
        """Return metadata that would be useful to recreate ourselves after our
        child is .remove()d and .add()ed"""
        return None

    @staticmethod
    def _note_user_split(widget):
        try:
            from .session import note_window_grown
            note_window_grown(widget.get_toplevel())
        except Exception as ex:
            dbg('note_window_grown: %s' % ex)

    def split_auto(self, widget, cwd=None):
        """Split this container automatically"""
        self._note_user_split(widget)
        width  = widget.get_allocation().width
        height = widget.get_allocation().height
        dbg("split as per current dimenstions:(%s %s)" % (width, height))
        if width > height:
            self.split_axis(widget, False, cwd)
        else:
            self.split_axis(widget, True , cwd)

    def split_horiz(self, widget, cwd=None):
        """Split this container horizontally"""
        self._note_user_split(widget)
        return(self.split_axis(widget, True, cwd))

    def split_vert(self, widget, cwd=None):
        """Split this container vertically"""
        self._note_user_split(widget)
        return(self.split_axis(widget, False, cwd))

    def split_axis(self, widget, vertical=True, cwd=None, sibling=None, siblinglast=None):
        """Default axis splitter. This should be implemented by subclasses"""
        raise NotImplementedError('split_axis')

    def rotate(self, widget, clockwise):
        """Rotate children in this container"""
        raise NotImplementedError('rotate')

    def add(self, widget, metadata=None):
        """Add a widget to the container"""
        raise NotImplementedError('add')

    def remove(self, widget):
        """Remove a widget from the container"""
        raise NotImplementedError('remove')

    def replace(self, oldwidget, newwidget):
        """Replace the child oldwidget with newwidget. This is the bare minimum
        required for this operation. Containers should override it if they have
        more complex requirements"""
        if not oldwidget in self.get_children():
            err('%s is not a child of %s' % (oldwidget, self))
            return
        self.remove(oldwidget)
        self.add(newwidget)

    def hoover(self):
        """Ensure we still have a reason to exist"""
        raise NotImplementedError('hoover')

    def get_children(self):
        """Return an ordered list of the children of this Container"""
        raise NotImplementedError('get_children')

    def closeterm(self, widget):
        """Handle the closure of a terminal"""
        # m26 (a): record whether this pane's window is excluded from the
        # session while it is still attached; after remove() its toplevel is
        # the pane itself and the window can no longer be found.
        try:
            from .session import terminal_is_excluded
            terminal_is_excluded(widget)
        except Exception as ex:
            dbg('closeterm record exclusion: %s' % ex)
        try:
            if self.get_property('term_zoomed'):
                # We're zoomed, so unzoom and then start closing again
                dbg('terminal zoomed, unzooming')
                from .zoomguard import leave_zoom
                # Window.closeterm already left an overlay maximise; this is
                # the legacy-zoom case (m26: same helper as every close path).
                if leave_zoom(self, reason='container-closeterm',
                              quiet=False):
                    widget.close()
                    return(True)
                # m26 review: nothing could be undone (stale term_zoomed);
                # re-closing would recurse forever, so fall through to the
                # normal close path instead.
                err('closeterm: term_zoomed set but no zoom to leave')
        except TypeError:
            pass

        self._session_before_last_close(widget)

        if not self.remove(widget):
            dbg('self.remove() failed for %s' % widget)
            return(False)

        self.terminator.deregister_terminal(widget)
        widget.close()
        self.terminator.group_hoover()
        return(True)

    def _session_before_last_close(self, widget):
        """Capture the session while `widget` is still in the tree.

        Round-2 P1-2: the last terminal of the run is closing (exit,
        Ctrl+Shift+W, titlebar X).  Finalize while it is still in the tree
        and registered: the final save then describes what was open (this
        pane, fresh cwd) and its latest output is flushed synchronously
        before the cache stops.  Deregistering first destroys the window,
        and finalize would see 0 terminals.

        m26 (e2e 2b): the same holds for the last terminal of a window when
        other windows remain (its shell exited): the window is destroyed
        only after the terminal was removed, so Window.on_destroy_event's
        D5 note_window_closing saw 0 terminals and the window was lost.
        Buffer its fragment now, like Ctrl+Shift+Q does before teardown.
        """
        try:
            from .session import SessionManager
            if self.terminator.terminals == [widget]:
                SessionManager().finalize()
                return
            window = widget.get_toplevel()
            if window is None or window not in self.terminator.windows:
                return
            if getattr(window, '_session_destroy_handled', False) or \
                    getattr(window, 'isDestroyed', False):
                return  # on_destroy_event already described the window
            if [t for t in window.get_terminals() if t is not widget]:
                return  # not the last terminal of its window
            remaining = [w for w in self.terminator.windows
                         if w is not window
                         and not getattr(w, 'isDestroyed', False)
                         and not getattr(w, '_session_destroy_handled', False)]
            sess = SessionManager()
            if not remaining:
                # Last window, but stray registered terminals elsewhere:
                # same as the last terminal of the run.
                sess.finalize()
            else:
                sess.note_window_closing(window)
        except Exception as ex:
            import traceback
            err('session capture before last close: %s\n%s'
                % (ex, traceback.format_exc()))

    def resizeterm(self, widget, keyname):
        """Handle a keyboard event requesting a terminal resize"""
        raise NotImplementedError('resizeterm')

    def zoom(self, widget, fontscale = False):
        """Zoom a terminal"""
        raise NotImplementedError('zoom')

    def unzoom(self, widget):
        """Unzoom a terminal"""
        raise NotImplementedError('unzoom')

    def construct_confirm_close(self, window, child):
        """Create a confirmation dialog for closing things"""
        maker = Factory()

        # D17: process-running confirmation takes priority
        try:
            from .close_confirm import construct_confirm_close_with_processes
            proc_result = construct_confirm_close_with_processes(
                self, window, child)
            if proc_result is not None:
                return proc_result
        except Exception as ex:
            from .util import dbg
            dbg('construct_confirm_close processes: %s' % ex)

        has_multiple_terms = False
        if maker.isinstance(child, 'Window'):
            try:
                from .close_confirm import window_has_multiple_terminals as _hmt
                has_multiple_terms = _hmt(child)
            except Exception:
                has_multiple_terms = True
        elif not maker.isinstance(child, 'Terminal'):
            has_multiple_terms = True
        elif maker.isinstance(self, 'Window'):
            # Overlay maximise also sets term_zoomed; count real terminals
            # instead of treating any zoom as "multiple".
            try:
                from .close_confirm import window_has_multiple_terminals as _hmt
                has_multiple_terms = _hmt(self)
            except Exception:
                has_multiple_terms = self.is_zoomed()

        # skip this dialog if applicable
        if self.config['ask_before_closing'] == 'never':
            return Gtk.ResponseType.ACCEPT
        elif self.config['ask_before_closing'] == 'multiple_terminals':
            if not has_multiple_terms:
                return Gtk.ResponseType.ACCEPT

        # text
        confirm_button_text = (_('Close _Terminals') if has_multiple_terms
                               else _('Close _Terminal'))
        big_label_text = (_('Close multiple terminals?') if has_multiple_terms
                          else _('Close terminal?'))

        if not has_multiple_terms:
            description_text = _('Do you really wish to close this terminal?')
        elif maker.isinstance(self, 'Window'):
            description_text = _('This window has several terminals open. Closing \
the window will also close all terminals within it.')
        elif maker.isinstance(self, 'Notebook'):
            description_text = _('This tab has several terminals open. Closing \
the tab will also close all terminals within it.')
        else:
            description_text = ''

        # dialog GUI
        dialog = Gtk.Dialog(_('Close?'), window, Gtk.DialogFlags.MODAL)
        dialog.set_resizable(False)
    
        dialog.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.REJECT)
        c_all = dialog.add_button(Gtk.STOCK_CLOSE, Gtk.ResponseType.ACCEPT)
        c_all.get_children()[0].get_children()[0].get_children()[1].set_label(
                confirm_button_text)
    
        primary = Gtk.Label(label='<big><b>' + big_label_text + '</b></big>')
        primary.set_use_markup(True)
        primary.set_alignment(0, 0.5)

        secondary = Gtk.Label(label=description_text)
        secondary.set_line_wrap(True)
                    
        labels = Gtk.VBox()
        labels.pack_start(primary, False, False, 6)
        labels.pack_start(secondary, False, False, 6)
    
        image = Gtk.Image.new_from_stock(Gtk.STOCK_DIALOG_WARNING,
                                         Gtk.IconSize.DIALOG)
        image.set_alignment(0.5, 0)
    
        box = Gtk.HBox()
        box.pack_start(image, False, False, 6)
        box.pack_start(labels, False, False, 6)
        dialog.vbox.pack_start(box, False, False, 12)

        checkbox = Gtk.CheckButton(_("Do not show this message next time"))
        dialog.vbox.pack_end(checkbox, True, True, 0)
    
        dialog.show_all()

        result = dialog.run()
        
        # set configuration
        self.config.base.reload()
        if checkbox.get_active():
            self.config['ask_before_closing'] = 'never'
        self.config.save()

        dialog.destroy()
                
        return(result)

    def propagate_title_change(self, widget, title):
        """Pass a title change up the widget stack"""
        from .util import logical_parent
        maker = Factory()
        parent = logical_parent(self)
        title = widget.get_window_title()

        if maker.isinstance(self, 'Notebook'):
            self.update_tab_label_text(widget, title)
        elif maker.isinstance(self, 'Window'):
            self.title.set_title(widget, title)

        if maker.isinstance(parent, 'Container'):
            parent.propagate_title_change(widget, title)

    def get_visible_terminals(self):
        """Walk the widget tree to find all of the visible terminals. That is,
        any terminals which are not hidden in another Notebook pane"""
        if not hasattr(self, 'cached_maker'):
            self.cached_maker = Factory()
        maker = self.cached_maker
        terminals = {}

        for child in self.get_offspring():
            if not child:
                continue
            if getattr(child, 'is_pane_placeholder', False):
                # Module D: report the floating terminal at its slot geometry
                if child.terminal is not None:
                    terminals[child.terminal] = child.slot_allocation()
            elif maker.isinstance(child, 'Terminal'):
                terminals[child] = child.get_allocation()
            elif maker.isinstance(child, 'Container'):
                terminals.update(child.get_visible_terminals())
            else:
                dbg('Unknown child type %s, skipping' % type(child))

        return(terminals)

    def describe_layout(self, count, parent, global_layout, child_order, save_cwd = False):
        """Describe our current layout"""
        layout = {}
        maker = Factory()
        mytype = maker.type(self)
        if not mytype:
            err('unable to determine own type. %s' % self)
            return({})

        layout['type'] = mytype
        layout['parent'] = parent
        layout['order'] = child_order

        # m34: a Window's position is meaningless on Wayland (clients
        # cannot place toplevels; get_position() returns junk), so it is
        # not saved there.  Size, maximised/fullscreen and layout are.
        can_pos = getattr(self, 'can_set_position', None)
        if hasattr(self, 'get_position') and \
                (can_pos is None or can_pos()):
            position = self.get_position()
            if hasattr(position, '__iter__'):
                position = ':'.join([str(x) for x in position])
            layout['position'] = position
        
        if hasattr(self, 'ismaximised'):
            layout['maximised'] = self.ismaximised
        
        if hasattr(self, 'isfullscreen'):
            layout['fullscreen'] = self.isfullscreen
        
        if hasattr(self, 'ratio'):
            layout['ratio'] = self.ratio

        if hasattr(self, 'get_size'):
            layout['size'] = self.get_size()

        # Only a user-forced window title is part of the layout; the dynamic
        # (focused-terminal) title would otherwise be re-applied with
        # force_title() on load and pin the window title forever.
        title = getattr(self, 'title', None)
        # CLI -T titles are forced but not persisted (persist=False).
        if title is not None and getattr(title, 'forced', False) \
                and getattr(title, 'persist', False) \
                and getattr(title, 'text', None):
            layout['title'] = title.text
            # Marker: upstream layouts carry the *dynamic* title under
            # 'title'; only marked titles are re-applied on load.
            layout['title_forced'] = True

        if mytype == 'Notebook':
            labels = []
            last_active_term = []
            for tabnum in range(0, self.get_n_pages()):
                page = self.get_nth_page(tabnum)
                label = self.get_tab_label(page)
                labels.append(label.get_custom_label())
                last_active_term.append(self.last_active_term[self.get_nth_page(tabnum)])
            layout['labels'] = labels
            layout['last_active_term'] = last_active_term
            layout['active_page'] = self.get_current_page()
        else:
            if hasattr(self, 'last_active_term') and self.last_active_term is not None:
                layout['last_active_term'] = self.last_active_term

        if mytype == 'Window':
            if self.uuid == self.terminator.last_active_window:
                layout['last_active_window'] = True
            else:
                layout['last_active_window'] = False

        name = 'child%d' % count
        count = count + 1

        global_layout[name] = layout

        child_order = 0
        for child in self.get_children():
            if hasattr(child, 'describe_layout'):
                count = child.describe_layout(count, name, global_layout, child_order, save_cwd)
            child_order = child_order + 1

        return(count)

    def create_layout(self, layout):
        """Apply settings for our layout"""
        raise NotImplementedError('create_layout')


# vim: set expandtab ts=4 sw=4:
