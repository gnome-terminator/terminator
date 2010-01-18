#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""testborg.py - We are the borg. Resistance is futile.
   doctests for borg.py

>>> obj1 = TestBorg()
>>> obj2 = TestBorg()
>>> obj1.attribute
0
>>> obj2.attribute
0
>>> obj1.attribute = 12345
>>> obj1.attribute
12345
>>> obj2.attribute
12345
>>> obj2.attribute = 54321
>>> obj1.attribute
54321
>>> obj3 = TestBorg2()
>>> obj3.attribute
1
>>> obj4 = TestBorg2()
>>> obj3.attribute = 98765
>>> obj4.attribute
98765
>>>

"""

from ..borg import Borg

class TestBorg(Borg):
    attribute = None

    def __init__(self):
        Borg.__init__(self, self.__class__.__name__)
        self.prepare_attributes()
    
    def prepare_attributes(self):
        if not self.attribute:
            self.attribute = 0

class TestBorg2(Borg):
    attribute = None

    def __init__(self):
        Borg.__init__(self, self.__class__.__name__)
        self.prepare_attributes()

    def prepare_attributes(self):
        if not self.attribute:
            self.attribute = 1

