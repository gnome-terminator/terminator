"""Load up the tests."""
from unittest import TestSuite
from doctest import DocTestSuite, ELLIPSIS

def test_suite():
    suite = TestSuite()
    for name in (
        'config',
        'plugin',
        'testborg',
        'cwd',
        'factory',
        'util',
        ):
        suite.addTest(DocTestSuite('terminatorlib.' + name))
    return suite
