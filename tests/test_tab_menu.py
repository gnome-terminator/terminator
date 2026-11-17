"""Tab context menu: which actions are available."""

import gi
gi.require_version('Gtk', '3.0')

from terminatorlib.notebook import tab_menu_sensitive


def test_toolbar_icons_share_one_ink_size():
    from terminatorlib.util import icon_scale_for_ink
    # Theme plus is 11px and the arrows span 14px; both land on 20.
    assert abs(icon_scale_for_ink(11, 20, 16, 32) - (20 / 11.0)) < 0.001
    assert abs(icon_scale_for_ink(14, 20, 16, 32) - (20 / 14.0)) < 0.001
    # A tiny glyph cannot grow past the button.
    assert icon_scale_for_ink(4, 20, 16, 32) == 32 / 16.0


def test_tree_drop_can_reorder_or_change_level():
    from terminatorlib.notebook import tree_drop_target
    rows = [
        {'depth': 0, 'page': 0, 'pane': None, 'top': 0, 'bottom': 20},
        {'depth': 1, 'page': 0, 'pane': 0, 'top': 20, 'bottom': 40},
        {'depth': 1, 'page': 0, 'pane': 1, 'top': 40, 'bottom': 60},
        {'depth': 0, 'page': 1, 'pane': None, 'top': 60, 'bottom': 80},
    ]
    assert tree_drop_target(rows, 40, 10) == ('into', 0)
    assert tree_drop_target(rows, 40, 2) == ('tab', 0)
    assert tree_drop_target(rows, 40, 18) == ('tab', 1)
    assert tree_drop_target(rows, 40, 25) == ('pane', 0, 0)
    assert tree_drop_target(rows, 40, 35) == ('pane', 0, 1)
    assert tree_drop_target(rows, 4, 25) == ('tab', 0)
    assert tree_drop_target(rows, 30, 25) == ('tab', 0)
    assert tree_drop_target(rows, 36, 25) == ('pane', 0, 0)
    assert tree_drop_target(rows, 4, 35) == ('tab', 1)
    assert tree_drop_target(rows, 40, 70) == ('into', 1)
    assert tree_drop_target(rows, 40, 90) == ('tab', 2)


def test_tab_drop_index_uses_the_row_midpoint():
    from terminatorlib.notebook import tab_drop_index, reorder_to_index
    spans = [(0, 20), (20, 40), (40, 60)]
    assert tab_drop_index(spans, 0) == 0
    assert tab_drop_index(spans, 9) == 0
    assert tab_drop_index(spans, 10) == 1
    assert tab_drop_index(spans, 45) == 2
    assert tab_drop_index(spans, 50) == 3
    assert tab_drop_index(spans, 80) == 3
    assert tab_drop_index([], 10) == 0
    # Lifting page 0 out and inserting at the end lands on the last slot.
    assert reorder_to_index(0, 3, 3) == 2
    # Dropping a page on itself does not move it.
    assert reorder_to_index(1, 1, 3) is None
    assert reorder_to_index(1, 2, 3) is None
    assert reorder_to_index(2, 0, 3) == 0


def test_tab_nav_does_not_wrap():
    from terminatorlib.notebook import tab_nav_sensitive
    assert tab_nav_sensitive(0, 1) == {'back': False, 'forward': False}
    assert tab_nav_sensitive(0, 3) == {'back': False, 'forward': True}
    assert tab_nav_sensitive(1, 3) == {'back': True, 'forward': True}
    assert tab_nav_sensitive(2, 3) == {'back': True, 'forward': False}


def test_only_tab_can_only_close():
    assert tab_menu_sensitive(0, 1) == {
        'left': False, 'right': False, 'detach': False, 'close': True}


def test_first_of_several_cannot_move_left():
    state = tab_menu_sensitive(0, 3)
    assert state['left'] is False
    assert state['right'] is True
    assert state['detach'] is True
    assert state['close'] is True


def test_middle_tab_can_move_either_way():
    assert tab_menu_sensitive(1, 3) == {
        'left': True, 'right': True, 'detach': True, 'close': True}


def test_last_tab_cannot_move_right():
    assert tab_menu_sensitive(2, 3)['right'] is False
    assert tab_menu_sensitive(2, 3)['left'] is True


def test_out_of_range_is_all_off():
    assert tab_menu_sensitive(-1, 2)['close'] is False
    assert tab_menu_sensitive(2, 2)['close'] is False


def test_folder_name_and_path():
    from terminatorlib.notebook import folder_basename, folder_subtitle
    assert folder_basename('/home/clarence/Projects/terminator') == 'terminator'
    assert folder_subtitle('/home/clarence/Projects/terminator').endswith(
        '/Projects/terminator')
    assert folder_basename('') == ''


def test_focused_pane_names_the_tab():
    from terminatorlib.notebook import choose_naming_terminal
    a, b = object(), object()
    assert choose_naming_terminal([a, b], b) is b
    assert choose_naming_terminal([a, b], None) is a
    assert choose_naming_terminal([a, b], object()) is a


def test_custom_title_beats_the_folder_name():
    from terminatorlib.notebook import TabLabel

    class Notebook(object):
        def get_tab_pos(self):
            from gi.repository import Gtk
            return Gtk.PositionType.LEFT

    label = TabLabel('terminator', Notebook())
    label.set_folder_name('/home/clarence/Projects/terminator')
    assert label.get_label() == 'terminator'
    assert label.folder_label.get_visible() is True
    label.set_custom_label('build')
    label.set_folder_name('/home/clarence/Projects/Android')
    assert label.get_label() == 'build'
    assert 'Android' in label.folder_label.get_text()


def test_split_panes_are_the_second_tree_level():
    from terminatorlib.notebook import sidebar_tree_rows
    pages = [
        ('ClientMessageSync', ['ClientMessageSync']),
        ('ClientMessageSync', ['ClientMessageSync', 'ClientMessageSync']),
        ('terminator', ['left', 'right', 'bottom']),
    ]
    rows = sidebar_tree_rows(pages)
    assert [(row['depth'], row['title'], row['pane']) for row in rows] == [
        (0, 'ClientMessageSync', None),
        (0, 'ClientMessageSync', None),
        (1, 'ClientMessageSync', 0),
        (1, 'ClientMessageSync', 1),
        (0, 'terminator', None),
        (1, 'left', 0),
        (1, 'right', 1),
        (1, 'bottom', 2),
    ]


def test_tab_bar_css_is_a_left_list():
    from terminatorlib.terminator import Terminator
    css = Terminator.tab_bar_css(object())
    assert 'terminator-tab-sidebar' in css
    assert '#f3f3f3' in css
    assert '#e4e4e6' in css
    assert 'terminator-tab-add' in css
    assert 'terminator-tab-tree' in css
    assert 'terminator-tab-row' in css
    assert 'terminator-tab-lock-mark' in css
    assert 'terminator-tab-action:active' in css


def test_close_mark_stays_hidden_until_hover():
    from terminatorlib.notebook import TabLabel

    class Notebook(object):
        def get_tab_pos(self):
            from gi.repository import Gtk
            return Gtk.PositionType.TOP

    label = TabLabel('vscode', Notebook())
    assert label.button is not None
    assert label.button.get_visible() is False
    label._on_pointer_enter(None, None)
    assert label.button.get_visible() is True


def test_pane_menu_moves_do_not_wrap():
    from terminatorlib.notebook import pane_menu_sensitive
    assert pane_menu_sensitive(0, 2) == {
        'up': False, 'down': True, 'promote': True, 'close': True}
    assert pane_menu_sensitive(1, 2)['up'] is True
    assert pane_menu_sensitive(1, 2)['down'] is False
    assert pane_menu_sensitive(1, 3)['down'] is True
    assert pane_menu_sensitive(-1, 2)['close'] is False


def test_child_row_opens_a_pane_menu():
    import inspect
    from terminatorlib.notebook import Notebook
    press = inspect.getsource(Notebook._on_sidebar_row_press)
    assert 'popup_pane_menu' in press
    menu = inspect.getsource(Notebook.popup_pane_menu)
    for label in ('Move Pane _Up', 'Move Pane _Down',
                  'Detach as _Tab', '_Close Pane'):
        assert label in menu


def test_tab_label_opens_menu_on_right_click():
    import inspect
    from terminatorlib.notebook import TabLabel
    src = inspect.getsource(TabLabel.on_button_pressed)
    assert 'event.button == 3' in src
    assert 'popup_tab_menu' in src
    menu = inspect.getsource(TabLabel.popup_tab_menu)
    for label in ('Move Terminal _Left', 'Move Terminal _Right',
                  '_Detach Terminal', '_Close Terminal',
                  '_Keep for next launch'):
        assert label in menu
