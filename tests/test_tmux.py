#!/usr/bin/env python2

import os
import sys, os.path
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from terminatorlib.tmux import notifications

class NotificationsTests(unittest.TestCase):

    def test_layout_changed_parsing(self):
        layouts = [
            'sum,80x24,0,0,0',
            'sum,80x24,0,0[80x12,0,0,0,80x5,0,13,1,80x2,0,19,2,80x2,0,22,3]',
            'sum,80x24,0,0{40x24,0,0,0,19x24,41,0,1,9x24,61,0,2,4x24,71,0,3,4x24,76,0,4}',
            'sum,80x24,0,0[80x12,0,0,0,80x5,0,13,1,80x5,0,19{40x5,0,19,2,19x5,41,19,3,9x5,61,19,4,4x5,71,19,5,4x5,76,19,6}]'
        ]
        for layout in layouts:
            notification = notifications.LayoutChange()
            notification.consume(['', layout])
            print notification.window_layout


def main():
    unittest.main()

if __name__ == '__main__':
    main()
