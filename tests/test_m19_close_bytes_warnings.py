import os, re, warnings
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _src(p):
    return open(os.path.join(ROOT, 'terminatorlib', p)).read()

def test_scrollback_requires_vte_before_import():
    s = _src('scrollback.py')
    req = s.index("gi.require_version('Vte', '2.91')")
    assert req < s.index('from gi.repository import GLib, Vte')

def test_prefseditor_no_dialog_flags_kwarg():
    assert 'flags=Gtk.DialogFlags' not in _src('prefseditor.py')

@pytest.mark.parametrize('p', ['paned.py', 'window.py', 'terminal.py', 'notebook.py'])
def test_no_gobject_idle_add(p):
    assert 'GObject.idle_add(' not in _src(p)

from tests.test_altscreen_cache import cache, _Term  # noqa: F401


def test_sync_write_counts_bytes(cache):
    c, screen = cache
    c._bytes_since_gc = 0
    c._flush_uuid(_Term(), 'u1', sync=True)
    n = os.path.getsize(c.path_for('u1'))
    assert n > 0 and c._bytes_since_gc == n
    screen['text'] = 'more history\n$ ls'
    c._flush_uuid(_Term(), 'u1', sync=True)
    assert c._bytes_since_gc == n + os.path.getsize(c.path_for('u1'))


def test_sync_write_unchanged_does_not_count(cache):
    c, _ = cache
    c._flush_uuid(_Term(), 'u2', sync=True)
    before = c._bytes_since_gc
    c._flush_uuid(_Term(), 'u2', sync=True)
    assert c._bytes_since_gc == before


def test_scrollback_import_no_vte_version_warning():
    import subprocess, sys
    r = subprocess.run([sys.executable, '-W', 'error::PyGIWarning', '-c',
                        'import gi\ntry:\n from gi import PyGIWarning\nexcept ImportError: pass\nimport terminatorlib.scrollback'],
                       cwd=ROOT, capture_output=True, text=True)
    assert 'require_version' not in r.stderr, r.stderr
