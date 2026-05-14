"""Tmux notification handlers - maps tmux events to Terminator widget operations.

All GTK operations are dispatched via GLib.idle_add() for thread safety.
"""

from gi.repository import GLib, Gtk

from terminatorlib.util import dbg
from terminatorlib.tmux.layout import (
    parse_tmux_layout, get_pane_ids, find_pane_parent, find_pane_node,
)


ALTERNATE_SCREEN_ENTER = b'\x1b[?1049h'
ALTERNATE_SCREEN_EXIT = b'\x1b[?1049l'

SHELL_COMMANDS = {'bash', 'zsh', 'fish', 'sh', 'dash', 'csh', 'tcsh', 'ksh'}


class TmuxHandlers:
    """Handles tmux notifications and maps them to Terminator operations."""

    def __init__(self, controller):
        self.controller = controller
        self.state = controller.state
        self.protocol = controller.protocol
        # Register handlers
        self.protocol.add_handler('output', self.on_output)
        self.protocol.add_handler('layout-change', self.on_layout_change)
        self.protocol.add_handler('window-add', self.on_window_add)
        self.protocol.add_handler('window-close', self.on_window_close)
        self.protocol.add_handler('unlinked-window-close', self.on_window_close)
        self.protocol.add_handler('window-renamed', self.on_window_renamed)
        self.protocol.add_handler('exit', self.on_exit)

    _output_count = 0
    _output_log_interval = 50  # log every Nth %output

    def on_output(self, info):
        """Handle %output: feed data to the terminal's VTE."""
        pane_id = info['pane_id']
        data = info['data']

        self.__class__._output_count += 1
        if self.__class__._output_count <= 5 or \
                self.__class__._output_count % \
                self.__class__._output_log_interval == 0:
            dbg('%%output #%d: %s %d bytes' % (
                self.__class__._output_count,
                pane_id, len(data)))

        terminal = self.controller.pane_to_terminal.get(pane_id)
        if not terminal:
            # Buffer output for panes not yet registered (race: %output
            # arrives before _create_tab_for_window finishes).
            buf = self.controller._pending_output
            if pane_id not in buf:
                buf[pane_id] = []
            buf[pane_id].append(data)
            dbg('TmuxHandlers: buffered %%output for unregistered '
                'pane %s (%d chunks)' % (pane_id, len(buf[pane_id])))
            return

        # Track alternate screen state (vim, less, etc.)
        if ALTERNATE_SCREEN_ENTER in data:
            self.controller.pane_alternate[pane_id] = True
        if ALTERNATE_SCREEN_EXIT in data:
            self.controller.pane_alternate[pane_id] = False

        # Feed to VTE on GTK thread
        GLib.idle_add(self._feed_terminal, terminal, data)

    def _feed_terminal(self, terminal, data):
        """Feed data to terminal VTE widget. Must be called on GTK thread."""
        try:
            if hasattr(terminal, 'vte') and terminal.vte:
                terminal.vte.feed(data)
        except Exception as e:
            dbg('TmuxHandlers: feed error: %s' % e)
        return False

    def _feed_terminal_logged(self, terminal, data, pane_id):
        """Feed initial capture data with logging."""
        try:
            if hasattr(terminal, 'vte') and terminal.vte:
                vte = terminal.vte
                cols_before = vte.get_column_count()
                rows_before = vte.get_row_count()
                vte.feed(data)
                dbg('initial capture FED %s: %d bytes '
                    'vte=%dx%d' % (
                    pane_id, len(data),
                    cols_before, rows_before))
            else:
                dbg('initial capture: %s has no vte' % pane_id)
        except Exception as e:
            dbg('initial capture feed error %s: %s' % (
                pane_id, e))
        return False

    def _get_chrome_size(self, window):
        """Compute chrome pixels (tab bar, borders) excluding pane area.

        Chrome = content_allocation - notebook_page_allocation.
        Using the notebook page (not a terminal) avoids counting
        other panes as chrome when splits are present.

        Falls back to preferred sizes when allocations aren't
        available yet (before GTK's first layout pass).
        """
        content = window.get_child()
        if not content:
            return 0, 0
        ca = content.get_allocation()
        if hasattr(content, 'get_current_page'):
            page_num = content.get_current_page()
            if page_num >= 0:
                page = content.get_nth_page(page_num)
                pa = page.get_allocation()
                cw = ca.width - pa.width
                ch = ca.height - pa.height
                if cw > 0 or ch > 0:
                    return cw, ch
                # Allocations not ready — use preferred sizes
                _, cnt_w = content.get_preferred_width()
                _, cnt_h = content.get_preferred_height()
                _, pg_w = page.get_preferred_width()
                _, pg_h = page.get_preferred_height()
                return max(0, cnt_w - pg_w), max(0, cnt_h - pg_h)
        return 0, 0

    def _find_tmux_window(self, terminator):
        """Find the Terminator window that contains this controller's terminals."""
        for window in terminator.windows:
            for terminal in window.get_terminals():
                if terminal in self.controller.terminal_to_pane:
                    return window
        return None

    def _is_active_window(self, tree, window_id=None):
        """Check if this layout tree's panes are in the currently visible tab."""
        # Check tmux's active window flag first (reliable before
        # terminals are mapped and during rapid resize sequences)
        if window_id is None:
            awid = self.controller.active_window_id
            if awid:
                for wid, t in self.state.layout_trees.items():
                    if t is tree:
                        return wid == awid
        elif self.controller.active_window_id:
            return window_id == self.controller.active_window_id
        # Fall back to GTK mapped state
        pane_ids = get_pane_ids(tree)
        for pid in pane_ids:
            terminal = self.controller.pane_to_terminal.get(pid)
            if terminal and terminal.get_mapped():
                return True
        return False

    _layout_change_count = 0

    def on_layout_change(self, info):
        """Handle %layout-change: sync Terminator splits with tmux layout."""
        import time, traceback
        self.__class__._layout_change_count += 1
        window_id = info['window_id']
        layout_string = info['layout_string']

        try:
            new_tree = parse_tmux_layout(layout_string)
        except ValueError as e:
            dbg('TmuxHandlers: layout parse error: %s' % e)
            return

        new_panes = get_pane_ids(new_tree)
        old_tree = self.state.layout_trees.get(window_id)
        old_panes = get_pane_ids(old_tree) if old_tree else set()

        deleted_panes = old_panes - new_panes
        added_panes = new_panes - old_panes

        # Debug: log every layout-change with dimensions and what triggered it
        old_dims = '%dx%d' % (old_tree.width, old_tree.height) if old_tree else 'none'
        new_dims = '%dx%d' % (new_tree.width, new_tree.height)
        client_size = self.state.last_client_size
        elapsed = time.monotonic() - self.state.layout_applied_time \
            if self.state.layout_applied_time else float('inf')
        qd = self.protocol._command_queue.qsize() \
            if hasattr(self.protocol, '_command_queue') else '?'
        dbg('layout-change #%d: %s old=%s new=%s client=%s '
                 'del=%s add=%s elapsed=%.3fs applying=%s '
                 'qd=%s' % (
                     self.__class__._layout_change_count,
                     window_id, old_dims, new_dims, client_size,
                     deleted_panes or '{}', added_panes or '{}',
                     elapsed, self.state.applying_layout, qd))

        self.state.layout_trees[window_id] = new_tree
        self.controller.window_layouts[window_id] = layout_string

        # Update authoritative pane sizes immediately so
        # _feed_terminal (which may run before _update_pane_sizes)
        # buffers %output that's for the new size while VTEs are
        # still at the old size.
        self._record_tmux_sizes(new_tree)

        # Trace window size at layout-change entry
        for t in list(self.controller.terminal_to_pane.keys())[:1]:
            try:
                top = t.get_toplevel()
                wa = top.get_allocation()
                ws = top.get_size()
                va = t.vte.get_allocation()
                vc = t.vte.get_column_count()
                vr = t.vte.get_row_count()
                dbg('size_trace layout-change: '
                    'alloc=%dx%d ws=%dx%d vte=%dx%d '
                    'chars=%dx%d tree=%dx%d' % (
                    wa.width, wa.height, ws[0], ws[1],
                    va.width, va.height, vc, vr,
                    new_tree.width, new_tree.height))
            except Exception:
                pass

        if deleted_panes:
            GLib.idle_add(self._close_panes, deleted_panes)
        elif added_panes:
            GLib.idle_add(self._add_panes, added_panes, new_tree)

        # Resize/constraint logic is active-window-only —
        # background windows must not resize us or set MAX.
        active = self._is_active_window(new_tree, window_id)
        if not active:
            if not deleted_panes and not added_panes:
                dbg('layout-change: skipping resize for background '
                    'window %s' % window_id)
        else:
            new_size = (new_tree.width, new_tree.height)
            # Use state flags instead of elapsed-time heuristic
            # to determine if we caused this layout change.
            we_caused_it = (self.state.refresh_client_in_flight
                            or self.state.window_resize_pending)

            if not client_size:
                # Initial startup: resize to match tree
                GLib.idle_add(self._resize_window_to_tree,
                              new_tree)
            elif new_size != client_size and not we_caused_it:
                # Unsolicited change from tmux/another client
                dbg('layout-change: unsolicited size change '
                    '%dx%d -> %dx%d (elapsed=%.3fs), '
                    'resizing window' % (
                        client_size[0], client_size[1],
                        new_size[0], new_size[1], elapsed))
                self.state.tmux_max_cols = None
                self.state.tmux_max_rows = None
                GLib.idle_add(self._resize_window_to_tree,
                              new_tree)
            elif new_size != client_size and we_caused_it:
                # Response to our refresh-client
                rejected = (new_size[0] < client_size[0] or
                            new_size[1] < client_size[1])
                if rejected:
                    dbg('layout-change: tmux rejected '
                        '%dx%d -> %dx%d '
                        '(elapsed=%.3fs), '
                        're-constraining' % (
                            client_size[0], client_size[1],
                            new_size[0], new_size[1],
                            elapsed))
                else:
                    dbg('layout-change: echo-back size '
                        'change %dx%d -> %dx%d '
                        '(elapsed=%.3fs)' % (
                            client_size[0], client_size[1],
                            new_size[0], new_size[1],
                            elapsed))
            # else: size matches — no window resize needed,
            # ratios applied below via _update_pane_sizes

            # Update max size from tree dimensions (free, no query)
            GLib.idle_add(self._update_max_from_tree,
                          new_tree.width, new_tree.height)

        # Apply tmux's layout positions.  Skip for added panes —
        # _add_panes handles layout via pending_new_paneds mechanism
        # (new widgets need allocation before ratios can apply).
        if not added_panes:
            self.state.layout_change_pending = True
            GLib.idle_add(self._update_pane_sizes, new_tree)

    def _log_layout_sizes(self, node, depth=0):
        """Log tmux layout sizes vs actual VTE and Terminal widget sizes."""
        if node.is_leaf:
            terminal = self.controller.pane_to_terminal.get(node.pane_id)
            if terminal:
                try:
                    vte_cols = terminal.vte.get_column_count()
                    vte_rows = terminal.vte.get_row_count()
                    tw_cols, tw_rows = self.controller._pane_size_for_tmux(terminal)
                    match = 'OK' if (tw_cols == node.width and tw_rows == node.height) else 'MISMATCH'
                    dbg('  %s%s: tmux=%dx%d widget=%dx%d vte=%dx%d %s' % (
                        '  ' * depth, node.pane_id, node.width, node.height,
                        tw_cols, tw_rows, vte_cols, vte_rows, match))
                except Exception:
                    pass
        else:
            dbg('  %s%s split %dx%d:' % ('  ' * depth, node.orientation, node.width, node.height))
            for child in node.children:
                self._log_layout_sizes(child, depth + 1)

    def _update_pane_sizes(self, tree):
        """Update split ratios to match tmux's pane dimensions.
        Called on GTK thread."""
        # Defer if the initial widget tree is still being built.
        # split_axis drains the GTK event queue (main_iteration_do),
        # so an idle_add from on_layout_change can fire mid-build.
        # Running _apply_ratios on a half-built tree sets positions
        # on paneds whose children are about to be replaced, and the
        # subsequent remove() clears position_set — causing GTK to
        # auto-compute a wrong position on the next allocation.
        from terminatorlib.terminator import Terminator
        if Terminator().doing_layout:
            dbg('_update_pane_sizes: deferred (doing_layout)')
            GLib.timeout_add(100, self._update_pane_sizes, tree)
            return False
        # During handle drag: stash tree for replay on release
        # (safety net), but continue processing.  Tmux is the
        # authority — _apply_ratios applies tmux's layout for all
        # paneds, and do_size_allocate suppresses anchoring during
        # drag to prevent fighting.
        for p in self.state.tmux_paneds:
            if getattr(p, '_tmux_handle_pressed', False):
                self.state.deferred_layout_tree = tree
                break
        self.state.layout_change_pending = False
        import time
        # Trace window size at pane-size update
        for t in list(self.controller.terminal_to_pane.keys())[:1]:
            try:
                top = t.get_toplevel()
                wa = top.get_allocation()
                ws = top.get_size()
                va = t.vte.get_allocation()
                vc = t.vte.get_column_count()
                vr = t.vte.get_row_count()
                dbg('size_trace update_pane_sizes: '
                    'alloc=%dx%d ws=%dx%d vte=%dx%d '
                    'chars=%dx%d tree=%dx%d' % (
                    wa.width, wa.height, ws[0], ws[1],
                    va.width, va.height, vc, vr,
                    tree.width, tree.height))
            except Exception:
                pass
        self.state.begin_layout()
        dbg('_apply_layout_to_tree: set applying_layout=True')
        deferred = False
        try:
            self._record_tmux_sizes(tree)
            self.state.ratios_changed = False
            if not tree.is_leaf:
                self.state.needs_ratio_retry = False
                self._apply_ratios(tree)
                if self.state.needs_ratio_retry:
                    if self.state.pending_new_paneds:
                        dbg('retrying ratios when new paneds '
                            'allocated (%d pending)' %
                            len(self.state.pending_new_paneds))
                        self._new_paneds_handler_id = \
                            self.state.connect(
                                'new-paneds-allocated',
                                self._on_new_paneds_ready,
                                tree)
                    else:
                        dbg('retrying ratios in 100ms '
                            '(unallocated paneds)')
                        GLib.timeout_add(
                            100,
                            self._apply_ratios_and_finish,
                            tree)
                    deferred = True
        finally:
            if not deferred:
                import time
                self.state.layout_applied_time = time.monotonic()
                if self.state.ratios_changed:
                    # Ratios changed → VTE allocations will change →
                    # notify_resize will fire and clear the flag
                    # reactively via _finish_applying_layout.
                    self.state.pending_layout_tree = tree
                else:
                    # No ratios changed (single pane or same layout).
                    # No VTE allocations will change, so nothing will
                    # trigger _finish_applying_layout.  Defer to idle
                    # so GTK can process pending allocations (e.g.
                    # notebook tab bar) before the chrome check runs.
                    GLib.idle_add(self._finish_applying_layout, tree)
        return False

    def _apply_ratios_and_finish(self, tree):
        """Deferred callback to apply ratios for unallocated Paneds.

        _applying_layout stays True until all ratios are applied,
        providing continuous suppression of resize echo-back.
        """
        self.state.needs_ratio_retry = False
        self.state.ratios_changed = False
        try:
            self._apply_ratios(tree)
            if self.state.needs_ratio_retry:
                dbg('retrying ratios in 100ms (unallocated paneds)')
                GLib.timeout_add(100, self._apply_ratios_and_finish, tree)
                return False  # keep _applying_layout True
        except Exception:
            pass
        import time
        self.state.layout_applied_time = time.monotonic()
        if self.state.ratios_changed:
            self.state.pending_layout_tree = tree
        else:
            GLib.idle_add(self._finish_applying_layout, tree)
        return False

    def _finish_applying_layout(self, tree):
        """Clear _applying_layout after deferred VTE size-allocate
        handlers have been processed.

        Runs at priority DEFAULT_IDLE+10 (210), which is lower than
        the deferred notify_resize at DEFAULT_IDLE (200).  This
        ensures _applying_layout stays True long enough to suppress
        the stale resize echo-back that would otherwise send a
        refresh-client with pre-ratio VTE column counts.
        """
        import time

        # Recompute positions from the tree using actual post-resize
        # paned allocations.  The first _apply_ratios (from
        # _update_pane_sizes) used pre-resize dimensions; now that
        # the WM resize has landed, recomputing gives exact positions.

        # --- diagnostic: log window and VTE state before _apply_ratios ---
        for t in list(self.controller.terminal_to_pane.keys()):
            try:
                pid = self.controller.terminal_to_pane[t]
                top = t.get_toplevel()
                ws = top.get_size()
                vte = t.vte
                vte_pref_h = vte.get_preferred_height()
                cols = vte.get_column_count()
                rows = vte.get_row_count()
                va = vte.get_allocation()
                char_h = vte.get_char_height()
                # Terminal (VBox) preferred height
                term_pref_h = t.get_preferred_height()
                ta = t.get_allocation()
                dbg('_finish PRE: %s ws=%dx%d '
                    'vte_alloc=%dx%d vte_chars=%dx%d '
                    'vte_pref_h=%s term_pref_h=%s '
                    'term_alloc_h=%d char_h=%d' % (
                    pid, ws[0], ws[1],
                    va.width, va.height, cols, rows,
                    vte_pref_h, term_pref_h,
                    ta.height, char_h))
            except Exception as e:
                dbg('_finish PRE: %s exception: %s' % (
                    self.controller.terminal_to_pane.get(t, '?'), e))
        # Also log root paned preferred height
        for t in list(self.controller.terminal_to_pane.keys())[:1]:
            try:
                rp = self._find_root_paned(t)
                if rp:
                    rp_pref_h = rp.get_preferred_height()
                    rp_alloc = rp.get_allocation()
                    dbg('_finish PRE: root_paned '
                        'pref_h=%s alloc=%dx%d' % (
                        rp_pref_h,
                        rp_alloc.width, rp_alloc.height))
            except Exception:
                pass

        # Re-apply ratios for ALL trees with current (correct)
        # paned allocations.  The first _apply_ratios (from
        # _update_pane_sizes) may have used stale allocations
        # from before the WM responded to our resize.
        self.state.ratios_changed = False
        for t in self.state.layout_trees.values():
            if not t.is_leaf:
                self._apply_ratios(t)
        if self.state.ratios_changed:
            # Ratios changed → VTE sizes are stale.
            # Don't pre-seed stability or clear
            # _applying_layout. Wait for VTE to settle.
            self.state.pending_layout_tree = tree
            return False

        # --- diagnostic: log window and VTE state after _apply_ratios ---
        for t in list(self.controller.terminal_to_pane.keys()):
            try:
                pid = self.controller.terminal_to_pane[t]
                top = t.get_toplevel()
                ws = top.get_size()
                vte = t.vte
                vte_pref_h = vte.get_preferred_height()
                va = vte.get_allocation()
                term_pref_h = t.get_preferred_height()
                ta = t.get_allocation()
                dbg('_finish POST: %s ws=%dx%d '
                    'vte_alloc=%dx%d '
                    'vte_pref_h=%s term_pref_h=%s '
                    'term_alloc_h=%d' % (
                    pid, ws[0], ws[1],
                    va.width, va.height,
                    vte_pref_h, term_pref_h,
                    ta.height))
            except Exception:
                pass
        # Also log root paned preferred height after
        for t in list(self.controller.terminal_to_pane.keys())[:1]:
            try:
                rp = self._find_root_paned(t)
                if rp:
                    rp_pref_h = rp.get_preferred_height()
                    rp_alloc = rp.get_allocation()
                    dbg('_finish POST: root_paned '
                        'pref_h=%s alloc=%dx%d' % (
                        rp_pref_h,
                        rp_alloc.width, rp_alloc.height))
            except Exception:
                pass

        dbg('_finish_applying_layout: clearing applying_layout')
        # Snapshot actual window size so notify_resize detects any
        # WM bounce (the WM may have given us a different size than
        # we requested, and the configure-event handler may have
        # stamped last_window_pixels with a stale value).
        for t in list(self.controller.terminal_to_pane.keys())[:1]:
            try:
                top = t.get_toplevel()
                self.state.last_window_pixels = top.get_size()
                break
            except Exception:
                pass
        # Emits 'layout-settled' — controller's handler clears
        # refresh_client_in_flight and processes tripwire.
        self.state.finish_layout(tree)
        self.state.layout_applied_time = time.monotonic()
        initial = self.state.last_client_size is None
        if not initial:
            # Only update client size from the ACTIVE window's
            # tree — background windows may have stale/different
            # sizes and must not flip-flop the client size.
            active = self._is_active_window(tree)
            if active and tree and tree.width > 0 and tree.height > 0:
                # We just applied the active layout from tmux —
                # the tree dimensions ARE the authoritative client
                # size.  Don't use _calculate_client_size() here:
                # VTE pixel rounding means the sum of VTE chars
                # can exceed the tree, triggering a grow loop
                # (tree→VTE→bigger refresh-client→bigger
                # tree→repeat).
                size = (tree.width, tree.height)
                if size != self.state.last_client_size:
                    dbg('_finish_applying_layout: client size '
                        'changed %dx%d -> %dx%d (from tree)' % (
                        self.state.last_client_size[0],
                        self.state.last_client_size[1],
                        size[0], size[1]))
                    self.state.last_client_size = size
                    self.controller.protocol.send_command(
                        'refresh-client -C {},{}'.format(
                            size[0], size[1]))
                    self.state.layout_applied_time = \
                        time.monotonic()
            self._snapshot_vte_sizes()
            # Check unsettled panes against updated targets.
            # Background panes match immediately; active panes
            # that received their allocation also settle here.
            if self.state.initial_capture_pending:
                self._update_capture_targets()
                for t, pid in (self.controller
                               .terminal_to_pane.items()):
                    if pid in self.state.capture_settled:
                        continue
                    try:
                        c = t.vte.get_column_count()
                        r = t.vte.get_row_count()
                        self._check_pane_stable(pid, c, r)
                    except Exception:
                        pass
        else:
            # Initial startup: VTE hasn't settled into the
            # resized window yet — paned position changes from
            # _apply_ratios are still pending allocation.
            # Skip reconcile; the natural flow (VTE settles →
            # notify_resize → do_resize → refresh-client →
            # layout-change) will converge without it.
            cols = tree.width if tree else 0
            rows = tree.height if tree else 0
            if cols > 0 and rows > 0:
                size = (cols, rows)
                self.state.last_client_size = size
                dbg('_finish_applying_layout: initial '
                    'client size %d,%d (from tree)' % (cols, rows))
                self.controller._refresh_layout_state()
                self._snapshot_vte_sizes()
                # Populate capture targets and check all panes.
                # At initial startup, active-window VTEs are still
                # at stale sizes and won't match targets — they
                # settle later via notify_resize or subsequent
                # _finish rounds.  Background panes match now.
                if self.state.initial_capture_pending:
                    self._update_capture_targets()
                    for t, pid in (self.controller
                                   .terminal_to_pane.items()):
                        if pid in self.state.capture_settled:
                            continue
                        try:
                            c = t.vte.get_column_count()
                            r = t.vte.get_row_count()
                            self._check_pane_stable(pid, c, r)
                        except Exception:
                            pass
        # Check for chrome change (e.g. tab bar appeared) before
        # reconcile.  If chrome changed, update geometry hints first
        # (so the WM snaps to the correct grid), then resize the
        # window.  Skip reconcile — the resize will trigger fresh
        # VTE allocations that produce correct sizes.
        chrome_changed = False
        for t in list(self.controller.terminal_to_pane.keys())[:1]:
            try:
                top = t.get_toplevel()
                chrome = self._get_chrome_size(top)
                if (self.state.last_chrome is not None
                        and chrome != self.state.last_chrome):
                    dbg('_finish_applying_layout: chrome_changed '
                        '%dx%d -> %dx%d' % (
                        self.state.last_chrome[0],
                        self.state.last_chrome[1],
                        chrome[0], chrome[1]))
                    self.state.last_chrome = chrome
                    # Update hints before resize so WM uses new BASE
                    top.set_tmux_geometry_hints(t)
                    self._resize_window_to_tree(tree)
                    self.state.layout_applied_time = \
                        time.monotonic()
                    chrome_changed = True
            except Exception:
                pass
            break

        # No reconcile — refresh-client -C tells tmux the correct
        # total size; tmux distributes panes.  Reconcile's per-pane
        # resize-pane commands caused a feedback loop (resize-pane →
        # layout-change → reconcile → resize-pane → ...) that made
        # pane proportions jump during window resize.
        self.state.dump('_finish_applying_layout')
        return False  # don't repeat

    def _snapshot_vte_sizes(self):
        """Snapshot current VTE sizes into _prev_vte_sizes.

        Called after layout application so notify_resize won't
        misinterpret ratio-driven VTE changes as split-bar drags.
        """
        for t, pid in self.controller.terminal_to_pane.items():
            try:
                self.state.prev_vte_sizes[pid] = (
                    t.vte.get_column_count(), t.vte.get_row_count())
            except Exception:
                pass

    def _schedule_reconcile(self, tree):
        """Schedule reconciliation after all pending allocations.

        Uses idle priority below _finish_applying_layout (210) so
        VTE size-allocate handlers have already run by the time
        reconcile executes — no timer race.
        """
        if self.state.reconcile_timer:
            GLib.source_remove(self.state.reconcile_timer)
        self.state.reconcile_timer = GLib.idle_add(
            self._reconcile_pane_sizes, tree,
            priority=GLib.PRIORITY_DEFAULT_IDLE + 20)

    def _reconcile_pane_sizes(self, tree):
        """Send resize-pane for any pane where VTE is smaller than tmux."""
        import time
        self.state.reconcile_timer = None
        client_size = self.state.last_client_size
        dbg('reconcile: tree=%dx%d client=%s' % (
            tree.width, tree.height, client_size))
        if client_size and (tree.width > client_size[0]
                            or tree.height > client_size[1]):
            dbg('reconcile: skipping — layout %dx%d '
                'exceeds client %dx%d' % (
                tree.width, tree.height,
                client_size[0], client_size[1]))
            return False

        mismatches = []
        self._collect_mismatches(tree, mismatches)
        if not mismatches:
            dbg('reconcile: all panes match tmux')
            return False
        dbg('reconcile: fixing %d mismatched pane(s):' % len(mismatches))
        for pane_id, vte_cols, vte_rows, tmux_cols, tmux_rows in mismatches:
            dbg('  %s: vte=%dx%d tmux=%dx%d' % (
                pane_id, vte_cols, vte_rows, tmux_cols, tmux_rows))
            parts = ['resize-pane -t {}'.format(pane_id)]
            # Only shrink axes — never grow tmux panes
            if vte_cols < tmux_cols:
                parts.append('-x {}'.format(vte_cols))
            if vte_rows < tmux_rows:
                parts.append('-y {}'.format(vte_rows))
            if len(parts) == 1:
                continue  # nothing to shrink
            cmd = ' '.join(parts)
            dbg('reconcile: %s' % cmd)
            self.protocol.send_command(cmd)
        # Suppress echo-back from layout-change responses
        self.state.layout_applied_time = time.monotonic()
        # Snapshot VTE sizes so subsequent notify_resize has correct baseline
        for t, pid in self.controller.terminal_to_pane.items():
            try:
                self.state.prev_vte_sizes[pid] = (
                    t.vte.get_column_count(), t.vte.get_row_count())
            except Exception:
                pass
        self.controller._refresh_layout_state()
        return False

    def _collect_mismatches(self, node, out):
        """Collect panes where VTE is smaller than tmux expects.

        Only shrink direction: if VTE has fewer cols/rows than
        tmux's tree, report it so tmux can reallocate.  Never
        report VTE > tmux — that's pixel rounding slack and
        growing tmux panes causes a feedback loop.
        """
        if node.is_leaf:
            terminal = self.controller.pane_to_terminal.get(node.pane_id)
            if terminal:
                try:
                    vte_cols = terminal.vte.get_column_count()
                    vte_rows = terminal.vte.get_row_count()
                    if (vte_cols < node.width
                            or vte_rows < node.height):
                        out.append((node.pane_id, vte_cols,
                                    vte_rows, node.width,
                                    node.height))
                except Exception:
                    pass
        else:
            for child in node.children:
                self._collect_mismatches(child, out)

    def _record_tmux_sizes(self, node):
        """Record tmux's reported pane sizes to prevent resize feedback loops.

        Only updates _last_pane_sizes (tmux's view). Does NOT touch
        _prev_vte_sizes — those track actual VTE widget sizes and are
        only updated from real VTE measurements in do_resize.
        """
        if node.is_leaf:
            self.state.last_pane_sizes[node.pane_id] = (node.width, node.height)
        else:
            for child in node.children:
                self._record_tmux_sizes(child)

    def _apply_ratios(self, node, expected_allocs=None):
        """Recursively set split ratios on Paned containers to match tmux layout.

        expected_allocs: dict mapping orientation ('h'/'v') → expected
        pixel length, computed from the parent's already-set position.
        Eliminates stale GTK get_length() reads for inner paneds whose
        parent hasn't propagated its allocation yet.

        Computes ratios in pixels (not characters) to account for the
        scrollbar width and titlebar height inside each Terminal widget.
        Without this correction, each pane loses ~1 column/row because
        the character-based ratio doesn't reserve space for scrollbars.

        For N-ary splits (3+ children), the GTK widget tree uses nested
        binary paneds: [A, B, C] becomes Paned1(A, Paned2(B, C)).
        This method sets ratios on all intermediate paneds, not just the
        outermost one.
        """
        if node.is_leaf or len(node.children) < 2:
            return

        # Set ratios for each binary split in the chain.
        # For children [c0, c1, c2, ...], we have paneds:
        #   Paned_0: c0 vs (c1 + c2 + ...)
        #   Paned_1: c1 vs (c2 + ...)     (intermediate paned)
        #   etc.
        orient = node.orientation  # 'h' or 'v'
        remaining = node.children
        expected_child2_len = None
        child_allocs = {}  # child index → allocation in orient

        while len(remaining) >= 2:
            first_leaf_l = self._first_leaf(remaining[0])
            first_leaf_r = self._first_leaf(remaining[1])
            term_l = self.controller.pane_to_terminal.get(first_leaf_l.pane_id)
            term_r = self.controller.pane_to_terminal.get(first_leaf_r.pane_id)

            if not (term_l and term_r):
                break

            paned = self._find_common_paned(term_l, term_r)
            if not (paned and hasattr(paned, 'ratio')):
                break

            # Get metrics from an allocated terminal
            char_w, char_h, sb_w, tb_h, vpad_x, vpad_y = \
                self._get_terminal_metrics(term_l)
            if char_w <= 0 or char_h <= 0:
                char_w, char_h, sb_w, tb_h, vpad_x, vpad_y = \
                    self._get_terminal_metrics(term_r)
            if char_w <= 0 or char_h <= 0:
                break

            # Mark as tmux-managed and stash state reference
            # so _snap_position can check applying_layout.
            paned._tmux_managed = True
            paned._tmux_state = self.state

            handle_size = paned.get_handlesize()
            if expected_child2_len is not None:
                paned_len = expected_child2_len
            elif expected_allocs and orient in expected_allocs:
                paned_len = expected_allocs[orient]
            else:
                paned_len = paned.get_length()

            if paned_len <= handle_size:
                dbg('ratio SKIPPED: paned not allocated '
                         '(len=%d <= handle=%d)' % (paned_len, handle_size))
                self.state.needs_ratio_retry = True
                break

            left_px = self._subtree_px(
                remaining[0], orient,
                char_w, char_h, sb_w, tb_h,
                handle_size, vpad_x, vpad_y)
            right_px = sum(
                self._subtree_px(c, orient,
                                 char_w, char_h, sb_w, tb_h,
                                 handle_size, vpad_x, vpad_y)
                for c in remaining[1:])
            # Add separators between right-side children
            if len(remaining) > 2:
                sep = char_w if orient == 'h' else char_h
                right_px += (len(remaining) - 2) * sep

            # Log tree node dimensions vs paned allocation
            left_node = remaining[0]
            right_nodes = remaining[1:]
            left_dim = ('%dx%d' % (left_node.width,
                                    left_node.height)
                        if left_node.is_leaf
                        else '%s(%dx%d)' % (
                            left_node.orientation,
                            left_node.width,
                            left_node.height))
            right_dim = ','.join(
                ('%dx%d' % (c.width, c.height)
                 if c.is_leaf
                 else '%s(%dx%d)' % (
                     c.orientation, c.width, c.height))
                for c in right_nodes)
            total_needed = left_px + right_px + handle_size
            stale = total_needed > paned_len + handle_size
            dbg('ratio tree: left=[%s] right=[%s] '
                'need=%dpx paned=%dpx %s' % (
                left_dim, right_dim,
                total_needed, paned_len,
                'STALE' if stale else 'ok'))

            # If the paned is newly created and STALE, its GTK
            # allocation hasn't propagated yet — skip it and
            # retry once the correct allocation arrives via
            # the 'new-paneds-allocated' signal.
            if stale and paned in self.state.pending_new_paneds:
                dbg('ratio SKIPPED: new paned has stale '
                    'allocation (need=%d > paned=%d + '
                    'handle=%d)' % (
                    total_needed, paned_len, handle_size))
                self.state.needs_ratio_retry = True
                break

            # Cap paned_len at the pixel budget _subtree_px
            # computed (children + one char-sized separator).
            # Without this, excess padding from an ancestor
            # (char_sep - handle_size per VPaned level) leaks
            # through cross-direction paneds into this one,
            # and this formula adds ANOTHER increment —
            # doubling dead space per nesting level.
            #
            # With the cap, target_pos = left_px + (char_sep -
            # handle_size), giving child1 exactly its content
            # pixels plus one separator's worth of padding
            # above the handle.  Any ancestor excess migrates
            # to the deepest child2 as sub-row dead space.
            char_sep = char_h if orient == 'v' else char_w
            padded_need = left_px + right_px + char_sep
            effective_len = min(paned_len, padded_need)
            target_pos = max(0,
                effective_len - right_px - handle_size)

            # Snap so child2 starts at a character cell boundary.
            # Without this, floor(pixels / char_w) can be off by 1
            # from what tmux expects, causing %output to be fed at
            # the wrong column count.
            aligned = round(
                (target_pos + handle_size) / char_sep) * char_sep
            target_pos = max(0, aligned - handle_size)

            # Detect if user is actively dragging THIS handle:
            # mouse button held + position differs from last sync
            # + length unchanged (not a parent reallocation).
            synced = getattr(paned, '_tmux_synced_pos', None)
            prev_len = getattr(paned, '_tmux_prev_len', None)
            cur_pos = paned.get_position()
            user_dragging = (getattr(paned,
                                 '_tmux_handle_pressed', False)
                             and synced is not None
                             and prev_len is not None
                             and cur_pos != synced
                             and paned_len == prev_len)

            skip_tag = ' SKIP(user dragging)' if user_dragging \
                else ''

            dbg('ratio %s-split: left=%dpx right=%dpx '
                     'pos=%d old_pos=%d paned=%d eff=%d '
                     'char=%dx%d sb=%d tb=%d handle=%d '
                     'vte_pad=%dx%d%s' % (
                         orient, left_px, right_px, target_pos,
                         cur_pos, paned_len, effective_len,
                         char_w, char_h, sb_w, tb_h,
                         handle_size, vpad_x, vpad_y,
                         skip_tag))

            if user_dragging:
                # Don't fight GTK's native drag for THIS handle.
                # DON'T update synced_pos — keep it at the last
                # confirmed position so _send_split_bar_resize
                # can detect continued movement (pos != synced).
                pass
            elif abs(cur_pos - target_pos) > 0:
                paned.set_pos(target_pos)
                paned.ratio = paned.ratio_by_position(
                    paned_len, handle_size, target_pos)
                self.state.ratios_changed = True
                paned._tmux_synced_pos = paned.get_position()
            else:
                paned._tmux_synced_pos = cur_pos

            paned._tmux_prev_len = paned_len
            effective_pos = paned.get_position()
            expected_child2_len = (paned_len - effective_pos
                                   - handle_size)
            mgap = getattr(paned, '_measured_gap', None)
            c2 = paned.get_child2()
            c2w = c2.get_allocation().width if c2 else -1
            c2h = c2.get_allocation().height if c2 else -1
            dbg('ratio child2: pos=%d paned=%d handle=%d '
                'mgap=%s expect_c2=%d actual_c2=%s' % (
                effective_pos, paned_len, handle_size,
                mgap, expected_child2_len,
                '%dx%d' % (c2w, c2h) if c2 else 'None'))
            child_idx = len(node.children) - len(remaining)
            child_allocs[child_idx] = effective_pos
            if not getattr(paned, '_tmux_anchor_connected', False):
                paned.connect('button-press-event',
                              self._on_paned_button_press)
                paned.connect('button-release-event',
                              self._on_paned_button_release)
                paned._tmux_anchor_connected = True

            # Store child1's pane_id — use the first leaf so
            # resize-pane targets a pane spanning child1's full
            # extent (height for VPaned, width for HPaned).
            # The last leaf can be deeply nested in a cross-
            # orientation sub-split, causing tmux to move an
            # internal boundary instead of the main split.
            first_leaf_l = self._first_leaf(remaining[0])
            paned._tmux_child1_pane_id = first_leaf_l.pane_id
            self.state.tmux_paneds.add(paned)

            # Move to the next intermediate paned
            remaining = remaining[1:]

        # Record last child's allocation from the final
        # expected_child2_len (set by the last while iteration).
        if expected_child2_len is not None and len(node.children) >= 2:
            child_allocs[len(node.children) - 1] = expected_child2_len

        # Recurse into children, passing expected allocations so
        # inner paneds use computed sizes instead of stale GTK values.
        for idx, child in enumerate(node.children):
            if not child.is_leaf:
                new_allocs = dict(expected_allocs or {})
                if idx in child_allocs:
                    new_allocs[orient] = child_allocs[idx]
                self._apply_ratios(child, new_allocs)

    def _subtree_px(self, node, orientation, char_w, char_h, sb_w, tb_h,
                     handle_size, vte_pad_x=0, vte_pad_y=0):
        """Compute target pixel extent of a layout subtree along orientation.

        For 'h' orientation: returns width in pixels (chars*char_w + vte_pad + scrollbar + handles).
        For 'v' orientation: returns height in pixels (chars*char_h + vte_pad + titlebar + handles).

        vte_pad_x/y accounts for VTE's internal CSS padding (typically 1px
        each side). Without this, VTE gets exactly cols*char_w pixels but
        subtracts its padding first, leaving room for only cols-1 characters.
        """
        if node.is_leaf:
            if orientation == 'h':
                return node.width * char_w + vte_pad_x + sb_w
            else:
                return node.height * char_h + vte_pad_y + tb_h

        if node.orientation == orientation:
            # Same direction: sum children + separators.
            # For v-splits, use char_h as separator size (not handle_size)
            # so the total matches tmux's 1-char-tall separators. The
            # extra pixels (char_h - handle_size) become padding in
            # _apply_ratios to visually merge with the handle.
            child_px = [self._subtree_px(c, orientation,
                                         char_w, char_h, sb_w, tb_h,
                                         handle_size, vte_pad_x, vte_pad_y)
                        for c in node.children]
            sep = char_w if orientation == 'h' else char_h
            return sum(child_px) + (len(child_px) - 1) * sep
        else:
            # Cross direction: take max — a v-split child needs more
            # pixels than a leaf for the same character count (extra
            # titlebars, VTE padding, handles inside the subtree).
            return max(self._subtree_px(c, orientation,
                                        char_w, char_h, sb_w, tb_h,
                                        handle_size, vte_pad_x, vte_pad_y)
                       for c in node.children)

    def _get_terminal_metrics(self, terminal):
        """Get char/scrollbar/titlebar/VTE-padding pixel sizes from a terminal.

        Returns (char_w, char_h, sb_w, tb_h, vte_pad_x, vte_pad_y).
        char_w and char_h are fractional (Pango-based) for accuracy —
        get_char_width()/get_char_height() truncate to int, and the
        error accumulates over many characters.
        Returns all zeros if the terminal is not yet allocated.
        """
        try:
            int_cw = terminal.vte.get_char_width()
            int_ch = terminal.vte.get_char_height()
            alloc = terminal.vte.get_allocation()
            if int_cw <= 0 or int_ch <= 0 \
                    or alloc.width <= int_cw \
                    or alloc.height <= int_ch:
                return 0, 0, 0, 0, 0, 0
            char_w = int_cw
            char_h = int_ch
            # Scrollbar is overlaid (Gtk.Overlay) — it doesn't consume
            # layout space, so sb_w is always 0 for pixel calculations.
            sb_w = 0
            # Titlebar: only counts if packed in the Terminal VBox
            # (consuming layout space). When overlaid (tmux mode), the
            # titlebar's parent is the Overlay, not the Terminal VBox.
            tb_h = 0
            if (hasattr(terminal, 'titlebar') and terminal.titlebar
                    and terminal.titlebar.get_visible()
                    and terminal.titlebar.get_parent() == terminal):
                tb_h = terminal.titlebar.get_allocation().height
            vte_pad_x = 0
            vte_pad_y = 0
            return char_w, char_h, sb_w, tb_h, vte_pad_x, vte_pad_y
        except Exception:
            return 0, 0, 0, 0, 0, 0

    def _on_paned_button_press(self, paned, event):
        """Track when user starts dragging a paned handle.

        GTK propagates button-press from child paneds up to parents.
        Only set the flag if the click actually landed on THIS
        paned's handle — not on a descendant widget.
        """
        if event.button == 1:
            target = Gtk.get_event_widget(event)
            c1 = paned.get_child1()
            c2 = paned.get_child2()
            parent = target.get_parent() if target else None
            child1_id = getattr(paned,
                '_tmux_child1_pane_id', '?')
            dbg('paned button-press RAW: child1=%s '
                'target=%s parent=%s paned=%s '
                'is_paned=%s is_c1=%s is_c2=%s' % (
                child1_id,
                type(target).__name__ if target else None,
                type(parent).__name__ if parent else None,
                type(paned).__name__,
                target is paned,
                target is c1,
                target is c2))
            # Accept if the click is on the paned or its handle —
            # reject clicks that bubbled up from child widgets.
            on_handle = (target is paned
                         or (target is not None
                             and parent is paned
                             and target is not c1
                             and target is not c2))
            if on_handle:
                dbg('paned button-press: child1=%s' % child1_id)
                paned._tmux_handle_pressed = True
        return False  # let GTK handle the drag

    def _on_paned_button_release(self, paned, event):
        """Track when user stops dragging a paned handle.

        Sends a final resize-pane so tmux knows the exact end
        position, then replays any stashed layout so tmux's
        authoritative layout reconciles all pane positions.
        """
        if event.button == 1:
            child1_id = getattr(paned,
                '_tmux_child1_pane_id', '?')
            dbg('paned button-release: child1=%s' % child1_id)
            # Send final resize-pane BEFORE clearing drag state
            # so _send_split_bar_resize can still detect this
            # handle as the dragged one (cur_pos != synced_pos).
            self.controller._send_split_bar_resize()
            paned._tmux_handle_pressed = False
            paned._tmux_synced_pos = paned.get_position()
            # Discard stale deferred layout — the final
            # resize-pane triggers a fresh layout-change from
            # tmux that reconciles all positions correctly.
            self.state.deferred_layout_tree = None
        return False

    def _on_new_paned_allocated(self, paned, allocation):
        """One-shot size-allocate handler for newly created paneds.

        Waits for a second allocation — the first is the default
        half-size from GTK, the second is the correct propagated
        size from the parent container.
        """
        paned_len = paned.get_length()
        if paned_len <= paned.get_handlesize():
            return  # completely unallocated, keep waiting

        prev = getattr(paned, '_tmux_prev_alloc_len', None)
        paned._tmux_prev_alloc_len = paned_len
        if prev is None:
            return  # first alloc (default half-size), wait

        # Second+ allocation — disconnect and mark allocated
        handler_id = getattr(paned,
                             '_tmux_alloc_handler_id', None)
        if handler_id:
            paned.disconnect(handler_id)
            paned._tmux_alloc_handler_id = None
        self.state.mark_paned_allocated(paned)

    def _on_new_paneds_ready(self, state, tree):
        """Signal: all new paneds allocated — apply ratios."""
        dbg('new-paneds-allocated: applying ratios')
        hid = getattr(self, '_new_paneds_handler_id', None)
        if hid:
            self.state.disconnect(hid)
            self._new_paneds_handler_id = None
        self._apply_ratios_and_finish(tree)

    def _get_handle_size(self, terminal):
        """Get Paned handle size by walking up from a terminal."""
        w = terminal.get_parent()
        while w is not None:
            if hasattr(w, 'get_handlesize'):
                return w.get_handlesize()
            w = w.get_parent()
        return 0

    def _find_root_paned(self, terminal):
        """Find the highest Paned ancestor (the content container)."""
        root_paned = None
        w = terminal.get_parent()
        while w is not None:
            if hasattr(w, 'get_handlesize'):
                root_paned = w
            w = w.get_parent()
        return root_paned

    def _find_common_paned(self, term_a, term_b):
        """Find the Paned widget that is the direct common parent of two terminals."""
        # Walk up from term_a collecting parents
        parents_a = []
        w = term_a.get_parent()
        while w is not None:
            parents_a.append(w)
            w = w.get_parent()
        # Walk up from term_b and find first match
        w = term_b.get_parent()
        while w is not None:
            if w in parents_a:
                return w
            w = w.get_parent()
        return None

    def _close_panes(self, pane_ids):
        """Close terminals for deleted panes. Called on GTK thread."""
        for pane_id in pane_ids:
            terminal = self.controller.pane_to_terminal.get(pane_id)
            if terminal:
                # Clean up any pending allocation tracking
                paned = terminal.get_parent()
                if (paned and paned in
                        self.state.pending_new_paneds):
                    handler_id = getattr(
                        paned, '_tmux_alloc_handler_id', None)
                    if handler_id:
                        paned.disconnect(handler_id)
                        paned._tmux_alloc_handler_id = None
                    self.state.pending_new_paneds.discard(paned)
                terminal._tmux_closing = True
                terminal.close()
        return False

    def _add_panes(self, pane_ids, layout_tree):
        """Create terminals for new panes. Called on GTK thread."""
        from terminatorlib.factory import Factory
        maker = Factory()

        # Suppress notify_resize during transient allocations
        # from split_axis — the sizes are wrong until
        # _update_pane_sizes applies the correct ratios.
        self.state.begin_layout()

        for pane_id in pane_ids:
            pane_node = find_pane_node(pane_id, layout_tree)
            parent_container = find_pane_parent(pane_id, layout_tree)
            if not pane_node or not parent_container:
                continue

            # Find the sibling pane (the one before the new pane in the parent)
            idx = None
            for i, child in enumerate(parent_container.children):
                if child.is_leaf and child.pane_id == pane_id:
                    idx = i
                    break
            if idx is None:
                continue

            # Find the previous sibling's terminal
            sibling_idx = idx + 1 if idx + 1 < len(parent_container.children) else idx - 1
            if sibling_idx >= len(parent_container.children):
                continue
            sibling = parent_container.children[sibling_idx]
            if not sibling.is_leaf:
                continue
            old_terminal = self.controller.pane_to_terminal.get(sibling.pane_id)
            if not old_terminal:
                continue

            # Create new terminal
            new_terminal = maker.make('Terminal')
            new_terminal.tmux_pane_id = pane_id
            new_terminal._make_titlebar_overlay()
            self.controller.register_terminal(pane_id, new_terminal)

            # Don't capture-pane here — the shell prompt and any
            # output that arrived before registration are already
            # buffered in _pending_output and replayed by
            # register_terminal.  Capturing would duplicate them.

            # Split the existing terminal
            old_parent = old_terminal.get_parent()
            vertical = parent_container.orientation == 'v'
            widget_first = idx > sibling_idx
            old_parent.split_axis(old_terminal, vertical=vertical,
                                   sibling=new_terminal, widgetfirst=widget_first)

            # Track the new paned for allocation gating —
            # _apply_ratios will skip STALE paneds in this set
            # and retry once their size-allocate fires.
            new_paned = new_terminal.get_parent()
            if new_paned and isinstance(new_paned, Gtk.Paned):
                self.state.pending_new_paneds.add(new_paned)
                handler_id = new_paned.connect(
                    'size-allocate',
                    self._on_new_paned_allocated)
                new_paned._tmux_alloc_handler_id = handler_id

        # Cancel any stale _layout_clear_source that notify_resize
        # scheduled during split_axis (via main_iteration_do).
        # Those were scheduled with pending_layout_tree=None and
        # would clear applying_layout prematurely.
        src = self.state.layout_clear_source
        if src:
            GLib.source_remove(src)
            self.state.layout_clear_source = None

        # Apply ratios after GTK processes the new paned.
        # _apply_ratios handles unallocated paneds via
        # _needs_ratio_retry (100ms timeout).
        GLib.idle_add(self._update_pane_sizes, layout_tree)

        return False

    def _feed_captured(self, terminal, result):
        """Feed captured pane content to a terminal."""
        if result.is_error or not result.output_lines:
            return
        from terminatorlib.tmux.protocol import unescape_tmux_output
        raw = b'\r\n'.join(line for line in result.output_lines if line)
        data = unescape_tmux_output(raw)
        GLib.idle_add(self._feed_terminal, terminal, data)

    def on_window_add(self, info):
        """Handle %window-add: query the new window's layout, then create a tab."""
        window_id = info.get('window_id', '')
        dbg('TmuxHandlers: window-add: %s' % window_id)
        # Query the layout of this specific window
        self.protocol.send_command(
            'list-windows -F "W:#{{window_id}}:#{{window_index}}:#{{window_name}}:#{{window_layout}}" -f "#{{==:#{{window_id}},{wid}}}"'.format(
                wid=window_id),
            callback=lambda result, wid=window_id: self._on_new_window_layout(wid, result),
        )

    def _on_new_window_layout(self, window_id, result):
        """Handle layout query for a newly added window."""
        if result.is_error:
            dbg('TmuxHandlers: new window layout query error')
            return
        for line in result.output_lines:
            decoded = line.decode('utf-8', errors='replace').strip()
            if not decoded.startswith('W:@'):
                continue
            rest = decoded[2:]
            parts = rest.split(':', 3)
            if len(parts) < 4:
                continue
            wid = parts[0]
            window_index = parts[1]
            window_name = parts[2]
            layout_string = parts[3]
            self.controller.window_layouts[window_id] = layout_string
            self.controller.window_names[window_id] = window_name
            self.controller.window_indices[window_id] = window_index
            try:
                tree = parse_tmux_layout(layout_string)
                self.state.layout_trees[window_id] = tree
            except ValueError as e:
                dbg('TmuxHandlers: parse error for new window %s: %s' % (window_id, e))
                return
            GLib.idle_add(self._create_tab_for_window, window_id, tree)
            return

    def _create_tab_for_window(self, window_id, tree):
        """Create a new Terminator tab for a tmux window. Called on GTK thread.

        Builds the full split tree with correct sizes matching tmux's
        actual pane dimensions.
        """
        from terminatorlib.factory import Factory
        from terminatorlib.terminator import Terminator

        term = Terminator()
        maker = Factory()

        # Create the first terminal from the first leaf
        first_pane_id = self._first_leaf(tree).pane_id
        root_terminal = maker.make('Terminal')
        root_terminal.tmux_pane_id = first_pane_id
        root_terminal._make_titlebar_overlay()
        self.controller.register_terminal(first_pane_id, root_terminal)

        # Add as a new tab
        window = self._find_tmux_window(term)
        if not window:
            dbg('TmuxHandlers: no tmux window to add tab to')
            return False

        if not window.is_child_notebook():
            Factory().make('Notebook', window=window)
        notebook = window.get_child()
        notebook.newtab(widget=root_terminal)

        # Set initial tab label from cached window name, then refresh
        # with full formatting (async query to tmux)
        name = self.controller.window_names.get(window_id, '')
        if name:
            tab_root = notebook.find_tab_root(root_terminal)
            if tab_root:
                label = notebook.get_tab_label(tab_root)
                if label:
                    label.set_label('[%s]' % name)
        self._refresh_tab_labels()

        # Now build the rest of the split tree
        if not tree.is_leaf:
            self._build_split_tree(tree, root_terminal, maker)

        return False

    def _first_leaf(self, node):
        """Find the first leaf node in a layout tree."""
        if node.is_leaf:
            return node
        return self._first_leaf(node.children[0])

    def _last_leaf(self, node):
        """Find the last leaf node in a layout tree."""
        if node.is_leaf:
            return node
        return self._last_leaf(node.children[-1])

    def _build_split_tree(self, node, terminal, maker):
        """Recursively split terminals to match the tmux layout tree.

        Starting from a single terminal that represents the first leaf,
        split it for each additional child in the layout node.
        """
        if node.is_leaf:
            return

        # The terminal currently represents the first child.
        # For each subsequent child, split from the previous terminal.
        current_terminal = terminal
        for i in range(1, len(node.children)):
            child = node.children[i]
            first_leaf = self._first_leaf(child)

            new_terminal = maker.make('Terminal')
            new_terminal.tmux_pane_id = first_leaf.pane_id
            new_terminal._make_titlebar_overlay()
            self.controller.register_terminal(first_leaf.pane_id, new_terminal)

            # vertical=True means VPaned (top/bottom split) = tmux 'v' orientation
            vertical = node.orientation == 'v'

            # Calculate ratio: size of everything before this child / total
            if vertical:
                prev_size = sum(node.children[j].height for j in range(i))
                total_size = sum(c.height for c in node.children)
            else:
                prev_size = sum(node.children[j].width for j in range(i))
                total_size = sum(c.width for c in node.children)

            parent = current_terminal.get_parent()
            parent.split_axis(current_terminal, vertical=vertical,
                              sibling=new_terminal, widgetfirst=True)

            # Set the ratio on the newly created paned container
            paned = current_terminal.get_parent()
            if hasattr(paned, 'ratio') and total_size > 0:
                # For the i-th split, ratio is first_child / (first + second)
                first_child = node.children[i - 1]
                if vertical:
                    ratio = first_child.height / (first_child.height + child.height)
                else:
                    ratio = first_child.width / (first_child.width + child.width)
                paned.ratio = ratio
                paned.set_position_by_ratio()

            # If the child itself has sub-splits, recurse
            if not child.is_leaf:
                self._build_split_tree(child, new_terminal, maker)

            # The current terminal for the next iteration stays the same
            # (we always split from the last terminal added)
            current_terminal = new_terminal

        # Also recurse into the first child if it has sub-splits
        first_child = node.children[0]
        if not first_child.is_leaf:
            self._build_split_tree(first_child, terminal, maker)

    def on_window_close(self, info):
        """Handle %window-close: close all terminals in that window."""
        window_id = info.get('window_id', '')
        dbg('window-close: %s (known trees: %s)' % (
            window_id, list(self.state.layout_trees.keys())))
        tree = self.state.layout_trees.pop(window_id, None)
        self.controller.window_layouts.pop(window_id, None)
        if tree:
            pane_ids = get_pane_ids(tree)
            dbg('closing panes: %s' % pane_ids)
            GLib.idle_add(self._close_panes, pane_ids)
        else:
            dbg('TmuxHandlers: no tree found for window %s' % window_id)

    def on_window_renamed(self, info):
        """Handle %window-renamed: refresh tab labels from tmux."""
        window_id = info.get('window_id', '')
        name = info.get('name', '')
        dbg('TmuxHandlers: window-renamed: %s -> %s' % (window_id, name))
        self.controller.window_names[window_id] = name
        # Refresh with full formatting (command, path, custom title)
        self._refresh_tab_labels()

    def _update_tab_label(self, window_id, tab_label):
        """Update the tab label for a tmux window. Called on GTK thread."""
        tree = self.state.layout_trees.get(window_id)
        if not tree:
            return False
        # Store window name and index on all terminals in this window
        name = self.controller.window_names.get(window_id, '')
        index = self.controller.window_indices.get(window_id, '')
        for pane_id in get_pane_ids(tree):
            t = self.controller.pane_to_terminal.get(pane_id)
            if t:
                t._tmux_window_name = name
                t._tmux_window_index = index
        first_pane_id = self._first_leaf(tree).pane_id
        terminal = self.controller.pane_to_terminal.get(first_pane_id)
        if not terminal:
            return False
        widget = terminal.get_parent()
        while widget is not None:
            if hasattr(widget, 'find_tab_root'):
                tab_root = widget.find_tab_root(terminal)
                if tab_root:
                    label = widget.get_tab_label(tab_root)
                    if label and label.get_label() != tab_label:
                        label.set_label(tab_label)
                break
            widget = widget.get_parent()
        return False

    def on_exit(self, info):
        """Handle %exit: clean up everything."""
        reason = info.get('reason', 'unknown')
        dbg('TmuxHandlers: exit: %s' % reason)
        # Restore termios immediately on the reader thread, before the
        # shell resumes and readline saves the wrong terminal state.
        # Close the duped fd to force the bridge reader to stop instantly
        # so it can't consume the shell's prompt from the PTY buffer.
        # The original fd (in _saved_pty) remains open for VTE.
        proto = self.controller.protocol
        if hasattr(proto, '_bridge'):
            proto._bridge.restore_termios()
            import os
            try:
                os.close(proto._bridge._fd)
            except OSError:
                pass
            proto._bridge._alive = False
        GLib.idle_add(self._handle_exit)

    def _handle_exit(self):
        """Handle tmux exit on GTK thread."""
        from terminatorlib.terminator import Terminator
        term = Terminator()
        window = self._find_tmux_window(term)
        # Close any remaining terminals (tmux may not send %window-close
        # for the last window before %exit)
        for terminal in list(self.controller.pane_to_terminal.values()):
            terminal._tmux_closing = True
            terminal.close()
        self.controller.stop(send_detach=False)
        # If the window still exists and has no children, destroy it
        if window:
            window.hoover()
        return False

    def on_initial_list_windows(self, result):
        """Handle the initial list-windows response.

        Parses window layouts and stores them for initial layout building.
        """
        if result.is_error:
            dbg('TmuxHandlers: initial list-windows error')
            return

        for line in result.output_lines:
            decoded = line.decode('utf-8', errors='replace').strip()
            if not decoded:
                continue
            # Format: W:@WINDOW_ID:INDEX:NAME:ACTIVE:LAYOUT
            if not decoded.startswith('W:@'):
                dbg('TmuxHandlers: skipping invalid line: %s' % decoded)
                continue
            # Strip the W: prefix, split on colons
            rest = decoded[2:]
            parts = rest.split(':', 4)
            if len(parts) < 5:
                continue
            window_id = parts[0]
            window_index = parts[1]
            window_name = parts[2]
            window_active = parts[3]
            layout_string = parts[4]
            if window_active == '1':
                self.controller.active_window_id = window_id
            self.controller.window_layouts[window_id] = layout_string
            self.controller.window_names[window_id] = window_name
            self.controller.window_indices[window_id] = window_index
            try:
                tree = parse_tmux_layout(layout_string)
                self.state.layout_trees[window_id] = tree
            except ValueError as e:
                dbg('TmuxHandlers: parse error for window %s: %s' % (window_id, e))

        dbg('TmuxHandlers: initial layout parsed, %d windows' %
            len(self.controller.window_layouts))

        # Signal the controller that the initial layout is ready
        self.controller._initial_layout_ready.set()

        # Trees just refreshed — re-check capture targets in case
        # the initial _finish_applying_layout set targets from stale
        # pre-refresh trees (background windows may have different
        # sizes before refresh-client adjusts them).
        if self.state.initial_capture_pending:
            GLib.idle_add(self._refresh_capture_after_trees)

    def _refresh_capture_after_trees(self):
        """Re-check capture targets after trees refreshed."""
        if not self.state.initial_capture_pending:
            return False
        self._update_capture_targets()
        for t, pid in self.controller.terminal_to_pane.items():
            if pid in self.state.capture_settled:
                continue
            try:
                c = t.vte.get_column_count()
                r = t.vte.get_row_count()
                self._check_pane_stable(pid, c, r)
            except Exception:
                pass
        return False

    def capture_initial_content(self):
        """Set up initial state after terminals are registered.

        Sends the initial resize command, captures existing pane content
        once (for re-attach), and starts the periodic title refresh timer.
        After this initial capture, all content comes via %output.
        """
        self._send_initial_resize()
        # Defer initial capture until after first ratio reconciliation
        # so VTEs are at the correct size.  The 'all-panes-stable'
        # signal fires exactly once when every pane reports a stable
        # size — _do_initial_capture runs in response.
        self.state.initial_capture_pending = True
        self.state.connect('all-panes-stable',
                           lambda s: self._on_all_panes_stable())
        self._refresh_pane_titles()
        self._refresh_tab_labels()
        self._title_timer = GLib.timeout_add(3000, self._periodic_title_refresh)

    def _send_initial_captures(self):
        """One-shot capture of existing pane content for re-attach.

        Called after the first ratio reconciliation so VTEs are at their
        correct size. Never called again — subsequent content arrives
        via the %output stream.
        """
        all_panes = []
        for window_id, tree in self.state.layout_trees.items():
            pids = get_pane_ids(tree)
            all_panes.extend(sorted(pids))
        dbg('sending initial capture-pane commands: %s '
            '(queue depth=%d)' % (
            all_panes,
            self.protocol._command_queue.qsize()
            if hasattr(self.protocol, '_command_queue')
            else '?'))
        for pid in all_panes:
            self.protocol.send_command(
                'capture-pane -J -p -t {} -e -S - -E -'.format(
                    pid),
                callback=lambda result, _pid=pid:
                    self._feed_initial_capture(_pid, result),
            )

    def _feed_initial_capture(self, pane_id, result):
        """Feed initially captured content to the right terminal."""
        if result.is_error:
            dbg('initial capture ERROR for %s: %d lines' % (
                pane_id, len(result.output_lines)))
            return
        terminal = self.controller.pane_to_terminal.get(pane_id)
        if not terminal:
            dbg('initial capture: no terminal for %s' % pane_id)
            return
        if not result.output_lines:
            dbg('initial capture: empty result for %s' % pane_id)
            return
        from terminatorlib.tmux.protocol import unescape_tmux_output
        non_empty = [line for line in result.output_lines if line]
        raw = b'\r\n'.join(non_empty)
        data = unescape_tmux_output(raw)
        dbg('initial capture: %s lines=%d non_empty=%d '
            'raw=%d data=%d bytes' % (
            pane_id, len(result.output_lines),
            len(non_empty), len(raw), len(data)))
        GLib.idle_add(self._feed_terminal_logged,
                      terminal, data, pane_id)

    def _check_pane_stable(self, pane_id, cols, rows):
        """Settle pane if VTE size matches its tmux tree target.

        Called from notify_resize (non-suppressed path) and from
        _finish_applying_layout.  Skips during applying_layout since
        VTE sizes are transitional and won't match targets yet.
        """
        if self.state.applying_layout:
            return
        # Targets are only valid for the window size they were
        # computed from.  If the window changed (WM adjustment,
        # user resize), block settling — a new layout round will
        # set fresh targets from the updated tree.
        if (self.state.capture_window_pixels is not None
                and self.state.last_window_pixels
                    != self.state.capture_window_pixels):
            return
        target = self.state.capture_targets.get(pane_id)
        if target is not None and (cols, rows) == target:
            self.state.mark_pane_stable(pane_id)

    def _update_capture_targets(self):
        """Populate target sizes from tmux layout tree nodes.

        Also records the current window pixel size.  Targets are
        only valid for this window size — if the window changes
        (e.g. WM adjustment), _check_pane_stable blocks settling
        until fresh targets are set from the new layout.

        Only ACTIVE window panes are added to expected_panes.
        Background tab VTEs don't get GTK allocations after a
        window resize, so they'd never settle (stale allocation
        size != post-resize tree target).
        """
        self.state.capture_targets.clear()
        self.state.capture_settled.clear()
        # Collect targets from all trees (for reference)
        for tree in self.state.layout_trees.values():
            self._collect_capture_targets(tree)
        # Only wait for active window panes to settle — background
        # tab VTEs have stale allocations from GTK.
        active_panes = set()
        awid = self.controller.active_window_id
        if awid and awid in self.state.layout_trees:
            active_panes = get_pane_ids(
                self.state.layout_trees[awid])
        self.state.expected_panes = active_panes & set(
            self.controller.terminal_to_pane.values())
        self.state.capture_window_pixels = \
            self.state.last_window_pixels

    def _collect_capture_targets(self, node):
        """Recursively extract pane_id → (cols, rows) from tree."""
        if node.is_leaf:
            self.state.capture_targets[node.pane_id] = (
                node.width, node.height)
        else:
            for child in node.children:
                self._collect_capture_targets(child)

    def _on_all_panes_stable(self):
        """Handle 'all-panes-stable' signal — clean up and capture."""
        dbg('initial capture: all %d panes settled'
            % len(self.state.expected_panes))
        self.state.clear_capture_state()
        self._do_initial_capture()

    def _do_initial_capture(self):
        """VTEs converged — send refresh-client and capture all panes."""
        size = self.state.last_client_size
        if size:
            dbg('do_initial_capture: refresh-client -C %d,%d'
                % (size[0], size[1]))
            self.controller.protocol.send_command(
                'refresh-client -C {},{}'.format(
                    size[0], size[1]))
        self._send_initial_captures()
        self._snapshot_vte_sizes()

    def _chars_to_max_pixels(self, cols, rows):
        """Convert character dimensions to max pixel size for geometry hints.

        Accounts for layout structure, chrome, and CSD."""
        terminals = list(self.controller.terminal_to_pane.keys())
        if not terminals:
            return None

        term = None
        char_w = char_h = sb_w = tb_h = vpad_x = vpad_y = 0
        for t in terminals:
            char_w, char_h, sb_w, tb_h, vpad_x, vpad_y = \
                self._get_terminal_metrics(t)
            if char_w > 0:
                term = t
                break
        if not term or char_w <= 0:
            return None

        handle_size = self._get_handle_size(term)

        # Use the active window's tree for structural info
        tree = None
        awid = self.controller.active_window_id
        if awid and awid in self.state.layout_trees:
            tree = self.state.layout_trees[awid]
        if tree is None:
            for t in self.state.layout_trees.values():
                if self._is_active_window(t):
                    tree = t
                    break
        if tree is None:
            for tree in self.state.layout_trees.values():
                break
        if tree is None:
            return None

        target_w = self._subtree_px(tree, 'h', char_w, char_h, sb_w, tb_h,
                                     handle_size, vpad_x, vpad_y)
        target_h = self._subtree_px(tree, 'v', char_w, char_h, sb_w, tb_h,
                                     handle_size, vpad_x, vpad_y)

        # Scale from tree's char dimensions to the requested dimensions
        if tree.width > 0 and tree.height > 0:
            target_w = target_w * cols / tree.width
            target_h = target_h * rows / tree.height

        window = term.get_toplevel()

        # Chrome = tab bar, borders — NOT other panes.
        chrome_w, chrome_h = self._get_chrome_size(window)

        max_w = int(target_w) + chrome_w
        max_h = int(target_h) + chrome_h

        return (max_w, max_h, chrome_w, chrome_h, 0, 0)

    def _set_max_size_pixels(self, max_w, max_h):
        """Apply max size geometry hints on the GTK window.

        max_w/max_h are content-based (get_size() coordinate space).
        Geometry hints constrain the outer allocation (including CSD),
        so we add CSD to reach the intended content max.
        Returns (hint_w, hint_h) — the actual values set on the hint
        (in allocation space, i.e. content + CSD).
        """
        terminals = list(self.controller.terminal_to_pane.keys())
        if not terminals:
            return (max_w, max_h)
        window = terminals[0].get_toplevel()
        # CSD = difference between outer allocation and content size
        alloc = window.get_allocation()
        ws = window.get_size()
        csd_w = max(0, alloc.width - ws[0])
        csd_h = max(0, alloc.height - ws[1])
        hint_w = max_w + csd_w
        hint_h = max_h + csd_h
        dbg('size_trace set_max_pixels: '
            'content_max=%dx%d csd=%dx%d '
            'hint=%dx%d alloc=%dx%d ws=%dx%d' % (
            max_w, max_h, csd_w, csd_h,
            hint_w, hint_h,
            alloc.width, alloc.height, ws[0], ws[1]))
        # Store in allocation space so window.py re-applies correctly
        # as geometry hints (which constrain allocation, not content)
        window._tmux_max_size = (hint_w, hint_h)
        # If CSD not yet known (window just created), skip —
        # setting hints without CSD makes the max too tight.
        # The tripwire will set correct hints once CSD is available.
        if csd_w == 0 and csd_h == 0:
            return (max_w, max_h)
        from gi.repository import Gdk
        geometry = Gdk.Geometry()
        geometry.max_width = hint_w
        geometry.max_height = hint_h
        window.set_geometry_hints(None, geometry, Gdk.WindowHints.MAX_SIZE)
        return (hint_w, hint_h)

    def _update_max_from_tree(self, cols, rows):
        """Update per-axis max size constraints from layout tree dimensions.

        Each axis is tracked independently: a column limit doesn't
        prevent the user from adding rows, and vice versa.
        """
        if self.state.last_client_size is None:
            dbg('size_trace update_max: skipped (initial startup)')
            return False

        sent = self.state.last_client_size
        max_c = self.state.tmux_max_cols
        max_r = self.state.tmux_max_rows

        # Per-axis: did tmux exceed a known limit (grew) or reject?
        grew_c = max_c is not None and cols > max_c
        grew_r = max_r is not None and rows > max_r
        rej_c = sent and cols < sent[0]
        rej_r = sent and rows < sent[1]

        if grew_c or grew_r:
            # Exceeded a known limit — clear that axis's constraint
            if grew_c:
                self.state.tmux_max_cols = None
            if grew_r:
                self.state.tmux_max_rows = None
            dbg('size_trace update_max: grew cols=%s->%d rows=%s->%d' % (
                max_c or 'free', cols, max_r or 'free', rows))

        if rej_c or rej_r:
            # At least one axis was rejected — constrain only that axis.
            if rej_c:
                self.state.tmux_max_cols = cols
            if rej_r:
                self.state.tmux_max_rows = rows
            dbg('size_trace update_max: rejected '
                'sent=%dx%d got=%dx%d max_cols=%s max_rows=%s' % (
                sent[0], sent[1], cols, rows,
                self.state.tmux_max_cols or 'free',
                self.state.tmux_max_rows or 'free'))
            # Use constraint values for pixel computation, not tree values.
            # The tree may be smaller than the limit (e.g. 118 cols when
            # max is 132) — we need MAX at the limit, not current size.
            hint_cols = self.state.tmux_max_cols \
                if self.state.tmux_max_cols is not None else cols
            hint_rows = self.state.tmux_max_rows \
                if self.state.tmux_max_rows is not None else rows
            info = self._chars_to_max_pixels(hint_cols, hint_rows)
            if info:
                # Use accumulated state, not just this cycle's rejection,
                # so existing constraints on the other axis are preserved.
                max_w = info[0] if self.state.tmux_max_cols is not None else 32767
                max_h = info[1] if self.state.tmux_max_rows is not None else 32767
                self._set_max_size_pixels(max_w, max_h)
            self.controller._arm_tripwire_after_idle()
        elif grew_c or grew_r:
            # Grew past a limit — arm tripwire instantly
            self.controller._do_arm_tripwire()
        else:
            # Echo-back confirmation, no change
            if not self.state.tripwire_armed \
                    and not self.state.tripwire_timer:
                self.controller._do_arm_tripwire()
        return False

    def _clear_tmux_max_size(self):
        """Remove the max size constraint."""
        terminals = list(self.controller.terminal_to_pane.keys())
        if not terminals:
            return False

        window = terminals[0].get_toplevel()
        if getattr(window, '_tmux_max_size', None):
            dbg('clearing tmux max size constraint')
            window._tmux_max_size = None
            window.set_geometry_hints(None, None, 0)

        return False

    def _resize_window_to_tree(self, tree):
        """Resize our GTK window to match tmux's layout tree dimensions.

        Called on GTK thread when tmux changes the layout size (e.g.
        another client attached with a different window size).
        """
        import time
        terminals = list(self.controller.terminal_to_pane.keys())
        if not terminals:
            return False

        term = None
        char_w = char_h = sb_w = tb_h = vpad_x = vpad_y = 0
        for t in terminals:
            char_w, char_h, sb_w, tb_h, vpad_x, vpad_y = \
                self._get_terminal_metrics(t)
            if char_w > 0:
                term = t
                break
        if not term or char_w <= 0:
            return False

        handle_size = self._get_handle_size(term)

        target_w = self._subtree_px(tree, 'h', char_w, char_h, sb_w, tb_h,
                                     handle_size, vpad_x, vpad_y)
        target_h = self._subtree_px(tree, 'v', char_w, char_h, sb_w, tb_h,
                                     handle_size, vpad_x, vpad_y)

        window = term.get_toplevel()
        # Chrome = tab bar, borders — NOT other panes.
        # window.resize() operates in content space — no CSD.
        chrome_w, chrome_h = self._get_chrome_size(window)

        win_w = int(target_w) + chrome_w
        win_h = int(target_h) + chrome_h

        wa = window.get_allocation()
        ws = window.get_size()
        dbg('size_trace resize_to_tree: '
            'alloc=%dx%d ws=%dx%d '
            'chrome=%dx%d resize=%dx%d tree=%dx%d' % (
            wa.width, wa.height, ws[0], ws[1],
            chrome_w, chrome_h, win_w, win_h,
            tree.width, tree.height))

        window.resize(win_w, win_h)
        # Update pixel tracking so notify_resize detects this as a
        # window resize (not a split drag) when VTE sizes change
        self.state.last_window_pixels = (win_w, win_h)
        self.state.layout_applied_time = time.monotonic()
        # If window isn't already at target size, the WM hasn't
        # processed the resize yet.  Gate _finish_applying_layout
        # on configure-event so we don't clear _applying_layout
        # while paneds are still at old size.
        if ws != (win_w, win_h):
            self.state.begin_window_resize()
            self.controller._ensure_configure_handler(window)
        return False

    def _send_initial_resize(self):
        """Size our window to match tmux's layout, then tell tmux our size.

        Uses actual VTE char metrics + scrollbar/titlebar/handle sizes to
        compute the correct pixel dimensions. If the layout won't fit on
        screen, clamps to screen size and tells tmux to use the smaller
        dimensions.
        """
        # Use the active window's tree — other windows may have
        # been pre-shrunk by tmux.  Prefer the window ID from
        # tmux's active flag (available before terminals are
        # mapped), then fall back to _is_active_window (checks
        # which tab is visible).
        tree = None
        awid = self.controller.active_window_id
        if awid and awid in self.state.layout_trees:
            tree = self.state.layout_trees[awid]
        if tree is None:
            for t in self.state.layout_trees.values():
                if self._is_active_window(t):
                    tree = t
                    break
        if tree is None:
            for tree in self.state.layout_trees.values():
                break
        if tree is None:
            return

        # Get metrics from an allocated terminal
        terminals = list(self.controller.terminal_to_pane.keys())
        char_w = char_h = sb_w = tb_h = vpad_x = vpad_y = 0
        term = None
        for t in terminals:
            char_w, char_h, sb_w, tb_h, vpad_x, vpad_y = \
                self._get_terminal_metrics(t)
            if char_w > 0:
                term = t
                break
        if not term or char_w <= 0:
            # Terminals not realized yet — fall back to tmux dimensions
            dbg('initial resize to %dx%d (from tmux layout, '
                     'no metrics yet)' % (tree.width, tree.height))
            self.protocol.send_command(
                'refresh-client -C {},{}'.format(tree.width, tree.height))
            return

        handle_size = self._get_handle_size(term)

        # Measure VTE CSS padding
        ctx = term.vte.get_style_context()
        vte_css_pad = ctx.get_padding(ctx.get_state())
        dbg('initial_resize step1: metrics '
            'char=%dx%d sb=%d tb=%d handle=%d vpad=%dx%d '
            'vte_css_pad=l%d,r%d,t%d,b%d' % (
            char_w, char_h, sb_w, tb_h,
            handle_size, vpad_x, vpad_y,
            vte_css_pad.left, vte_css_pad.right,
            vte_css_pad.top, vte_css_pad.bottom))

        # Compute pixel dimensions for tmux's layout (content area)
        target_w = self._subtree_px(tree, 'h', char_w, char_h,
                                     sb_w, tb_h, handle_size,
                                     vpad_x, vpad_y)
        target_h = self._subtree_px(tree, 'v', char_w, char_h,
                                     sb_w, tb_h, handle_size,
                                     vpad_x, vpad_y)

        dbg('initial_resize step2: subtree_px '
            'tmux=%dx%d target=%.1fx%.1f' % (
            tree.width, tree.height, target_w, target_h))

        # Measure every layer of the window
        window = term.get_toplevel()
        wa = window.get_allocation()
        ws = window.get_size()
        content = window.get_child()
        ca = content.get_allocation() if content else None
        ta = term.get_allocation()
        vte_alloc = term.vte.get_allocation()
        vc = term.vte.get_column_count()
        vr = term.vte.get_row_count()

        dbg('initial_resize step3: layers '
            'win_alloc=%dx%d win_size=%dx%d '
            'content=%s term=%dx%d '
            'vte=%dx%d vte_chars=%dx%d' % (
            wa.width, wa.height, ws[0], ws[1],
            '%dx%d' % (ca.width, ca.height)
                if ca else 'None',
            ta.width, ta.height,
            vte_alloc.width, vte_alloc.height,
            vc, vr))

        # Chrome using different reference points
        csd_w = wa.width - ws[0]
        csd_h = wa.height - ws[1]
        chrome_ws_vte = (ws[0] - vte_alloc.width,
                         ws[1] - vte_alloc.height)
        chrome_alloc_vte = (wa.width - vte_alloc.width,
                            wa.height - vte_alloc.height)
        chrome_content_term = (
            (ca.width - ta.width, ca.height - ta.height)
            if ca else (0, 0))

        dbg('initial_resize step4: chrome options '
            'csd=%dx%d '
            'ws-vte=%dx%d '
            'alloc-vte=%dx%d '
            'content-term=%dx%d' % (
            csd_w, csd_h,
            chrome_ws_vte[0], chrome_ws_vte[1],
            chrome_alloc_vte[0], chrome_alloc_vte[1],
            chrome_content_term[0], chrome_content_term[1]))

        # Chrome = tab bar, borders — NOT other panes.
        # window.resize() operates in content space (get_size()),
        # NOT allocation space — do NOT add CSD.
        chrome_w, chrome_h = self._get_chrome_size(window)

        # Get screen limits
        from gi.repository import Gdk
        screen = window.get_screen()
        monitor = screen.get_monitor_at_window(window.get_window()) \
            if window.get_window() else 0
        mon_geom = screen.get_monitor_workarea(monitor)
        max_w = mon_geom.width
        max_h = mon_geom.height

        target_win_w = int(target_w) + chrome_w
        target_win_h = int(target_h) + chrome_h

        fits = target_win_w <= max_w and target_win_h <= max_h
        win_w = min(target_win_w, max_w)
        win_h = min(target_win_h, max_h)

        dbg('initial_resize step5: final '
            'target_win=%dx%d resize=%dx%d '
            'screen=%dx%d fits=%s' % (
            target_win_w, target_win_h,
            win_w, win_h,
            max_w, max_h, fits))

        ws_before = window.get_size()
        window.resize(win_w, win_h)

        # Gate _finish_applying_layout on the WM's response
        if ws_before != (win_w, win_h):
            self.state.begin_window_resize()
            self.controller._ensure_configure_handler(window)

        # Set initial chrome baseline for change detection
        self.state.last_chrome = self._get_chrome_size(window)

        # Check what happened after resize
        wa2 = window.get_allocation()
        ws2 = window.get_size()
        va2 = term.vte.get_allocation()
        vc2 = term.vte.get_column_count()
        vr2 = term.vte.get_row_count()
        dbg('initial_resize step6: after resize '
            'win_alloc=%dx%d win_size=%dx%d '
            'vte=%dx%d vte_chars=%dx%d' % (
            wa2.width, wa2.height, ws2[0], ws2[1],
            va2.width, va2.height, vc2, vr2))

        if fits:
            # Tell tmux we match its layout
            dbg('initial resize to %dx%d (matches tmux)' % (
                tree.width, tree.height))
            self.protocol.send_command(
                'refresh-client -C {},{}'.format(tree.width, tree.height))
        else:
            # Screen too small — compute what we can fit and tell tmux
            # to downsize. Back-calculate character dimensions from pixels.
            fit_cols = (win_w - vpad_x - sb_w) // char_w
            fit_rows = (win_h - vpad_y - tb_h) // char_h
            dbg('initial resize to %dx%d (screen limited from %dx%d)' % (
                fit_cols, fit_rows, tree.width, tree.height))
            self.protocol.send_command(
                'refresh-client -C {},{}'.format(fit_cols, fit_rows))

    def _periodic_title_refresh(self):
        """Periodically refresh pane titles from tmux.

        Tmux intercepts title-setting escape sequences (OSC 0/2) and
        does not forward them via %output, so VTE never sees them.
        Polling is the only way to get updated pane titles.
        """
        if not self.controller.active:
            return False
        self._refresh_pane_titles()
        self._refresh_tab_labels()
        return True

    def _refresh_tab_labels(self):
        """Query tmux for current window names and active pane info."""
        self.protocol.send_command(
            'list-windows -F "#{window_id}\t#{window_index}\t#{window_name}\t#{pane_current_command}\t#{pane_current_path}\t#{pane_title}"',
            callback=self._on_window_names,
        )

    def _on_window_names(self, result):
        """Handle window name query response and update tab labels."""
        if result.is_error:
            return
        import os, socket
        home = os.environ.get('HOME', '')
        hostname = socket.gethostname()
        for line in result.output_lines:
            decoded = line.decode('utf-8', errors='replace').strip()
            parts = decoded.split('\t', 5)
            if len(parts) < 6:
                continue
            window_id, index, name, command, path, pane_title = parts
            self.controller.window_names[window_id] = name
            self.controller.window_indices[window_id] = index
            # Build tab label: command:path or custom title (no size)
            if home and path.startswith(home):
                path = '~' + path[len(home):]
            has_custom = (pane_title and pane_title != hostname
                          and pane_title != command)
            if has_custom:
                tab_label = pane_title
            else:
                tab_label = '%s:%s' % (command, path) if path else command
            GLib.idle_add(self._update_tab_label, window_id, tab_label)
        # Set the window title to hostname: session-name
        if self.controller.session_name:
            self.protocol.send_command(
                'display-message -p "#{user}@#{host_short}"',
                callback=self._on_tmux_hostname,
            )

    def _on_tmux_hostname(self, result):
        """Handle hostname query response."""
        userhost = 'tmux'
        if not result.is_error and result.output_lines:
            userhost = result.output_lines[0].decode('utf-8', errors='replace').strip()
        title = '%s: %s [tmux]' % (userhost, self.controller.session_name)
        GLib.idle_add(self._set_window_title, title)

    def _set_window_title(self, title):
        """Set the Terminator window title. Called on GTK thread."""
        from terminatorlib.terminator import Terminator
        try:
            term = Terminator()
            window = self._find_tmux_window(term)
            if window:
                window.title.force_title(title)
        except Exception:
            pass
        return False

    def _refresh_pane_titles(self):
        """Query tmux for pane titles and update terminal titlebars."""
        self.protocol.send_command(
            'list-panes -s -F "#{pane_id}\t#{pane_current_command}\t#{pane_current_path}\t#{pane_title}"',
            callback=self._on_pane_titles,
        )

    def _on_pane_titles(self, result):
        """Handle pane title query response."""
        if result.is_error:
            return
        import os, socket
        home = os.environ.get('HOME', '')
        hostname = socket.gethostname()
        for line in result.output_lines:
            decoded = line.decode('utf-8', errors='replace').strip()
            parts = decoded.split('\t', 3)
            if len(parts) < 4:
                continue
            pane_id, command, path, pane_title = parts
            terminal = self.controller.pane_to_terminal.get(pane_id)
            if not terminal:
                continue
            # Shorten home prefix to ~
            if home and path.startswith(home):
                path = '~' + path[len(home):]
            # Detect app-set custom title (not tmux's default hostname)
            has_custom = (pane_title and pane_title != hostname
                          and pane_title != command)
            if has_custom:
                title = pane_title
            else:
                title = '%s:%s' % (command, path) if path else command
            GLib.idle_add(self._set_terminal_title, terminal, title)

    def _set_terminal_title(self, terminal, title):
        """Set a terminal's titlebar text. Must be called on GTK thread.

        Only updates the pane titlebar directly — does NOT emit
        title-change, which would override the tab label with the
        pane title instead of the tmux window name.
        """
        try:
            old_title = getattr(terminal, '_tmux_title', None)
            if title == old_title:
                return False
            terminal._tmux_title = title
            if hasattr(terminal, 'titlebar'):
                terminal.titlebar.set_terminal_title(None, title)
        except Exception:
            pass
        return False
