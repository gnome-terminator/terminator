"""m26: one helper for "leave zoom before describe/close"; make_uuid('')
explicit; prefseditor without deprecated ColorButton/FontButton calls."""
import os
import re
import uuid
import warnings

import pytest

from terminatorlib import zoomguard
from terminatorlib.zoomguard import (leave_zoom, is_legacy_zoomed,
                                     is_overlay_maximised,
                                     leave_legacy_zoom_all,
                                     leave_overlay_all, any_legacy_zoom)

ROOT = os.path.join(os.path.dirname(__file__), '..', 'terminatorlib')


class FakeWin:
    def __init__(self, zoomed=False, overlay=False, boom=False):
        self.zoomed = zoomed or overlay   # overlay also sets term_zoomed
        self.overlay = overlay
        self.boom = boom
        self.calls = []

    def is_zoomed(self):
        return self.zoomed

    def is_overlay_maximised(self):
        return self.overlay

    def overlay_restore(self, animate=True):
        self.calls.append(('overlay_restore', animate))
        if self.boom:
            raise RuntimeError('x')
        self.overlay = self.zoomed = False
        return True

    def unzoom(self, widget=None):
        self.calls.append(('unzoom',))
        if self.boom:
            raise RuntimeError('x')
        self.zoomed = False


# --- helper semantics -------------------------------------------------

def test_predicates():
    assert is_legacy_zoomed(FakeWin(zoomed=True))
    assert not is_legacy_zoomed(FakeWin(overlay=True))
    assert not is_legacy_zoomed(FakeWin())
    assert is_overlay_maximised(FakeWin(overlay=True))
    assert not is_overlay_maximised(object())
    assert not is_legacy_zoomed(object())
    assert not leave_zoom(None)


def test_both_modes_overlay_snap_no_animation():
    w = FakeWin(overlay=True)
    assert leave_zoom(w) is True
    assert w.calls == [('overlay_restore', False)]


def test_both_modes_legacy():
    w = FakeWin(zoomed=True)
    assert leave_zoom(w) is True
    assert w.calls == [('unzoom',)]


def test_legacy_only_keeps_overlay():
    w = FakeWin(overlay=True)
    assert leave_zoom(w, legacy=True, overlay=False) is False
    assert w.calls == []


def test_overlay_only_keeps_legacy():
    w = FakeWin(zoomed=True)
    assert leave_zoom(w, legacy=False, overlay=True) is False
    assert w.calls == []


def test_not_zoomed_noop():
    w = FakeWin()
    assert leave_zoom(w) is False and w.calls == []


def test_quiet_swallows_loud_raises():
    assert leave_zoom(FakeWin(zoomed=True, boom=True)) is False
    with pytest.raises(RuntimeError):
        leave_zoom(FakeWin(zoomed=True, boom=True), quiet=False)


def test_bulk_helpers():
    ws = [FakeWin(zoomed=True), FakeWin(overlay=True), FakeWin(),
          FakeWin(zoomed=True, boom=True), object()]
    assert any_legacy_zoom(ws)
    assert leave_legacy_zoom_all(ws) == 1          # boom one swallowed
    assert ws[1].calls == []
    assert leave_overlay_all(ws) == 1
    assert ws[1].calls == [('overlay_restore', False)]
    assert not any_legacy_zoom([FakeWin(overlay=True)])


# --- every close/save path goes through the helper ----------------------

def _src(name):
    with open(os.path.join(ROOT, name)) as fh:
        return fh.read()


def test_no_inline_unzoom_patterns_left():
    """The scattered 'is_zoomed() and not is_overlay_maximised(): unzoom'
    and bare overlay_restore(animate=False) close-path snippets are gone."""
    pat_legacy = re.compile(r'is_zoomed\(\)\s+and\s+not\s+\S*is_overlay_maximised')
    pat_both = re.compile(r'if self\.is_overlay_maximised\(\):\s*\n\s*self\.overlay_restore\(animate=False\)\s*\n\s*else:')
    for name in ('window.py', 'session.py', 'terminator.py', 'notebook.py',
                 'terminal.py'):
        s = _src(name)
        assert not pat_legacy.search(s), name
        assert not pat_both.search(s), name
    for name in ('session.py', 'terminator.py', 'notebook.py', 'terminal.py',
                 'paned.py'):
        assert 'overlay_restore(animate=False)' not in _src(name), name
    w = _src('window.py')
    # Window.destroy / closeterm use the helper
    assert "reason='destroy'" in w and "reason='closeterm'" in w


@pytest.fixture
def sm(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    from terminatorlib.borg import Borg
    Borg._Borg__shared_state.pop('SessionManager', None)
    from terminatorlib.session import SessionManager
    s = SessionManager()
    yield s
    Borg._Borg__shared_state.pop('SessionManager', None)


def test_session_legacy_helpers_route(sm, monkeypatch):
    from terminatorlib.terminator import Terminator
    ws = [FakeWin(zoomed=True), FakeWin(overlay=True)]
    monkeypatch.setattr(Terminator(), 'windows', ws, raising=False)
    assert sm._any_legacy_zoom() is True
    sm._unzoom_legacy_all()
    assert ws[0].calls == [('unzoom',)]
    assert ws[1].calls == []          # save keeps the overlay (maximised_pane)
    assert sm._any_legacy_zoom() is False


def test_note_window_closing_unzooms_legacy_only(sm, monkeypatch):
    monkeypatch.setattr(sm, 'is_writer', lambda: True)
    sm.final_saving = False
    seen = []
    real = zoomguard.leave_zoom
    monkeypatch.setattr(zoomguard, 'leave_zoom',
                        lambda w, **kw: seen.append(kw) or real(w, **kw))
    legacy, ov = FakeWin(zoomed=True), FakeWin(overlay=True)
    for w in (legacy, ov):
        try:
            sm.note_window_closing(w)   # describe on a fake may fail later
        except Exception:
            pass
    assert [k['legacy'] for k in seen] == [True, True]
    assert [k['overlay'] for k in seen] == [False, False]
    assert legacy.calls == [('unzoom',)]
    assert ov.calls == []               # fragment keeps maximised_pane


def test_container_closeterm_legacy_zoom_routes(monkeypatch):
    from terminatorlib.container import Container
    w = FakeWin(zoomed=True)
    w.get_property = lambda name: w.zoomed
    closed = []

    class T:
        def close(self):
            closed.append(1)
    assert Container.closeterm(w, T()) is True
    assert w.calls == [('unzoom',)] and closed == [1]


def test_paned_collapse_guard_routes(monkeypatch):
    from terminatorlib import paned
    w = FakeWin(overlay=True)
    w.is_maximised_pane = lambda t: False

    class PH:
        def is_ancestor(self, p):
            return True

    class OV:
        def placeholder(self):
            return PH()
    w._overlay = OV()

    class P:
        def get_toplevel(self):
            return w
    assert paned._restore_overlay_before_collapse(P(), object()) is True
    assert w.calls == [('overlay_restore', False)]
    # not overlay-maximised: untouched
    w2 = FakeWin(zoomed=True)
    P.get_toplevel = lambda self: w2
    assert paned._restore_overlay_before_collapse(P(), object()) is False
    assert w2.calls == []


# --- make_uuid ----------------------------------------------------------

def test_make_uuid_explicit(monkeypatch):
    from terminatorlib import util
    logged = []
    monkeypatch.setattr(util, 'err', lambda m='': logged.append(m))
    u = util.make_uuid('')
    assert isinstance(u, uuid.UUID) and logged
    logged.clear()
    assert isinstance(util.make_uuid('  '), uuid.UUID) and logged
    logged.clear()
    assert isinstance(util.make_uuid(), uuid.UUID) and not logged
    s = '12345678-1234-5678-1234-567812345678'
    assert util.make_uuid(s) == uuid.UUID(s)
    assert util.make_uuid(uuid.UUID(s)) == uuid.UUID(s)
    with pytest.raises(ValueError):
        util.make_uuid('garbage')
    assert not logged


# --- prefseditor deprecations ------------------------------------------

def test_prefseditor_no_deprecated_calls():
    s = _src('prefseditor.py')
    assert not re.search(r'\.set_color\(', s)
    assert not re.search(r'\.set_font_name\(', s)
    assert not re.search(r'\.get_font_name\(', s)
    assert not re.search(r'widget\.get_color\(', s)


def test_prefseditor_color_font_helpers_no_warning():
    gi = pytest.importorskip('gi')
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk
    from terminatorlib.prefseditor import (set_button_color, set_button_font,
                                           color2hex, rgba2hex)
    btn = Gtk.ColorButton()
    fbtn = Gtk.FontButton()
    with warnings.catch_warnings():
        warnings.simplefilter('error', DeprecationWarning)
        set_button_color(btn, '#12ab3c')
        assert color2hex(btn) == '#12ab3c' == rgba2hex(btn)
        with pytest.raises(ValueError):
            set_button_color(btn, 'not-a-colour')
        with pytest.raises(ValueError):
            set_button_color(btn, '')
        set_button_font(fbtn, 'Monospace 13')
        assert fbtn.get_font() == 'Monospace 13'


# --- m26 independent review --------------------------------------------

def test_container_closeterm_stale_zoom_does_not_recurse(monkeypatch):
    """term_zoomed stuck True but nothing to leave: must not re-close."""
    from terminatorlib import container
    from terminatorlib.container import Container
    w = FakeWin(zoomed=True)
    w.is_zoomed = lambda: False          # helper sees nothing to undo
    w.get_property = lambda name: True   # stale property
    logged = []
    monkeypatch.setattr(container, 'err', lambda m='': logged.append(m))

    class Stop(Exception):
        pass

    class T:
        def close(self):
            raise AssertionError('recursive close')

    class Term:
        @property
        def terminals(self):
            raise Stop()
    w.terminator = Term()
    with pytest.raises(Stop):            # reached the normal close path
        Container.closeterm(w, T())
    assert logged and w.calls == []


def test_loud_mode_propagates_predicate_errors():
    w = FakeWin(zoomed=True)

    def bad():
        raise RuntimeError('ov')
    w.is_overlay_maximised = bad
    with pytest.raises(RuntimeError):
        leave_zoom(w, quiet=False)
    assert w.calls == []                 # not misread as legacy zoom
    assert leave_zoom(w) is True         # quiet: old fallback kept
    assert w.calls == [('unzoom',)]


def test_set_button_color_accepts_named_colours():
    gi = pytest.importorskip('gi')
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk
    from terminatorlib.prefseditor import set_button_color, color2hex
    btn = Gtk.ColorButton()
    set_button_color(btn, 'red')         # Gdk.color_parse accepted names
    assert color2hex(btn) == '#ff0000'
