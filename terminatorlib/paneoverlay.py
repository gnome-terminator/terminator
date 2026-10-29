# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""paneoverlay.py - Wave-style single-pane overlay maximise (module D / M3).

Temporary Gtk.Overlay while maximised: float one pane over the pane area
with margins, dim siblings, optional expand/restore animation. The tab list
(left sidebar, or the native tab strip) stays outside that area. Not
full-window zoom and not the legacy reparent zoom.

m37 (smooth animation): frames come from the widget frame clock
(add_tick_callback) with the clock starting at the first painted frame, so
the reparent/relayout before it never eats animation time. Per frame only a
server-side snapshot surface is scaled and the dimmer repainted; the real
terminal (already at its final size, one PTY resize) is not drawn until the
hand-over, so no VTE reflow, font change or opacity group happens mid-flight.
"""

from __future__ import print_function

import time

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

from .util import dbg, err, logical_parent
from .config import Config


# ---------------------------------------------------------------------------
# Geometry / motion helpers (pure; unit-testable)
# ---------------------------------------------------------------------------

def ease_out_cubic(t):
    t = max(0.0, min(1.0, float(t)))
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_cubic(t):
    t = max(0.0, min(1.0, float(t)))
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 - ((-2.0 * t + 2.0) ** 3) / 2.0


def interpolate_rect(a, b, t):
    """Linear interpolate two (x, y, w, h) tuples."""
    t = max(0.0, min(1.0, float(t)))
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
        a[3] + (b[3] - a[3]) * t,
    )


def should_reduce_motion(config=None):
    """True when zoom animation should be skipped (dim fade only)."""
    if config is None:
        config = Config()
    try:
        mode = config['reduce_motion']
    except Exception:
        mode = 'system'
    if mode == 'on':
        return True
    if mode == 'off':
        return False
    # system
    try:
        settings = Gtk.Settings.get_default()
        if settings is not None:
            return not bool(settings.get_property('gtk-enable-animations'))
    except Exception:
        pass
    return False


def _widget_for_gdk_window(widget, gdk_win):
    """Walk up until widget.get_window() is gdk_win."""
    cur = widget
    while cur is not None:
        try:
            if cur.get_window() is gdk_win:
                return cur
        except Exception:
            pass
        cur = cur.get_parent()
    return None


def _translate_xy(widget, dest, x=0, y=0):
    """PyGObject may strip the gboolean and return (x, y) only."""
    try:
        rv = widget.translate_coordinates(dest, x, y)
    except Exception:
        return None
    if rv is None:
        return None
    if isinstance(rv, tuple):
        if len(rv) == 3:
            ok, tx, ty = rv
            return (int(tx), int(ty)) if ok else None
        if len(rv) == 2:
            return (int(rv[0]), int(rv[1]))
    return None


def _scale_factor(widget, gdk_win=None):
    """m33: integer HiDPI scale (>=1) of the widget / its GdkWindow."""
    for obj in (gdk_win, widget):
        try:
            f = int(obj.get_scale_factor())
            if f >= 1:
                return f
        except Exception:
            pass
    return 1


def _capture_scaled(gdk_win, wx, wy, w, h, scale):
    """m33: snapshot at device resolution (w*scale x h*scale) so the
    maximize animation is not blurry on HiDPI. None on failure."""
    try:
        import cairo
        dw, dh = int(w * scale), int(h * scale)
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, dw, dh)
        cr = cairo.Context(surf)
        cr.scale(scale, scale)
        Gdk.cairo_set_source_window(cr, gdk_win, -float(wx), -float(wy))
        cr.paint()
        surf.flush()
        return Gdk.pixbuf_get_from_surface(surf, 0, 0, dw, dh)
    except Exception as ex:
        dbg('HiDPI capture failed, falling back: %s' % ex)
        return None


def placeholder_pixbuf_scale(pixbuf, logical_w, scale=None):
    """m33 fix-review: user-space factor to draw a snapshot at the logical
    size it was captured at. logical_w is the terminal's logical width at
    capture time (not the placeholder's current allocation, which can
    change on resize). Device-res pixbufs (w*scale) get logical_w/pw, so
    any capture scale works and later window/pane resizes or monitor
    scale changes don't break it. scale is accepted for compatibility."""
    try:
        pw = int(pixbuf.get_width())
        lw = int(logical_w or 0)
    except Exception:
        return 1.0
    if lw > 0 and pw > lw:
        return float(lw) / float(pw)
    return 1.0


def _window_is_rgba(widget):
    """m38: True when widget's toplevel uses the screen's RGBA visual
    (transparent profile backgrounds), so snapshots must keep alpha."""
    try:
        top = widget.get_toplevel()
        visual = top.get_visual() if top is not None else None
        if visual is None:
            return False
        rgba = top.get_screen().get_rgba_visual()
        return rgba is not None and visual == rgba
    except Exception:
        return False


def _is_wayland(widget):
    try:
        disp = widget.get_display()
        return 'wayland' in type(disp).__name__.lower()
    except Exception:
        return False


def surface_looks_blank(surf, w, h, samples=16, threshold=8):
    """m38: downsample surf to samples x samples and report whether every
    pixel is (near) black or fully transparent, i.e. a stale/empty capture.
    Best effort: a genuinely all-black pane also counts as blank, which only
    costs the zoom animation (fade fallback), never correctness."""
    try:
        import cairo
        n = max(1, int(samples))
        img = cairo.ImageSurface(cairo.FORMAT_ARGB32, n, n)
        cr = cairo.Context(img)
        cr.scale(float(n) / max(1, w), float(n) / max(1, h))
        cr.set_source_surface(surf, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_FAST)
        cr.paint()
        img.flush()
        data = bytes(img.get_data())
        stride = img.get_stride()
        for y in range(n):
            row = data[y * stride:y * stride + 4 * n]
            for x in range(0, 4 * n, 4):
                px = row[x:x + 4]       # B G R A (native little endian)
                if px[3] > threshold and max(px[0], px[1], px[2]) > threshold:
                    return False
        return True
    except Exception as ex:
        dbg('surface_looks_blank: %s' % ex)
        return False


def capture_widget_surface(widget):
    """m37: snapshot widget's on-screen area into a surface similar to its
    GdkWindow (server-side copy on X11, HiDPI-aware via the window's device
    scale). Returns (surface, logical_w, logical_h) or None. Painting this
    each frame is a cheap server-side composite, unlike a client pixbuf that
    is converted and uploaded again on every frame."""
    try:
        import cairo
        gdk_win = widget.get_window()
        if gdk_win is None:
            return None
        alloc = widget.get_allocation()
        w, h = int(alloc.width), int(alloc.height)
        if w <= 1 or h <= 1:
            return None
        owner = _widget_for_gdk_window(widget, gdk_win) or widget
        xy = _translate_xy(widget, owner, 0, 0)
        if xy is None:
            return None
        content = (cairo.CONTENT_COLOR_ALPHA if _window_is_rgba(widget)
                   else cairo.CONTENT_COLOR)
        surf = gdk_win.create_similar_surface(content, w, h)
        if surf is None:
            return None
        cr = cairo.Context(surf)
        if content == cairo.CONTENT_COLOR_ALPHA:
            cr.set_operator(cairo.OPERATOR_SOURCE)
        Gdk.cairo_set_source_window(cr, gdk_win, -float(xy[0]),
                                    -float(xy[1]))
        cr.paint()
        surf.flush()
        # m38: outside a draw cycle Wayland may hand back a stale/empty
        # backing store; a blank capture would flash black, so report
        # failure and let the caller take the fallback/fade path.
        if _is_wayland(widget) and surface_looks_blank(surf, w, h):
            dbg('capture_widget_surface: blank snapshot on Wayland')
            return None
        return (surf, w, h)
    except Exception as ex:
        dbg('capture_widget_surface failed: %s' % ex)
        return None


def pixbuf_to_surface(pixbuf, widget=None, logical_w=0):
    """Convert a (possibly device-resolution) pixbuf ONCE into a cairo
    surface; returns (surface, logical_w, logical_h) or None."""
    if pixbuf is None:
        return None
    try:
        pw, ph = int(pixbuf.get_width()), int(pixbuf.get_height())
        k = placeholder_pixbuf_scale(pixbuf, logical_w)
        lw, lh = max(1, int(round(pw * k))), max(1, int(round(ph * k)))
        scale = max(1, int(round(1.0 / k))) if k < 1.0 else 1
        gdk_win = widget.get_window() if widget is not None else None
        surf = Gdk.cairo_surface_create_from_pixbuf(pixbuf, scale, gdk_win)
        return (surf, lw, lh)
    except Exception as ex:
        dbg('pixbuf_to_surface failed: %s' % ex)
        return None


def snap_has_alpha(snap):
    """True for a snapshot captured with alpha (RGBA / transparent window)."""
    try:
        import cairo
        return snap is not None and \
            snap[0].get_content() == cairo.CONTENT_COLOR_ALPHA
    except Exception:
        return False


def paint_snapshot(cr, snap, rect, alpha=1.0, replace=False):
    """Draw snap=(surface, w, h) stretched into rect=(x, y, w, h).
    Bilinear keeps it on the XRender fast path (GOOD may fall back to a
    client-side box filter when shrinking).

    replace (transparent backgrounds): an opaque-phase snapshot REPLACES
    what is under it (OPERATOR_SOURCE), exactly like the live VTE does with
    its see-through background, so the dimmer below doesn't stack on top of
    the terminal's own alpha (a dark pulse mid-flight). Only for
    alpha >= 1; a fading snapshot is blended OVER the live terminal."""
    if snap is None or alpha <= 0.0:
        return False
    surf, sw, sh = snap
    x, y, w, h = rect
    if w <= 1 or h <= 1 or sw <= 0 or sh <= 0:
        return False
    import cairo
    cr.save()
    cr.rectangle(x, y, w, h)
    cr.clip()
    cr.translate(x, y)
    cr.scale(w / float(sw), h / float(sh))
    cr.set_source_surface(surf, 0, 0)
    try:
        cr.get_source().set_filter(cairo.FILTER_BILINEAR)
    except Exception:
        pass
    if replace and alpha >= 1.0:
        # PAD: no transparent fringe from sampling past the surface edge
        try:
            cr.get_source().set_extend(cairo.EXTEND_PAD)
        except Exception:
            pass
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
    elif alpha >= 1.0:
        cr.paint()
    else:
        cr.paint_with_alpha(alpha)
    cr.restore()
    return True


def capture_terminal_pixbuf(terminal):
    """Snapshot a terminal's VTE region. Never call terminal.draw(cr)."""
    try:
        widget = getattr(terminal, 'vte', None) or terminal
        gdk_win = widget.get_window()
        if gdk_win is None:
            return None
        alloc = widget.get_allocation()
        if alloc.width <= 1 or alloc.height <= 1:
            return None
        owner = _widget_for_gdk_window(widget, gdk_win) or widget
        xy = _translate_xy(widget, owner, 0, 0)
        if xy is None:
            return None
        wx, wy = xy
        scale = _scale_factor(widget, gdk_win)
        if scale > 1:
            pb = _capture_scaled(gdk_win, wx, wy, alloc.width,
                                 alloc.height, scale)
            if pb is not None:
                return pb
        pb = Gdk.pixbuf_get_from_window(
            gdk_win, int(wx), int(wy), int(alloc.width), int(alloc.height))
        return pb
    except Exception as ex:
        dbg('capture_terminal_pixbuf failed: %s' % ex)
        return None


def _rect_from_widget(widget, relative_to):
    """Return (x, y, w, h) of widget relative to relative_to."""
    alloc = widget.get_allocation()
    xy = _translate_xy(widget, relative_to, 0, 0)
    if xy is None:
        x, y = alloc.x, alloc.y
    else:
        x, y = xy
    return (float(x), float(y), float(alloc.width), float(alloc.height))


def _widget_size(widget):
    try:
        alloc = widget.get_allocation()
        return int(alloc.width), int(alloc.height)
    except Exception:
        return 0, 0


def _pos_in(widget, ancestor):
    """Origin of widget inside ancestor.

    ``get_allocation().x/y`` is relative to the nearest GdkWindow, so a
    header bar makes it larger than the offset inside the overlay. Prefer
    ``translate_coordinates``. Allocation is only a parent-relative fallback
    for unrealized widgets and unit-test fakes.
    """
    xy = _translate_xy(widget, ancestor, 0, 0)
    if xy is not None:
        return int(xy[0]), int(xy[1])
    try:
        if widget.get_parent() is ancestor:
            alloc = widget.get_allocation()
            return int(alloc.x), int(alloc.y)
    except Exception:
        pass
    return None


def tab_chrome_insets(main):
    """Physical (left, top, right, bottom) of tab chrome inside the overlay's
    main child.

    The dimmer and the maximised frame stay in the pane area. A left tab
    list, and a native tab strip on any side, stay visible and clickable.
    Returns zeros when there is no chrome or the allocation is not usable.
    """
    if main is None:
        return (0, 0, 0, 0)
    mw, mh = _widget_size(main)
    if mw <= 1 or mh <= 1:
        return (0, 0, 0, 0)

    left = top = right = bottom = 0
    content = main
    notebook = getattr(main, '_tab_shell_notebook', None)
    try:
        if (notebook is not None and notebook.get_parent() is main
                and notebook.get_visible()):
            origin = _pos_in(notebook, main)
            nw, nh = _widget_size(notebook)
            if origin is not None and nw > 1 and nh > 1:
                left, top = max(0, origin[0]), max(0, origin[1])
                right = max(0, mw - left - nw)
                bottom = max(0, mh - top - nh)
                content = notebook
    except Exception:
        pass

    try:
        show_tabs = bool(content.get_show_tabs())
    except Exception:
        show_tabs = False
    if show_tabs:
        try:
            page = content.get_nth_page(content.get_current_page())
            if page is not None and page.get_visible():
                origin = _pos_in(page, content)
                pw, ph = _widget_size(page)
                cw, ch = _widget_size(content)
                if (origin is not None and pw > 1 and ph > 1
                        and cw > 1 and ch > 1):
                    left += max(0, origin[0])
                    top += max(0, origin[1])
                    right += max(0, cw - origin[0] - pw)
                    bottom += max(0, ch - origin[1] - ph)
        except Exception:
            pass

    if left + right >= mw - 32 or top + bottom >= mh - 32:
        return (0, 0, 0, 0)
    return (left, top, right, bottom)


def margins_from_physical(rtl, left, right, top, bottom):
    """Map physical insets to Gtk margin (start, end, top, bottom).

    Allocation x grows to the right. ``margin_start`` is the left in LTR
    and the right in RTL.
    """
    if rtl:
        return (int(right), int(left), int(top), int(bottom))
    return (int(left), int(right), int(top), int(bottom))


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

FRAME_CHROME_PX = 8  # .pane-maximised border 2px + padding 2px, per side


def vte_size_for_rect(terminal, rect, frame_chrome=None):
    """VTE pixels available when terminal fills a PaneFrame/slot of rect
    (UI review P2-14): minus titlebar/scrollbar (measured as Terminal minus
    VTE allocation), minus an auto-hidden scrollbar the font logic also
    ignores, minus the frame border/padding when the rect is the frame."""
    w, h = int(rect[2]), int(rect[3])
    try:
        tw, th = terminal.get_allocated_width(), terminal.get_allocated_height()
        vte = terminal.vte
        vw, vh = vte.get_allocated_width(), vte.get_allocated_height()
        if tw > 1 and th > 1 and vw > 1 and vh > 1:
            w -= max(0, tw - vw)
            h -= max(0, th - vh)
        alt = getattr(terminal, 'altscreen', None)
        slot_held = False
        try:
            slot = getattr(terminal, '_scrollbar_slot', None)
            slot_held = slot is not None and bool(slot.get_visible())
        except Exception:
            slot_held = False
        # The gap between Terminal and VTE already includes a held slot.
        # Subtract only when the bar was hidden and the VTE actually grew.
        hidden = 0
        if alt is not None and not slot_held:
            effective = getattr(alt, 'effective_hidden_width', None)
            if callable(effective):
                hidden = effective()
            elif getattr(alt, 'auto_hidden', False):
                hidden = getattr(alt, 'hidden_width', 0)
        if hidden > 0:
            w -= hidden
    except Exception:
        pass
    if frame_chrome:
        w -= int(frame_chrome)
        h -= int(frame_chrome)
    return max(1, w), max(1, h)


def terminal_in_current_tab(window, terminal):
    """True unless the window's root is a Notebook whose current page does
    not contain terminal."""
    try:
        root = window.get_child()
    except Exception:
        return True
    if not isinstance(root, Gtk.Notebook):
        return True
    page = root.get_nth_page(root.get_current_page())
    if page is None:
        return False
    return page is terminal or terminal.is_ancestor(page)


class PanePlaceholder(Gtk.DrawingArea):
    """Slot stand-in while the real terminal floats in the overlay Frame."""

    is_pane_placeholder = True

    def __init__(self, terminal, pixbuf=None, snap=None):
        Gtk.DrawingArea.__init__(self)
        self._terminal = terminal
        self._pixbuf = pixbuf
        # m37: (surface, w, h) painted without a per-frame pixbuf upload
        self._snap = snap
        # m33 fix-review: logical width of the snapshot, taken now (the
        # terminal is still in its slot) so draw-time resizes don't matter.
        self._pixbuf_logical_w = 0
        if pixbuf is not None:
            try:
                w = getattr(terminal, 'vte', None) or terminal
                self._pixbuf_logical_w = int(w.get_allocation().width)
            except Exception:
                self._pixbuf_logical_w = 0
        self.set_app_paintable(True)
        self.connect('draw', self._on_draw)
        self.set_hexpand(True)
        self.set_vexpand(True)

    @property
    def terminal(self):
        return self._terminal

    def slot_allocation(self):
        """Allocation of the slot in toplevel coordinates (like
        Terminal.get_allocation) for navigation / D16 geometry."""
        alloc = self.get_allocation()
        xy = _translate_xy(self, self.get_toplevel(), 0, 0)
        if xy is not None:
            alloc.x, alloc.y = xy
        return alloc

    def grab_focus(self):
        """Focus requests on the slot go to the floating terminal."""
        if self._terminal is not None:
            self._terminal.grab_focus()

    def describe_layout(self, count, parent, global_layout, child_order,
                        save_cwd=False):
        """Delegate to the floating terminal and mark maximised_pane."""
        term = self._terminal
        if term is None or not hasattr(term, 'describe_layout'):
            return count
        count = term.describe_layout(
            count, parent, global_layout, child_order, save_cwd)
        # Last written layout key for this terminal — set maximised flag
        try:
            # describe_layout writes under 'terminalN'; find by uuid
            for _name, layout in global_layout.items():
                if layout.get('type') == 'Terminal' and \
                        str(layout.get('uuid')) == str(term.uuid):
                    layout['maximised_pane'] = 'True'
                    break
        except Exception as ex:
            dbg('PanePlaceholder.describe_layout flag: %s' % ex)
        return count

    def _on_draw(self, widget, cr):
        """Paint cached pixbuf or solid background. NEVER terminal.draw(cr)."""
        alloc = widget.get_allocation()
        if not _window_is_rgba(widget):
            # No opaque fill in a see-through window: it would show as a
            # dark block through the translucent snapshot / terminal.
            cr.set_source_rgb(0.08, 0.08, 0.08)
            cr.rectangle(0, 0, alloc.width, alloc.height)
            cr.fill()
        if self._snap is None and self._pixbuf is not None and \
                widget.get_window() is not None:
            # m37: convert once, not on every frame of the animation
            self._snap = pixbuf_to_surface(self._pixbuf, widget,
                                           self._pixbuf_logical_w)
        # Slot size, not the capture size. A resize while maximised
        # would otherwise leave a ghost at the old width and height.
        aw = max(1, int(alloc.width))
        ah = max(1, int(alloc.height))
        if self._snap is not None:
            try:
                paint_snapshot(cr, self._snap, (0, 0, aw, ah), 0.35)
            except Exception:
                pass
        elif self._pixbuf is not None:
            try:
                # m33 post-review: HiDPI snapshots are device-resolution
                # (w*scale). Scale device pixels down to logical size,
                # then stretch that image to the slot's current allocation.
                k = placeholder_pixbuf_scale(self._pixbuf,
                                             self._pixbuf_logical_w)
                pw = max(1, int(self._pixbuf.get_width()))
                ph = max(1, int(self._pixbuf.get_height()))
                lw = max(1.0, pw * k)
                lh = max(1.0, ph * k)
                cr.save()
                cr.scale(aw / lw, ah / lh)
                if k != 1.0:
                    cr.scale(k, k)
                Gdk.cairo_set_source_pixbuf(cr, self._pixbuf, 0, 0)
                cr.paint_with_alpha(0.35)
                cr.restore()
            except Exception:
                pass
        return False


class PaneFrame(Gtk.Box):
    """Chrome box holding the maximised terminal. Skipped by logical_parent."""

    is_pane_frame = True

    def __init__(self):
        Gtk.Box.__init__(self, orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._terminal = None
        self.get_style_context().add_class('pane-maximised')
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.FILL)
        self.set_hexpand(True)
        self.set_vexpand(True)

    def set_terminal(self, terminal):
        if self._terminal is not None:
            try:
                self.remove(self._terminal)
            except Exception:
                pass
        self._terminal = terminal
        if terminal is not None:
            self.pack_start(terminal, True, True, 0)
            terminal.show_all()

    def get_terminal(self):
        return self._terminal

    def apply_rect(self, rect, relative_width, relative_height):
        """Position via margins relative to overlay size (margin+align)."""
        x, y, w, h = rect
        right = max(0, int(relative_width - x - w))
        bottom = max(0, int(relative_height - y - h))
        self.set_margin_start(max(0, int(x)))
        self.set_margin_top(max(0, int(y)))
        self.set_margin_end(right)
        self.set_margin_bottom(bottom)
        # No size request (UI review P1-1): a fixed request would keep the
        # frame at its maximise-time size when the window shrinks, since
        # Gtk.Overlay allocates max(main, child request). Margins + FILL
        # alone give the right geometry at every window size.

    def set_uniform_margin(self, margin):
        """Arrived state: MARGIN on every side, independent of any
        (possibly stale or not-yet-allocated) window size (P1-1/P1-2)."""
        m = max(0, int(margin))
        self.set_margin_start(m)
        self.set_margin_top(m)
        self.set_margin_end(m)
        self.set_margin_bottom(m)


NO_COMPOSITE_MAX_ALPHA = 0.45


def _cairo_over():
    try:
        import cairo
        return cairo.OPERATOR_OVER
    except Exception:
        return 2


def _screen_composited(widget):
    try:
        screen = widget.get_screen()
        return bool(screen.is_composited()) if screen is not None else False
    except Exception:
        return False


class DimLayer(Gtk.EventBox):
    """Full-area dimmer; clicks restore (after guard)."""

    def __init__(self):
        Gtk.EventBox.__init__(self)
        try:
            self.set_visible_window(False)
        except Exception:
            pass
        self.set_app_paintable(True)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.FILL)
        self._alpha = 0.0
        self.connect('draw', self._on_draw)

    def set_alpha(self, a):
        self._alpha = max(0.0, min(1.0, float(a)))
        self.queue_draw()

    def effective_alpha(self):
        """m33: degrade gracefully without a compositor. The dimmer paints
        into the toplevel's own buffer (no input-only child window), which
        blends without compositing; but if it ever got its own native
        window on a non-composited screen, translucency can turn opaque /
        black, so then cap it hard (or skip when painting can't blend)."""
        a = self._alpha
        if a <= 0.0:
            return 0.0
        if _screen_composited(self):
            return a
        try:
            own_window = bool(self.get_has_window()) and \
                bool(self.get_visible_window())
        except Exception:
            own_window = False
        if own_window:
            return 0.0
        return min(a, NO_COMPOSITE_MAX_ALPHA)

    def _on_draw(self, widget, cr):
        alpha = self.effective_alpha()
        if alpha <= 0.0:
            return False
        alloc = widget.get_allocation()
        cr.set_operator(_cairo_over())
        cr.set_source_rgba(0.0, 0.0, 0.0, alpha)
        cr.rectangle(0, 0, alloc.width, alloc.height)
        cr.fill()
        return False


class SnapshotArea(Gtk.DrawingArea):
    """Full-window DrawingArea that stretches a snapshot into a progress
    rect. m37: paints a cached surface (server-side on X11), never converts
    a pixbuf per frame."""

    def __init__(self):
        Gtk.DrawingArea.__init__(self)
        self.set_app_paintable(True)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.FILL)
        self._pixbuf = None
        self._snap = None
        self._rect = (0.0, 0.0, 1.0, 1.0)
        self._opacity = 1.0
        self.connect('draw', self._on_draw)

    def set_pixbuf(self, pb):
        self._pixbuf = pb
        self._snap = None
        self.queue_draw()

    def set_snap(self, snap):
        """snap = (surface, logical_w, logical_h) from capture_widget_surface."""
        self._snap = snap
        self._pixbuf = None
        self.queue_draw()

    def has_content(self):
        return self._snap is not None or self._pixbuf is not None

    def set_progress_rect(self, rect):
        self._rect = rect
        self.queue_draw()

    def set_opacity(self, o):
        self._opacity = max(0.0, min(1.0, float(o)))
        self.queue_draw()

    def _on_draw(self, widget, cr):
        if self._opacity <= 0.0:
            return False
        if self._snap is None and self._pixbuf is not None:
            self._snap = pixbuf_to_surface(self._pixbuf, widget)
        try:
            paint_snapshot(cr, self._snap, self._rect, self._opacity,
                           replace=snap_has_alpha(self._snap))
        except Exception as ex:
            dbg('SnapshotArea draw: %s' % ex)
        return False


def frame_clock_scheduler(widget):
    """m37: (schedule, unschedule) pair driving Animator from widget's frame
    clock (one tick per painted frame, timestamp = frame time), or None when
    the widget has no frame clock yet (not realized)."""
    try:
        if widget is None or widget.get_frame_clock() is None:
            return None
    except Exception:
        return None

    def schedule(cb):
        return widget.add_tick_callback(
            lambda _w, clock: cb(clock.get_frame_time() / 1e6))

    def unschedule(tick_id):
        widget.remove_tick_callback(tick_id)

    return schedule, unschedule


class Animator(object):
    """Single tick driver over progress 0 (src) .. 1 (dst).

    start(reverse=False) runs from_progress → 1; reverse=True runs → 0.
    reverse() flips direction mid-flight without a jump. Clock and scheduler
    are injectable for unit tests.

    m37: the scheduled callback may be handed the frame time (frame clock
    ticks); with sync_first_frame the time origin is the first tick, so
    expensive setup before the first painted frame does not skip progress.
    """

    def __init__(self, on_tick, on_done, clock=None, schedule=None,
                 unschedule=None, sync_first_frame=False):
        self._on_tick = on_tick
        self._on_done = on_done
        self._clock = clock or (lambda: time.monotonic())
        self._schedule = schedule or (lambda cb: GLib.timeout_add(16, cb))
        self._unschedule = unschedule or GLib.source_remove
        self._sync_first = bool(sync_first_frame)
        self._source = None
        self._start = 0.0
        self._duration = 0.2
        self._reverse = False
        self._from = 0.0
        self._progress = 0.0
        self._easing = ease_out_cubic
        self._running = False
        self.ticks = 0

    @property
    def running(self):
        return self._running

    @property
    def progress(self):
        return self._progress

    @property
    def reversed(self):
        return self._reverse

    @property
    def duration(self):
        """Current leg duration in seconds (m38: public accessor)."""
        return self._duration

    def start(self, duration_ms, reverse=False, easing=None,
              from_progress=None):
        self._stop_source()
        self._duration = max(1, int(duration_ms)) / 1000.0
        self._reverse = bool(reverse)
        self._easing = easing or (ease_in_out_cubic if reverse
                                  else ease_out_cubic)
        if from_progress is None:
            from_progress = 1.0 if reverse else 0.0
        self._from = max(0.0, min(1.0, float(from_progress)))
        self._progress = self._from
        self._start = None if self._sync_first else self._clock()
        self._running = True
        self._source = self._schedule(self._tick)

    def reverse(self, duration_ms=None, easing=None):
        """Flip direction from the current progress (no jump). The new leg
        is shortened to the distance left, so a quick re-toggle doesn't
        crawl over a full duration."""
        if not self._running:
            return
        dur = duration_ms if duration_ms is not None else \
            int(self._duration * 1000)
        to_reversed = not self._reverse
        left = self._progress if to_reversed else 1.0 - self._progress
        dur = max(60, int(round(dur * max(0.0, min(1.0, left)))))
        self.start(dur, reverse=to_reversed, easing=easing,
                   from_progress=self._progress)

    def _stop_source(self):
        if self._source is not None:
            try:
                self._unschedule(self._source)
            except Exception:
                pass
            self._source = None

    def cancel(self, jump_to_end=False, silent=False):
        """Stop. jump_to_end applies the terminal frame and fires on_done
        (unless silent)."""
        self._stop_source()
        was = self._running
        self._running = False
        if jump_to_end:
            self._progress = 0.0 if self._reverse else 1.0
            try:
                self._on_tick(self._progress, 1.0)
            except Exception as ex:
                dbg('Animator jump tick: %s' % ex)
        if was and not silent:
            try:
                self._on_done(cancelled=not jump_to_end)
            except Exception as ex:
                dbg('Animator cancel done: %s' % ex)

    def _value(self, raw):
        eased = self._easing(raw)
        if self._reverse:
            return self._from * (1.0 - eased)
        return self._from + (1.0 - self._from) * eased

    def _tick(self, now=None):
        if not self._running:
            return False
        if now is None:
            now = self._clock()
        if self._start is None:
            self._start = now
        self.ticks += 1
        raw = (now - self._start) / self._duration
        raw = max(0.0, min(1.0, raw))
        self._progress = self._value(raw)
        try:
            self._on_tick(self._progress, raw)
        except Exception as ex:
            dbg('Animator tick: %s' % ex)
        if raw >= 1.0:
            self._source = None
            self._running = False
            self._progress = 0.0 if self._reverse else 1.0
            try:
                self._on_done(cancelled=False)
            except Exception as ex:
                dbg('Animator done: %s' % ex)
            return False
        return True


# ---------------------------------------------------------------------------
# Controller bound to a Window
# ---------------------------------------------------------------------------

class OverlayController(object):
    """Owns the overlay-maximise state of one Window.

    State lives in self.data (dict) while maximised or animating; the
    temporary Gtk.Overlay exists exactly as long as self.data is not None.
    """

    DIM_ALPHA = 0.55
    MARGIN = 12
    CLICK_GUARD_MS = 300
    REDUCED_MS = 100

    WATCHDOG_STALL_S = 0.6  # no frame for this long → jump to the end

    def __init__(self, window):
        self.window = window
        self.data = None
        self._animator = None
        self._frozen = None  # terminal currently frozen for E
        self._probe = None   # m37 animprofile probe (opt-in)
        self._watchdog = None

    # -- queries ----------------------------------------------------------

    def is_active(self):
        return self.data is not None

    def is_animating(self):
        """m37: an expand/restore animation is in flight (session saves
        and other heavy work wait until it is over)."""
        anim = self._animator
        return self.data is not None and anim is not None and anim.running

    def is_maximised_pane(self, terminal):
        return self.data is not None and self.data.get('terminal') is terminal

    def placeholder(self):
        return self.data.get('placeholder') if self.data else None

    def main(self):
        """Layout root under the temporary Overlay. The Overlay's own Bin
        child is authoritative: the root can be replaced while maximised
        (sibling exit collapses the root Paned → Window.replace), and a stale
        captured reference would hide every terminal (P0-1)."""
        if not self.data:
            return None
        overlay = self.data.get('overlay')
        if overlay is not None:
            try:
                child = Gtk.Bin.get_child(overlay)
            except Exception:
                child = None
            if child is not None:
                self.data['main'] = child
                return child
            return None
        return self.data.get('main')

    def note_main_replaced(self, widget):
        """Window.add/remove hook: keep data['main'] in sync."""
        data = self.data
        if data is None:
            return
        bound = data.get('_geo_main')
        bound_widget = bound[0] if bound else None
        if bound and bound_widget is not widget:
            old, sig = bound
            if old is not None and sig is not None:
                try:
                    old.disconnect(sig)
                except Exception:
                    pass
            data['_geo_main'] = None
        data['main'] = widget
        if widget is not None and data.get('_geo_main') is None:
            try:
                sig = widget.connect(
                    'size-allocate',
                    lambda _w, _a: self._schedule_geometry(data))
            except Exception:
                sig = None
            data['_geo_main'] = (widget, sig)
        self._schedule_geometry(data)

    def _widget_rtl(self, widget):
        try:
            return widget.get_direction() == Gtk.TextDirection.RTL
        except Exception:
            return False

    @staticmethod
    def _set_margins(widget, start, end, top, bottom):
        if widget is None:
            return
        start, end, top, bottom = int(start), int(end), int(top), int(bottom)
        try:
            if (widget.get_margin_start() == start
                    and widget.get_margin_end() == end
                    and widget.get_margin_top() == top
                    and widget.get_margin_bottom() == bottom):
                return
        except Exception:
            pass
        widget.set_margin_start(start)
        widget.set_margin_end(end)
        widget.set_margin_top(top)
        widget.set_margin_bottom(bottom)

    def _apply_chrome_geometry(self, data, alloc):
        """Keep the dimmer and frame inside the pane area.

        Tab chrome (left list, native strip) is not dimmed and not covered,
        so it still receives clicks. ``dst_rect`` is physical overlay
        coordinates; widget margins follow text direction.
        """
        if data is not self.data or data is None or alloc is None:
            return
        width, height = int(alloc.width), int(alloc.height)
        if width <= 1 or height <= 1:
            return
        main = self.main() or data.get('main')
        chrome = tab_chrome_insets(main)
        m = int(self.MARGIN)
        left, top, right, bottom = (chrome[0] + m, chrome[1] + m,
                                     chrome[2] + m, chrome[3] + m)
        if left + right >= width or top + bottom >= height:
            chrome = (0, 0, 0, 0)
            left = right = top = bottom = m
        data['dst_rect'] = (float(left), float(top),
                            max(1.0, width - left - right),
                            max(1.0, height - top - bottom))
        rtl = self._widget_rtl(data.get('frame') or data.get('overlay'))
        self._set_margins(data.get('frame'),
                          *margins_from_physical(rtl, left, right, top, bottom))
        self._set_margins(data.get('dim'),
                          *margins_from_physical(
                              rtl, chrome[0], chrome[2], chrome[1], chrome[3]))

    def _flush_geometry(self, data):
        """Run a pending chrome update now, so arrival sees the latest rect."""
        if data is None or data is not self.data:
            return
        idle = data.get('_geo_idle')
        if not idle:
            return
        try:
            GLib.source_remove(idle)
        except Exception:
            pass
        data['_geo_idle'] = None
        ov = data.get('overlay')
        if ov is None:
            return
        try:
            self._apply_chrome_geometry(data, ov.get_allocation())
        except Exception as ex:
            dbg('flush geometry: %s' % ex)

    def _schedule_geometry(self, data):
        if data is not self.data or data is None:
            return
        if data.get('_geo_idle'):
            return
        overlay = data.get('overlay')
        if overlay is None:
            return

        def apply():
            data['_geo_idle'] = None
            if data is not self.data:
                return False
            ov = data.get('overlay')
            if ov is None:
                return False
            self._apply_chrome_geometry(data, ov.get_allocation())
            return False

        data['_geo_idle'] = GLib.idle_add(apply)

    def _bind_geometry(self, data):
        overlay = data.get('overlay')
        main = data.get('main')
        if overlay is not None and data.get('_geo_overlay') is None:
            data['_geo_overlay'] = overlay.connect(
                'size-allocate',
                lambda _w, alloc: self._on_overlay_allocate(data, alloc))
        if main is not None and data.get('_geo_main') is None:
            try:
                sig = main.connect(
                    'size-allocate',
                    lambda _w, _a: self._schedule_geometry(data))
            except Exception:
                sig = None
            data['_geo_main'] = (main, sig)

    def _unbind_geometry(self, data):
        idle = data.pop('_geo_idle', None)
        if idle:
            try:
                GLib.source_remove(idle)
            except Exception:
                pass
        overlay = data.get('overlay')
        sig = data.pop('_geo_overlay', None)
        if overlay is not None and sig is not None:
            try:
                overlay.disconnect(sig)
            except Exception:
                pass
        bound = data.pop('_geo_main', None)
        if bound:
            widget, sig = bound
            if widget is not None and sig is not None:
                try:
                    widget.disconnect(sig)
                except Exception:
                    pass

    # -- E (auto font) freeze contract ------------------------------------

    def _pause_font(self, terminal):
        if terminal is None or self._frozen is terminal:
            return
        pause = getattr(terminal, 'pause_auto_font_scale', None)
        if callable(pause):
            try:
                pause('freeze')
                self._frozen = terminal
            except Exception as ex:
                dbg('pause_auto_font_scale: %s' % ex)

    def _resume_font(self, terminal, avail=None):
        if terminal is None or self._frozen is not terminal:
            return
        self._frozen = None
        resume = getattr(terminal, 'resume_auto_font_scale', None)
        if callable(resume):
            try:
                if avail is None:
                    resume()
                else:
                    resume(avail=avail)
            except TypeError:
                try:
                    resume()
                except Exception as ex:
                    dbg('resume_auto_font_scale: %s' % ex)
            except Exception as ex:
                dbg('resume_auto_font_scale: %s' % ex)

    @staticmethod
    def _apply_tier_for_rect(terminal, rect, frame_chrome=0):
        """Same-frame tier for the destination size (one SIGWINCH)."""
        if terminal is None or rect is None:
            return
        compute = getattr(terminal, 'compute_tier_for_size', None)
        apply = getattr(terminal, 'apply_font_tier_scale', None)
        if not callable(compute) or not callable(apply):
            return
        try:
            w, h = vte_size_for_rect(terminal, rect, frame_chrome)
            scale = compute(w, h)
            apply(scale, toast=False)
        except Exception as ex:
            dbg('apply_font_tier_scale: %s' % ex)

    def _config_ms(self, key, default):
        try:
            return int(self.window.config[key])
        except Exception:
            return default

    # -- public API -------------------------------------------------------

    def maximise(self, terminal, animate=True):
        window = self.window
        if terminal is None:
            return False

        if self.is_maximised_pane(terminal):
            data = self.data
            if data.get('restore_pending') and self._animator is not None \
                    and self._animator.running:
                # Toggle again during restore → reverse back to expanded
                data['restore_pending'] = False
                self._animator.reverse(
                    self._config_ms('pane_animation_expand_ms', 200),
                    ease_out_cubic)
                return True
            return self.restore(animate=animate)

        if self.is_active():
            return self.transfer(terminal, animate=animate)

        if not window.has_multiple_terms():
            dbg('overlay_maximise: single visible terminal, no-op')
            return False

        config = window.config
        # m37: gtk-enable-animations=False / reduce_motion=on → instant
        if animate and should_reduce_motion(config):
            animate = False
        if animate:
            from . import animprofile
            self._probe = animprofile.begin('expand', window)
        # Capture BEFORE reparent (whole Terminal incl. titlebar, so the
        # first frame matches what is on screen); failure → dim fade only
        # Flight uses only the whole-terminal surface. A VTE pixbuf is a
        # fallback for the placeholder, never stretched across the flight.
        snap = capture_widget_surface(terminal) if animate else None
        pixbuf = None
        if animate and snap is None:
            pixbuf = capture_terminal_pixbuf(terminal)
            if pixbuf is not None and _is_wayland(terminal):
                vte = getattr(terminal, 'vte', None) or terminal
                candidate = pixbuf_to_surface(
                    pixbuf, vte, vte.get_allocated_width())
                blank = True
                if candidate is not None:
                    blank = surface_looks_blank(
                        candidate[0], candidate[1], candidate[2])
                if blank:
                    pixbuf = None
        zoom_anim = bool(animate) and snap is not None
        fade_only = bool(animate) and not zoom_anim

        parent = terminal.get_parent()
        main = Gtk.Window.get_child(window)
        if parent is None or main is None:
            err('overlay_maximise: terminal/main missing')
            return False

        src_rect = _rect_from_widget(terminal, main)
        main_alloc = main.get_allocation()
        chrome = tab_chrome_insets(main)
        m = float(self.MARGIN)
        dst_rect = (chrome[0] + m, chrome[1] + m,
                    max(1.0, main_alloc.width - chrome[0] - chrome[2] - 2.0 * m),
                    max(1.0, main_alloc.height - chrome[1] - chrome[3] - 2.0 * m))

        self._pause_font(terminal)

        placeholder = PanePlaceholder(terminal, pixbuf=pixbuf, snap=snap)
        overlay = Gtk.Overlay()
        overlay.get_style_context().add_class('pane-overlay')

        # 1) insert temporary Overlay above the layout root
        Gtk.Window.remove(window, main)
        overlay.add(main)
        Gtk.Window.add(window, overlay)

        # 2) terminal → placeholder in its slot (no Terminal signals on it)
        if not self._swap(parent, terminal, placeholder):
            Gtk.Window.remove(window, overlay)
            overlay.remove(main)
            Gtk.Window.add(window, main)
            self._resume_font(terminal)
            return False
        placeholder.show()
        terminal._overlay_placeholder = placeholder

        frame = PaneFrame()
        # m37: the real terminal is not painted while the snapshot flies
        frame.connect('draw', self._on_frame_draw)
        dim = DimLayer()
        dim.add_events(Gdk.EventMask.BUTTON_PRESS_MASK |
                       Gdk.EventMask.BUTTON_RELEASE_MASK)
        dim.connect('button-press-event', self._on_dim_press)
        dim.connect('button-release-event', self._on_dim_release)
        overlay.add_overlay(dim)
        overlay.add_overlay(frame)

        snapshot = None
        if zoom_anim:
            snapshot = SnapshotArea()
            snapshot.set_snap(snap)
            snapshot.set_progress_rect(src_rect)
            overlay.add_overlay(snapshot)
            try:
                overlay.set_overlay_pass_through(snapshot, True)
            except Exception:
                pass

        self.data = {
            'terminal': terminal,
            'placeholder': placeholder,
            'overlay': overlay,
            'main': main,
            'frame': frame,
            'dim': dim,
            'snapshot': snapshot,
            'pixbuf': pixbuf,
            'snap': snap,
            'src_rect': src_rect,
            'dst_rect': dst_rect,
            'frame_hidden': zoom_anim,
            'animating': False,
            'restore_pending': False,
            'emitted': False,
            'press_on_dim': False,
            'ready_at': 0.0,
        }
        window.set_property('term_zoomed', True)

        # 3) same-frame E tier at the frame's final size, then reparent
        self._apply_tier_for_rect(terminal, dst_rect, FRAME_CHROME_PX)
        frame.set_terminal(terminal)
        # Arrived margins exclude the tab list. size-allocate keeps them
        # in step when the window or the list changes width.
        data_ref = self.data
        self._apply_chrome_geometry(data_ref, main_alloc)
        self._bind_geometry(data_ref)
        window._connect_overlay_terminal_signals(terminal)

        overlay.show()
        main.show()
        dim.show()
        frame.show_all()
        if snapshot is not None:
            snapshot.show()
        terminal.grab_focus()

        if zoom_anim or fade_only:
            dim.set_alpha(0.0)
            self._run_animation(expand=True, reduced=fade_only)
        else:
            dim.set_alpha(self.DIM_ALPHA)
            self._arrive_maximised()
        return True

    def _on_overlay_allocate(self, data, alloc):
        if data is not self.data or data is None:
            return
        if alloc.width <= 1 or alloc.height <= 1:
            return
        # Margins cannot be changed inside size-allocate. Record the size
        # and apply on idle, after the tab list has its new width too.
        self._schedule_geometry(data)

    def teardown(self):
        """Window is being destroyed: stop the animation tick and put the
        terminal back without animating (UI review P2-1)."""
        if self._animator is not None:
            self._animator.cancel(silent=True)
        if self.data is not None:
            self.data['restore_pending'] = True
            try:
                self._finish_restore()
            except Exception as ex:
                dbg('overlay teardown: %s' % ex)
                self.data = None
        self._animator = None
        self._cancel_watchdog()
        if self._probe is not None:
            self._probe.close()
            self._probe = None

    def maximise_when_ready(self, terminal):
        """Session restore (P1-2): maximise once the window has a real
        allocation, and only if the terminal's tab is the current one
        (a background-tab pane must not float over the visible tab).

        Not parented yet, not mapped, or not sized yet: keep waiting.
        Map and size-allocate both queue another attempt, so a map that
        does not allocate again still runs. A terminal that already lives
        in some other window is not waited on."""
        window = self.window
        state = {'ids': [], 'done': False}

        def _finish():
            if state['done']:
                return
            state['done'] = True
            for obj, hid in state['ids']:
                try:
                    obj.disconnect(hid)
                except Exception:
                    pass
            state['ids'] = []

        def _kick(*_a):
            if not state['done']:
                GLib.idle_add(_attempt)

        def _attempt():
            if state['done']:
                return False
            if getattr(window, 'isDestroyed', False):
                _finish()
                return False
            try:
                if terminal.in_destruction():
                    _finish()
                    return False
                top = terminal.get_toplevel()
            except Exception:
                _finish()
                return False
            # Unparented: toplevel is the terminal itself. Another real
            # window means this pane will not land here.
            if top is not window:
                if isinstance(top, Gtk.Window):
                    _finish()
                return False
            alloc = window.get_allocation()
            if not window.get_mapped() or alloc.width <= 1 or \
                    alloc.height <= 1:
                return False
            _finish()
            if not terminal_in_current_tab(window, terminal):
                dbg('maximise_when_ready: %s not in current tab, skipped'
                    % terminal)
                return False
            try:
                self.maximise(terminal, animate=False)
            except Exception as ex:
                dbg('maximise_when_ready: %s' % ex)
            return False

        state['ids'].append((window, window.connect('size-allocate', _kick)))
        state['ids'].append((window, window.connect('map', _kick)))
        state['ids'].append((window, window.connect('destroy',
                                                    lambda *_a: _finish())))
        try:
            state['ids'].append(
                (terminal, terminal.connect('hierarchy-changed', _kick)))
        except Exception:
            pass
        GLib.idle_add(_attempt)
        return True

    def restore(self, animate=True):
        if not self.is_active():
            return False
        data = self.data
        anim = self._animator
        if anim is not None and anim.running:
            if not animate:
                data['restore_pending'] = True
                anim.cancel(jump_to_end=True)  # on_done → _finish_restore
                if self.data is not None:
                    self._finish_restore()
                return True
            if data.get('restore_pending'):
                return True  # already restoring
            data['restore_pending'] = True
            anim.reverse(self._config_ms('pane_animation_restore_ms', 160),
                         ease_in_out_cubic)
            return True

        if animate and should_reduce_motion(self.window.config):
            animate = False  # m37: instant when animations are disabled
        if not animate:
            self._finish_restore()
            return True

        from . import animprofile
        self._probe = animprofile.begin('restore', self.window)
        terminal = data['terminal']
        self._pause_font(terminal)
        overlay = data['overlay']
        # m37: land on the slot as it is NOW (the window may have been
        # resized while maximised), fly from where the terminal really is.
        try:
            ph = data['placeholder']
            if ph.get_mapped() and ph.get_allocated_width() > 1:
                data['src_rect'] = _rect_from_widget(ph, overlay)
        except Exception as ex:
            dbg('restore slot rect: %s' % ex)
        snap = capture_widget_surface(terminal)
        data['restore_pending'] = True
        if snap is not None:
            try:
                data['fly_dst'] = _rect_from_widget(terminal, overlay)
            except Exception:
                data['fly_dst'] = None
            snapshot = data.get('snapshot')
            if snapshot is None:
                snapshot = SnapshotArea()
                overlay.add_overlay(snapshot)
                try:
                    overlay.set_overlay_pass_through(snapshot, True)
                except Exception:
                    pass
                data['snapshot'] = snapshot
            snapshot.set_snap(snap)
            snapshot.set_progress_rect(self._fly_dst(data))
            snapshot.set_opacity(1.0)
            snapshot.show()
            self._set_frame_hidden(True)
            self._run_animation(expand=False, reduced=False)
        else:
            self._run_animation(expand=False, reduced=True)
        return True

    def transfer(self, target, animate=True):
        """D16: move the maximise to another terminal (no full-window flash:
        both swaps happen before the next frame is drawn)."""
        if not self.is_active() or target is None:
            return False
        if self.is_maximised_pane(target):
            return True
        self.restore(animate=False)
        return self.maximise(target, animate=False)

    # -- animation --------------------------------------------------------

    # -- animation (m37) --------------------------------------------------

    def _on_frame_draw(self, _widget, _cr):
        """Block painting the real terminal (and its titlebar) while the
        snapshot stands in for it: returning True skips the Box's own draw
        and therefore every child. No opacity group, no VTE repaint."""
        data = self.data
        return bool(data is not None and data.get('frame_hidden'))

    def _set_frame_hidden(self, hidden):
        data = self.data
        if data is None or bool(data.get('frame_hidden')) == bool(hidden):
            return
        data['frame_hidden'] = bool(hidden)
        try:
            data['frame'].queue_draw()
        except Exception:
            pass

    def _fly_dst(self, data):
        """Rect the snapshot flies to/from on the maximised side: the
        terminal inside the frame chrome (not the chrome itself), so the
        hand-over to the live terminal doesn't jump by the border."""
        rect = data.get('fly_dst')
        if rect is not None:
            return rect
        x, y, w, h = data['dst_rect']
        inset = FRAME_CHROME_PX / 2.0
        return (x + inset, y + inset, max(1.0, w - 2 * inset),
                max(1.0, h - 2 * inset))

    def _run_animation(self, expand, reduced):
        data = self.data
        data['animating'] = True
        if reduced:
            ms = self.REDUCED_MS
        elif expand:
            ms = self._config_ms('pane_animation_expand_ms', 200)
        else:
            ms = self._config_ms('pane_animation_restore_ms', 160)
        dim_alpha = self.DIM_ALPHA
        fade_ms = 60.0

        def on_tick(progress, raw):
            # Never touch VTE size / font here: only snapshot rect + dim
            data['dim'].set_alpha(dim_alpha * progress)
            snap = data.get('snapshot')
            if snap is None:
                return
            anim = self._animator
            expanding = anim is not None and not anim.reversed
            snap.set_progress_rect(interpolate_rect(
                data['src_rect'], self._fly_dst(data), progress))
            # Hand-over at the end of an expand: the live terminal (already
            # laid out at this size) is drawn under the snapshot, which
            # fades out over it. Cross-fading by fading the snapshot avoids
            # an offscreen opacity group of the whole VTE.
            dur_ms = max(1.0, (anim.duration * 1000.0) if anim else ms)
            fade_span = min(1.0, fade_ms / dur_ms)
            if expanding and (1.0 - raw) <= fade_span:
                self._set_frame_hidden(False)
                snap.set_opacity((1.0 - raw) / fade_span if fade_span else 0)
            else:
                self._set_frame_hidden(True)
                snap.set_opacity(1.0)

        sched = frame_clock_scheduler(data['overlay'])
        if sched is not None:
            self._animator = Animator(on_tick, self._on_anim_done,
                                      schedule=sched[0], unschedule=sched[1],
                                      sync_first_frame=True)
        else:
            self._animator = Animator(on_tick, self._on_anim_done,
                                      sync_first_frame=True)
        if self._probe is not None:
            self._probe.mark('anim_start')
        if expand:
            self._animator.start(ms, reverse=False, easing=ease_out_cubic,
                                 from_progress=0.0)
        else:
            self._animator.start(ms, reverse=True, easing=ease_in_out_cubic,
                                 from_progress=1.0)
        self._arm_watchdog()

    def _arm_watchdog(self):
        """A frame clock that stops ticking (window unmapped/iconified mid
        animation) must not leave the overlay stuck half-way: if no frame
        arrives for WATCHDOG_STALL_S, jump to the end state."""
        if self._watchdog is not None:
            return
        state = {'anim': None, 'ticks': -1, 'since': time.monotonic()}

        def check():
            anim = self._animator
            if self.data is None or anim is None or not anim.running:
                self._watchdog = None
                return False
            now = time.monotonic()
            if anim is not state['anim'] or anim.ticks != state['ticks']:
                state.update(anim=anim, ticks=anim.ticks, since=now)
                return True
            if now - state['since'] >= self.WATCHDOG_STALL_S:
                dbg('overlay animation stalled (no frames); finishing')
                self._watchdog = None
                anim.cancel(jump_to_end=True)
                return False
            return True

        self._watchdog = GLib.timeout_add(150, check)

    def _cancel_watchdog(self):
        if self._watchdog is not None:
            try:
                GLib.source_remove(self._watchdog)
            except Exception:
                pass
            self._watchdog = None

    def _on_anim_done(self, cancelled=False):
        data = self.data
        if data is None:
            return
        data['animating'] = False
        self._cancel_watchdog()
        probe, self._probe = self._probe, None
        if data.get('restore_pending'):
            self._finish_restore()
        else:
            self._arrive_maximised()
        if probe is not None:
            probe.done()

    def _arrive_maximised(self):
        data = self.data
        if data is None:
            return
        snap = data.get('snapshot')
        if snap is not None:
            snap.set_opacity(0.0)
            snap.hide()
        data['fly_dst'] = None
        self._set_frame_hidden(False)
        data['frame'].set_opacity(1.0)
        data['dim'].set_alpha(self.DIM_ALPHA)
        data['ready_at'] = time.monotonic() + self.CLICK_GUARD_MS / 1000.0
        terminal = data['terminal']
        # A resize during the flight updates dst_rect on idle. Apply that
        # landed size before resume reads the VTE, which can still be the
        # allocation from animation start.
        self._flush_geometry(data)
        rect = data.get('dst_rect')
        avail = None
        if rect is not None:
            try:
                avail = vte_size_for_rect(terminal, rect, FRAME_CHROME_PX)
            except Exception:
                avail = None
        self._resume_font(terminal, avail=avail)
        if not data['emitted']:
            data['emitted'] = True
            self._emit_changed(terminal, True)

    def _finish_restore(self):
        data = self.data
        if data is None:
            return
        window = self.window
        terminal = data['terminal']
        placeholder = data['placeholder']
        overlay = data['overlay']
        main = data['main']
        frame = data['frame']
        self._unbind_geometry(data)

        if self._animator is not None:
            self._animator.cancel(silent=True)
        self._animator = None
        self._cancel_watchdog()
        if self._probe is not None:
            self._probe.close()
            self._probe = None
        data['frame_hidden'] = False
        self._pause_font(terminal)
        # Round-2 P2-9: on a dying window (destroy teardown / finalize) only
        # put the tree back for describe/close; no focus grab, tier
        # recompute or font resume on terminals that are about to close.
        dying = bool(getattr(window, 'isDestroyed', False) or
                     getattr(window, '_session_destroy_handled', False))
        emitted = bool(data.get('emitted'))

        # Window-side handlers off before the terminal returns to its slot.
        # On a failed rehome they are connected again with the overlay table.
        try:
            window.disconnect_child(terminal)
        except Exception:
            pass
        frame.set_terminal(None)
        removed_extras = []
        for extra in (frame, data.get('dim'), data.get('snapshot')):
            if extra is not None and extra.get_parent() is overlay:
                overlay.remove(extra)
                removed_extras.append(extra)

        # Same-frame E tier for the slot size, then swap back
        try:
            alloc = placeholder.get_allocation()
            slot = (0, 0, alloc.width, alloc.height) \
                if alloc.width > 1 and alloc.height > 1 else data['src_rect']
        except Exception:
            slot = data['src_rect']
        if not dying:
            self._apply_tier_for_rect(terminal, slot)

        root_terminal = False
        removed_placeholder = False
        placeholder_parent = None
        try:
            placeholder_parent = placeholder.get_parent()
        except Exception:
            placeholder_parent = None
        # The Overlay's Bin child is the real layout root; data['main'] may
        # be stale if the root was replaced while maximised (P0-1).
        try:
            actual_main = Gtk.Bin.get_child(overlay)
        except Exception:
            actual_main = None
        if placeholder_parent is overlay:
            # Siblings all exited: the placeholder became the layout root
            try:
                overlay.remove(placeholder)
                removed_placeholder = True
            except Exception as ex:
                dbg('overlay restore: drop root placeholder: %s' % ex)
            main = None
            root_terminal = True
        else:
            main = actual_main if actual_main is not None else data['main']

        try:
            if main is not None and main.get_parent() is overlay:
                overlay.remove(main)
            if overlay.get_parent() is window:
                Gtk.Window.remove(window, overlay)
        except Exception as ex:
            dbg('overlay teardown: %s' % ex)

        # Clear the session before the swap. Window.add nests into the
        # Overlay while is_active() is still true.
        self.data = None
        window.set_property('term_zoomed', False)

        attached = False
        if root_terminal:
            attached = self._rehome_root(window, terminal, dying)
        else:
            if main is not None and main.get_parent() is None:
                try:
                    Gtk.Window.add(window, main)
                except Exception as ex:
                    dbg('overlay restore: reattach main: %s' % ex)
            parent = placeholder_parent
            if parent is not None and self._swap(parent, placeholder, terminal):
                attached = (terminal.get_parent() is not None and
                            terminal.get_toplevel() is window)
            if not attached and parent is not None:
                attached, removed_now = self._same_slot_replace(
                    window, parent, placeholder, terminal, dying)
                if removed_now:
                    removed_placeholder = True

        if not attached:
            self._abort_restore(
                window, terminal, placeholder, overlay, main, frame,
                removed_extras, root_terminal, dying, data,
                removed_placeholder, placeholder_parent)
            err('overlay restore: placeholder slot lost; terminal %s '
                'not re-parented' % terminal)
            return

        terminal._overlay_placeholder = None
        terminal.show_all()
        try:
            placeholder.destroy()
        except Exception:
            pass
        if dying:
            # Leave the terminal frozen; it is closed right after this.
            self._frozen = None
        else:
            # Root success already grabbed inside Window.add.
            if not root_terminal:
                try:
                    terminal.grab_focus()
                except Exception:
                    pass
            self._resume_font(terminal)
        if emitted:
            self._emit_changed(terminal, False)

    def _rehome_root(self, window, terminal, dying):
        """Placeholder was the layout root. data is already clear."""
        if dying:
            try:
                Gtk.Window.add(window, terminal)
            except Exception as ex:
                dbg('overlay restore: window add failed: %s' % ex)
            if terminal.get_parent() is None or \
                    terminal.get_toplevel() is not window:
                return False
            try:
                window.connect_terminal_signals(
                    terminal,
                    window.terminal_signals(terminal, overlay=False))
            except Exception:
                pass
            return True
        try:
            window.add(terminal)
        except Exception as ex:
            dbg('overlay restore: window add failed: %s' % ex)
        return (terminal.get_parent() is not None and
                terminal.get_toplevel() is window)

    def _same_slot_replace(self, window, parent, placeholder, terminal, dying):
        """Swap failed. Replace that one slot. Never add onto the layout root.

        Returns (attached, placeholder_was_removed).
        """
        page_num = getattr(parent, 'page_num', None)
        detach_tab = getattr(parent, 'detach_tab', None)
        if callable(page_num) and callable(detach_tab):
            # Notebook.add is newtab. A live window gives up; a dying
            # window may move the existing page.
            if not dying:
                return False, False
            try:
                page = page_num(placeholder)
            except Exception:
                return False, False
            if page is None or page < 0:
                return False, False
            removed = False
            try:
                label = parent.get_tab_label(placeholder)
                detach_tab(placeholder)
                removed = True
                parent.insert_page(terminal, label, page)
                terminal.show_all()
            except Exception as ex:
                dbg('overlay restore: notebook slot: %s' % ex)
                return False, removed
            attached = (terminal.get_parent() is not None and
                        terminal.get_toplevel() is window)
            return attached, removed

        remove = getattr(parent, 'remove', None)
        add = getattr(parent, 'add', None)
        if not callable(remove) or not callable(add):
            return False, False
        try:
            remove(placeholder)
        except Exception as ex:
            dbg('overlay restore: slot remove: %s' % ex)
            return False, False
        try:
            add(terminal)
        except Exception as ex:
            dbg('overlay restore: slot add: %s' % ex)
            try:
                add(placeholder)
            except Exception:
                return False, True
            return False, False
        attached = (terminal.get_parent() is not None and
                    terminal.get_toplevel() is window)
        return attached, True

    def _abort_restore(self, window, terminal, placeholder, overlay, main,
                       frame, removed_extras, root_terminal, dying, data,
                       removed_placeholder, placeholder_parent):
        """Swap missed. A live window keeps this maximise. A dying window
        must not leave is_active() true."""
        try:
            parent = terminal.get_parent()
            if parent is not None and parent is not frame:
                parent.remove(terminal)
        except Exception:
            pass

        if dying:
            self._abort_restore_dying(
                window, terminal, placeholder, overlay, main, frame,
                removed_extras, root_terminal)
            return

        try:
            frame.set_terminal(terminal)
        except Exception as ex:
            err('overlay restore: frame rollback failed: %s' % ex)
        if (removed_placeholder and placeholder_parent is not None
                and placeholder_parent is not overlay):
            adder = getattr(placeholder_parent, 'add', None)
            if callable(adder):
                try:
                    adder(placeholder)
                    removed_placeholder = False
                except Exception as ex:
                    dbg('overlay restore: put placeholder back: %s' % ex)
        try:
            child = Gtk.Window.get_child(window)
            if child is not None and child is not overlay:
                Gtk.Window.remove(window, child)
        except Exception:
            pass
        try:
            if root_terminal:
                if removed_placeholder:
                    overlay.add(placeholder)
            elif main is not None and main.get_parent() is None:
                overlay.add(main)
        except Exception as ex:
            dbg('overlay restore: rollback main: %s' % ex)
        for extra in removed_extras:
            try:
                if extra is not None and extra.get_parent() is None:
                    overlay.add_overlay(extra)
            except Exception:
                pass
        # data is still None, so this cannot take Window.add's overlay branch.
        try:
            if overlay.get_parent() is None:
                Gtk.Window.add(window, overlay)
        except Exception as ex:
            dbg('overlay restore: rollback overlay: %s' % ex)
        self.data = data
        window.set_property('term_zoomed', True)
        try:
            data['main'] = Gtk.Bin.get_child(overlay)
        except Exception:
            data['main'] = main
        self._bind_geometry(data)
        self._schedule_geometry(data)
        # Undo the slot-sized tier applied before the failed swap.
        self._apply_tier_for_rect(
            terminal, data.get('dst_rect'), FRAME_CHROME_PX)
        self._resume_font(terminal)
        try:
            window._connect_overlay_terminal_signals(terminal)
        except Exception:
            pass
        try:
            overlay.show()
            frame.show_all()
        except Exception:
            pass

    def _abort_restore_dying(self, window, terminal, placeholder, overlay,
                             main, frame, removed_extras, root_terminal):
        """Leave the terminal in the frame. data stays None."""
        try:
            frame.set_terminal(terminal)
        except Exception as ex:
            err('overlay restore: frame rollback failed: %s' % ex)
        try:
            child = Gtk.Window.get_child(window)
            if child is not None and child is not overlay:
                Gtk.Window.remove(window, child)
                if (not root_terminal and main is not None
                        and main.get_parent() is None):
                    overlay.add(main)
        except Exception as ex:
            dbg('overlay restore: dying rollback: %s' % ex)
        for extra in removed_extras:
            try:
                if extra is not None and extra.get_parent() is None:
                    overlay.add_overlay(extra)
            except Exception:
                pass
        try:
            if overlay.get_parent() is None:
                Gtk.Window.add(window, overlay)
        except Exception as ex:
            dbg('overlay restore: dying overlay: %s' % ex)
        try:
            placeholder.destroy()
        except Exception:
            pass
        self._frozen = None

    def _emit_changed(self, terminal, active):
        try:
            self.window.emit('pane-maximise-changed', terminal, bool(active))
        except Exception as ex:
            dbg('emit pane-maximise-changed: %s' % ex)

    # -- dim click (D21) --------------------------------------------------

    def _on_dim_press(self, widget, event):
        if self.data is not None and event.button == 1:
            self.data['press_on_dim'] = True
            return True
        return False

    def _on_dim_release(self, widget, event):
        data = self.data
        if data is None or event.button != 1:
            return False
        pressed = data.get('press_on_dim')
        data['press_on_dim'] = False
        if not pressed or data.get('animating'):
            return True
        if time.monotonic() < data.get('ready_at', 0.0):
            return True
        self.restore(animate=True)
        return True

    # -- swap helper ------------------------------------------------------

    @staticmethod
    def _swap(parent, old, new):
        if hasattr(parent, 'swap_child'):
            try:
                return parent.swap_child(old, new) is not False
            except Exception as ex:
                err('swap_child failed: %s' % ex)
                return False
        err('overlay: %s has no swap_child' % type(parent).__name__)
        return False
