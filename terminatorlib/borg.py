#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""borg.py - We are the borg. Resistance is futile.
   http://code.activestate.com/recipes/66531/"""

# pylint: disable-msg=R0903
class Borg:
    """Definition of a class that can never be duplicated"""
    __shared_state = {} 
    def __init__(self):
        self.__dict__ = self.__shared_state

# vim: set expandtab ts=4 sw=4:
