"""Drag-and-drop text: a Mozilla URL keeps its first line, and a
file:// list stays shell-quoted."""

import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')

from terminatorlib.terminal import Terminal


class _Selection(object):
    def __init__(self, payload):
        self.payload = payload

    def get_data_type(self):
        return 'text/x-moz-url'

    def get_data(self):
        return self.payload


class _Context(object):
    def list_targets(self):
        return ['text/plain']


def _term():
    fed = []

    class _Target(object):
        def feed(self, text):
            fed.append(text)

    term = Terminal.__new__(Terminal)
    term.terminator = type('App', (), {
        'get_target_terms': lambda self, widget: [_Target()],
    })()
    term.fed = fed
    return term


def _drop(monkeypatch, payload, info, decode_as=None):
    import terminatorlib.terminal as terminal_mod
    monkeypatch.setattr(
        terminal_mod.Gtk, 'targets_include_text', lambda *_args: True)
    monkeypatch.setattr(
        terminal_mod.Gtk, 'targets_include_uri', lambda *_args: False)
    term = _term()
    data = payload.encode('utf-16') if decode_as == 'utf-16' else payload.encode()
    term.on_drag_data_received(
        None, _Context(), 0, 0, _Selection(data), info, 0, None)
    assert len(term.fed) == 1
    return term.fed[0]


def test_moz_url_keeps_the_first_line_only(monkeypatch):
    text = _drop(
        monkeypatch,
        'http://example.com/one\nSecond title\rThird',
        Terminal.TARGET_TYPE_MOZ,
        decode_as='utf-16')
    assert text == 'http://example.com/one'


def test_moz_url_crlf_title_is_dropped(monkeypatch):
    text = _drop(
        monkeypatch,
        'http://example.com/only\r\nPage title',
        Terminal.TARGET_TYPE_MOZ,
        decode_as='utf-16')
    assert text == 'http://example.com/only'


def test_file_url_list_stays_quoted(monkeypatch):
    text = _drop(
        monkeypatch,
        'file:///tmp/a%20b\r\nfile:///tmp/c\r\n',
        0)
    assert text == "'/tmp/a b' '/tmp/c' "
    assert '\r' not in text
    assert text == text.rstrip('\r\n') or text.endswith(' ')
