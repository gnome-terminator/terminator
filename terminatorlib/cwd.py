#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""cwd.py - function necessary to get the cwd for a given pid on various OSes

>>> cwd = get_default_cwd()
>>> cwd.__class__.__name__
'str'

"""

import platform
import os
import pwd
from util import dbg, err

def get_default_cwd():
    """Determine a reasonable default cwd"""
    cwd = os.getcwd()
    if not os.path.exists(cwd) or not os.path.isdir(cwd):
        try:
            cwd = pwd.getpwuid(os.getuid())[5]
        except KeyError:
            cwd = '/'
    
    return(cwd)

# vim: set expandtab ts=4 sw=4:
