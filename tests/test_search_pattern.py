"""Find dialog: literal text, whole word, and regular expressions."""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')

from gi.repository import Gio

from terminatorlib import config as _config

# Test-env guard: Config.connect_gsetting_callbacks aborts the process
# when the org.gnome.desktop.interface schema is missing.
if 'org.gnome.desktop.interface' not in Gio.Settings.list_schemas():
    _config.Config.connect_gsetting_callbacks = lambda self: None

from terminatorlib.searchbar import Searchbar, build_search_pattern
from terminatorlib import regex


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


class _FakeVte(object):
    def __init__(self):
        self.regexes = []
        self.gregexes = []
        self.wraps = []
        self.find_next = 0
        self.find_prev = 0

    def search_set_regex(self, compiled, _flags):
        self.regexes.append(compiled)

    def search_set_gregex(self, compiled, _flags):
        self.gregexes.append(compiled)

    def search_set_wrap_around(self, wrap):
        self.wraps.append(wrap)

    def search_find_next(self):
        self.find_next += 1
        return True

    def search_find_previous(self):
        self.find_prev += 1
        return True


class _FakeTerminal(object):
    def __init__(self):
        self.vte = _FakeVte()

    def get_toplevel(self):
        return object()


def _pattern_calls(monkeypatch):
    """Record patterns handed to PCRE2, or to GLib when PCRE2 is absent."""
    import terminatorlib.searchbar as searchbar_mod
    patterns = []
    if regex.FLAGS_PCRE2:
        real_new = searchbar_mod.Vte.Regex.new_for_search

        def spy_new(pattern, length, flags):
            patterns.append(pattern)
            return real_new(pattern, length, flags)

        monkeypatch.setattr(searchbar_mod.Vte.Regex, 'new_for_search', spy_new)
    else:
        real_regex = searchbar_mod.GLib.Regex

        def spy_regex(pattern, flags, match_flags):
            patterns.append(pattern)
            return real_regex(pattern, flags, match_flags)

        monkeypatch.setattr(searchbar_mod.GLib, 'Regex', spy_regex)
    return patterns


def test_reopen_search_reinstalls_pattern_without_finding(monkeypatch):
    patterns = _pattern_calls(monkeypatch)
    term = _FakeTerminal()
    bar = Searchbar(term)
    bar._ensure_dialog()
    text = 'alpha'
    bar.entry.set_text(text)
    bar.vte = term.vte
    bar._apply(jump=False)
    assert patterns
    bar.end_search()
    assert bar.get_search_term() == text
    assert bar._last == ''
    assert term.vte.regexes[-1] is None or (
        term.vte.gregexes and term.vte.gregexes[-1] is None)

    expected = build_search_pattern(
        text, bar.whole_word.get_active(), bar.as_regex.get_active())
    find_next = term.vte.find_next
    find_prev = term.vte.find_prev
    regex_count = len(term.vte.regexes)
    gregex_count = len(term.vte.gregexes)
    bar.start_search()
    new_regex = term.vte.regexes[regex_count:]
    new_gregex = term.vte.gregexes[gregex_count:]
    installed = [item for item in new_regex + new_gregex if item is not None]
    assert installed
    assert patterns[-1] == expected
    assert term.vte.find_next == find_next
    assert term.vte.find_prev == find_prev
    assert bar.next.get_sensitive()
    assert bar.prev.get_sensitive()

    bar.next_search()
    assert term.vte.find_next == find_next + 1

    find_next = term.vte.find_next
    find_prev = term.vte.find_prev
    bar.entry.set_text('')
    bar.end_search()
    bar.start_search()
    assert bar.next.get_sensitive() is False
    assert bar.prev.get_sensitive() is False
    assert term.vte.find_next == find_next
    assert term.vte.find_prev == find_prev
    assert term.vte.regexes[-1] is None or (
        term.vte.gregexes and term.vte.gregexes[-1] is None)


def test_pcre2_search_length_is_not_code_points(monkeypatch):
    if not regex.FLAGS_PCRE2:
        import pytest
        pytest.skip('PCRE2 search flags are unavailable')
    import terminatorlib.searchbar as searchbar_mod
    seen = []
    compiled = object()

    def fake_new(pattern, length, flags):
        seen.append((pattern, length, flags))
        return compiled

    monkeypatch.setattr(
        searchbar_mod.Vte.Regex, 'new_for_search', fake_new)
    term = _FakeTerminal()
    bar = Searchbar(term)
    bar.vte = term.vte
    bar._ensure_dialog()
    pattern = build_search_pattern('caféx', False, False)
    assert bar._install_pattern(pattern) is True
    assert len(seen) == 1
    got_pattern, length, flags = seen[0]
    assert got_pattern == pattern
    assert length == -1 or length == len('caféx'.encode('utf-8'))
    assert length != len('caféx')
    assert flags & regex.PCRE2_MULTILINE
    assert term.vte.regexes[-1] is compiled
