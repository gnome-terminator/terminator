# Terminator.util - misc utility functions
# Copyright (C) 2006-2010  cmsj@tenshu.net
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, version 2 only.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
"""Terminator.util - misc utility functions"""

from __future__ import print_function

import sys
import cairo
import os
import pwd
import inspect
import uuid
import subprocess
import gi


try:
    gi.require_version('Gtk','3.0')
    from gi.repository import Gtk, Gdk
except ImportError:
    print('You need Gtk 3.0+ to run Remotinator.')
    sys.exit(1)

# set this to true to enable debugging output
DEBUG = False
# set this to true to additionally list filenames in debugging
DEBUGFILES = False
# list of classes to show debugging for. empty list means show all classes
DEBUGCLASSES = []
# list of methods to show debugging for. empty list means show all methods
DEBUGMETHODS = []

def is_flatpak():
    return os.path.exists("/.flatpak-info")

def dbg(log = ""):
    """Print a message if debugging is enabled"""
    if DEBUG:
        stackitem = inspect.stack()[1]
        parent_frame = stackitem[0]
        method = parent_frame.f_code.co_name
        names, varargs, keywords, local_vars = inspect.getargvalues(parent_frame)
        try:
            self_name = names[0]
            classname = local_vars[self_name].__class__.__name__
        except IndexError:
            classname = "noclass"
        if DEBUGFILES:
            line = stackitem[2]
            filename = parent_frame.f_code.co_filename
            extra = " (%s:%s)" % (filename, line)
        else:
            extra = ""
        if DEBUGCLASSES != [] and classname not in DEBUGCLASSES:
            return
        if DEBUGMETHODS != [] and method not in DEBUGMETHODS:
            return
        try:
            print("%s::%s: %s%s" % (classname, method, log, extra), file=sys.stderr)
        except IOError:
            pass

def err(log = ""):
    """Print an error message"""
    try:
        print(log, file=sys.stderr)
    except IOError:
        pass

def gerr(message = None):
    """Display a graphical error. This should only be used for serious
    errors as it will halt execution"""

    dialog = Gtk.MessageDialog(None, Gtk.DialogFlags.MODAL,
            Gtk.MessageType.ERROR, Gtk.ButtonsType.OK, message)
    dialog.run()
    dialog.destroy()

def has_ancestor(widget, wtype):
    """Walk up the family tree of widget to see if any ancestors are of type"""
    while widget:
        widget = widget.get_parent()
        if isinstance(widget, wtype):
            return(True)
    return(False)

def manual_lookup():
    '''Choose the manual to open based on LANGUAGE'''
    available_languages = ['en']
    base_url = 'http://gnome-terminator.readthedocs.io/%s/latest/'
    target = 'en'   # default to English
    if 'LANGUAGE' in os.environ:
        languages = os.environ['LANGUAGE'].split(':')
        for language in languages:
            if language in available_languages:
                target = language
                break
    elif 'LANG' in os.environ:
        language = os.environ['LANG'].split('.')[0]
        for i in range(len(available_languages)):
            if language == available_languages[i]:
                target = language
                break
    return base_url % target

def path_lookup(command):
    '''Find a command in our path'''
    if os.path.isabs(command):
        if os.path.isfile(command):
            return(command)
        else:
            return(None)
    elif command[:2] == './' and os.path.isfile(command):
        dbg('path_lookup: Relative filename %s found in cwd' % command)
        return(command)

    try:
        paths = os.environ['PATH'].split(':')
        if len(paths[0]) == 0: 
            raise(ValueError)
    except (ValueError, NameError):
        dbg('path_lookup: PATH not set in environment, using fallbacks')
        paths = ['/usr/local/bin', '/usr/bin', '/bin']

    dbg('path_lookup: Using %d paths: %s' % (len(paths), paths))

    for path in paths:
        target = os.path.join(path, command)
        if os.path.isfile(target):
            dbg('path_lookup: found %s' % target)
            return(target)

    dbg('path_lookup: Unable to locate %s' % command)

def shell_lookup():
    """Find an appropriate shell for the user"""
    if is_flatpak():
        getent = subprocess.check_output([
            'flatpak-spawn', '--host', 'getent', 'passwd',
            pwd.getpwuid(os.getuid())[0]
        ]).decode(encoding='UTF-8').rstrip('\n')
        shell = getent.split(':')[6]
        return shell
    try:
        usershell = pwd.getpwuid(os.getuid())[6]
    except KeyError:
        usershell = None
    shells = [usershell, 'bash', 'zsh', 'tcsh', 'ksh', 'csh', 'sh']

    for shell in shells:
        if shell is None:
            continue
        elif os.path.isfile(shell):
            return(shell)
        else:
            rshell = path_lookup(shell)
            if rshell is not None:
                dbg('shell_lookup: Found %s at %s' % (shell, rshell))
                return(rshell)
    dbg('shell_lookup: Unable to locate a shell')

def widget_pixbuf(widget, maxsize=None):
    """Generate a pixbuf of a widget"""
    # FIXME: Can this be changed from using "import cairo" to "from gi.repository import cairo"?
    window = widget.get_window()
    width, height = window.get_width(), window.get_height()

    longest = max(width, height)

    if maxsize is not None:
        factor = float(maxsize) / float(longest)

    if not maxsize or (width * factor) > width or (height * factor) > height:
        factor = 1

    preview_width, preview_height = int(width * factor), int(height * factor)

    preview_surface = Gdk.Window.create_similar_surface(window,
        cairo.CONTENT_COLOR, preview_width, preview_height)

    cairo_context = cairo.Context(preview_surface)
    cairo_context.scale(factor, factor)
    Gdk.cairo_set_source_window(cairo_context, window, 0, 0)
    cairo_context.paint()

    scaledpixbuf = Gdk.pixbuf_get_from_surface(preview_surface, 0, 0, preview_width, preview_height)
    
    return(scaledpixbuf)

def get_system_config_dir():
    system_config_dir = '/etc/xdg'
    if 'XDG_CONFIG_DIRS' in os.environ.keys():
        for sysconfdir in os.environ['XDG_CONFIG_DIRS'].split(":"):
                if os.path.isdir(sysconfdir):
                    system_config_dir = sysconfdir
                    break
    return(os.path.join(system_config_dir,'terminator'))

def get_config_dir():
    """Expand all the messy nonsense for finding where ~/.config/terminator
    really is"""
    try:
        configdir = os.environ['XDG_CONFIG_HOME']
    except KeyError:
        configdir = os.path.join(os.path.expanduser('~'), '.config')

    dbg('Found config dir: %s' % configdir)
    return(os.path.join(configdir, 'terminator'))

def get_state_dir():
    """Return XDG state dir for terminator (~/.local/state/terminator)."""
    try:
        statedir = os.environ['XDG_STATE_HOME']
    except KeyError:
        statedir = os.path.join(os.path.expanduser('~'), '.local', 'state')
    dbg('Found state dir: %s' % statedir)
    return os.path.join(statedir, 'terminator')

def get_cache_dir():
    """Return XDG cache dir for terminator (~/.cache/terminator)."""
    try:
        cachedir = os.environ['XDG_CACHE_HOME']
    except KeyError:
        cachedir = os.path.join(os.path.expanduser('~'), '.cache')
    dbg('Found cache dir: %s' % cachedir)
    return os.path.join(cachedir, 'terminator')

def dict_diff(reference, working):
    """Examine the values in the supplied working set and return a new dict
    that only contains those values which are different from those in the
    reference dictionary
    
    >>> a = {'foo': 'bar', 'baz': 'bjonk'}
    >>> b = {'foo': 'far', 'baz': 'bjonk'}
    >>> dict_diff(a, b)
    {'foo': 'far'}
    """

    result = {}

    for key in reference:
        if reference[key] != working[key]:
            result[key] = working[key]

    return(result)

# Helper functions for directional navigation
def get_edge(allocation, direction):
    """Return the edge of the supplied allocation that we will care about for
    directional navigation"""
    if direction == 'left':
        edge = allocation.x
        p1, p2 = allocation.y, allocation.y + allocation.height
    elif direction == 'up':
        edge = allocation.y
        p1, p2 = allocation.x, allocation.x + allocation.width
    elif direction == 'right':
        edge = allocation.x + allocation.width
        p1, p2 = allocation.y, allocation.y + allocation.height
    elif direction == 'down':
        edge = allocation.y + allocation.height
        p1, p2 = allocation.x, allocation.x + allocation.width
    else:
        raise ValueError('unknown direction %s' % direction)
    
    return(edge, p1, p2)

def get_nav_possible(edge, allocation, direction, p1, p2):
    """Check if the supplied allocation is in the right direction of the
    supplied edge"""
    x1, x2 = allocation.x, allocation.x + allocation.width
    y1, y2 = allocation.y, allocation.y + allocation.height
    if direction == 'left':
        return(x2 <= edge and y1 <= p2 and y2 >= p1)
    elif direction == 'right':
        return(x1 >= edge and y1 <= p2 and y2 >= p1)
    elif direction == 'up':
        return(y2 <= edge and x1 <= p2 and x2 >= p1)
    elif direction == 'down':
        return(y1 >= edge and x1 <= p2 and x2 >= p1)
    else:
        raise ValueError('Unknown direction: %s' % direction)

def get_nav_offset(edge, allocation, direction):
    """Work out how far edge is from a particular point on the allocation
    rectangle, in the given direction"""
    if direction == 'left':
        return(edge - (allocation.x + allocation.width))
    elif direction == 'right':
        return(allocation.x - edge)
    elif direction == 'up':
        return(edge - (allocation.y + allocation.height))
    elif direction == 'down':
        return(allocation.y - edge)
    else:
        raise ValueError('Unknown direction: %s' % direction)

def get_nav_tiebreak(direction, cursor_x, cursor_y, rect):
    """We have multiple candidate terminals. Pick the closest by cursor
    position"""
    if direction in ['left', 'right']:
        return(cursor_y >= rect.y and cursor_y <= (rect.y + rect.height))
    elif direction in ['up', 'down']:
        return(cursor_x >= rect.x and cursor_x <= (rect.x + rect.width))
    else:
        raise ValueError('Unknown direction: %s' % direction)

def is_pane_placeholder(widget):
    """True for module D's slot stand-in (duck-typed, not Factory-registered)"""
    return bool(getattr(widget, 'is_pane_placeholder', False))

def logical_parent(widget):
    """Parent as the layout sees it, skipping module D's transient chrome.

    - Gtk.Overlay / PaneFrame (is_pane_frame) are skipped, so callers see
      Window / Paned / Notebook.
    - For the overlay-maximised terminal itself, the answer is the container
      holding its PanePlaceholder (its logical slot).
    """
    if widget is None:
        return None
    placeholder = getattr(widget, '_overlay_placeholder', None)
    if placeholder is not None and placeholder.get_parent() is not None:
        widget = placeholder
    parent = widget.get_parent()
    while parent is not None and (
            isinstance(parent, Gtk.Overlay) or
            getattr(parent, 'is_pane_frame', False)):
        parent = parent.get_parent()
    return parent

def enumerate_descendants(parent):
    """Walk all our children and build up a list of containers and
    terminals"""
    # FIXME: Does having to import this here mean we should move this function
    # back to Container?
    from .factory import Factory

    containerstmp = []
    containers = []
    terminals = []
    maker = Factory()

    if parent is None:
        err('no parent widget specified')
        return

    def _placeholder_term(widget):
        # Module D: the slot delegates to its floating terminal (sole source;
        # Window.get_terminals must not add the overlay terminal again)
        term = widget.terminal
        if term is not None and term not in terminals:
            terminals.append(term)

    for descendant in parent.get_children():
        if is_pane_placeholder(descendant):
            _placeholder_term(descendant)
        elif maker.isinstance(descendant, 'Container'):
            containerstmp.append(descendant)
        elif maker.isinstance(descendant, 'Terminal'):
            terminals.append(descendant)

        while len(containerstmp) > 0:
            child = containerstmp.pop(0)
            for descendant in child.get_children():
                if is_pane_placeholder(descendant):
                    _placeholder_term(descendant)
                elif maker.isinstance(descendant, 'Container'):
                    containerstmp.append(descendant)
                elif maker.isinstance(descendant, 'Terminal'):
                    terminals.append(descendant)
            containers.append(child)

    dbg('%d containers and %d terminals fall beneath %s' % (len(containers), 
        len(terminals), parent))
    return(containers, terminals)

def make_uuid(str_uuid=None):
    """Generate a UUID for an object.

    str_uuid=None -> fresh uuid4 (normal case).
    A non-empty string is parsed (ValueError propagates for garbage, as
    before).  An empty / whitespace-only string is a damaged layout value
    (m26): it used to fall through silently to a random uuid; now the same
    fresh uuid is returned but a warning is logged so it is visible."""
    if str_uuid is None:
        return uuid.uuid4()
    if isinstance(str_uuid, uuid.UUID):
        return str_uuid
    if not str(str_uuid).strip():
        err('make_uuid: empty uuid string %r, generating a new one'
            % (str_uuid,))
        return uuid.uuid4()
    return uuid.UUID(str(str_uuid).strip())

def inject_uuid(target):
    """Inject a UUID into an existing object"""
    uuid = make_uuid()
    if not hasattr(target, "uuid") or target.uuid == None:
        dbg("Injecting UUID %s into: %s" % (uuid, target))
        target.uuid = uuid
    else:
        dbg("Object already has a UUID: %s" % target)

def spawn_new_terminator(cwd, args):
    """Start a new terminator instance with the given arguments"""
    cmd = sys.argv[0]

    if not os.path.isabs(cmd):
        # Command is not an absolute path. Figure out where we are
        cmd = os.path.join (cwd, sys.argv[0])
        if not os.path.isfile(cmd):
            # we weren't started as ./terminator in a path. Give up
            err('Unable to locate Terminator')
            return False
      
    dbg("Spawning: %s" % cmd)
    subprocess.Popen([cmd]+args)

def _gdk_backend_name(display):
    """'X11' / 'WAYLAND' / 'OTHER' from a GdkDisplay's GType name
    (GdkX11Display / GdkWaylandDisplay; PyGObject wraps backend subclasses
    under their own GType even without the backend typelib), or None when
    it cannot be told."""
    if display is None:
        return None
    name = ''
    try:
        name = display.__gtype__.name or ''
    except Exception:
        name = ''
    if not name or name == 'GdkDisplay':
        name = type(display).__name__
    lname = name.lower()
    if 'wayland' in lname:
        return 'WAYLAND'
    if 'x11' in lname:
        return 'X11'
    if lname in ('display', 'gdkdisplay', ''):
        return None
    return 'OTHER'  # broadway, ...


def display_manager(display=None):
    """Which GDK backend we run under: 'X11', 'WAYLAND' or 'OTHER'.

    m34: decided by the GdkDisplay actually opened, not by the environment:
    GDK_BACKEND=x11 inside a Wayland session (XWayland) has WAYLAND_DISPLAY
    set but every X11 API works, while GDK_BACKEND=wayland may run without
    WAYLAND_DISPLAY (libwayland defaults to wayland-0).  Falls back to the
    environment only when no display is open yet (unit tests, early
    import)."""
    if display is None:
        try:
            from gi.repository import Gdk
            display = Gdk.Display.get_default()
        except Exception:
            display = None
    backend = _gdk_backend_name(display)
    if backend is not None:
        return backend
    gdk_backend = (os.environ.get('GDK_BACKEND') or '').split(',')[0].strip()
    if gdk_backend == 'x11':
        return 'X11'
    if gdk_backend == 'wayland' or os.environ.get('WAYLAND_DISPLAY'):
        return 'WAYLAND'
    # Fallback assumption of X11
    return 'X11'


def is_x11(display=None):
    """True when X11-only APIs (positions, xid, Keybinder, X properties,
    server time) are usable."""
    return display_manager(display) == 'X11'


def window_scale_factor(widget):
    """Integer GDK scale factor (GDK_SCALE / monitor scale) of a widget,
    >= 1.  Safe on unrealized widgets and mocks."""
    try:
        f = int(widget.get_scale_factor())
        return f if f >= 1 else 1
    except Exception:
        return 1


# Reference font height in px (10pt at 96 dpi) the fixed-px UI thresholds
# were tuned for.
_REF_FONT_PX = 10.0 * 96.0 / 72.0


def text_scale(widget):
    """How much bigger the UI text is than the 10pt/96dpi reference the
    pixel thresholds were tuned with (GDK_DPI_SCALE, Xft.dpi, a large
    desktop font).  Never below 1.0 (thresholds only grow) and capped at
    4.0.  GDK_SCALE does not count: logical px already include it."""
    try:
        from gi.repository import Pango
        ctx = widget.get_pango_context()
        desc = ctx.get_font_description()
        size = float(desc.get_size()) / Pango.SCALE
        if size <= 0:
            return 1.0
        if desc.get_size_is_absolute():
            px = size
        else:
            res = -1.0
            try:
                screen = widget.get_screen()
                if screen is not None:
                    res = float(screen.get_resolution())
            except Exception:
                res = -1.0
            if res <= 0:
                res = 96.0
            px = size * res / 72.0
        return max(1.0, min(4.0, px / _REF_FONT_PX))
    except Exception:
        return 1.0

def update_config_to_cell_height(filename):
    '''Replace ‘line_height’ with ‘cell_height’ in Terminator
    config file (usually ~/.config/terminator/config on
    Unix-like systems).'''

    dbg('update_config_to_cell_height() config filename %s' % filename)

    try:
        with open(filename, 'r+') as file:
            config_text = file.read()

            if not 'line_height' in config_text:
                #
                # It is either a new config, or it is already using the
                # new ‘cell_height’ property instead the old ‘line_height’.
                #
                dbg('No ‘line_height’ found in ‘%s’.' % filename)
                file.close()
                return

            updated_config_text = config_text.replace('line_height', 'cell_height')

            file.seek(0)
            file.write(updated_config_text)
            file.truncate()
            file.close()

            dbg('Updted ‘line_height’ to ‘cell_height’.')

    except Exception as ex:
        err('Unable to open ‘%s’ for reading and/or writing.\n(%s)'
                % (filename, ex))

def get_flatpak_args(args, envv, cwd):
    """Construct args to be executed via flatpak-spawn"""
    flatpak_args = None
    env_args = ['--env={}'.format(env) for env in envv]
    flatpak_spawn = [
        "flatpak-spawn", "--host", "--watch-bus", "--forward-fd=1",
        "--forward-fd=2", "--directory={}".format(cwd)
    ]
    # Detect and remove duplicate shell in args
    # to work around vte.spawn_sync() requirement.
    if len(set([args[0], args[1]])) == 1:
        del args[0]

    flatpak_args = flatpak_spawn + env_args + args

    dbg('returned flatpak args:  %s' % flatpak_args)

    return flatpak_args


_SOURCE_ICON_PATH_ADDED = False

def add_source_icon_path(icon_theme=None):
    """When running from a source checkout, let the icon theme find
    data/icons (app icon and titlebar receive/broadcast icons).
    Idempotent; no-op for installed copies."""
    global _SOURCE_ICON_PATH_ADDED
    if _SOURCE_ICON_PATH_ADDED:
        return False
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'data', 'icons')
    if not os.path.isdir(path):
        return False
    try:
        theme = icon_theme or Gtk.IconTheme.get_default()
        if theme is None:
            return False
        if path not in theme.get_search_path():
            theme.append_search_path(path)
        _SOURCE_ICON_PATH_ADDED = True
        return True
    except Exception as ex:
        dbg('add_source_icon_path: %s' % ex)
        return False
