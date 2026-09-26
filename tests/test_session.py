"""test_session.py - session restore: output relay, log rotation, replay"""

import os
import uuid

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import GLib, Gtk, Vte
import pytest

from terminatorlib import session


class FakeTerminal:
    """Just the bits of Terminal that the relay touches"""
    def __init__(self):
        self.window = Gtk.OffscreenWindow()
        self.vte = Vte.Terminal()
        self.vte.set_size_request(800, 500)
        self.window.add(self.vte)
        self.window.show_all()
        self.uuid = uuid.uuid4()
        self.cwd = '/'
        self.pid = None
        self.config = {'session_log_kb': 1}


@pytest.fixture(autouse=True)
def state_home(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path))
    os.makedirs(session.session_dir())


def run(terminal, script, typed=b''):
    """Run a shell script behind a relay, type into it, wait for it to exit"""
    log = session.Log(str(terminal.uuid), 64)
    session.Relay(terminal, ['/bin/sh', 'sh', '-c', script], None, log)
    if typed:
        GLib.timeout_add(300, lambda: terminal.vte.feed_child(typed))
    terminal.vte.connect('child-exited', lambda *a: Gtk.main_quit())
    GLib.timeout_add_seconds(10, Gtk.main_quit)
    Gtk.main()
    log.close()
    with open(log.path, 'rb') as logfile:
        return logfile.read()


def test_relay_records_output_and_passes_input():
    terminal = FakeTerminal()
    out = run(terminal,
              'printf "\\033[1;31mRED\\033[0m\\n"; read x; echo got:$x',
              b'hello\r')
    assert b'\x1b[1;31mRED\x1b[0m' in out
    assert b'got:hello' in out
    assert terminal.pid


def test_log_rotation_is_capped_and_trimmed():
    log = session.Log('abc', 1)
    for i in range(100):
        log.write(b'line %03d\r\n' % i)
    log.close()
    sizes = [os.path.getsize(log.path + ext) for ext in ('', '.old')]
    assert sum(sizes) <= 1024 + 10
    data = log.read()
    assert data.startswith(b'line ') and data.endswith(b'line 099\r\n')


@pytest.mark.parametrize('extra', ['', r'\033[?1049hvim screen'])
def test_replay_restores_previous_output(extra):
    """History comes back intact above the new shell, even if the old one
    died inside the alternate screen (vim, less)"""
    terminal = FakeTerminal()
    run(terminal, r'printf "\033[32mline1\033[0m\nline2\nline3\n%s"' % extra)

    restored = FakeTerminal()
    restored.uuid = terminal.uuid
    sess = session.Session()
    sess.restore = {str(terminal.uuid)}
    sess.spawn(restored, ['/bin/sh', 'sh', '-c', 'echo after'], None)
    restored.vte.connect('child-exited', lambda *a: Gtk.main_quit())
    GLib.timeout_add_seconds(10, Gtk.main_quit)
    Gtk.main()
    text = restored.vte.get_text_range_format(Vte.Format.TEXT, 0, 0, 50, 80)[0]
    lines = [line for line in text.splitlines() if line.strip()]
    assert lines[:3] == ['line1', 'line2', 'line3']
    assert lines[3].startswith('--- restored')
    assert lines[4] == 'after'


class FakeWidget:
    """A pane, tab or window: describe_layout() lists its terminals"""
    def __init__(self, kind, *uuids):
        self.kind, self.uuids = kind, uuids

    def describe_layout(self, count, parent, layout, order, save_cwd=False):
        layout['child0'] = {'type': self.kind, 'parent': parent}
        for num, uuid_ in enumerate(self.uuids):
            layout['terminal%d' % num] = {'type': 'Terminal', 'uuid': uuid_,
                                          'parent': 'child0'}


def test_closing_a_tab_is_remembered_once():
    sess = session.Session()
    sess.frozen, sess.closed_units = False, []
    sess.closed(FakeWidget('HPaned', 'a', 'b'), 'mytab')
    # the tab's terminals close right after; they are part of the tab
    sess.closed(FakeWidget('Terminal', 'a'))
    sess.closed(FakeWidget('Terminal', 'b'))
    assert len(sess.closed_units) == 1
    root = sess.closed_units[0]['child0']
    assert root['type'] == 'HPaned' and root['tab_label'] == 'mytab'

    for num in range(20):
        sess.closed(FakeWidget('Terminal', str(num)))
    assert len(sess.closed_units) == session.MAX_CLOSED

    sess.frozen = True  # quitting is not closing
    sess.closed(FakeWidget('Terminal', 'z'))
    assert len(sess.closed_units) == session.MAX_CLOSED
    sess.frozen = False
