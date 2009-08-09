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

# set this to true to enable debugging output
DEBUG = True

def dbg (log = ""):
    """Print a message if debugging is enabled"""
    if DEBUG:
        print >> sys.stderr, log

def err (log = ""):
    """Print an error message"""
    print >> sys.stderr, log
