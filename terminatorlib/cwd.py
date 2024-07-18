# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""cwd.py - function necessary to get the cwd for a given pid on various OSes


>>> cwd = get_pid_cwd(None)
>>> cwd.__class__.__name__
'str'

"""

import psutil
from .util import dbg

def get_pid_cwd(pid = None):
    """Determine the cwd of the current process"""
    psinfo =  psutil.Process(pid).as_dict()
    dbg('psinfo: %s %s' % (psinfo['cwd'],psinfo['pid']))
    # return func
    return psinfo['cwd']

def get_pid_venv(pid = None):
    """Determine the virtual environment of the current process"""
    psinfo =  psutil.Process(pid).as_dict()
    dbg('psinfo: %s' % (psinfo))
    #dbg('psinfo: %s %s' % (psinfo['venv'],psinfo['pid']))
    # prefix = getattr(sys, "base_prefix", None) or getattr(sys, "real_prefix", None) or sys.prefix
    # if prefix != sys.prefix: # session is in a virtual environment
    #     return sys.prefix
    # return func
    return "my-venv" #psinfo['venv']

# vim: set expandtab ts=4 sw=4:
