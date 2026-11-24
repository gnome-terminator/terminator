"""Centralized synchronization state for tmux integration.

All state transitions that cross module boundaries (controller <-> handlers)
emit GObject signals.  State that is internal to a single module or purely
data-tracking (no ordering implications) is stored as simple attributes.

All signal emissions MUST happen on the GTK main thread.
"""

from gi.repository import GObject

from terminatorlib.util import dbg


class TmuxSyncState(GObject.GObject):
    """Single source of truth for tmux sync flags and data."""

    __gsignals__ = {
        # Layout application lifecycle
        'layout-applying': (GObject.SignalFlags.RUN_LAST, None, ()),
        'layout-settled':  (GObject.SignalFlags.RUN_LAST, None,
                            (GObject.TYPE_PYOBJECT,)),

        # Refresh-client round-trip gating
        'refresh-started':  (GObject.SignalFlags.RUN_LAST, None, ()),
        'refresh-complete': (GObject.SignalFlags.RUN_LAST, None, ()),

        # Window resize tracking
        'window-resize-requested': (GObject.SignalFlags.RUN_LAST, None, ()),
        'window-resize-complete':  (GObject.SignalFlags.RUN_LAST, None, ()),

        # Initial capture convergence
        'all-panes-stable': (GObject.SignalFlags.RUN_LAST, None, ()),

        # New paned allocation gating
        'new-paneds-allocated': (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self):
        GObject.GObject.__init__(self)

        # -- Signal-backed flags (use setters to emit signals) --

        self.applying_layout = False
        self.refresh_client_in_flight = False
        self.window_resize_pending = False
        self.layout_change_pending = False
        self.initial_capture_pending = False

        # -- Layout timing / scheduling --

        self.layout_applied_time = 0       # time.monotonic() stamp
        self.layout_clear_source = None    # GLib source ID
        self.layout_clear_scheduled = False

        # -- Size tracking --

        self.last_client_size = None       # (cols, rows) last sent to tmux
        self.last_window_pixels = None     # (w, h) from window.get_size()
        self.last_chrome = None            # (w, h) chrome overhead
        self.prev_vte_sizes = {}           # pane_id -> (cols, rows)
        self.last_pane_sizes = {}          # pane_id -> (cols, rows)
        self.configure_handler_id = None   # GTK configure-event handler

        # -- Tripwire mechanism --

        self.tripwire_armed = False
        self.tripwire_pixels = None        # (w, h) allocation boundary
        self.pending_tripwire_hit = False
        self.tripwire_timer = None         # GLib timeout ID
        self.tmux_max_cols = None          # per-axis limit from tmux
        self.tmux_max_rows = None

        # -- Layout trees and paned tracking --

        self.layout_trees = {}             # window_id -> LayoutNode
        self.tmux_paneds = set()           # all tmux-managed Paned widgets
        self.pending_new_paneds = set()    # new paneds awaiting GTK allocation

        # -- Ratio retry state --

        self.needs_ratio_retry = False
        self.ratios_changed = False
        self.pending_layout_tree = None    # LayoutNode
        self.deferred_layout_tree = None   # stashed during handle drag

        # -- Initial capture stability --

        self.capture_targets = {}          # pane_id -> (cols, rows) from tmux tree
        self.capture_settled = set()       # pane_ids whose VTE matches target
        self.expected_panes = set()        # all pane_ids to wait for
        self.capture_window_pixels = None  # win pixels when targets were set

        # -- Other --

        self.reconcile_timer = None        # GLib source ID

    # ── Signal-emitting setters ───────────────────────────────

    def begin_layout(self):
        """Mark layout application as in-progress."""
        if not self.applying_layout:
            self.applying_layout = True
            self.emit('layout-applying')

    def finish_layout(self, tree):
        """Mark layout application as complete."""
        if self.applying_layout:
            self.applying_layout = False
            self.pending_layout_tree = None
            self.emit('layout-settled', tree)

    def begin_refresh(self):
        """Mark a refresh-client command as in-flight."""
        if not self.refresh_client_in_flight:
            self.refresh_client_in_flight = True
            self.emit('refresh-started')

    def end_refresh(self):
        """Mark the refresh-client round-trip as complete."""
        if self.refresh_client_in_flight:
            self.refresh_client_in_flight = False
            self.emit('refresh-complete')

    def begin_window_resize(self):
        """Mark that we've called window.resize() and await WM response."""
        if not self.window_resize_pending:
            self.window_resize_pending = True
            self.emit('window-resize-requested')

    def end_window_resize(self):
        """Mark that WM has responded to our resize request."""
        if self.window_resize_pending:
            self.window_resize_pending = False
            self.emit('window-resize-complete')

    def mark_pane_stable(self, pane_id):
        """Record that a pane's VTE size matches its tmux tree target.

        Emits 'all-panes-stable' when every expected pane has settled.
        """
        self.capture_settled.add(pane_id)
        if (self.expected_panes and
                self.capture_settled >= self.expected_panes):
            self.initial_capture_pending = False
            self.emit('all-panes-stable')

    def mark_paned_allocated(self, paned):
        """Record that a newly-created paned has its correct allocation.

        Emits 'new-paneds-allocated' when all pending paneds are allocated.
        """
        self.pending_new_paneds.discard(paned)
        if not self.pending_new_paneds:
            self.emit('new-paneds-allocated')

    def clear_capture_state(self):
        """Reset capture tracking after initial capture fires."""
        self.capture_targets.clear()
        self.capture_settled.clear()
        self.expected_panes.clear()
        self.capture_window_pixels = None

    # ── Lifecycle ─────────────────────────────────────────────

    def reset(self):
        """Clear all state (called on stop/cleanup)."""
        self.applying_layout = False
        self.refresh_client_in_flight = False
        self.window_resize_pending = False
        self.layout_change_pending = False
        self.initial_capture_pending = False
        self.layout_applied_time = 0
        self.layout_clear_source = None
        self.layout_clear_scheduled = False
        self.last_client_size = None
        self.last_window_pixels = None
        self.last_chrome = None
        self.prev_vte_sizes.clear()
        self.last_pane_sizes.clear()
        self.configure_handler_id = None
        self.tripwire_armed = False
        self.tripwire_pixels = None
        self.pending_tripwire_hit = False
        self.tripwire_timer = None
        self.tmux_max_cols = None
        self.tmux_max_rows = None
        self.layout_trees.clear()
        self.tmux_paneds.clear()
        self.pending_new_paneds.clear()
        self.needs_ratio_retry = False
        self.ratios_changed = False
        self.pending_layout_tree = None
        self.deferred_layout_tree = None
        self.capture_targets.clear()
        self.capture_settled.clear()
        self.expected_panes.clear()
        self.reconcile_timer = None

    # ── Debug ─────────────────────────────────────────────────

    def dump(self, prefix='TmuxState'):
        """Log all sync state in a single debug line."""
        dbg('%s: applying=%s layout_time=%.3f '
            'refresh=%s win_resize=%s '
            'layout_chg=%s capture=%s '
            'tripwire=%s/%s max=%s/%s '
            'client=%s win_px=%s chrome=%s '
            'trees=%d paneds=%d pending_new=%d '
            'settled=%d/%d' % (
                prefix,
                self.applying_layout,
                self.layout_applied_time,
                self.refresh_client_in_flight,
                self.window_resize_pending,
                self.layout_change_pending,
                self.initial_capture_pending,
                self.tripwire_armed,
                self.tripwire_pixels,
                self.tmux_max_cols,
                self.tmux_max_rows,
                self.last_client_size,
                self.last_window_pixels,
                self.last_chrome,
                len(self.layout_trees),
                len(self.tmux_paneds),
                len(self.pending_new_paneds),
                len(self.capture_settled),
                len(self.expected_panes),
            ))
