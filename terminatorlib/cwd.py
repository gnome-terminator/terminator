# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""cwd.py - function necessary to get the cwd for a given pid on various OSes


>>> cwd = get_pid_cwd(None)
>>> cwd.__class__.__name__
'str'

"""

import os
try:
    import psutil
except ImportError:
    # psutil is a soft dependency: it lets us read another process' cwd (used
    # to open a split terminal in the parent's directory). If it is absent
    # (e.g. the pacman python-psutil package failed to install on Windows),
    # degrade to the current process' cwd instead of crashing at startup --
    # the terminal still launches.
    psutil = None
from .util import dbg

def get_pid_cwd(pid = None):
    """Determine the cwd of the current process"""
    if psutil is not None:
        try:
            psinfo = psutil.Process(pid).as_dict()
            dbg('psinfo: %s %s' % (psinfo['cwd'], psinfo['pid']))
            return psinfo['cwd']
        except Exception as ex:
            dbg('psutil cwd lookup failed (%s); falling back to os.getcwd()' % ex)
    return os.getcwd()

# vim: set expandtab ts=4 sw=4:
