"""Tab lock: a normal exit keeps locked tabs; a kill keeps every tab."""

import json
import os

import gi
import pytest

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk  # noqa: E402

from terminatorlib.notebook import sidebar_icon_button
from terminatorlib.session import (
    collect_terminal_uuids,
    count_terminals_in_layout,
    layout_after_exit_policy,
    plain_launch_action,
    retain_locked_tabs,
)


def _tabs_and_a_split():
    """Two tabs in one window, plus a second window that is only a split."""
    return {
        'w': {'type': 'Window', 'parent': '', 'order': '0'},
        'nb': {
            'type': 'Notebook', 'parent': 'w', 'order': '0',
            'labels': ['keep', 'drop', 'also'],
            'locked': ['True', 'False', 'True'],
            'active_page': '1',
            'last_active_term': ['ua', 'ub', 'uc'],
        },
        'a': {'type': 'Terminal', 'parent': 'nb', 'order': '0', 'uuid': 'ua'},
        'b': {'type': 'HPaned', 'parent': 'nb', 'order': '1'},
        'b1': {'type': 'Terminal', 'parent': 'b', 'order': '0', 'uuid': 'ub'},
        'b2': {'type': 'Terminal', 'parent': 'b', 'order': '1', 'uuid': 'ub2'},
        'c': {'type': 'Terminal', 'parent': 'nb', 'order': '2', 'uuid': 'uc'},
        'w2': {'type': 'Window', 'parent': ''},
        'p': {'type': 'VPaned', 'parent': 'w2', 'order': '0'},
        'd': {'type': 'Terminal', 'parent': 'p', 'order': '0', 'uuid': 'ud'},
    }


def test_lock_and_close_are_buttons_that_act_on_release():
    """Pressing the close button must not run its action until release."""
    import inspect
    from terminatorlib.notebook import Notebook

    button = sidebar_icon_button(Gtk.Image())
    assert isinstance(button, Gtk.Button)
    assert 'terminator-tab-action' in button.get_style_context().list_classes()
    fired = []
    button.connect('clicked', lambda *_a: fired.append('clicked'))
    button.show()
    press = inspect.getsource(Notebook._on_sidebar_row_press)
    assert '_close_sidebar_page' not in press
    assert '_toggle_page_lock' not in press
    built = inspect.getsource(Notebook._make_sidebar_row)
    assert 'sidebar_icon_button' in built
    assert "connect(\n            'clicked'" in built or "'clicked'" in built
    assert fired == []


def test_retain_drops_unlocked_pages_and_keeps_plain_windows():
    kept = retain_locked_tabs(_tabs_and_a_split())
    assert collect_terminal_uuids(kept) == {'ua', 'uc', 'ud'}
    notebooks = [n for n in kept.values() if n.get('type') == 'Notebook']
    assert len(notebooks) == 1
    nb = notebooks[0]
    assert nb['locked'] == ['True', 'True']
    assert nb['labels'] == ['keep', 'also']
    assert nb['active_page'] == '0'
    assert nb['last_active_term'] == ['ua', 'uc']
    pages = [n for n in kept.values()
             if n.get('type') == 'Terminal' and n.get('uuid') in ('ua', 'uc')]
    assert sorted(n['order'] for n in pages) == ['0', '1']


def test_retain_drops_a_window_whose_tabs_are_all_unlocked():
    layout = _tabs_and_a_split()
    layout['nb']['locked'] = ['False', 'False', 'False']
    kept = retain_locked_tabs(layout)
    assert collect_terminal_uuids(kept) == {'ud'}
    assert not any(n.get('type') == 'Notebook' for n in kept.values())
    assert any(n.get('type') == 'Window' for n in kept.values())


def test_missing_lock_flags_mean_unlocked():
    layout = _tabs_and_a_split()
    del layout['nb']['locked']
    kept = retain_locked_tabs(layout)
    assert collect_terminal_uuids(kept) == {'ud'}


def test_live_snapshot_keeps_unlocked_tabs():
    layout = _tabs_and_a_split()
    assert collect_terminal_uuids(
        layout_after_exit_policy({'exit': 'live'}, layout)) == {
            'ua', 'ub', 'ub2', 'uc', 'ud'}
    # Older files have no exit field. They are a clean exit.
    assert 'ub' not in collect_terminal_uuids(
        layout_after_exit_policy({}, layout))


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


def _writer(state_home):
    from terminatorlib.session import SessionManager
    sm = SessionManager()
    assert sm.acquire_lock()
    sm._owns_session = True
    return sm


def test_save_now_live_keeps_tabs_and_clean_drops_them(state_home):
    sm = _writer(state_home)
    sm._describe_current = lambda: _tabs_and_a_split()
    assert sm.save_now(final=False) is True
    live = json.load(open(sm.session_path(), encoding='utf-8'))
    assert live['exit'] == 'live'
    assert collect_terminal_uuids(live['layout']) == {
        'ua', 'ub', 'ub2', 'uc', 'ud'}

    assert sm.save_now(final=True) is True
    clean = json.load(open(sm.session_path(), encoding='utf-8'))
    assert clean['exit'] == 'clean'
    assert collect_terminal_uuids(clean['layout']) == {'ua', 'uc', 'ud'}

    sm.final_saving = True

    class Term(object):
        def __init__(self, uid):
            self.uuid = uid

    assert sm.will_persist(Term('ub')) is False
    assert sm.will_persist(Term('ua')) is True


def test_clean_empty_session_opens_fresh_not_the_default_layout():
    """An unlocked close must not come back as [layouts][default]."""
    unlocked = {
        'w': {'type': 'Window', 'parent': ''},
        'nb': {'type': 'Notebook', 'parent': 'w', 'locked': ['False']},
        't': {'type': 'Terminal', 'parent': 'nb', 'uuid': 'old'},
    }
    action, kept = plain_launch_action({'exit': 'clean'}, unlocked)
    assert action == 'fresh'
    assert kept is None
    action, kept = plain_launch_action(
        {'exit': 'clean', 'layout': {}}, {})
    assert action == 'fresh'
    action, kept = plain_launch_action({'exit': 'live'}, unlocked)
    assert action == 'session'
    assert count_terminals_in_layout(kept) == 1
    action, kept = plain_launch_action(None, unlocked)
    assert action == 'layout'
    assert kept is None


def test_clean_exit_with_nothing_locked_writes_an_empty_session(state_home):
    layout = _tabs_and_a_split()
    layout['nb']['locked'] = ['False', 'False', 'False']
    del layout['w2']
    del layout['p']
    del layout['d']
    sm = _writer(state_home)
    sm._describe_current = lambda: layout
    assert sm.save_now(final=True) is True
    clean = json.load(open(sm.session_path(), encoding='utf-8'))
    assert clean['exit'] == 'clean'
    assert count_terminals_in_layout(clean['layout']) == 0
    assert layout_after_exit_policy(clean, clean['layout']) == {} or \
        count_terminals_in_layout(
            layout_after_exit_policy(clean, clean['layout'])) == 0


def _pump():
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)


def test_one_locked_tab_restores_as_a_single_page(state_home, monkeypatch):
    """A notebook of one kept tab used to grow a second empty page."""
    from terminatorlib.config import Config
    from terminatorlib.factory import Factory
    from terminatorlib.notebook import Notebook
    from terminatorlib.session import SESSION_LAYOUT_NAME, SessionManager
    from terminatorlib.terminal import Terminal
    from terminatorlib.terminator import Terminator

    monkeypatch.setattr(Terminal, 'spawn_child', lambda self, *a, **k: True)
    monkeypatch.setattr(Terminator(), 'terminals', [])
    monkeypatch.setattr(Terminator(), 'windows', [])
    sm = _writer(state_home)

    window = Factory().make('Window')
    first = Factory().make('Terminal')
    window.add(first)
    window.show_all()
    _pump()
    window.tab_new(first)
    _pump()
    notebook = window.get_child()
    assert isinstance(notebook, Notebook)
    assert notebook.get_n_pages() == 2
    kept = notebook.get_nth_page(0)
    kept_uuid = str(kept.uuid)
    notebook.get_tab_label(kept).set_locked(True)
    described = Terminator().describe_layout(True)
    flags = [n['locked'] for n in described.values() if n.get('type') == 'Notebook']
    assert flags == [['True', 'False']]

    assert sm.save_now(final=True) is True
    data = json.load(open(sm.session_path(), encoding='utf-8'))
    assert collect_terminal_uuids(data['layout']) == {kept_uuid}

    term = Terminator()
    wins = list(term.windows)
    term.windows = []
    term.terminals = []
    for old in wins:
        old.isDestroyed = True
        old._session_destroy_handled = True
        old.destroy()
    _pump()

    layout = sm.sanitize_layout(data['layout'])
    layout = layout_after_exit_policy(data, layout)
    Config().base.layouts[SESSION_LAYOUT_NAME] = layout
    before = list(Terminator().windows)
    Terminator().create_layout(SESSION_LAYOUT_NAME)
    Terminator().layout_done()
    _pump()
    restored = [w for w in Terminator().windows if w not in before]
    assert len(restored) == 1
    nb = restored[0].get_child()
    assert isinstance(nb, Notebook)
    assert nb.get_n_pages() == 1
    assert nb.get_tab_label(nb.get_nth_page(0)).get_locked() is True
    assert str(nb.get_nth_page(0).uuid) == kept_uuid

    if sm._timer is not None:
        from gi.repository import GLib
        GLib.source_remove(sm._timer)
        sm._timer = None
    Config().base.layouts.pop(SESSION_LAYOUT_NAME, None)
    for w in list(Terminator().windows):
        w.isDestroyed = True
        w._session_destroy_handled = True
        w.destroy()
    _pump()


def test_sidebar_marks_share_one_stroke():
    """Close, lock, and unlock are one SVG family, and the lock stays hollow."""
    from terminatorlib.notebook import (
        TAB_CLOSE_ICON, TAB_LOCK_ICON, TAB_UNLOCK_ICON,
    )
    from terminatorlib.util import (
        add_source_icon_path, icon_ink_span, monochrome_pixbuf,
    )

    add_source_icon_path()

    root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'data', 'icons', 'hicolor', 'scalable', 'actions')
    for name in (TAB_CLOSE_ICON, TAB_LOCK_ICON, TAB_UNLOCK_ICON):
        text = open(os.path.join(root, name + '.svg'), encoding='utf-8').read()
        assert 'stroke-width="1.7"' in text
        assert 'stroke-linecap="round"' in text
    spans = [icon_ink_span(name, 16) for name in (
        TAB_CLOSE_ICON, TAB_LOCK_ICON, TAB_UNLOCK_ICON)]
    assert all(span > 0 for span in spans)
    pixbuf = monochrome_pixbuf(TAB_LOCK_ICON, 16)
    assert pixbuf is not None
    pixels = pixbuf.get_pixels()
    stride = pixbuf.get_rowstride()
    channels = pixbuf.get_n_channels()
    clear = opaque = False
    for y in range(4, 12):
        for x in range(4, 12):
            alpha = pixels[y * stride + x * channels + channels - 1]
            clear = clear or alpha < 40
            opaque = opaque or alpha > 200
    assert clear and opaque
    from terminatorlib.notebook import SIDEBAR_ICON_PX
    from terminatorlib.util import svg_icon_surface
    surface = svg_icon_surface(TAB_LOCK_ICON, SIDEBAR_ICON_PX, 2)
    assert surface is not None
    assert surface.get_width() == SIDEBAR_ICON_PX * 2
    assert surface.get_device_scale() == (2.0, 2.0)


def test_swap_child_keeps_lock_and_custom_title(monkeypatch):
    from terminatorlib.factory import Factory
    from terminatorlib.notebook import Notebook
    from terminatorlib.terminal import Terminal
    from terminatorlib.terminator import Terminator

    monkeypatch.setattr(Terminal, 'spawn_child', lambda self, *a, **k: True)
    monkeypatch.setattr(Terminator(), 'terminals', [])
    monkeypatch.setattr(Terminator(), 'windows', [])
    window = Factory().make('Window')
    first = Factory().make('Terminal')
    window.add(first)
    window.show_all()
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)
    window.tab_new(first)
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)
    notebook = window.get_child()
    assert isinstance(notebook, Notebook)
    page = notebook.get_nth_page(0)
    assert isinstance(page, Terminal)
    label = notebook.get_tab_label(page)
    label.set_locked(True)
    label.set_custom_label('kept-name')
    other = Factory().make('Terminal')
    notebook.swap_child(page, other)
    assert notebook.page_num(other) == 0
    new_label = notebook.get_tab_label(other)
    assert new_label is not label
    assert new_label.get_locked() is True
    assert new_label.get_custom_label() == 'kept-name'
    box = Gtk.Box()
    notebook.swap_child(other, box)
    assert notebook.get_tab_label(box) is new_label
    assert new_label.get_locked() is True
    window.isDestroyed = True
    window._session_destroy_handled = True
    window.destroy()
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)
