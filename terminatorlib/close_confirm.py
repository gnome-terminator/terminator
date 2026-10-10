# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""close_confirm.py - Process-aware close confirmation (D17)."""

from __future__ import print_function

import os

from .util import dbg, err, enumerate_descendants

SHELL_BASENAMES = {
    'bash', 'sh', 'zsh', 'fish', 'dash', 'ksh', 'csh', 'tcsh', 'login',
}

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

    Conservative: if pid is None or /proc unavailable → returns
    [(None, '<unknown>')].
    """
    if ignore is None:
        ignore = _ignore_set()
    shells = SHELL_BASENAMES
    skip = shells | set(ignore)

    pid = getattr(terminal, 'pid', None)
    if pid is None:
        return [(None, '<unknown>')]

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
            except psutil.Error:
                return [(None, '<unknown>')]
            # Root process itself
            try:
                bname = _basename_of(root.name())
                if bname and bname not in skip:
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
            return [(None, '<unknown>')]
        if bname not in skip:
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
    """Return (need_confirm: bool, procs: list[(pid, name)])."""
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
    if type(widget).__name__ == 'PanePlaceholder' or (
            hasattr(widget, 'terminal') and
            getattr(widget, 'is_placeholder', False)):
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
            if hasattr(child, 'terminal') and type(child).__name__ == 'PanePlaceholder':
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


def construct_confirm_close_with_processes(container, window, child):
    """Process-first confirmation used by Container.construct_confirm_close."""
    from gi.repository import Gtk
    from .factory import Factory

    maker = Factory()
    if maker.isinstance(child, 'Window'):
        terminals = scope_terminals(child)
    else:
        terminals = scope_terminals(child)

    need, procs = should_confirm_processes(terminals)
    if need:
        return show_process_close_dialog(window, terminals, procs)

    # Fall through: caller continues with ask_before_closing
    return None  # sentinel: no process dialog; use legacy path


def request_close_terminal(terminal):
    """Confirm (D17 / ask_before_closing) then close. Returns True if closed."""
    from gi.repository import Gtk

    container = terminal.get_parent()
    while container and not hasattr(container, 'construct_confirm_close'):
        container = container.get_parent()

    if container:
        confirm = container.construct_confirm_close(
            terminal.get_toplevel(), terminal)
        if confirm != Gtk.ResponseType.ACCEPT:
            dbg('request_close_terminal: user cancelled')
            return False

    terminal.close()
    return True
