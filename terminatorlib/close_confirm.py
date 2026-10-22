# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""close_confirm.py - Process-aware close confirmation (D17)."""

from __future__ import print_function

import os

from .util import dbg, err, enumerate_descendants

SHELL_BASENAMES = {
    'bash', 'sh', 'zsh', 'fish', 'dash', 'ksh', 'csh', 'tcsh', 'login',
    # Less common interactive shells (an idle prompt is not "running")
    'nu', 'xonsh', 'elvish', 'pwsh', 'ion', 'oil', 'osh', 'ysh', 'yash',
    'mksh', 'lksh', 'oksh', 'rc', 'es', 'murex', 'busybox', 'ash',
}

# Seconds of slack when comparing a process start time with the spawn time
# (detects a pid that was reused after our shell exited).
PID_REUSE_SLACK_S = 5.0

DEFAULT_CLOSE_CONFIRM_IGNORE = [
    'gitstatusd', 'ssh-agent', 'gpg-agent', 'dbus-daemon',
]


def _basename_of(cmdline_or_name):
    if not cmdline_or_name:
        return ''
    name = os.path.basename(cmdline_or_name)
    if name.startswith('-'):
        name = name[1:]
    return name


def _never_ask():
    try:
        from .config import Config
        return Config()['ask_before_closing'] == 'never'
    except Exception:
        return False


def _ignore_set():
    names = set(DEFAULT_CLOSE_CONFIRM_IGNORE)
    try:
        from .config import Config
        configured = Config()['close_confirm_ignore']
        if configured:
            for item in configured:
                names.add(_basename_of(str(item)))
    except Exception:
        pass
    return names


def _proc_basename(pid):
    """Return process basename via /proc, or None on failure."""
    try:
        with open('/proc/%d/comm' % pid, 'r', encoding='utf-8',
                  errors='replace') as fh:
            return _basename_of(fh.read().strip())
    except Exception:
        pass
    try:
        with open('/proc/%d/cmdline' % pid, 'rb') as fh:
            data = fh.read().split(b'\x00')
            if data and data[0]:
                return _basename_of(data[0].decode('utf-8', 'replace'))
    except Exception:
        pass
    return None


def _child_pids(pid):
    """Return direct child pids of pid using /proc."""
    children = []
    try:
        for entry in os.listdir('/proc'):
            if not entry.isdigit():
                continue
            try:
                with open('/proc/%s/stat' % entry, 'r', encoding='utf-8',
                          errors='replace') as fh:
                    stat = fh.read()
                # comm may contain spaces/parens; ppid is field 4 after comm
                rparen = stat.rfind(')')
                if rparen < 0:
                    continue
                fields = stat[rparen + 2:].split()
                # fields[0]=state, fields[1]=ppid
                if len(fields) >= 2 and int(fields[1]) == pid:
                    children.append(int(entry))
            except Exception:
                continue
    except Exception:
        pass
    return children


def _descendants(pid):
    result = []
    stack = list(_child_pids(pid))
    seen = set()
    while stack:
        child = stack.pop()
        if child in seen:
            continue
        seen.add(child)
        result.append(child)
        stack.extend(_child_pids(child))
    return result


def process_basename_for_pid(pid):
    """Public helper used by tests; prefers psutil when available."""
    try:
        import psutil
        proc = psutil.Process(pid)
        name = proc.name()
        return _basename_of(name)
    except Exception:
        return _proc_basename(pid)


def relevant_processes_for_terminal(terminal, ignore=None):
    """Return list of (pid, basename) that should trigger confirmation.

    No pid (child exited, spawn failed, or flatpak-spawn where VTE gives us
    no pid) or a process that is gone → [] (nothing we can name; prompting
    on every close would be noise).  A pid that was reused by an unrelated
    process after our child exited is ignored too.  Only an unexpected
    error while inspecting a live process is conservative:
    [(None, '<unknown>')].
    """
    if ignore is None:
        ignore = _ignore_set()
    shells = SHELL_BASENAMES
    skip = shells | set(ignore)

    pid = getattr(terminal, 'pid', None)
    if getattr(terminal, 'child_exited', False):
        return []
    if pid is None or not isinstance(pid, int) or pid <= 0:
        return []
    spawn_time = getattr(terminal, 'spawn_time', None)

    found = []
    try:
        # Prefer psutil when present
        try:
            import psutil
            use_psutil = True
        except ImportError:
            use_psutil = False

        if use_psutil:
            try:
                root = psutil.Process(pid)
            except psutil.NoSuchProcess:
                return []
            except psutil.Error:
                return [(None, '<unknown>')]
            if spawn_time:
                try:
                    if root.create_time() > spawn_time + PID_REUSE_SLACK_S:
                        dbg('close_confirm: pid %d was reused' % pid)
                        return []
                except psutil.Error:
                    pass
            # Root process itself
            try:
                bname = _basename_of(root.name())
                # The wrapper itself is not a job. Its children still count.
                if bname and bname not in skip and bname != 'flatpak-spawn':
                    found.append((pid, bname))
            except psutil.Error:
                pass
            try:
                for child in root.children(recursive=True):
                    try:
                        bname = _basename_of(child.name())
                        if bname and bname not in skip:
                            found.append((child.pid, bname))
                    except psutil.Error:
                        continue
            except psutil.Error:
                pass
            return found

        # /proc fallback
        bname = _proc_basename(pid)
        if bname is None:
            # Gone (or /proc unavailable): nothing to name
            return []
        if bname not in skip and bname != 'flatpak-spawn':
            found.append((pid, bname))
        for child_pid in _descendants(pid):
            cb = _proc_basename(child_pid)
            if cb and cb not in skip:
                found.append((child_pid, cb))
        return found
    except Exception as ex:
        dbg('relevant_processes_for_terminal: %s' % ex)
        return [(None, '<unknown>')]


def should_confirm_processes(terminals):
    """Return (need_confirm: bool, procs: list[(pid, name)]).

    ask_before_closing = never disables this dialog too.
    """
    if _never_ask():
        return False, []
    procs = []
    for term in terminals:
        procs.extend(relevant_processes_for_terminal(term))
    # Deduplicate by pid (None counts as needing confirm)
    seen = set()
    uniq = []
    for pid, name in procs:
        key = (pid, name)
        if key in seen:
            continue
        seen.add(key)
        uniq.append((pid, name))
    need = bool(uniq)
    return need, uniq


def _terminals_under(widget):
    """Collect Terminal widgets under widget; PanePlaceholder → .terminal."""
    terms = []
    if widget is None:
        return terms
    # Placeholder delegation
    if getattr(widget, 'is_pane_placeholder', False) or \
            type(widget).__name__ == 'PanePlaceholder':
        t = getattr(widget, 'terminal', None)
        if t is not None:
            return [t]
    try:
        from .factory import Factory
        maker = Factory()
        if maker.isinstance(widget, 'Terminal'):
            return [widget]
    except Exception:
        pass
    try:
        _containers, terminals = enumerate_descendants(widget)
        terms.extend(terminals)
    except Exception as ex:
        dbg('_terminals_under: %s' % ex)
    # Also walk children looking for placeholders
    try:
        for child in widget.get_children():
            if child is None:
                continue
            if getattr(child, 'is_pane_placeholder', False):
                t = child.terminal
                if t is not None and t not in terms:
                    terms.append(t)
            else:
                for t in _terminals_under(child):
                    if t not in terms:
                        terms.append(t)
    except Exception:
        pass
    return terms


def scope_terminals(root_widget):
    """Terminals affected by closing root_widget (incl. legacy zoom tree)."""
    from .factory import Factory
    from .terminator import Terminator

    maker = Factory()
    if maker.isinstance(root_widget, 'Terminal'):
        return [root_widget]

    if maker.isinstance(root_widget, 'Window') or hasattr(root_widget, 'is_zoomed'):
        window = root_widget.get_toplevel()
        terms = [t for t in Terminator().terminals
                 if t.get_toplevel() is window]
        if hasattr(window, 'is_zoomed') and window.is_zoomed():
            zoom_data = getattr(window, 'zoom_data', None) or {}
            old = zoom_data.get('old_child')
            if old is not None:
                for t in _terminals_under(old):
                    if t not in terms:
                        terms.append(t)
        return terms

    return _terminals_under(root_widget)


def window_has_multiple_terminals(window):
    return len(scope_terminals(window)) > 1


def show_process_close_dialog(parent_window, terminals, procs):
    """Single MessageDialog; Cancel is default. No 'don't ask again'."""
    from gi.repository import Gtk
    from .translation import _

    names = []
    for pid, name in procs:
        if pid is None:
            names.append(name)
        else:
            names.append('%s (%s)' % (name, pid))
    # Cap list length for readability
    shown = names[:8]
    extra = len(names) - len(shown)
    proc_text = ', '.join(shown)
    if extra > 0:
        proc_text += _(' … and %d more') % extra

    nterms = len(terminals)
    if nterms > 1:
        primary = _('Close terminals with running processes?')
    else:
        primary = _('Close terminal with running processes?')
    secondary = _('The following process(es) are still running:\n%s\n\n'
                  'Closing will terminate them.') % proc_text

    dialog = Gtk.MessageDialog(
        transient_for=parent_window,
        modal=True,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.NONE,
        text=primary)
    dialog.format_secondary_text(secondary)
    dialog.add_button(_('_Cancel'), Gtk.ResponseType.CANCEL)
    dialog.add_button(_('_Close'), Gtk.ResponseType.ACCEPT)
    dialog.set_default_response(Gtk.ResponseType.CANCEL)
    try:
        dialog.set_focus(dialog.get_widget_for_response(Gtk.ResponseType.CANCEL))
    except Exception:
        pass
    response = dialog.run()
    dialog.destroy()
    return response


def show_process_close_popover(anchor_widget, terminals, procs):
    """Single Popover anchored to anchor_widget; Cancel is default."""
    from gi.repository import Gtk, GLib
    from .translation import _

    names = []
    for pid, name in procs:
        if pid is None:
            names.append(name)
        else:
            names.append('%s (%s)' % (name, pid))
    shown = names[:8]
    extra = len(names) - len(shown)
    proc_text = ', '.join(shown)
    if extra > 0:
        proc_text += _(' … and %d more') % extra

    nterms = len(terminals)
    if nterms > 1:
        primary = _('Close terminals with running processes?')
    else:
        primary = _('Close terminal with running processes?')
    secondary = _('The following process(es) are still running:\n%s\n\n'
                  'Closing will terminate them.') % proc_text

    try:
        if hasattr(anchor_widget, 'get_realized') and not anchor_widget.get_realized():
            toplevel = anchor_widget.get_toplevel()
            if toplevel and hasattr(toplevel, 'realize'):
                toplevel.realize()
            anchor_widget.realize()
    except Exception:
        pass

    popover = Gtk.Popover.new(anchor_widget)
    popover.set_modal(True)

    pos = Gtk.PositionType.BOTTOM
    try:
        w = anchor_widget
        while w is not None:
            if hasattr(w, 'get_style_context') and \
                    'terminator-tab-sidebar' in w.get_style_context().list_classes():
                pos = Gtk.PositionType.RIGHT
                break
            w = w.get_parent()
    except Exception:
        pass
    popover.set_position(pos)

    box = Gtk.Box.new(Gtk.Orientation.VERTICAL, 8)
    box.set_border_width(12)

    primary_label = Gtk.Label()
    try:
        primary_label.set_markup('<b>%s</b>' % GLib.markup_escape_text(primary))
    except Exception:
        primary_label.set_text(primary)
    primary_label.set_halign(Gtk.Align.START)
    primary_label.set_line_wrap(True)
    primary_label.set_max_width_chars(32)
    box.pack_start(primary_label, False, False, 0)

    secondary_label = Gtk.Label(label=secondary)
    secondary_label.set_halign(Gtk.Align.START)
    secondary_label.set_line_wrap(True)
    secondary_label.set_max_width_chars(36)
    box.pack_start(secondary_label, False, False, 0)

    bbox = Gtk.Box.new(Gtk.Orientation.HORIZONTAL, 8)
    bbox.set_halign(Gtk.Align.END)
    bbox.set_margin_top(4)

    btn_cancel = Gtk.Button.new_with_mnemonic(_('_Cancel'))
    btn_close = Gtk.Button.new_with_mnemonic(_('_Close'))
    try:
        btn_close.get_style_context().add_class('destructive-action')
    except Exception:
        pass

    bbox.pack_start(btn_cancel, False, False, 0)
    bbox.pack_start(btn_close, False, False, 0)
    box.pack_start(bbox, False, False, 0)

    box.show_all()
    popover.add(box)

    loop = GLib.MainLoop()
    response = [Gtk.ResponseType.CANCEL]

    def _on_close_clicked(_button):
        response[0] = Gtk.ResponseType.ACCEPT
        popover.popdown()

    def _on_cancel_clicked(_button):
        response[0] = Gtk.ResponseType.CANCEL
        popover.popdown()

    def _on_closed(_pop):
        if loop.is_running():
            loop.quit()

    def _on_anchor_destroy(_widget):
        popover.popdown()
        if loop.is_running():
            loop.quit()

    btn_close.connect('clicked', _on_close_clicked)
    btn_cancel.connect('clicked', _on_cancel_clicked)
    popover.connect('closed', _on_closed)
    popover.connect('destroy', _on_closed)
    popover._btn_close = btn_close
    popover._btn_cancel = btn_cancel
    try:
        anchor_widget._close_confirm_popover = popover
    except Exception:
        pass
    h_anchor = None
    try:
        h_anchor = anchor_widget.connect('destroy', _on_anchor_destroy)
    except Exception:
        pass

    popover.popup()
    btn_cancel.grab_focus()

    try:
        loop.run()
    finally:
        try:
            if getattr(anchor_widget, '_close_confirm_popover', None) is popover:
                del anchor_widget._close_confirm_popover
        except Exception:
            pass
        if h_anchor is not None:
            try:
                if anchor_widget.handler_is_connected(h_anchor):
                    anchor_widget.disconnect(h_anchor)
            except Exception:
                pass
        try:
            popover.destroy()
        except Exception:
            pass

    return response[0]


def show_shell_close_dialog(parent_window, terminals):
    """ask_before_closing=always, and nothing to name: ask once for the group."""
    from gi.repository import Gtk
    from .translation import _
    nterms = len(terminals)
    if nterms > 1:
        primary = _('Close multiple terminals?')
        secondary = _('Do you really wish to close these terminals?')
    else:
        primary = _('Close terminal?')
        secondary = _('Do you really wish to close this terminal?')
    dialog = Gtk.MessageDialog(
        transient_for=parent_window,
        modal=True,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.NONE,
        text=primary)
    dialog.format_secondary_text(secondary)
    dialog.add_button(_('_Cancel'), Gtk.ResponseType.CANCEL)
    dialog.add_button(_('_Close'), Gtk.ResponseType.ACCEPT)
    dialog.set_default_response(Gtk.ResponseType.CANCEL)
    try:
        dialog.set_focus(dialog.get_widget_for_response(
            Gtk.ResponseType.CANCEL))
    except Exception:
        pass
    response = dialog.run()
    dialog.destroy()
    return response


def no_process_close_result(ask_mode):
    """How to close when nothing but shells (and ignored helpers) is running.

    ``'accept'`` closes with no dialog. ``'legacy'`` is only for
    ``ask_before_closing = always``, which still uses the old prompt.
    """
    if ask_mode == 'always':
        return 'legacy'
    return 'accept'


def _ask_before_closing():
    try:
        from .config import Config
        return Config()['ask_before_closing']
    except Exception:
        return 'multiple_terminals'


def construct_confirm_close_with_processes(container, window, child, anchor_widget=None):
    """Decide the close dialog by which processes are still running.

    A program other than the shell asks, and names that program.
    Several idle shells do not. ``ask_before_closing = always`` still
    asks when every terminal is only a shell. ``never`` asks for neither.
    """
    from gi.repository import Gtk
    from .factory import Factory

    maker = Factory()
    if maker.isinstance(child, 'Window'):
        terminals = scope_terminals(child)
    else:
        terminals = scope_terminals(child)

    need, procs = should_confirm_processes(terminals)
    if need:
        if anchor_widget is not None:
            try:
                return show_process_close_popover(anchor_widget, terminals, procs)
            except Exception as ex:
                dbg('show_process_close_popover failed: %s; falling back to dialog' % ex)
        return show_process_close_dialog(window, terminals, procs)

    if no_process_close_result(_ask_before_closing()) == 'accept':
        return Gtk.ResponseType.ACCEPT
    return None


def request_close_terminal(terminal, anchor_widget=None):
    """Confirm (D17 / ask_before_closing) then close. Returns True if closed."""
    from gi.repository import Gtk
    from .util import logical_parent

    if anchor_widget is None:
        titlebar = getattr(terminal, 'titlebar', None)
        btn_close = getattr(titlebar, 'btn_close', None)
        if btn_close is not None and getattr(btn_close, 'get_visible', lambda: False)():
            anchor_widget = btn_close
        elif isinstance(terminal, Gtk.Widget) and getattr(terminal, 'get_visible', lambda: False)():
            anchor_widget = terminal

    # logical_parent skips Overlay / PaneFrame so an overlay-maximised
    # terminal resolves to its Paned/Notebook slot (not the Window).
    container = logical_parent(terminal)
    while container and not hasattr(container, 'construct_confirm_close'):
        container = logical_parent(container)

    if container:
        try:
            confirm = container.construct_confirm_close(
                terminal.get_toplevel(), terminal, anchor_widget=anchor_widget)
        except TypeError:
            confirm = container.construct_confirm_close(
                terminal.get_toplevel(), terminal)
        if confirm != Gtk.ResponseType.ACCEPT:
            dbg('request_close_terminal: user cancelled')
            return False

    terminal.close()
    return True


def confirm_close_terminals(terminals, parent_window=None):
    """Bulk-close gate (e.g. 'Close group'): one aggregated process dialog.

    Returns True when closing may proceed.
    """
    from gi.repository import Gtk
    terminals = [t for t in terminals if t is not None]
    if not terminals:
        return True
    need, procs = should_confirm_processes(terminals)
    if parent_window is None:
        try:
            parent_window = terminals[0].get_toplevel()
        except Exception:
            parent_window = None
    if need:
        return show_process_close_dialog(
            parent_window, terminals, procs) == Gtk.ResponseType.ACCEPT
    if no_process_close_result(_ask_before_closing()) == 'accept':
        return True
    return show_shell_close_dialog(
        parent_window, terminals) == Gtk.ResponseType.ACCEPT
