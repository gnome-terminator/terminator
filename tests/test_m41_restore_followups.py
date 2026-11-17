"""Off-screen restore placement and the one-shot "don't restore next launch"."""
import json
import os

import pytest

from terminatorlib.session import SessionManager
from terminatorlib.util import fit_rect_to_monitors
from terminatorlib.window import Window


def _reset_session_borg():
    from terminatorlib.borg import Borg
    Borg._Borg__shared_state.pop('SessionManager', None)


@pytest.fixture
def state_home(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    _reset_session_borg()
    yield tmp_path
    _reset_session_borg()


def _quiet_cache(monkeypatch):
    from terminatorlib.scrollback import ScrollbackCache
    monkeypatch.setattr(ScrollbackCache, 'stop',
                        lambda self, join_timeout=1.0: None)
    monkeypatch.setattr(ScrollbackCache, 'start', lambda self: None)
    monkeypatch.setattr(ScrollbackCache, 'clear_all', lambda self: None)


def test_fit_rect_keeps_a_window_that_meets_a_monitor():
    monitors = [(0, 0, 1920, 1080), (1920, 0, 1280, 1024)]
    assert fit_rect_to_monitors(2000, 100, 800, 600, monitors, primary=0) == \
        (2000, 100, 800, 600, False)
    # Still visible on the left monitor, so it stays put.
    assert fit_rect_to_monitors(1800, 0, 100, 100, monitors, primary=1) == \
        (1800, 0, 100, 100, False)


def test_fit_rect_moves_a_missing_monitor_onto_the_primary():
    monitors = [(0, 0, 1920, 1080), (1920, 0, 1280, 1024)]
    assert fit_rect_to_monitors(-3000, 40, 2000, 2000, monitors, primary=1) == \
        (1920, 0, 1280, 1024, True)
    # Maximised / fullscreen keeps the saved size; the WM applies it.
    assert fit_rect_to_monitors(
        -3000, 40, 2000, 2000, monitors, primary=1, shrink=False) == \
        (1920, 0, 2000, 2000, True)


def test_fit_rect_without_monitors_or_size_stays():
    assert fit_rect_to_monitors(10, 20, 30, 40, [], primary=0) == \
        (10, 20, 30, 40, False)
    assert fit_rect_to_monitors(10, 20, 0, 0, [(0, 0, 100, 100)]) == \
        (10, 20, 0, 0, False)
    assert fit_rect_to_monitors(500, 500, 0, 0, [(0, 0, 100, 100)]) == \
        (0, 0, 0, 0, True)


def test_window_fit_uses_workareas_and_skips_wayland(monkeypatch):
    monkeypatch.setattr(
        'terminatorlib.window.monitor_workareas',
        lambda _widget: ([(1920, 0, 800, 600)], 0))

    class Placed(object):
        def can_set_position(self):
            return True

    pos, size = Window.fit_restored_geometry(
        Placed(), (-40, 10), (900, 700), shrink=True)
    assert pos == (1920, 0)
    assert size == (800, 600)
    assert Window.fit_restored_geometry(
        Placed(), (2000, 10), (100, 100), shrink=True) == ((2000, 10), (100, 100))
    pos, size = Window.fit_restored_geometry(
        Placed(), (3000, 10), (100, 100), shrink=True)
    assert (pos, size) == ((1920, 0), (100, 100))

    class Wayland(object):
        def can_set_position(self):
            return False

    assert Window.fit_restored_geometry(
        Wayland(), (-40, 10), (900, 700)) == ((-40, 10), (900, 700))


def test_skip_next_restore_is_one_shot(state_home, monkeypatch):
    _quiet_cache(monkeypatch)
    sm = SessionManager()
    assert sm.acquire_lock()
    sm.set_owner_from_options(object())
    assert sm.arm_skip_next_restore() is True
    assert sm.skip_next_armed()
    assert sm.is_writer() is False
    path = sm.session_path()
    assert os.path.isfile(os.path.join(os.path.dirname(path),
                                       'skip-next-restore'))

    _reset_session_borg()
    nxt = SessionManager()
    assert nxt.consume_skip_next_restore() is True
    assert nxt.consume_skip_next_restore() is False
    assert nxt.skip_next_armed() is False


def test_uncheck_resumes_but_clear_keeps_saving_off(state_home, monkeypatch):
    _quiet_cache(monkeypatch)
    sm = SessionManager()
    assert sm.acquire_lock()
    sm.set_owner_from_options(object())
    sm.arm_skip_next_restore()
    assert sm.cancel_skip_next_restore() is True
    assert sm.is_writer() is True
    assert sm.skip_next_armed() is False

    sm.arm_skip_next_restore()
    sm.clear_session_files()
    assert sm.skip_next_armed() is False
    assert sm.cancel_skip_next_restore() is False
    assert sm.is_writer() is False


def test_use_previous_drops_the_skip_mark(state_home, monkeypatch):
    _quiet_cache(monkeypatch)
    sm = SessionManager()
    assert sm.acquire_lock()
    sm.set_owner_from_options(object())
    prev = sm.session_path() + '.prev'
    os.makedirs(os.path.dirname(prev), exist_ok=True)
    with open(prev, 'w', encoding='utf-8') as fh:
        json.dump({'version': 1, 'layout': {'child1': {'type': 'Window'}}}, fh)
    sm.arm_skip_next_restore()
    assert sm.restore_prev_session() is True
    assert sm.skip_next_armed() is False
    assert sm.is_writer() is False
    with open(sm.session_path(), encoding='utf-8') as fh:
        assert json.load(fh)['layout']['child1']['type'] == 'Window'


def test_menu_check_arms_and_clears_the_mark(state_home, monkeypatch):
    gi = pytest.importorskip('gi')
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk
    from terminatorlib.terminal_popup_menu import append_skip_restore_item
    from terminatorlib.translation import _

    _quiet_cache(monkeypatch)
    sm = SessionManager()
    assert sm.acquire_lock()
    sm.set_owner_from_options(object())
    menu = Gtk.Menu()
    item = append_skip_restore_item(menu)
    assert item.get_label() == _("Don't restore _next launch")
    assert item.get_sensitive()
    assert item.get_active() is False
    item.set_active(True)
    assert sm.skip_next_armed()
    assert sm.is_writer() is False
    item.set_active(False)
    assert sm.skip_next_armed() is False
    assert sm.is_writer() is True
