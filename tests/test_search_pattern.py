"""Find dialog: literal text, whole word, and regular expressions."""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')

from terminatorlib.searchbar import build_search_pattern


def test_empty_is_not_a_pattern():
    assert build_search_pattern('', False, False) is None
    assert build_search_pattern('', True, True) is None


def test_literal_escapes_metacharacters():
    assert build_search_pattern('foo.bar', False, False) == r'foo\.bar'


def test_regex_is_kept():
    assert build_search_pattern('foo.bar', False, True) == 'foo.bar'


def test_whole_word_wraps_a_literal():
    assert build_search_pattern('foo.bar', True, False) == r'\b(?:foo\.bar)\b'


def test_whole_word_wraps_a_regex():
    assert build_search_pattern('a|b', True, True) == r'\b(?:a|b)\b'
