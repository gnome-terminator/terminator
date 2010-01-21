"""Load up the tests."""
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
