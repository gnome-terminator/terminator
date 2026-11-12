"""r04: translated group names and the per-window KDE blur hint."""
import inspect

from terminatorlib.terminal import Terminal
from terminatorlib.window import Window


def test_group_all_toggle_uses_translated_all(monkeypatch):
    from terminatorlib import window as winmod

    monkeypatch.setattr(winmod, '_', lambda s: {'All': '全部'}.get(s, s))
    calls = []

    class Host(object):
        def ungroup_all(self, widget):
            calls.append('ungroup')

        def group_all(self, widget):
            calls.append('group')

    widget = type('Widget', (), {})()
    widget.group = '全部'
    Window.group_all_toggle(Host(), widget)
    widget.group = 'All'
    Window.group_all_toggle(Host(), widget)
    assert calls == ['ungroup', 'group']


def test_group_tab_toggle_matches_translated_template(monkeypatch):
    from terminatorlib import window as winmod

    table = {
        'Tab %d': '标签 %d',
    }
    monkeypatch.setattr(winmod, '_', lambda s: table.get(s, s))
    calls = []

    class Host(object):
        def ungroup_tab(self, widget):
            calls.append(('ungroup', widget.group))

        def group_tab(self, widget):
            calls.append(('group', widget.group))

    host = Host()
    widget = type('Widget', (), {})()
    for name in ('标签 2', '标签 0'):
        widget.group = name
        Window.group_tab_toggle(host, widget)
    for name in ('Tab 2', '标签2', '全部', None, ''):
        widget.group = name
        Window.group_tab_toggle(host, widget)
    assert calls == [
        ('ungroup', '标签 2'), ('ungroup', '标签 0'),
        ('group', 'Tab 2'), ('group', '标签2'), ('group', '全部'),
        ('group', None), ('group', ''),
    ]

    table['Tab %d'] = '%d 号标签'
    widget.group = '3 号标签'
    Window.group_tab_toggle(host, widget)
    widget.group = '全部'
    Window.group_tab_toggle(host, widget)
    assert calls[-2] == ('ungroup', '3 号标签')
    assert calls[-1] == ('group', '全部')

    table['Tab %d'] = 'タブ%d'
    widget.group = 'タブ2'
    Window.group_tab_toggle(host, widget)
    assert calls[-1] == ('ungroup', 'タブ2')

    table['Tab %d'] = '%d језичак'
    widget.group = '3 језичак'
    Window.group_tab_toggle(host, widget)
    assert calls[-1] == ('ungroup', '3 језичак')

    monkeypatch.setattr(winmod, '_', lambda s: s)
    widget.group = 'Tab 2'
    Window.group_tab_toggle(host, widget)
    widget.group = '标签 2'
    Window.group_tab_toggle(host, widget)
    assert calls[-2] == ('ungroup', 'Tab 2')
    assert calls[-1] == ('group', '标签 2')


def test_group_win_translates_before_interpolating(monkeypatch):
    from terminatorlib import window as winmod

    seen = []

    def translate(text):
        seen.append(text)
        if text == 'Window group %s':
            return '窗口组 %s'
        return text

    monkeypatch.setattr(winmod, '_', translate)
    created = []

    class Groups(object):
        groups = {'one': object()}

        def create_group(self, name):
            created.append(name)

    class Host(object):
        terminator = Groups()

        def get_terminals(self):
            return []

        def set_groups(self, group, terms):
            created.append(('set', group))

    Window.group_win(Host(), None)
    assert 'Window group %s' in seen
    assert created[0] == '窗口组 2'


def _blur_window(profiles, terms):
    win = Window.__new__(Window)

    class Base(object):
        pass

    class Cfg(object):
        base = Base()

    Cfg.base.profiles = profiles
    win.config = Cfg()
    win.get_terminals = lambda: terms
    return win


def test_blur_hint_follows_terminals_in_this_window():
    solid = {'background_blur': False, 'background_type': 'solid'}
    blur_clear = {'background_blur': True, 'background_type': 'transparent'}
    blur_image = {'background_blur': True, 'background_type': 'image'}
    blur_solid = {'background_blur': True, 'background_type': 'solid'}
    profiles = {
        'plain': solid,
        'glass': blur_clear,
        'picture': blur_image,
        'mud': blur_solid,
    }

    class Term(object):
        def __init__(self, name):
            self.name = name

        def get_profile(self):
            return self.name

    assert _blur_window(profiles, [Term('plain')]).blur_hint_wanted() is False
    assert _blur_window(profiles, [Term('glass')]).blur_hint_wanted() is True
    assert _blur_window(profiles, [Term('picture')]).blur_hint_wanted() is True
    assert _blur_window(profiles, [Term('mud')]).blur_hint_wanted() is False
    assert _blur_window(profiles, []).blur_hint_wanted() is False
    assert _blur_window(profiles, [Term('missing')]).blur_hint_wanted() is False


def test_set_blur_behind_uses_an_empty_cardinal(monkeypatch):
    import ctypes
    import ctypes.util
    from gi.repository import GdkX11
    from terminatorlib import window as winmod

    calls = {'change': [], 'delete': []}

    class Lib(object):
        def __init__(self):
            def intern(*_a):
                return 1

            def change(*args):
                calls['change'].append(args)
                return 0

            def delete(*args):
                calls['delete'].append(args)
                return 0

            def flush(*_a):
                return 0

            self.XInternAtom = intern
            self.XChangeProperty = change
            self.XDeleteProperty = delete
            self.XFlush = flush

    class GdkWindow(object):
        def get_xid(self):
            return 42

    win = Window.__new__(Window)
    win.get_window = lambda: GdkWindow()
    monkeypatch.setattr(winmod, 'display_manager', lambda: 'X11')
    monkeypatch.setattr(ctypes.util, 'find_library', lambda _name: 'libX11.so')
    monkeypatch.setattr(ctypes.cdll, 'LoadLibrary', lambda _path: Lib())
    monkeypatch.setattr(GdkX11, 'x11_get_default_xdisplay', lambda: object())

    win.set_blur_behind(True)
    assert len(calls['change']) == 1
    fmt, mode, data, nelements = calls['change'][0][4:8]
    assert (fmt, mode, data, nelements) == (32, 0, None, 0)
    assert calls['delete'] == []

    win.set_blur_behind(False)
    assert len(calls['change']) == 1
    assert len(calls['delete']) == 1

    monkeypatch.setattr(winmod, 'display_manager', lambda: 'WAYLAND')
    before = (len(calls['change']), len(calls['delete']))
    win.set_blur_behind(True)
    win.set_blur_behind(False)
    assert (len(calls['change']), len(calls['delete'])) == before


def test_reconfigure_syncs_each_window():
    from terminatorlib.terminator import Terminator
    src = inspect.getsource(Terminator.reconfigure)
    assert 'should_blur' not in src
    assert 'sync_blur_hint' in src


def test_terminal_syncs_blur_only_when_it_has_a_window():
    term = Terminal.__new__(Terminal)
    calls = []

    class Top(object):
        def sync_blur_hint(self):
            calls.append('sync')

    term.get_toplevel = lambda: term
    term._sync_owning_window_blur()
    assert calls == []
    top = Top()
    term.get_toplevel = lambda: top
    term._sync_owning_window_blur()
    assert calls == ['sync']
