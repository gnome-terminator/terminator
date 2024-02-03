# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""venv.py - function necessary to get the current virtual environment for a given pid on various OSes


>>> venv = get_pid_venv(None)
>>> venv.__class__.__name__
'str'

"""

import psutil
from .util import dbg

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
