#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""borg.py - We are the borg. Resistance is futile.
   http://code.activestate.com/recipes/66531/"""

class Borg:
    __shared_state = {} 
    def __init__(self):
         self.__dict__ = self.__shared_state

