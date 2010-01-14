#!/usr/bin/python
#    Terminator.util - misc utility functions
#    Copyright (C) 2006-2010  cmsj@tenshu.net
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

import sys
import gtk
import os
import pwd
import inspect

# set this to true to enable debugging output
DEBUG = False
# set this to true to additionally list filenames in debugging
DEBUGFILES = False

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
        print >> sys.stderr, "%s::%s: %s%s" % (classname, method, log, extra)

def err(log = ""):
    """Print an error message"""
    print >> sys.stderr, log

def gerr(message = None):
    """Display a graphical error. This should only be used for serious
    errors as it will halt execution"""

    dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL,
            gtk.MESSAGE_ERROR, gtk.BUTTONS_OK, message)
    dialog.run()

def has_ancestor(widget, wtype):
    """Walk up the family tree of widget to see if any ancestors are of type"""
    while widget:
        widget = widget.get_parent()
        if isinstance(widget, wtype):
            return(True)
    return(False)

def get_top_window(widget):
    """Return the Window instance a widget belongs to"""
    parent = widget.get_parent()
    while parent:
        widget = parent
        parent = widget.get_parent()
    return(widget)

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

    dbg('path_lookup: Using %d paths: %s', (len(paths), paths))

    for path in paths:
        target = os.path.join(path, command)
        if os.path.isfile(target):
            dbg('path_lookup: found %s' % target)
            return(target)

    dbg('path_lookup: Unable to locate %s' % command)

def shell_lookup():
    """Find an appropriate shell for the user"""
    shells = [os.getenv('SHELL'), pwd.getpwuid(os.getuid())[6], 'bash',
            'zsh', 'tcsh', 'ksh', 'csh', 'sh']

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
    pixmap = widget.get_snapshot()
    (width, height) = pixmap.get_size()
    pixbuf = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False, 8, width, height)
    pixbuf.get_from_drawable(pixmap, pixmap.get_colormap(), 0, 0, 0, 0, width,
            height)

    longest = max(width, height)

    if maxsize is not None:
        factor = float(maxsize) / float(longest)

    if not maxsize or (width * factor) > width or (height * factor) > height:
        factor = 1

    scaledpixbuf = pixbuf.scale_simple(int(width * factor), int(height * factor), gtk.gdk.INTERP_BILINEAR)

    return(scaledpixbuf)

def get_config_dir():
    """Expand all the messy nonsense for finding where ~/.config/terminator
    really is"""
    try:
        configdir = os.environ['XDG_CONFIG_HOME']
    except KeyError:
        configdir = os.path.join(os.path.expanduser('~'), '.config')

    return(os.path.join(configdir, 'terminator'))

def dict_diff(reference, working):
    """Examine the values in the supplied working set and return a new dict
    that only contains those values which are different from those in the
    reference dictionary"""

    result = {}

    for key in reference:
        if reference[key] != working[key]:
            result[key] = working[key]

    return(result)
