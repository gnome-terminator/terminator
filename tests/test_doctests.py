"""Load up the tests."""

import os
import sys, os.path
sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

from unittest import TestSuite
from doctest import DocTestSuite, ELLIPSIS

def test_suite():
    suite = TestSuite()
    for name in (
        'config',
        'plugin',
        'cwd',
        'factory',
        'util',
        'tests.testborg',
        'tests.testsignalman',
        ):
        suite.addTest(DocTestSuite('terminatorlib.' + name))
    return suite
