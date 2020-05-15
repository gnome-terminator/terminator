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
import psutil
from .util import dbg, err

def get_default_cwd():
    """Determine a reasonable default cwd"""
    try:
        cwd = os.getcwd()
    except (FileNotFoundError,OSError):
        err("unable to set current working directory, does not exist")
        cwd = '/'
    
    return(cwd)

def get_pid_cwd():
    """Determine an appropriate cwd function for the OS we are running on"""
    return psutil.Process().as_dict()['cwd']

# vim: set expandtab ts=4 sw=4:
