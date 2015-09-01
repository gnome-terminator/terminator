#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""cwd.py - function necessary to get the cwd for a given pid on various OSes

>>> cwd = get_default_cwd()
>>> cwd.__class__.__name__
'str'
>>> func = get_pid_cwd()
>>> func.__class__.__name__
'function'

"""

import platform
import os
import pwd
from util import dbg, err

try:
    import psutil
    psutil_avail = True
except (ImportError):
    dbg('psutil not found')
    psutil_avail = False

def get_default_cwd():
    """Determine a reasonable default cwd"""
    cwd = os.getcwd()
    if not os.path.exists(cwd) or not os.path.isdir(cwd):
        try:
            cwd = pwd.getpwuid(os.getuid())[5]
        except KeyError:
            cwd = '/'
    
    return(cwd)

def get_pid_cwd():
    """Determine an appropriate cwd function for the OS we are running on"""

    func = lambda pid: None
    system = platform.system()

    if system == 'Linux':
        dbg('Using Linux get_pid_cwd')
        func = linux_get_pid_cwd
    elif system == 'FreeBSD':
        try:
            import freebsd
            func = freebsd.get_process_cwd
            dbg('Using FreeBSD get_pid_cwd')
        except (OSError, NotImplementedError, ImportError):
            dbg('FreeBSD version too old for get_pid_cwd')
    elif system == 'SunOS':
        dbg('Using SunOS get_pid_cwd')
        func = sunos_get_pid_cwd
    elif psutil_avail:
        func = psutil_cwd
    else:
        dbg('Unable to determine a get_pid_cwd for OS: %s' % system)

    return(func)

def proc_get_pid_cwd(pid, path):
    """Extract the cwd of a PID from proc, given the PID and the /proc path to
    insert it into, e.g. /proc/%s/cwd"""
    try:
        cwd = os.path.realpath(path % pid)
    except Exception, ex:
        err('Unable to get cwd for PID %s: %s' % (pid, ex))
        cwd = '/'

    return(cwd)

def linux_get_pid_cwd(pid):
    """Determine the cwd for a given PID on Linux kernels"""
    return(proc_get_pid_cwd(pid, '/proc/%s/cwd'))

def sunos_get_pid_cwd(pid):
    """Determine the cwd for a given PID on SunOS kernels"""
    return(proc_get_pid_cwd(pid, '/proc/%s/path/cwd'))

def psutil_cwd(pid):
    """Determine the cwd using psutil which also supports Darwin"""
    return psutil.Process(pid).as_dict()['cwd']

# vim: set expandtab ts=4 sw=4:
