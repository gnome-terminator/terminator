#!/usr/bin/python
#    Terminator.util - misc utility functions
#    Copyright (C) 2006-2008  cmsj@tenshu.net
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

# set this to true to enable debugging output
DEBUG = True

def dbg(log = ""):
    """Print a message if debugging is enabled"""
    if DEBUG:
        print >> sys.stderr, log

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

