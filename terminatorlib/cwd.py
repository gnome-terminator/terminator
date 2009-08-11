#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""cwd.py - function necessary to get the cwd for a given pid on various OSes"""

import platform
import os
from util import dbg

def get_pidcwd():
    """Determine an appropriate cwd function for the OS we are running on"""

    func = lambda pid: None
    system = platform.system()

    if system == 'Linux':
        dbg('Using Linux get_pid_cwd')
        func = lambda pid: os.path.realpath('/proc/%s/cwd' % pid)
    elif system == 'FreeBSD':
        try:
            import freebsd
            func = freebsd.get_process_cwd
            dbg('Using FreeBSD get_pid_cwd')
        except (OSError, NotImplementedError, ImportError):
            dbg('FreeBSD version too old for get_pid_cwd')
    elif system == 'SunOS':
        dbg('Using SunOS get_pid_cwd')
        func = lambda pid: os.path.realpath('/proc/%s/path/cwd' % pid)
    else:
        dbg('Unable to determine a get_pid_cwd for OS: %s' % system)

    return(func)

# vim: set expandtab ts=4 sw=4:
