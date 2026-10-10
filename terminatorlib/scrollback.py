# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""scrollback.py - terminal scrollback text cache (module B).

Main thread exports from VTE; a worker thread converts (HTML -> SGR),
truncates and writes cache files under
~/.cache/terminator/scrollback/<uuid>.txt.

SessionManager APIs are duck-typed via getattr so this module works
before session.py lands on the branch.
"""

from __future__ import print_function

import hashlib
import os
import queue
import re
import shutil
import threading
import time

from gi.repository import GLib, Vte

from .borg import Borg
from .config import Config
from . import scrollback_text as sbt
from .util import dbg, err, get_cache_dir

try:
    from .translation import _
except Exception:  # pragma: no cover
    def _(text):
        return text

# Cached VTE capability probes (filled on first use)
_VTE_CAPS = None


def _vte_caps():
    global _VTE_CAPS
    if _VTE_CAPS is not None:
        return _VTE_CAPS
    major = Vte.get_major_version() if hasattr(Vte, 'get_major_version') else 0
    minor = Vte.get_minor_version() if hasattr(Vte, 'get_minor_version') else 0
    micro = Vte.get_micro_version() if hasattr(Vte, 'get_micro_version') else 0
    _VTE_CAPS = {
        'version': (major, minor, micro),
        'range_format': hasattr(Vte.Terminal, 'get_text_range_format'),
        'range': hasattr(Vte.Terminal, 'get_text_range'),
        'write_sync': hasattr(Vte.Terminal, 'write_contents_sync'),
    }
    dbg('VTE caps: %s' % _VTE_CAPS)
    return _VTE_CAPS


def _session_manager():
    """Return SessionManager instance or None if module A is absent."""
    try:
        from .session import SessionManager
        return SessionManager()
    except Exception:
        return None


def _sm_is_owner():
    sm = _session_manager()
    if sm is None:
        return False
    fn = getattr(sm, 'is_owner', None)
    if callable(fn):
        try:
            return bool(fn())
        except Exception as ex:
            dbg('is_owner failed: %s' % ex)
            return False
    return False


def _sm_writes_suspended():
    """True when SessionManager.suspend_writes has been called this run."""
    sm = _session_manager()
    if sm is None:
        return False
    fn = getattr(sm, 'writes_suspended', None)
    if callable(fn):
        try:
            return bool(fn())
        except Exception as ex:
            dbg('writes_suspended failed: %s' % ex)
            return False
    # Fallback for older SessionManager without the helper
    return bool(getattr(sm, '_disabled', False))


def _sm_restored_this_run():
    sm = _session_manager()
    if sm is None:
        return False
    return bool(getattr(sm, 'restored_this_run', False))


def _sm_will_persist(terminal):
    sm = _session_manager()
    if sm is None:
        return False
    fn = getattr(sm, 'will_persist', None)
    if callable(fn):
        try:
            return bool(fn(terminal))
        except Exception as ex:
            dbg('will_persist failed: %s' % ex)
            return False
    return False


def _sm_session_uuids():
    sm = _session_manager()
    if sm is None:
        return None
    fn = getattr(sm, 'session_uuids', None)
    if callable(fn):
        try:
            return fn()
        except Exception as ex:
            dbg('session_uuids failed: %s' % ex)
            return None
    return None


def _terminal_uuid_str(terminal):
    uuid_obj = getattr(terminal, 'uuid', None)
    if uuid_obj is None:
        return None
    try:
        return str(uuid_obj)
    except Exception:
        return None


def export_vte_text(vte, start_row, start_col, end_row, end_col,
                    color=False, raw=False):
    """Export a text range from VTE using the best available API.

    color=True exports Format.HTML and converts it to text + SGR (m14);
    falls back to plain text when HTML export is unavailable or fails.
    raw=True returns (source, is_html) without converting, so the costly
    HTML -> SGR conversion can run on the writer thread.
    """
    caps = _vte_caps()
    if color and caps['range_format']:
        try:
            result = vte.get_text_range_format(
                Vte.Format.HTML, start_row, start_col, end_row, end_col)
            html = result[0] if isinstance(result, (tuple, list)) else result
            if html:
                return (html, True) if raw else sbt.html_to_sgr(html)
        except Exception as ex:
            dbg('export_vte_text html failed: %s' % ex)
    text = ''
    try:
        if caps['range_format']:
            result = vte.get_text_range_format(
                Vte.Format.TEXT, start_row, start_col, end_row, end_col)
            text = result[0] if isinstance(result, (tuple, list)) else result
        elif caps['range']:
            result = vte.get_text_range(
                start_row, start_col, end_row, end_col, None)
            text = result[0] if isinstance(result, (tuple, list)) else result
    except Exception as ex:
        dbg('export_vte_text range failed: %s' % ex)
        text = ''
    text = text or ''
    return (text, False) if raw else text


def in_alt_screen(terminal):
    """True while a fullscreen TUI owns the alternate screen.

    VTE exposes only the alternate screen's rows then (no history), so a
    flush would overwrite the cached shell history with a snapshot of
    vim/htop.  Reuses the M8 detector; unknown => False.
    """
    alt = getattr(terminal, 'altscreen', None)
    det = getattr(alt, 'detector', None)
    try:
        if det is None:
            return False
        # active needs evidence of history (scrollbar heuristic); for the
        # cache, any collapsed+busy episode is enough: a TUI started in a
        # fresh terminal must not be cached as "history" either.  Deferring
        # only keeps the previous cache until the screen expands again.
        return bool(det.active is True or det.episode_start is not None)
    except Exception:
        return False


def read_last_n_lines_raw(vte, n_lines, color=False):
    """Main-thread part of a flush: return (source, is_html) for the last
    n_lines rows. Only the VTE export runs here; conversion and truncation
    happen in render_cache_text (writer thread for async flushes)."""
    n_lines = max(0, int(n_lines))
    if n_lines == 0:
        return '', False
    try:
        col, end_row = vte.get_cursor_position()
    except Exception as ex:
        dbg('get_cursor_position failed: %s' % ex)
        return '', False
    try:
        lower = int(vte.get_vadjustment().get_lower())
    except Exception:
        lower = 0
    start_row = max(lower, end_row - max(0, n_lines - 1))
    src, is_html = export_vte_text(vte, start_row, 0, end_row, col,
                                   color=color, raw=True)
    if not src:
        # Fallback: write_contents_sync only when range APIs missing and
        # scrollback is finite (caller must gate infinite).
        caps = _vte_caps()
        if not caps['range_format'] and not caps['range'] and caps['write_sync']:
            src = _export_via_write_contents(vte)
        is_html = False
    return src or '', is_html


def render_cache_text(src, is_html, n_lines, max_kb):
    """Convert (if HTML) and truncate to the line/byte budget. Thread-safe
    (pure function); returns the str written to the cache file."""
    text = sbt.html_to_sgr(src) if is_html else (src or '')
    if is_html:
        return sbt.truncate_sgr_lines(text, n_lines, max_kb)
    return sbt.truncate_lines_and_bytes(text, n_lines, max_kb)


def read_last_n_lines(vte, n_lines, color=False):
    """Read the last n_lines of VTE scrollback as text (+SGR if color)."""
    n_lines = max(0, int(n_lines))
    if n_lines == 0:
        return ''
    src, is_html = read_last_n_lines_raw(vte, n_lines, color=color)
    text = sbt.html_to_sgr(src) if is_html else src
    if not text:
        return ''
    lines = text.split('\n')
    if len(lines) > n_lines:
        lines = lines[-n_lines:]
    return '\n'.join(lines)


def _export_via_write_contents(vte):
    """Best-effort full export truncated later by caller. Main thread only."""
    try:
        from gi.repository import Gio
        stream = Gio.MemoryOutputStream.new_resizable()
        flags = Vte.WriteFlags.DEFAULT if hasattr(Vte, 'WriteFlags') else 0
        vte.write_contents_sync(stream, flags, None)
        data = stream.steal_as_bytes()
        if data is None:
            return ''
        raw = data.get_data()
        if not raw:
            return ''
        return raw.decode('utf-8', 'replace')
    except Exception as ex:
        dbg('write_contents_sync failed: %s' % ex)
        return ''


class ScrollbackCache(Borg):
    """Debounced scrollback text cache. Borg singleton."""

    _enabled = None
    _started = None
    _dir = None
    _dirty = None
    _last_hash = None
    _timer_id = None
    _worker = None
    _queue = None
    _fail_count = None
    _disabled_by_error = None
    _config = None
    _seq = None
    _io_lock = None
    _snap_at = None
    _snap_pending = None
    _snap_tokens = None
    _SNAP_BURST = 3.0
    _visit = None
    _tick = None
    _bytes_since_gc = None
    _last_gc = None
    GC_MIN_INTERVAL_S = 60.0

    def __init__(self):
        Borg.__init__(self, self.__class__.__name__)
        self.prepare_attributes()

    def prepare_attributes(self):
        if self._enabled is None:
            self._enabled = False
        if self._started is None:
            self._started = False
        if self._dir is None:
            self._dir = ''
        if self._dirty is None:
            self._dirty = set()
        if self._last_hash is None:
            self._last_hash = {}
        if self._timer_id is None:
            self._timer_id = 0
        if self._worker is None:
            self._worker = None
        if self._queue is None:
            self._queue = None
        if self._fail_count is None:
            self._fail_count = 0
        if self._disabled_by_error is None:
            self._disabled_by_error = False
        if self._config is None:
            self._config = Config()
        if self._seq is None:
            # uuid -> generation of the newest write/delete intent; the worker
            # drops queued writes that a later sync write/delete superseded.
            self._seq = {}
        if self._io_lock is None:
            # Serialises seq-check+write in the worker against sync writes
            # and deletes on the main thread (closes check-then-write race).
            # m18: re-entrant so _bump can always take it, even when the
            # caller already holds it (Lock.locked() can't tell the owner).
            self._io_lock = threading.RLock()

    # ---- config helpers ----
    def _cfg(self, key, default=None):
        try:
            return self._config[key]
        except Exception:
            return default

    def _lines(self):
        return int(self._cfg('scrollback_cache_lines', 2000) or 2000)

    def _max_kb(self):
        return int(self._cfg('scrollback_cache_max_kb', 512) or 512)

    def _color(self):
        return bool(self._cfg('scrollback_cache_color', True))

    def _interval_s(self):
        return max(5, int(self._cfg('scrollback_cache_interval_s', 20) or 20))

    def _total_mb(self):
        return self._int_or_off('scrollback_cache_total_mb', 20)

    def _ttl_days(self):
        return self._int_or_off('scrollback_cache_ttl_days', 7)

    def _int_or_off(self, key, default):
        """m17: 0 (or negative) means disabled; only None/garbage -> default."""
        v = self._cfg(key, default)
        if v is None or v == '':
            return default
        try:
            return max(0, int(v))
        except (TypeError, ValueError):
            return default

    # ---- paths ----
    def path_for(self, uuid_str):
        """Absolute path for uuid, or None if invalid."""
        if not sbt.is_valid_uuid_filename(uuid_str):
            return None
        if not self._dir:
            self._dir = os.path.join(get_cache_dir(), 'scrollback')
        return os.path.join(self._dir, '%s.txt' % uuid_str)

    def _ensure_dir(self):
        path = os.path.join(get_cache_dir(), 'scrollback')
        self._dir = path
        try:
            os.makedirs(path, mode=0o700, exist_ok=True)
        except OSError as ex:
            err('scrollback mkdir failed: %s' % ex)
            return False
        try:
            st = os.stat(path)
            if st.st_uid != os.geteuid():
                err('scrollback dir owned by uid %s, not euid %s — disabled'
                    % (st.st_uid, os.geteuid()))
                return False
        except OSError as ex:
            err('scrollback dir stat failed: %s' % ex)
            return False
        return True

    # ---- lifecycle ----
    def start(self):
        """Enable cache when config on, owner instance, and dir ownership ok.

        Also refuses to start when SessionManager writes are suspended
        (prefs Clear / Use previous), so reconfigure() cannot revive
        writing after suspend_writes() stopped the cache.
        """
        self.prepare_attributes()
        want = bool(self._cfg('scrollback_cache', True))
        if not want:
            self._enabled = False
            dbg('scrollback_cache disabled by config')
            return
        if not _sm_is_owner():
            self._enabled = False
            dbg('scrollback_cache disabled: not session owner')
            return
        if _sm_writes_suspended():
            self._enabled = False
            dbg('scrollback_cache disabled: session writes suspended')
            return
        if not self._ensure_dir():
            self._enabled = False
            return
        self._enabled = True
        self._disabled_by_error = False
        self._fail_count = 0
        if not self._started:
            self._queue = queue.Queue()
            self._worker = threading.Thread(
                target=self._worker_loop, name='scrollback-writer', daemon=True)
            self._worker.start()
            self._started = True
        self._arm_timer()
        try:
            self.cleanup_startup()
        except Exception as ex:
            dbg('cleanup_startup failed: %s' % ex)
        dbg('ScrollbackCache started at %s' % self._dir)

    def stop(self, join_timeout=1.0):
        """Stop timer and worker. Does not flush — finalize does that first."""
        self._enabled = False
        if self._timer_id:
            try:
                GLib.source_remove(self._timer_id)
            except Exception:
                pass
            self._timer_id = 0
        if self._queue is not None:
            try:
                self._queue.put(('stop',))
            except Exception:
                pass
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join(join_timeout)
        self._worker = None
        self._started = False
        self._queue = None

    def reconfigure(self):
        """React to preference changes: enable/disable cache."""
        want = bool(self._cfg('scrollback_cache', True))
        if want and not self._enabled:
            self.start()
        elif not want and (self._enabled or self._started or self._dir):
            self.stop(join_timeout=1.0)
            self.clear_all()

    def _arm_timer(self):
        if self._timer_id:
            try:
                GLib.source_remove(self._timer_id)
            except Exception:
                pass
            self._timer_id = 0
        if not self._enabled or self._disabled_by_error:
            return
        interval_ms = self._interval_s() * 1000
        self._timer_id = GLib.timeout_add(interval_ms, self._on_interval)

    # ---- dirty / flush ----
    def mark_dirty(self, terminal):
        if not self._enabled or self._disabled_by_error:
            return
        uuid_str = _terminal_uuid_str(terminal)
        if not uuid_str:
            return
        self._dirty.add(uuid_str)

    def snapshot_before_command(self, terminal, now=None):
        """Async-flush a dirty terminal on Enter (rate-limited 1/s/uuid).

        Captures the normal-screen history right before a command that may
        switch to the alternate screen; no-op in alt screen or when clean.
        """
        if not self._enabled or self._disabled_by_error:
            return False
        uuid_str = _terminal_uuid_str(terminal)
        if not uuid_str or uuid_str not in self._dirty:
            return False
        if in_alt_screen(terminal):
            return False
        if self._snap_at is None:
            self._snap_at = {}
        now = time.monotonic() if now is None else now
        # Token bucket (burst 3, refill 1/s): two quick Enters such as
        # `echo x` then `vim` must both snapshot synchronously, because by
        # the time a deferred retry fires the TUI is already on the alt
        # screen and the normal-screen output is unreadable (m15 review).
        if self._snap_tokens is None:
            self._snap_tokens = {}
        last = self._snap_at.get(uuid_str)
        tokens = self._SNAP_BURST if last is None else min(
            self._SNAP_BURST,
            self._snap_tokens.get(uuid_str, 0.0) + max(0.0, now - last))
        wait = 1.0 - tokens
        if wait > 0:
            # Rate-limited: don't drop it (the 2nd of two quick Enters may
            # launch the TUI) -- defer to the end of the window (m15).
            self._defer_snapshot(terminal, uuid_str, wait)
            return False
        self._snap_at[uuid_str] = now
        self._snap_tokens[uuid_str] = tokens - 1.0
        self._flush_uuid(terminal, uuid_str, sync=False)
        return True

    def _defer_snapshot(self, terminal, uuid_str, wait):
        if self._snap_pending is None:
            self._snap_pending = {}
        if uuid_str in self._snap_pending:
            return  # one pending retry per terminal is enough
        ms = max(1, int(wait * 1000) + 10)

        def _fire():
            if self._snap_pending is not None:
                self._snap_pending.pop(uuid_str, None)
            try:
                # Re-checks enabled/dirty/alt-screen/rate limit; only saves
                # if the terminal is still on the normal screen.
                self.snapshot_before_command(terminal)
            except Exception as ex:
                dbg('deferred snapshot failed: %s' % ex)
            return False
        self._snap_pending[uuid_str] = GLib.timeout_add(ms, _fire)

    def _cancel_pending(self, uuid_str=None):
        if not self._snap_pending:
            return
        keys = [uuid_str] if uuid_str else list(self._snap_pending)
        for k in keys:
            sid = self._snap_pending.pop(k, None)
            if sid:
                try:
                    GLib.source_remove(sid)
                except Exception:
                    pass

    def flush(self, terminal, sync=False, **kwargs):
        """Read VTE and write (sync=True on main thread, else queue)."""
        if kwargs.get('synchronous'):
            sync = True
        if not self._enabled or self._disabled_by_error:
            return
        uuid_str = _terminal_uuid_str(terminal)
        if not uuid_str:
            return
        self._flush_uuid(terminal, uuid_str, sync=sync)

    def flush_all(self, sync=False, **kwargs):
        """Flush terminals that will_persist. sync/synchronous/final → sync write."""
        if kwargs.get('synchronous') or kwargs.get('final'):
            sync = True
        if not self._enabled and not sync:
            return
        # During finalize we may still flush even if disabled_by_error was set,
        # but only when sync and still owner-enabled originally.
        try:
            from .terminator import Terminator
            terminals = list(Terminator().terminals)
        except Exception as ex:
            dbg('flush_all: no Terminator: %s' % ex)
            return
        for term in terminals:
            uuid_str = _terminal_uuid_str(term)
            if not uuid_str:
                continue
            if not _sm_will_persist(term):
                continue
            try:
                self._flush_uuid(term, uuid_str, sync=sync)
            except Exception as ex:
                dbg('flush_all term failed: %s' % ex)

    def _flush_uuid(self, terminal, uuid_str, sync=False):
        vte = getattr(terminal, 'vte', None)
        if vte is None:
            return
        # Guard infinite scrollback without range APIs
        caps = _vte_caps()
        try:
            infinite = bool(self._config['scrollback_infinite'])
        except Exception:
            infinite = False
        if infinite and not caps['range_format'] and not caps['range']:
            dbg('skip flush %s: infinite scrollback without range API' % uuid_str)
            self._dirty.discard(uuid_str)
            return
        if in_alt_screen(terminal):
            # Keep the previous cache and stay dirty: we flush the real
            # history once the TUI leaves the alternate screen.
            dbg('defer flush %s: alternate screen active' % uuid_str)
            self._dirty.add(uuid_str)
            return
        color = self._color()
        lines, max_kb = self._lines(), self._max_kb()
        src, is_html = read_last_n_lines_raw(vte, lines, color=color)
        # Hash the *source* (cheap) so unchanged terminals are skipped on the
        # main thread without paying for HTML -> SGR conversion.
        h = hashlib.sha256(('%d:%d:%d:' % (is_html, lines, max_kb)).encode())
        h.update((src or '').encode('utf-8', 'replace'))
        digest = h.hexdigest()
        if self._last_hash.get(uuid_str) == digest:
            self._dirty.discard(uuid_str)
            return
        path = self.path_for(uuid_str)
        if not path:
            return
        if sync:
            try:
                data = render_cache_text(src, is_html, lines, max_kb).encode(
                    'utf-8')
                if not self._dir:
                    self._ensure_dir()
                with self._io_lock:
                    self._bump(uuid_str)
                    sbt.atomic_write_txt(path, data, mode=0o600)
                self._last_hash[uuid_str] = digest
                self._fail_count = 0
            except OSError as ex:
                self._on_write_failed(ex)
            self._dirty.discard(uuid_str)
        else:
            if self._queue is None:
                return
            # The worker converts/truncates and drops writes superseded by a
            # newer intent (seq) for the same uuid.
            with self._io_lock:
                seq = self._bump(uuid_str)
            self._queue.put(('write', uuid_str, (src, is_html, lines, max_kb),
                             digest, seq))
            self._dirty.discard(uuid_str)

    def on_terminal_close(self, terminal):
        if not self._enabled:
            return
        uuid_str = _terminal_uuid_str(terminal)
        if not uuid_str:
            return
        # A deferred pre-command retry must not fire on a closed terminal
        # (m15 review2): cancel it before the final flush.
        self._cancel_pending(uuid_str)
        try:
            if _sm_will_persist(terminal):
                self.flush(terminal, sync=True)
            else:
                self.delete_uuid(uuid_str)
        except Exception as ex:
            dbg('on_terminal_close failed: %s' % ex)

    def _on_interval(self):
        if not self._enabled or self._disabled_by_error:
            self._timer_id = 0
            return False
        if not self._dirty:
            return True
        try:
            from .terminator import Terminator
            by_uuid = {}
            for term in Terminator().terminals:
                u = _terminal_uuid_str(term)
                if u:
                    by_uuid[u] = term
        except Exception as ex:
            dbg('interval: Terminator unavailable: %s' % ex)
            return True
        dirty_list = list(self._dirty)
        if not dirty_list:
            return True
        # Flush the 1-2 dirty terminals that waited longest (least recently
        # visited).  A set's iteration order plus a rotating index could
        # repeatedly pick a continuously-dirty terminal and skip others when
        # the set changed size; LRU order guarantees each dirty terminal is
        # visited within ceil(len(dirty)/2) ticks.
        if self._visit is None:
            self._visit = {}
        self._tick = (self._tick or 0) + 1
        dirty_list.sort(key=lambda u: self._visit.get(u, 0))
        n = min(2, len(dirty_list))
        for uuid_str in dirty_list[:n]:
            self._visit[uuid_str] = self._tick
            term = by_uuid.get(uuid_str)
            if term is None:
                self._dirty.discard(uuid_str)
                self._visit.pop(uuid_str, None)
                continue
            try:
                self._flush_uuid(term, uuid_str, sync=False)
            except Exception as ex:
                dbg('interval flush failed: %s' % ex)
        self._maybe_queue_gc(set(by_uuid))
        return True

    def _maybe_queue_gc(self, live, now=None):
        """m16: queue a runtime total-size prune on the worker (throttled).

        Runs when enough bytes were written since the last prune to possibly
        exceed the cap, at most every GC_MIN_INTERVAL_S.  `live` uuids (open
        terminals) are pruned only after every non-live file is gone.
        """
        if self._queue is None or not self._started:
            return False
        now = time.monotonic() if now is None else now
        if self._last_gc is not None and now - self._last_gc < self.GC_MIN_INTERVAL_S:
            return False
        # m18: read+reset atomically; the worker increments concurrently.
        with self._io_lock:
            pending = self._bytes_since_gc
            if not pending:
                return False
            self._bytes_since_gc = 0
        self._last_gc = now
        try:
            self._queue.put(('gc', frozenset(live or ())))
        except Exception:
            return False
        return True

    def enforce_total_cap(self, protect=()):
        """Prune cache files until total <= scrollback_cache_total_mb.

        Only non-live (orphan/closed) files are removed, oldest-first; live
        files are never removed at runtime (see loop).  Runs on the worker, so writes queued earlier have already
        landed (FIFO); seq is deliberately NOT bumped (that would drop a newer
        write queued after this gc item).  Returns the list of removed uuids.
        """
        total_cap = max(0, self._total_mb()) * 1024 * 1024
        removed = []
        if total_cap <= 0 or not self._dir or not os.path.isdir(self._dir):
            return removed
        protect = set(protect or ())
        files = []
        try:
            names = os.listdir(self._dir)
        except OSError:
            return removed
        for name in names:
            if not name.endswith('.txt'):
                continue
            u = name[:-4]
            if not sbt.is_valid_uuid_filename(u):
                continue
            try:
                st = os.stat(os.path.join(self._dir, name))
            except OSError:
                continue
            files.append((u in protect, st.st_mtime, u, st.st_size))
        total = sum(f[3] for f in files)
        if total <= total_cap:
            return removed
        files.sort()  # non-live first, then oldest
        for is_live, _mtime, u, size in files:
            if total <= total_cap:
                break
            if is_live:
                # m16 review: never delete an open terminal's cache at runtime.
                # It would just be rewritten next tick (delete/rewrite churn
                # every GC interval) and a crash in between loses it.  Live
                # files are bounded per-file by scrollback_cache_max_kb; the
                # startup cleanup enforces the cap on them.
                break
            with self._io_lock:
                try:
                    os.unlink(os.path.join(self._dir, u + '.txt'))
                except FileNotFoundError:
                    pass
                except OSError as ex:
                    dbg('gc unlink failed: %s' % ex)
                    continue
            total -= size
            removed.append(u)
            GLib.idle_add(self._on_gc_removed, u)
        dbg('scrollback gc removed %d file(s)' % len(removed))
        return removed

    def _on_gc_removed(self, uuid_str):
        self._last_hash.pop(uuid_str, None)
        return False

    # ---- worker ----
    def _worker_loop(self):
        q = self._queue
        while True:
            try:
                item = q.get()
            except Exception:
                break
            if not item or item[0] == 'stop':
                break
            try:
                if item[0] == 'write':
                    _, uuid_str, payload, digest, seq = item
                    path = self.path_for(uuid_str)
                    if not path or self._seq.get(uuid_str) != seq:
                        continue
                    if isinstance(payload, tuple):
                        # HTML -> SGR conversion + truncation off the main
                        # thread (~50ms for 2000 coloured lines).
                        data = render_cache_text(*payload).encode('utf-8')
                    else:
                        data = payload
                    with self._io_lock:
                        if self._seq.get(uuid_str) != seq:
                            continue  # superseded by newer sync write / delete
                        sbt.atomic_write_txt(path, data, mode=0o600)
                    # Update hash on main thread
                    GLib.idle_add(self._on_write_ok, uuid_str, digest, seq)
                    with self._io_lock:
                        self._bytes_since_gc = (self._bytes_since_gc or 0) + len(data)
                elif item[0] == 'gc':
                    _, protect = item
                    self.enforce_total_cap(protect)
                elif item[0] == 'delete':
                    _, uuid_str = item
                    path = self.path_for(uuid_str)
                    if path and os.path.isfile(path):
                        try:
                            os.unlink(path)
                        except FileNotFoundError:
                            pass
            except OSError as ex:
                GLib.idle_add(self._on_write_failed, ex)
            except Exception as ex:
                dbg('scrollback worker error: %s' % ex)

    def _on_write_ok(self, uuid_str, digest, seq=None):
        if seq is not None and self._seq.get(uuid_str) != seq:
            return False
        self._last_hash[uuid_str] = digest
        self._fail_count = 0
        return False

    def _bump(self, uuid_str):
        """Bump the write-intent seq under _io_lock (an RLock, so callers
        that already hold it -- seq bump + write must be atomic -- re-enter
        safely, and a different thread holding it makes us wait)."""
        with self._io_lock:
            return self._bump_locked(uuid_str)

    def _bump_locked(self, uuid_str):
        seq = self._seq.get(uuid_str, 0) + 1
        self._seq[uuid_str] = seq
        return seq

    def _on_write_failed(self, exc):
        self._fail_count = (self._fail_count or 0) + 1
        err('scrollback write failed (%s): %s' % (self._fail_count, exc))
        if self._fail_count >= 3:
            self._disabled_by_error = True
            if self._timer_id:
                try:
                    GLib.source_remove(self._timer_id)
                except Exception:
                    pass
                self._timer_id = 0
            err('scrollback cache disabled after repeated write failures')
        return False

    # ---- restore / notice ----
    def restore_into(self, terminal):
        """Feed cached text + separator into terminal.vte (display feed only)."""
        if not self._enabled:
            return False
        if not _sm_restored_this_run():
            return False
        uuid_str = _terminal_uuid_str(terminal)
        if not uuid_str:
            return False
        path = self.path_for(uuid_str)
        if not path or not os.path.isfile(path):
            return False
        try:
            max_bytes = self._max_kb() * 1024
            with open(path, 'rb') as fh:
                size = os.fstat(fh.fileno()).st_size
                if size > max_bytes:
                    # Keep the newest output (tail), not the oldest, and
                    # start on a line boundary.
                    fh.seek(size - max_bytes)
                    rawb = fh.read()
                    nl = rawb.find(b'\n')
                    if 0 <= nl < len(rawb) - 1:
                        rawb = rawb[nl + 1:]
                else:
                    rawb = fh.read()
                raw = rawb.decode('utf-8', 'replace')
            mtime = os.path.getmtime(path)
        except OSError as ex:
            dbg('restore read failed: %s' % ex)
            return False
        # Keep SGR colours (m14) but strip every other control sequence;
        # reset afterwards so a truncated style never bleeds into the shell.
        body = sbt.normalize_newlines_for_feed(
            sbt.sanitize_for_feed(raw, keep_sgr=self._color()))
        if self._color():
            body += '\x1b[0m'
        sep = sbt.format_separator_feed(mtime, translate=_)
        vte = getattr(terminal, 'vte', None)
        if vte is None:
            return False
        try:
            # MUST use vte.feed (display buffer), never Terminal.feed / feed_child
            # VTE 0.80+ feed() requires bytes (str raises TypeError)
            payload = body + sep
            if isinstance(payload, str):
                payload = payload.encode('utf-8')
            vte.feed(payload)
        except Exception as ex:
            dbg('vte.feed restore failed: %s' % ex)
            return False
        return True

    def feed_notice(self, terminal, text):
        """Feed a grey notice line (spawn-before). Not gated by restored_this_run."""
        vte = getattr(terminal, 'vte', None)
        if vte is None:
            return
        cleaned = sbt.sanitize_for_feed(text or '')
        if not cleaned:
            return
        payload = '\r\n\x1b[90m' + cleaned + '\x1b[0m\r\n'
        try:
            if isinstance(payload, str):
                payload = payload.encode('utf-8')
            vte.feed(payload)
        except Exception as ex:
            dbg('feed_notice failed: %s' % ex)

    # ---- cleanup ----
    def delete_uuid(self, uuid_str):
        if not uuid_str:
            return
        self._dirty.discard(uuid_str)
        self._last_hash.pop(uuid_str, None)
        self._cancel_pending(uuid_str)
        for d in (self._visit, self._snap_at, self._snap_tokens):
            if d is not None:
                d.pop(uuid_str, None)
        with self._io_lock:
            self._bump(uuid_str)
        path = self.path_for(uuid_str)
        if not path:
            return
        if self._queue is not None and self._started and self._worker and self._worker.is_alive():
            try:
                self._queue.put(('delete', uuid_str))
                return
            except Exception:
                pass
        try:
            if os.path.isfile(path):
                os.unlink(path)
        except FileNotFoundError:
            pass
        except OSError as ex:
            dbg('delete_uuid failed: %s' % ex)

    def discard_uuids(self, uuids):
        """Delete caches for a set of uuid strings (D5 buffer expiry)."""
        if not uuids:
            return
        for u in set(uuids):
            if not sbt.is_valid_uuid_filename(str(u)):
                continue
            self.delete_uuid(str(u))

    def clear_all(self):
        """Remove the scrollback directory. Safe before start()."""
        self._dirty.clear()
        self._last_hash.clear()
        self._cancel_pending()
        for d in (self._visit, self._snap_at, self._snap_tokens):
            if d is not None:
                d.clear()
        # Drain queue if present
        if self._queue is not None:
            try:
                while True:
                    self._queue.get_nowait()
            except Exception:
                pass
        path = os.path.join(get_cache_dir(), 'scrollback')
        self._dir = path
        if os.path.isdir(path):
            try:
                shutil.rmtree(path)
            except OSError as ex:
                err('clear_all failed: %s' % ex)

    def cleanup_startup(self):
        """Owner-only: drop tmp files, TTL, total size, orphans."""
        if not self._dir:
            self._dir = os.path.join(get_cache_dir(), 'scrollback')
        if not os.path.isdir(self._dir):
            return
        now = time.time()
        ttl = max(0, self._ttl_days()) * 86400
        # Remove temp leftovers
        for name in os.listdir(self._dir):
            full = os.path.join(self._dir, name)
            if name.startswith('.') and name.endswith('.tmp'):
                try:
                    os.unlink(full)
                except OSError:
                    pass
        # Collect .txt cache files
        files = []
        for name in os.listdir(self._dir):
            if not name.endswith('.txt'):
                continue
            uuid_part = name[:-4]
            if not sbt.is_valid_uuid_filename(uuid_part):
                continue
            full = os.path.join(self._dir, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            files.append((full, uuid_part, st.st_mtime, st.st_size))
        # TTL
        if ttl > 0:
            kept = []
            for full, uuid_part, mtime, size in files:
                if now - mtime > ttl:
                    try:
                        os.unlink(full)
                    except OSError:
                        pass
                else:
                    kept.append((full, uuid_part, mtime, size))
            files = kept
        # Orphans (only when session_uuids is a set)
        live = _sm_session_uuids()
        if live is not None:
            live_set = set(str(u) for u in live)
            kept = []
            for full, uuid_part, mtime, size in files:
                if uuid_part not in live_set:
                    try:
                        os.unlink(full)
                    except OSError:
                        pass
                else:
                    kept.append((full, uuid_part, mtime, size))
            files = kept
        # Total size cap
        total_cap = max(0, self._total_mb()) * 1024 * 1024
        if total_cap > 0:
            files.sort(key=lambda x: x[2])  # oldest first
            total = sum(x[3] for x in files)
            while total > total_cap and files:
                full, uuid_part, mtime, size = files.pop(0)
                try:
                    os.unlink(full)
                    total -= size
                except OSError:
                    pass
