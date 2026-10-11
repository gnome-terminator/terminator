"""Tests for terminal context menu actions."""

import os
import sys

import gi

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))
gi.require_version("Gtk", "3.0")

from gi.repository import Gtk

from terminatorlib.terminal_popup_menu import TerminalPopupMenu


class FakeContainer:
    """Container recording confirmation requests."""

    def __init__(self, response, parent=None):
        self.response = response
        self.parent = parent
        self.confirmations = []

    def construct_confirm_close(self, window, child):
        self.confirmations.append((window, child))
        return self.response

    def get_parent(self):
        return self.parent


class FakeParent:
    """Intermediate widget without close confirmation behavior."""

    def __init__(self, parent):
        self.parent = parent

    def get_parent(self):
        return self.parent


class FakeTerminal:
    """Terminal recording close calls."""

    def __init__(self, parent=None, toplevel=None):
        self.parent = parent
        self.toplevel = toplevel
        self.closed = False

    def get_parent(self):
        return self.parent

    def get_toplevel(self):
        return self.toplevel

    def close(self):
        self.closed = True


def popup_for(terminal):
    popup = TerminalPopupMenu.__new__(TerminalPopupMenu)
    popup.terminal = terminal
    return popup


class _Classes(object):
    def __init__(self):
        self.classes = set()

    def add_class(self, name):
        self.classes.add(name)

    def remove_class(self, name):
        self.classes.discard(name)


def test_focus_border_hidden_for_a_single_pane():
    from terminatorlib.terminal import Terminal
    ctx = _Classes()

    class Term(object):
        def __init__(self, multiple):
            self.multiple = multiple

        def get_style_context(self):
            return ctx

        def _focus_border_wanted(self):
            return self.multiple

    Terminal.set_focus_chrome(Term(False), True)
    assert 'terminator-term-focused' not in ctx.classes
    assert 'terminator-term-unfocused' in ctx.classes

    Terminal.set_focus_chrome(Term(True), True)
    assert 'terminator-term-focused' in ctx.classes
    assert 'terminator-term-unfocused' not in ctx.classes


def test_only_one_pane_keeps_the_focus_border():
    from terminatorlib.terminal import Terminal

    class Ctx(object):
        def __init__(self):
            self.classes = set()

        def add_class(self, name):
            self.classes.add(name)

        def remove_class(self, name):
            self.classes.discard(name)

    class Win(object):
        def __init__(self, terms):
            self.terms = terms

        def get_visible_terminals(self):
            return self.terms

    class Term(object):
        def __init__(self):
            self.ctx = Ctx()

        def get_style_context(self):
            return self.ctx

        def set_focus_chrome(self, focused, multiple=None):
            Terminal.set_focus_chrome(self, focused, multiple=multiple)

    a, b = Term(), Term()
    win = Win([a, b])
    a.get_toplevel = b.get_toplevel = lambda: win
    Terminal.refresh_visible_focus_chrome(a, focused=b)
    assert 'terminator-term-focused' not in a.ctx.classes
    assert 'terminator-term-focused' in b.ctx.classes
    Terminal.refresh_visible_focus_chrome(b, focused=a)
    assert 'terminator-term-focused' in a.ctx.classes
    assert 'terminator-term-focused' not in b.ctx.classes


def test_focus_border_is_not_a_transparent_css_frame():
    from terminatorlib.terminator import Terminator

    class App(object):
        def pane_accent_color(self):
            return '#3fb950'

    css = Terminator.pane_chrome_css(App())
    assert 'transparent' not in css
    assert 'border: none' in css


def test_focus_border_strokes_only_the_focused_pane():
    from terminatorlib.terminal import Terminal

    class Ctx(object):
        def __init__(self, focused):
            self.focused = focused

        def has_class(self, name):
            return self.focused and name == 'terminator-term-focused'

    class Pen(object):
        def __init__(self):
            self.stroked = False

        def save(self):
            pass

        def restore(self):
            pass

        def set_source_rgba(self, r, g, b, a):
            self.rgba = (r, g, b, a)

        def set_line_width(self, _width):
            pass

        def rectangle(self, *_args):
            pass

        def stroke(self):
            self.stroked = True

    class Widget(object):
        def __init__(self, focused):
            self.ctx = Ctx(focused)

        def get_style_context(self):
            return self.ctx

        def get_allocated_width(self):
            return 40

        def get_allocated_height(self):
            return 20

    class Term(object):
        titlebar = type('Bar', (), {'_bar_bg': '#ffffff'})()

        def get_toplevel(self):
            return None

    plain = Pen()
    Terminal._draw_focus_border(Term(), Widget(False), plain)
    assert plain.stroked is False
    marked = Pen()
    Terminal._draw_focus_border(Term(), Widget(True), marked)
    assert marked.stroked is True
    assert marked.rgba[0] > 0.99 and marked.rgba[1] > 0.99 and marked.rgba[2] > 0.99


def test_focus_ring_uses_the_titlebar_background():
    from terminatorlib.terminal import Terminal

    class Term(object):
        titlebar = type('Bar', (), {'_bar_bg': '#0076c9'})()

    assert Terminal._focus_ring_color(Term()) == '#0076c9'

    class Bare(object):
        config = {'title_transmit_bg_color': '#ffffff'}

    assert Terminal._focus_ring_color(Bare()) == '#ffffff'


def test_single_pane_hides_its_titlebar():
    from terminatorlib.titlebar import Titlebar

    class Bar(object):
        _split_needs_titlebar = Titlebar._split_needs_titlebar

        def __init__(self, multiple, configured=True, group=None, editing=False):
            self.multiple = multiple
            self.config = {'show_titlebar': configured}
            self.terminal = type('Term', (), {'group': group})()
            self._editing = editing

        def editing(self):
            return self._editing

        def get_toplevel(self):
            return type('Win', (), {
                'has_multiple_terms': lambda _win: self.multiple
            })()

    assert Titlebar.get_desired_visibility(Bar(False)) is False
    assert Titlebar.get_desired_visibility(Bar(True)) is True
    assert Titlebar.get_desired_visibility(Bar(True, configured=False)) is False
    assert Titlebar.get_desired_visibility(Bar(False, group='work')) is True


def test_hidden_titlebar_keeps_the_terminal_menu():
    popup = popup_for(FakeTerminal())
    popup.config = {'show_titlebar': True}

    class Hidden(object):
        def get_visible(self):
            return False

    popup.terminal.titlebar = Hidden()
    assert popup.wants_chrome_menu(None, False) is True


def test_vte_menu_does_not_end_on_a_separator():
    from terminatorlib.terminal_popup_menu import TerminalPopupMenu

    class Vte(object):
        def get_has_selection(self):
            return False

        def get_input_enabled(self):
            return True

    class Bar(object):
        def get_property(self, _name):
            return False

    class Top(object):
        def get_child(self):
            return None

        def has_multiple_terms(self):
            return True

    class Term(object):
        is_held_open = False
        matches = {}
        vte = Vte()
        scrollbar = Bar()

        class titlebar(object):
            @staticmethod
            def get_visible():
                return True

        def is_zoomed(self):
            return False

        def get_profile(self):
            return 'default'

        def get_cwd(self):
            return '/tmp'

        def emit(self, *_args):
            pass

        def get_toplevel(self):
            return Top()

        def maximise(self, *_args):
            pass

    captured = []
    original = Gtk.Menu.popup_at_pointer
    Gtk.Menu.popup_at_pointer = lambda self, *_a: captured.append(self)
    try:
        popup = TerminalPopupMenu(Term())
        popup.show(popup.terminal, None)
    finally:
        Gtk.Menu.popup_at_pointer = original
    menu = captured[-1]
    children = menu.get_children()
    assert children
    assert not isinstance(children[-1], Gtk.SeparatorMenuItem)
    previous_rule = False
    for child in children:
        rule = isinstance(child, Gtk.SeparatorMenuItem)
        assert not (rule and previous_rule)
        previous_rule = rule


def test_chrome_items_follow_titlebar():
    """Settings stay on the titlebar menu while the titlebar is visible."""
    popup = popup_for(FakeTerminal())
    popup.config = {'show_titlebar': True}
    assert popup.wants_chrome_menu(None, False) is False
    assert popup.wants_chrome_menu(None, True) is True
    assert popup.wants_chrome_menu(object(), False) is True
    popup.config = {'show_titlebar': False}
    assert popup.wants_chrome_menu(None, False) is True


def test_close_terminal_closes_after_confirmation_accepts():
    """Context menu close uses the container confirmation path."""
    window = object()
    container = FakeContainer(Gtk.ResponseType.ACCEPT)
    terminal = FakeTerminal(parent=container, toplevel=window)

    popup_for(terminal).close_terminal()

    assert terminal.closed
    assert container.confirmations == [(window, terminal)]


def test_close_terminal_keeps_terminal_open_when_confirmation_rejects():
    """A rejected confirmation prevents context menu close."""
    container = FakeContainer(Gtk.ResponseType.REJECT)
    terminal = FakeTerminal(parent=container, toplevel=object())

    popup_for(terminal).close_terminal()

    assert not terminal.closed
    assert container.confirmations == [(terminal.get_toplevel(), terminal)]


def test_close_terminal_finds_confirmation_container_above_parent_widget():
    """Intermediate GTK widgets do not bypass close confirmation."""
    container = FakeContainer(Gtk.ResponseType.ACCEPT)
    parent = FakeParent(container)
    terminal = FakeTerminal(parent=parent, toplevel=object())

    popup_for(terminal).close_terminal()

    assert terminal.closed
    assert container.confirmations == [(terminal.get_toplevel(), terminal)]
