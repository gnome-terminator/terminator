#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""testsignalman.py - Test the signalman class

>>> widget = TestWidget()
>>> signalman = Signalman()
>>> signalman.new(widget, 'test1', handler)
1
>>> signalman.cnxids[widget].keys()
['test1']
>>> widget.signals.values()
['test1']
>>> signalman.remove_widget(widget)
>>> signalman.cnxids.has_key(widget)
False
>>> widget.signals.values()
[]
>>> signalman.new(widget, 'test2', handler)
2
>>> signalman.new(widget, 'test3', handler)
3
>>> signalman.remove_signal(widget, 'test2')
>>> signalman.cnxids[widget].keys()
['test3']
>>> widget.signals.values()
['test3']
>>> signalman.remove_widget(widget)
>>>

"""

from ..signalman import Signalman

class TestWidget():
    signals = None
    count = None

    def __init__(self):
        self.signals = {}
        self.count = 0

    def connect(self, signal, handler, *args):
        self.count = self.count + 1
        self.signals[self.count] = signal
        return(self.count)

    def disconnect(self, signalid):
        del(self.signals[signalid])

def handler():
    print "I am a test handler"

if __name__ == '__main__':
    import sys
    import doctest
    (failed, attempted) = doctest.testmod()
    print "%d/%d tests failed" % (failed, attempted)
    sys.exit(failed)
