"""m26: round2-ux P2 fixes (titlebar refresh, cwd probe, narrow titlebars,
shortcut conflicts, icon fallback, 'None' title, version)."""
import os

import pytest

gi = pytest.importorskip('gi')
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')
from gi.repository import Gtk  # noqa: E402

from terminatorlib import cwd as cwd_mod  # noqa: E402
from terminatorlib.keybindings import Keybindings  # noqa: E402
from terminatorlib.config import DEFAULTS  # noqa: E402


# ---- P2-2 cwd probe -------------------------------------------------------

def test_get_pid_cwd_is_cheap_and_correct(monkeypatch):
    import psutil
    monkeypatch.setattr(psutil.Process, 'as_dict',
                        lambda *a, **k: pytest.fail('as_dict used'))
    assert cwd_mod.get_pid_cwd(os.getpid()) == os.getcwd()
    assert cwd_mod.get_pid_cwd() == os.getcwd()


def test_get_pid_cwd_falls_back_to_psutil(monkeypatch):
    def nolink(path):
        raise OSError('no /proc')
    monkeypatch.setattr(cwd_mod, '_readlink', nolink)
    assert cwd_mod.get_pid_cwd(os.getpid()) == os.getcwd()


def test_cwd_probe_skipped_while_tui_active(monkeypatch):
    from terminatorlib import terminal as term_mod
    from terminatorlib.terminal import Terminal
    t = Terminal.__new__(Terminal)
    t.__dict__['pid'] = 4242

    class Det(object):
        active = True

    class Alt(object):
        detector = Det()
    t.__dict__['altscreen'] = Alt()
    calls = []
    monkeypatch.setattr(term_mod, 'get_pid_cwd',
                        lambda pid: calls.append(pid) or '/x')
    assert t.cwd_probe_check() is False and calls == []
    Det.active = False
    t.cwd_probe_check()
    assert calls == [4242]


# ---- P2-4 shortcut conflicts ---------------------------------------------

def _kb(overrides):
    keys = dict(DEFAULTS['keybindings'])
    keys.update(overrides)
    kb = Keybindings()
    kb.configure(keys)
    return kb


def _owner(kb, binding):
    keyval, mask = kb._parsebinding(binding)
    from gi.repository import Gdk
    if mask & Gdk.ModifierType.SHIFT_MASK:
        keyvals = Gdk.keyval_convert_case(keyval)
        if keyvals[0] != keyvals[1]:
            keyval = keyvals[1]
            mask &= ~Gdk.ModifierType.SHIFT_MASK
    else:
        keyval = Gdk.keyval_to_lower(keyval)
    return kb._lookup.get(mask, {}).get(keyval)


def test_user_binding_beats_new_default():
    kb = _kb({'new_window': '<Shift><Control>Return',
              'hide_window': '<Shift>Escape'})
    assert _owner(kb, '<Shift><Control>Return') == 'new_window'
    assert _owner(kb, '<Shift>Escape') == 'hide_window'
    assert kb.resolved_bindings('maximise') == []
    assert kb.resolved_bindings('restore_maximised') == []
    assert kb.resolved_bindings('new_window') == ['<Shift><Control>Return']
    assert 'maximise' in kb.shadowed


def test_defaults_resolve_to_themselves():
    kb = _kb({})
    assert kb.resolved_bindings('maximise') == ['<Shift><Control>Return']
    assert kb.resolved_bindings('restore_maximised') == ['<Shift>Escape']
    assert not kb.shadowed


def test_two_user_bindings_last_writer_wins():
    kb = _kb({'new_window': '<Shift><Control>Return',
              'maximise': '<Shift><Control>Return'})
    # both user-set: unchanged upstream behaviour (dict order)
    assert _owner(kb, '<Shift><Control>Return') in ('new_window', 'maximise')


def test_titlebar_tooltip_uses_resolved_binding(monkeypatch):
    from terminatorlib.terminator import Terminator
    from tests.test_titlebar_chrome import FakeTerminal, make_config
    keys = dict(DEFAULTS['keybindings'])
    keys['new_window'] = '<Shift><Control>Return'
    monkeypatch.setattr(Terminator(), 'keybindings', _kb(keys))
    from terminatorlib.titlebar import Titlebar
    tb = Titlebar(FakeTerminal(make_config(keybindings=keys)))
    # maximise lost Ctrl+Shift+Return → fall back to toggle_zoom (Ctrl+Shift+X)
    label = tb._accel_label('maximise', 'toggle_zoom')
    assert 'Return' not in label and 'Enter' not in label
    tb.destroy()


# ---- P2-3 / P2-5 titlebar -------------------------------------------------

@pytest.fixture
def titlebar():
    from tests.test_titlebar_chrome import FakeTerminal, make_config
    from terminatorlib.titlebar import Titlebar
    tb = Titlebar(FakeTerminal(make_config()))
    yield tb
    tb.destroy()


def test_narrow_titlebar_hides_badge_then_gear_then_max(titlebar):
    tb = titlebar
    tb.set_scale_badge(0.8, False)
    for width, badge, gear, mx in ((400, True, True, True),
                                   (230, False, True, True),
                                   (190, False, False, True),
                                   (120, False, False, False)):
        tb._collapse_level = tb._collapse_level_for(width)
        tb._apply_collapse()
        assert tb.scale_badge.get_visible() is badge, width
        assert tb.btn_gear.get_visible() is gear, width
        assert tb.btn_max.get_visible() is mx, width
        assert tb.btn_close.get_visible(), width
    assert tb._title_viewport.get_size_request()[0] >= 6 * 4


def test_buttons_hidden_by_config_stay_hidden(titlebar):
    tb = titlebar
    tb.config['titlebar_buttons'] = False
    tb.apply_chrome_config()
    tb._collapse_level = 0
    tb._apply_collapse()
    assert not tb.btn_gear.get_visible() and not tb.btn_max.get_visible()


def test_icon_fallback_to_text(monkeypatch):
    from terminatorlib import titlebar as tbmod
    monkeypatch.setattr(tbmod, '_ICON_LOADABLE', {})

    class Theme(object):
        def has_icon(self, name):
            return True

        def load_icon(self, *a):
            raise gi.repository.GLib.Error('no svg loader')
    monkeypatch.setattr(Gtk.IconTheme, 'get_default', staticmethod(lambda: Theme()))
    from tests.test_titlebar_chrome import FakeTerminal, make_config
    tb = tbmod.Titlebar(FakeTerminal(make_config()))
    assert tb.btn_close.get_label() == '\u2715'
    assert tb.btn_gear.get_label() == '\u2699'
    assert tb.btn_max.get_label() in ('\u2922', '\u2921')
    assert tb.btn_close.get_image() is None
    tb.destroy()


# ---- P2-6 title -------------------------------------------------------------

def test_no_literal_none_title(monkeypatch):
    from terminatorlib.terminal import Terminal

    class V(object):
        def get_window_title(self):
            return None
    t = Terminal.__new__(Terminal)
    t.__dict__.update({'vte': V(), 'command': None, 'pid': os.getpid()})
    title = t.get_window_title()
    assert title and title != 'None'
    t.__dict__['pid'] = None
    monkeypatch.setenv('SHELL', '/usr/bin/zsh')
    assert t.get_window_title() == 'zsh'
    t.__dict__['command'] = 'htop'
    assert t.get_window_title() == 'htop'


# ---- P2-10 version ------------------------------------------------------------

def test_version_marks_fork():
    from terminatorlib.version import APP_VERSION
    assert APP_VERSION.startswith('2.1.6') and APP_VERSION != '2.1.6'


# ---- P2-1 titlebar refresh on focus change ---------------------------------

from tests.test_m25_round2_fixes import _pump, app, sess  # noqa: E402,F401


def test_focus_refresh_walks_tree_once(app, monkeypatch):
    from terminatorlib.window import Window
    from terminatorlib.titlebar import Titlebar
    w = app(4)
    terms = w.get_terminals()
    calls = {'multi': 0, 'refresh': 0}
    real_refresh = Titlebar.refresh_maximise_state

    def counting_refresh(self, *a, **k):
        calls['refresh'] += 1
        return real_refresh(self, *a, **k)
    monkeypatch.setattr(Window, 'has_multiple_terms',
                        lambda self: calls.__setitem__('multi', calls['multi'] + 1) or True)
    monkeypatch.setattr(Titlebar, 'refresh_maximise_state', counting_refresh)
    w._titlebar_max_sig = None
    terms[0].refresh_titlebars_maximise_state()
    assert calls == {'multi': 0, 'refresh': 4}
    # plain focus move, same structure: nothing to redo
    terms[1].refresh_titlebars_maximise_state()
    assert calls['refresh'] == 4
    # structure change (split) → refreshed again
    before = calls['refresh']
    terms[1].get_parent().split_axis(terms[1], True)
    _pump(0.1)
    w.get_terminals()[0].refresh_titlebars_maximise_state()
    assert calls['refresh'] > before
    assert w._titlebar_max_sig[0] == tuple(
        id(t) for t in w.get_visible_terminals())
