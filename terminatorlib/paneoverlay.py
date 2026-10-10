# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""paneoverlay.py - Wave-style single-pane overlay maximise (module D / M3).

Temporary Gtk.Overlay while maximised: float one pane over the window with
margins, dim siblings, optional expand/restore animation. Not full-window
zoom and not the legacy reparent zoom.
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


def placeholder_pixbuf_scale(pixbuf, alloc_w, scale):
    """m33 post-review: user-space factor to draw a snapshot at logical
    size. Device-res pixbufs (wider than the logical alloc) get 1/scale."""
    try:
        pw = int(pixbuf.get_width())
    except Exception:
        return 1.0
    if scale > 1 and alloc_w > 0 and pw > alloc_w:
        return 1.0 / float(scale)
    return 1.0


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
        if alt is not None and alt.auto_hidden and alt.hidden_width > 0:
            w -= alt.hidden_width
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

    def __init__(self, terminal, pixbuf=None):
        Gtk.DrawingArea.__init__(self)
        self._terminal = terminal
        self._pixbuf = pixbuf
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
        cr.set_source_rgb(0.08, 0.08, 0.08)
        cr.rectangle(0, 0, alloc.width, alloc.height)
        cr.fill()
        if self._pixbuf is not None:
            try:
                # m33 post-review: HiDPI snapshots are device-resolution
                # (w*scale); draw them at logical size, not scale x larger.
                k = placeholder_pixbuf_scale(self._pixbuf, alloc.width,
                                             _scale_factor(widget))
                cr.save()
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
    """Full-window DrawingArea that letterboxes a pixbuf into a progress rect."""

    def __init__(self):
        Gtk.DrawingArea.__init__(self)
        self.set_app_paintable(True)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.FILL)
        self._pixbuf = None
        self._rect = (0.0, 0.0, 1.0, 1.0)
        self._opacity = 1.0
        self.connect('draw', self._on_draw)

    def set_pixbuf(self, pb):
        self._pixbuf = pb
        self.queue_draw()

    def set_progress_rect(self, rect):
        self._rect = rect
        self.queue_draw()

    def set_opacity(self, o):
        self._opacity = max(0.0, min(1.0, float(o)))
        self.queue_draw()

    def _on_draw(self, widget, cr):
        if self._pixbuf is None or self._opacity <= 0.0:
            return False
        x, y, w, h = self._rect
        if w <= 1 or h <= 1:
            return False
        try:
            pw = self._pixbuf.get_width()
            ph = self._pixbuf.get_height()
            if pw <= 0 or ph <= 0:
                return False
            cr.save()
            cr.translate(x, y)
            cr.scale(w / float(pw), h / float(ph))
            Gdk.cairo_set_source_pixbuf(cr, self._pixbuf, 0, 0)
            cr.paint_with_alpha(self._opacity)
            cr.restore()
        except Exception as ex:
            dbg('SnapshotArea draw: %s' % ex)
        return False


class Animator(object):
    """Single tick driver over progress 0 (src) .. 1 (dst).

    start(reverse=False) runs from_progress → 1; reverse=True runs → 0.
    reverse() flips direction mid-flight without a jump. Clock and scheduler
    are injectable for unit tests.
    """

    def __init__(self, on_tick, on_done, clock=None, schedule=None,
                 unschedule=None):
        self._on_tick = on_tick
        self._on_done = on_done
        self._clock = clock or (lambda: time.monotonic())
        self._schedule = schedule or (lambda cb: GLib.timeout_add(16, cb))
        self._unschedule = unschedule or GLib.source_remove
        self._source = None
        self._start = 0.0
        self._duration = 0.2
        self._reverse = False
        self._from = 0.0
        self._progress = 0.0
        self._easing = ease_out_cubic
        self._running = False

    @property
    def running(self):
        return self._running

    @property
    def progress(self):
        return self._progress

    @property
    def reversed(self):
        return self._reverse

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
        self._start = self._clock()
        self._running = True
        self._source = self._schedule(self._tick)

    def reverse(self, duration_ms=None, easing=None):
        """Flip direction from the current progress (no jump)."""
        if not self._running:
            return
        dur = duration_ms if duration_ms is not None else \
            int(self._duration * 1000)
        self.start(dur, reverse=not self._reverse, easing=easing,
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

    def _tick(self):
        if not self._running:
            return False
        raw = (self._clock() - self._start) / self._duration
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

    def __init__(self, window):
        self.window = window
        self.data = None
        self._animator = None
        self._frozen = None  # terminal currently frozen for E

    # -- queries ----------------------------------------------------------

    def is_active(self):
        return self.data is not None

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
        if self.data is not None:
            self.data['main'] = widget

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

    def _resume_font(self, terminal):
        if terminal is None or self._frozen is not terminal:
            return
        self._frozen = None
        resume = getattr(terminal, 'resume_auto_font_scale', None)
        if callable(resume):
            try:
                resume()
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
        reduce_motion = should_reduce_motion(config)
        # Capture BEFORE reparent; failure → no zoom animation
        pixbuf = capture_terminal_pixbuf(terminal) if animate else None
        zoom_anim = bool(animate) and pixbuf is not None and not reduce_motion
        fade_only = bool(animate) and not zoom_anim and reduce_motion

        parent = terminal.get_parent()
        main = Gtk.Window.get_child(window)
        if parent is None or main is None:
            err('overlay_maximise: terminal/main missing')
            return False

        src_rect = _rect_from_widget(terminal, main)
        main_alloc = main.get_allocation()
        dst_rect = (float(self.MARGIN), float(self.MARGIN),
                    max(1.0, main_alloc.width - 2.0 * self.MARGIN),
                    max(1.0, main_alloc.height - 2.0 * self.MARGIN))

        self._pause_font(terminal)

        placeholder = PanePlaceholder(terminal, pixbuf=pixbuf)
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
            snapshot.set_pixbuf(pixbuf)
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
            'src_rect': src_rect,
            'dst_rect': dst_rect,
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
        frame.set_uniform_margin(self.MARGIN)
        # Keep the animation target in sync with the real overlay size
        # (window resized / allocated later than the maximise).
        data_ref = self.data
        overlay.connect('size-allocate',
                        lambda w, a: self._on_overlay_allocate(data_ref, a))
        window._connect_overlay_terminal_signals(terminal)

        overlay.show()
        main.show()
        dim.show()
        frame.show_all()
        if snapshot is not None:
            snapshot.show()
        terminal.grab_focus()

        if zoom_anim or fade_only:
            frame.set_opacity(0.0 if zoom_anim else 1.0)
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
        m = float(self.MARGIN)
        data['dst_rect'] = (m, m, max(1.0, alloc.width - 2.0 * m),
                            max(1.0, alloc.height - 2.0 * m))

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

    def maximise_when_ready(self, terminal):
        """Session restore (P1-2): maximise once the window has a real
        allocation, and only if the terminal's tab is the current one
        (a background-tab pane must not float over the visible tab)."""
        window = self.window
        state = {'hid': None, 'done': False}

        def _finish():
            state['done'] = True
            if state['hid'] is not None:
                try:
                    window.disconnect(state['hid'])
                except Exception:
                    pass
                state['hid'] = None

        def _attempt():
            if state['done']:
                return False
            if getattr(window, 'isDestroyed', False) or \
                    terminal.get_toplevel() is not window:
                _finish()
                return False
            alloc = window.get_allocation()
            if not window.get_mapped() or alloc.width <= 1 or \
                    alloc.height <= 1:
                return False  # wait for size-allocate
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

        def _on_alloc(_w, _a):
            if not state['done']:
                GLib.idle_add(_attempt)

        state['hid'] = window.connect('size-allocate', _on_alloc)
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

        if not animate:
            self._finish_restore()
            return True

        terminal = data['terminal']
        self._pause_font(terminal)
        reduce_motion = should_reduce_motion(self.window.config)
        pixbuf = None if reduce_motion else capture_terminal_pixbuf(terminal)
        data['restore_pending'] = True
        if pixbuf is not None:
            snap = data.get('snapshot')
            if snap is None:
                snap = SnapshotArea()
                data['overlay'].add_overlay(snap)
                try:
                    data['overlay'].set_overlay_pass_through(snap, True)
                except Exception:
                    pass
                data['snapshot'] = snap
            snap.set_pixbuf(pixbuf)
            snap.set_progress_rect(data['dst_rect'])
            snap.set_opacity(1.0)
            snap.show()
            data['frame'].set_opacity(0.0)
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

    def _run_animation(self, expand, reduced):
        data = self.data
        data['animating'] = True
        if reduced:
            ms = self.REDUCED_MS
        elif expand:
            ms = self._config_ms('pane_animation_expand_ms', 200)
        else:
            ms = self._config_ms('pane_animation_restore_ms', 160)
        src, dst = data['src_rect'], data['dst_rect']
        dim_alpha = self.DIM_ALPHA

        def on_tick(progress, raw):
            # Never touch VTE size / font here: only snapshot rect + dim
            data['dim'].set_alpha(dim_alpha * progress)
            snap = data.get('snapshot')
            if snap is None:
                return
            snap.set_progress_rect(interpolate_rect(src, dst, progress))
            anim = self._animator
            expanding = anim is not None and not anim.reversed
            fade_span = min(1.0, 80.0 / max(1.0, float(ms)))
            if expanding and (1.0 - raw) <= fade_span:
                o = (1.0 - raw) / fade_span if fade_span else 0.0
                snap.set_opacity(o)
                data['frame'].set_opacity(1.0 - o)
            else:
                snap.set_opacity(1.0)
                data['frame'].set_opacity(0.0)

        self._animator = Animator(on_tick, self._on_anim_done)
        if expand:
            self._animator.start(ms, reverse=False, easing=ease_out_cubic,
                                 from_progress=0.0)
        else:
            self._animator.start(ms, reverse=True, easing=ease_in_out_cubic,
                                 from_progress=1.0)

    def _on_anim_done(self, cancelled=False):
        data = self.data
        if data is None:
            return
        data['animating'] = False
        if data.get('restore_pending'):
            self._finish_restore()
            return
        self._arrive_maximised()

    def _arrive_maximised(self):
        data = self.data
        if data is None:
            return
        snap = data.get('snapshot')
        if snap is not None:
            snap.set_opacity(0.0)
            snap.hide()
        data['frame'].set_opacity(1.0)
        data['dim'].set_alpha(self.DIM_ALPHA)
        data['ready_at'] = time.monotonic() + self.CLICK_GUARD_MS / 1000.0
        terminal = data['terminal']
        self._resume_font(terminal)
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

        if self._animator is not None:
            self._animator.cancel(silent=True)
        self._animator = None
        self._pause_font(terminal)
        # Round-2 P2-9: on a dying window (destroy teardown / finalize) only
        # put the tree back for describe/close; no focus grab, tier
        # recompute or font resume on terminals that are about to close.
        dying = bool(getattr(window, 'isDestroyed', False) or
                     getattr(window, '_session_destroy_handled', False))

        # Window-side handlers off before the terminal returns to its slot
        try:
            window.disconnect_child(terminal)
        except Exception:
            pass
        frame.set_terminal(None)
        for extra in (frame, data.get('dim'), data.get('snapshot')):
            if extra is not None and extra.get_parent() is overlay:
                overlay.remove(extra)

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
        # The Overlay's Bin child is the real layout root; data['main'] may
        # be stale if the root was replaced while maximised (P0-1).
        try:
            actual_main = Gtk.Bin.get_child(overlay)
        except Exception:
            actual_main = None
        if placeholder.get_parent() is overlay:
            # Siblings all exited: the placeholder became the layout root
            overlay.remove(placeholder)
            main = None
            root_terminal = True
        else:
            # Take the overlay out of the window first so logical_parent and
            # Window.add/remove see the plain tree again
            main = actual_main if actual_main is not None else data['main']

        try:
            if main is not None and main.get_parent() is overlay:
                overlay.remove(main)
            Gtk.Window.remove(window, overlay)
        except Exception as ex:
            dbg('overlay teardown: %s' % ex)

        self.data = None
        window.set_property('term_zoomed', False)

        if root_terminal:
            terminal._overlay_placeholder = None
            window.add(terminal)
        else:
            if main is not None:
                Gtk.Window.add(window, main)
            parent = placeholder.get_parent()
            terminal._overlay_placeholder = None
            if parent is None or not self._swap(parent, placeholder,
                                                 terminal):
                err('overlay restore: placeholder slot lost; terminal %s '
                    'not re-parented' % terminal)
        terminal.show_all()
        placeholder.destroy()
        if dying:
            # Leave the terminal frozen; it is closed right after this.
            self._frozen = None
        else:
            try:
                terminal.grab_focus()
            except Exception:
                pass
            self._resume_font(terminal)
        if data.get('emitted'):
            self._emit_changed(terminal, False)

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
