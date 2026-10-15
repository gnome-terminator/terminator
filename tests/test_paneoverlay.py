# GPL v2 only
"""Unit tests for module D (Wave overlay maximise) — pure helpers + hooks."""

from __future__ import print_function

import types

import pytest


def test_ease_out_cubic_bounds():
    from terminatorlib.paneoverlay import ease_out_cubic
    assert ease_out_cubic(0.0) == 0.0
    assert ease_out_cubic(1.0) == 1.0
    assert 0.0 < ease_out_cubic(0.5) < 1.0
    assert ease_out_cubic(-1.0) == 0.0
    assert ease_out_cubic(2.0) == 1.0


def test_ease_in_out_cubic_symmetric():
    from terminatorlib.paneoverlay import ease_in_out_cubic
    assert ease_in_out_cubic(0.0) == 0.0
    assert ease_in_out_cubic(1.0) == 1.0
    mid = ease_in_out_cubic(0.5)
    assert abs(mid - 0.5) < 1e-9


def test_tab_chrome_insets_sidebar_and_strip():
    from terminatorlib.paneoverlay import tab_chrome_insets, margins_from_physical

    class Alloc(object):
        def __init__(self, x, y, w, h):
            self.x, self.y, self.width, self.height = x, y, w, h

    class Box(object):
        def __init__(self, x, y, w, h):
            self.alloc = Alloc(x, y, w, h)
            self.visible = True
            self.parent = None
            self.page = None
            self.show_tabs = False

        def get_allocation(self):
            return self.alloc

        def get_parent(self):
            return self.parent

        def get_visible(self):
            return self.visible

        def get_show_tabs(self):
            return self.show_tabs

        def get_current_page(self):
            return 0

        def get_nth_page(self, _n):
            return self.page

    shell = Box(0, 0, 1000, 700)
    notebook = Box(240, 0, 760, 700)
    notebook.parent = shell
    shell._tab_shell_notebook = notebook
    assert tab_chrome_insets(shell) == (240, 0, 0, 0)

    page = Box(0, 36, 760, 664)
    page.parent = notebook
    notebook.page = page
    notebook.show_tabs = True
    assert tab_chrome_insets(shell) == (240, 36, 0, 0)

    bare = Box(0, 0, 800, 600)
    bare.show_tabs = True
    bare.page = Box(0, 28, 800, 572)
    bare.page.parent = bare
    assert tab_chrome_insets(bare) == (0, 28, 0, 0)

    tiny = Box(0, 0, 1, 1)
    assert tab_chrome_insets(tiny) == (0, 0, 0, 0)
    # An inset that leaves no pane is ignored.
    eaten = Box(0, 0, 100, 100)
    eaten.show_tabs = True
    eaten.page = Box(0, 90, 10, 10)
    eaten.page.parent = eaten
    assert tab_chrome_insets(eaten) == (0, 0, 0, 0)

    assert margins_from_physical(False, 240, 0, 12, 0) == (240, 0, 12, 0)
    assert margins_from_physical(True, 240, 8, 12, 0) == (8, 240, 12, 0)


def test_interpolate_rect():
    from terminatorlib.paneoverlay import interpolate_rect
    a = (0.0, 0.0, 10.0, 20.0)
    b = (100.0, 50.0, 200.0, 100.0)
    assert interpolate_rect(a, b, 0.0) == a
    assert interpolate_rect(a, b, 1.0) == b
    mid = interpolate_rect(a, b, 0.5)
    assert mid == (50.0, 25.0, 105.0, 60.0)


def test_should_reduce_motion_on_off():
    from terminatorlib.paneoverlay import should_reduce_motion

    class C(dict):
        def __getitem__(self, k):
            return dict.__getitem__(self, k)

    assert should_reduce_motion(C(reduce_motion='on')) is True
    assert should_reduce_motion(C(reduce_motion='off')) is False


def test_animator_runs_to_end_with_fake_clock():
    from terminatorlib.paneoverlay import Animator, ease_out_cubic

    ticks = []
    done = []
    clock = {'t': 0.0}
    sources = {}

    def schedule(cb):
        sources['cb'] = cb
        return 1

    def unschedule(_sid):
        sources.pop('cb', None)

    anim = Animator(
        on_tick=lambda p, r: ticks.append((p, r)),
        on_done=lambda cancelled=False: done.append(cancelled),
        clock=lambda: clock['t'],
        schedule=schedule,
        unschedule=unschedule,
    )
    anim.start(100, reverse=False, easing=ease_out_cubic, from_progress=0.0)
    assert anim.running
    # Mid-flight
    clock['t'] = 0.05
    assert sources['cb']() is True
    assert 0.0 < anim.progress < 1.0
    # Finish
    clock['t'] = 0.2
    assert sources['cb']() is False
    assert anim.running is False
    assert abs(anim.progress - 1.0) < 1e-9
    assert done == [False]


def test_animator_reverse_midflight():
    from terminatorlib.paneoverlay import Animator, ease_out_cubic

    clock = {'t': 0.0}
    sources = {}

    def schedule(cb):
        sources['cb'] = cb
        return 1

    anim = Animator(
        on_tick=lambda p, r: None,
        on_done=lambda cancelled=False: None,
        clock=lambda: clock['t'],
        schedule=schedule,
        unschedule=lambda _s: sources.pop('cb', None),
    )
    anim.start(100, reverse=False, easing=ease_out_cubic)
    clock['t'] = 0.05
    sources['cb']()
    mid = anim.progress
    anim.reverse(duration_ms=100)
    assert anim.reversed is True
    assert abs(anim.progress - mid) < 1e-9  # no jump


def test_logical_parent_skips_overlay_and_frame():
    from terminatorlib.util import logical_parent

    class W(object):
        def __init__(self, parent=None, **flags):
            self._parent = parent
            for k, v in flags.items():
                setattr(self, k, v)

        def get_parent(self):
            return self._parent

    # Avoid needing real Gtk.Overlay: monkeypatch isinstance check by using
    # a stand-in that util.logical_parent recognises via is_pane_frame only,
    # and a fake Overlay-like object by patching.
    import terminatorlib.util as util
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk

    win = W()
    # Real Overlay instance (no realize needed for isinstance)
    overlay = Gtk.Overlay()
    frame = W(overlay, is_pane_frame=True)
    term = W(frame)
    # Re-parent overlay under window for the walk
    # Gtk.Overlay.get_parent may be None; simulate by wrapping walk:
    # logical_parent uses widget.get_parent() — set via a thin proxy

    class Proxy(object):
        def __init__(self, real, parent):
            self._real = real
            self._parent = parent
            self.is_pane_frame = getattr(real, 'is_pane_frame', False)

        def get_parent(self):
            return self._parent

        def __getattr__(self, name):
            return getattr(self._real, name)

    # Build: term -> frame -> overlay_proxy -> win
    # isinstance(overlay_proxy, Gtk.Overlay) is False, so put real overlay
    # in the chain with a patched get_parent.

    class OverlayProxy(Gtk.Overlay):
        def __init__(self, parent):
            Gtk.Overlay.__init__(self)
            self._lp_parent = parent

        def get_parent(self):
            return self._lp_parent

    ov = OverlayProxy(win)
    fr = W(ov, is_pane_frame=True)
    t = W(fr)
    assert logical_parent(t) is win
    assert logical_parent(fr) is win


def test_logical_parent_via_placeholder_on_terminal():
    from terminatorlib.util import logical_parent

    class W(object):
        def __init__(self, parent=None):
            self._parent = parent
            self._overlay_placeholder = None

        def get_parent(self):
            return self._parent

    paned = W()
    placeholder = W(paned)
    frame = W()  # would be PaneFrame; not needed
    term = W(frame)
    term._overlay_placeholder = placeholder
    assert logical_parent(term) is paned


def test_enumerate_descendants_counts_placeholder_once():
    from terminatorlib.util import enumerate_descendants

    class FakeTerm(object):
        pass

    class FakePlaceholder(object):
        is_pane_placeholder = True

        def __init__(self, term):
            self.terminal = term

    class FakePaned(object):
        def __init__(self, children):
            self._children = children

        def get_children(self):
            return list(self._children)

    term_a = FakeTerm()
    term_b = FakeTerm()
    ph = FakePlaceholder(term_a)
    paned = FakePaned([ph, term_b])

    # Factory.isinstance must recognise nothing here — patch maker
    import terminatorlib.util as util
    import terminatorlib.factory as factory

    class FakeFactory(object):
        def isinstance(self, obj, name):
            if name == 'Container':
                return obj is paned or type(obj).__name__ == 'FakePaned'
            if name == 'Terminal':
                return isinstance(obj, FakeTerm)
            return False

    real = factory.Factory
    factory.Factory = FakeFactory
    try:
        # Also need paned to be seen as Container when walking from a parent
        class Root(object):
            def get_children(self):
                return [paned]

        # First call: parent.get_children → paned recognised as Container
        # Our FakeFactory.isinstance(paned, 'Container') is True
        containers, terminals = enumerate_descendants(Root())
        assert term_a in terminals
        assert term_b in terminals
        assert len(terminals) == 2
        assert terminals.count(term_a) == 1
    finally:
        factory.Factory = real


def test_is_maximised_pane_overlay_path():
    from terminatorlib.window import Window

    class Ctrl(object):
        def __init__(self, term):
            self._term = term

        def is_active(self):
            return True

        def is_maximised_pane(self, t):
            return t is self._term

    a, b = object(), object()
    win = Window.__new__(Window)
    win._overlay = Ctrl(a)
    win.zoom_data = None
    win.term_zoomed = True
    # is_zoomed reads GObject property — stub it
    win.is_zoomed = lambda: True
    assert Window.is_maximised_pane(win, a) is True
    assert Window.is_maximised_pane(win, b) is False


def test_describe_layout_sets_maximised_pane_flag():
    """PanePlaceholder.describe_layout delegates and stamps maximised_pane."""
    import gi
    gi.require_version('Gtk', '3.0')
    from terminatorlib.paneoverlay import PanePlaceholder

    class FakeTerm(object):
        uuid = 'u-1'

        def describe_layout(self, count, parent, global_layout, child_order,
                            save_cwd=False):
            global_layout['terminal%d' % count] = {
                'type': 'Terminal', 'uuid': self.uuid, 'order': child_order}
            return count + 1

    term = FakeTerm()
    ph = PanePlaceholder.__new__(PanePlaceholder)
    ph._terminal = term
    ph._pixbuf = None
    layout = {}
    count = ph.describe_layout(0, 'child0', layout, 0)
    assert count == 1
    assert layout['terminal0']['maximised_pane'] == 'True'
