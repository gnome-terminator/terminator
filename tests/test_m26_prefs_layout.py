"""m26 P1-2: new pane options live in their own 'Panes' tab and the tall
pages scroll, so the dialog's minimum height is back to upstream (~781 px)."""
import os

import pytest

gi = pytest.importorskip('gi')
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import Gtk  # noqa: E402

from tests.test_m25_round2_fixes import _pump  # noqa: E402

PANE_WIDGETS = (
    'titlebar_buttons_checkbutton', 'titlebar_density_combo',
    'pane_accent_colorbutton', 'pane_overlay_maximise_checkbutton',
    'reduce_motion_combo', 'pane_anim_expand_spinbutton',
    'pane_anim_restore_spinbutton', 'auto_font_scale_checkbutton',
    'auto_font_scale_badge_checkbutton', 'reading_measure_spinbutton')


@pytest.fixture
def pe(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    from terminatorlib import terminal, prefseditor
    term = terminal.Terminal()
    editor = prefseditor.PrefsEditor(term=term)
    yield editor
    editor.window.destroy()


def _is_inside(widget, ancestor):
    while widget is not None:
        if widget is ancestor:
            return True
        widget = widget.get_parent()
    return False


def test_pane_options_moved_to_panes_tab(pe):
    get = pe.builder.get_object
    panes, glob = get('panes_page_box'), get('vbox5')
    for wid in PANE_WIDGETS:
        assert _is_inside(get(wid), panes), wid
        assert not _is_inside(get(wid), glob), wid
    nb = get('notebook1')
    labels = [nb.get_tab_label_text(nb.get_nth_page(i))
              for i in range(nb.get_n_pages())]
    assert labels[:3] == ['Global', 'Panes', 'Profiles']


def test_page_names_resolve_through_scrollers(pe):
    get = pe.builder.get_object
    nb = get('notebook1')
    for name, page in (('global', 'global_page_scroller'),
                       ('panes', 'panes_page_scroller'),
                       ('session', 'session_page_scroller'),
                       ('keybindings', 'vbox124')):
        assert nb.get_nth_page(pe.resolve_page(name)) is get(page), name


def test_tall_pages_scroll(pe):
    get = pe.builder.get_object
    for sid in ('global_page_scroller', 'panes_page_scroller',
                'session_page_scroller'):
        sw = get(sid)
        assert isinstance(sw, Gtk.ScrolledWindow)
        assert sw.get_policy()[0] == Gtk.PolicyType.NEVER
        assert sw.get_propagate_natural_height()


def test_dialog_min_height_not_above_upstream(pe):
    _pump(0.2)
    min_h = pe.window.get_preferred_height()[0]
    assert min_h <= 781, min_h
    # opens at its natural height (all Global options visible) when the
    # screen allows it, never taller than the work area
    _pump(0.3)
    assert pe.window.get_size()[1] >= min_h
