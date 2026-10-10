# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""cwd.py - function necessary to get the cwd for a given pid on various OSes


>>> cwd = get_pid_cwd(None)
>>> cwd.__class__.__name__
'str'

"""

import os
from os import readlink as _readlink

import psutil
from .util import dbg

def get_pid_cwd(pid = None):
    """Determine the cwd of the current process

    m26 (round2-ux P2-2): Process.cwd() / readlink of /proc/PID/cwd only;
    as_dict() gathered every attribute (~2.3 ms vs ~0.01 ms) and the
    session cwd probe calls this for every pane whose contents change.
    """
    if pid is None:
        pid = os.getpid()
    try:
        cwd = _readlink('/proc/%d/cwd' % int(pid))
        dbg('cwd: %s %s' % (cwd, pid))
        return cwd
    except (OSError, ValueError, TypeError):
        pass
    cwd = psutil.Process(pid).cwd()
    dbg('psutil cwd: %s %s' % (cwd, pid))
    return cwd

# vim: set expandtab ts=4 sw=4:
