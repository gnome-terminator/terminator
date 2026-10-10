# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""session.py - SessionManager for layout/cwd save and restore."""

from __future__ import print_function

import errno
import fcntl
import hashlib
import json
import os
import tempfile
import time
from copy import deepcopy
from datetime import datetime, timezone

from .borg import Borg
from .util import dbg, err, get_state_dir


def tighten_dir(path):
    """chmod an existing private dir to 0700 when we own it (P2-9)."""
    try:
        st = os.stat(path)
        if st.st_uid == os.geteuid() and (st.st_mode & 0o077):
            os.chmod(path, 0o700)
    except OSError as ex:
        dbg('tighten_dir %s: %s' % (path, ex))

SESSION_LAYOUT_NAME = '__last_session__'
SESSION_VERSION = 1
QUIT_ALL_WINDOW_GRACE_S = 10.0
SAVE_BACKOFF_MAX_S = 300
PERIODIC_MARK_DIRTY_S = 60
RESTORING_CLEAR_DELAY_S = 10


def _now_iso():
    try:
        return datetime.now().astimezone().isoformat(timespec='seconds')
    except Exception:
        return datetime.now(timezone.utc).isoformat(timespec='seconds')


def stringify_leaves(obj):
    """Recursively stringify layout leaves for ConfigObj-compatible types.

    Sequences become lists of stringified elements (never str(tuple)).
    Bools become 'True'/'False'. UUID-like objects become str().
    """
    if obj is None:
        return None
    if isinstance(obj, bool):
        return 'True' if obj else 'False'
    if isinstance(obj, (str, int, float)):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): stringify_leaves(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [stringify_leaves(x) for x in obj]
    # uuid.UUID and other objects
    return str(obj)


def layout_change_hash(layout):
    """Stable hash of layout alone (saved_at must not participate)."""
    canonical = json.dumps(layout, sort_keys=True, separators=(',', ':'),
                           ensure_ascii=False)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def count_terminals_in_layout(layout):
    if not layout:
        return 0
    n = 0
    for node in layout.values():
        if isinstance(node, dict) and node.get('type') == 'Terminal':
            n += 1
    return n


def collect_terminal_uuids(layout):
    uuids = set()
    if not layout:
        return uuids
    for node in layout.values():
        if isinstance(node, dict) and node.get('type') == 'Terminal':
            uid = node.get('uuid')
            if uid:
                uuids.add(str(uid))
    return uuids


def sanitize_layout(layout, missing_dirs=None):
    """Sanitize a loaded session layout for restore.

    Missing directories become ~; command keys removed; values stringified.
    Malformed nodes (non-dict, or without a string ``type``) are dropped so
    Terminator.create_layout cannot crash on them.
    missing_dirs (if a list) is appended with paths that were rewritten.

    Window titles: session.json only ever contained user-set ("Set window
    title") titles -- earlier builds stripped titles at save time and
    describe_layout now only emits persisted forced titles -- so a Window
    ``title`` is kept and marked ``title_forced`` (older session files lack
    the marker).
    """
    if missing_dirs is None:
        missing_dirs = []
    if not isinstance(layout, dict):
        return {}
    # Validate before stringify_leaves (it would turn type 3 into '3')
    layout = {k: v for k, v in layout.items()
              if isinstance(v, dict) and isinstance(v.get('type'), str)}
    layout = stringify_leaves(deepcopy(layout)) if layout else {}
    home = os.path.expanduser('~')
    for name in list(layout.keys()):
        node = layout[name]
        if not isinstance(node, dict) or not isinstance(node.get('type'), str) \
                or not node.get('type'):
            dbg('sanitize_layout: dropping malformed node %r' % (name,))
            del layout[name]
            continue
        if node.get('type') == 'Terminal':
            node.pop('command', None)
            directory = node.get('directory')
            if directory:
                expanded = os.path.expanduser(directory)
                if not os.path.isdir(expanded):
                    missing_dirs.append(directory)
                    node['directory'] = home
                else:
                    node['directory'] = expanded
        if node.get('type') == 'Window':
            if node.get('title'):
                node['title_forced'] = 'True'
            else:
                node.pop('title', None)
                node.pop('title_forced', None)
    return layout


def is_explicit_launch(options):
    """True when a launch asked for something other than a plain window.

    -e/-x commands, an explicit -l NAME (not the synthetic default) or
    --config-json.  Windows created by such launches are not part of the
    saved session (restoring them as plain shells would be wrong), but they
    no longer prevent the process from saving the plain windows.
    --working-directory alone is a plain window in another directory (a
    DBus follower always forwards its cwd), so it does not count.
    """
    def opt(name):
        value = getattr(options, name, None)
        if isinstance(value, str) and value in ('', 'None', 'False'):
            return None
        return value
    layout_from_default = bool(opt('layout_from_default'))
    layout = opt('layout')
    explicit_layout = (layout is not None and not layout_from_default and
                       layout not in ('default', SESSION_LAYOUT_NAME))
    has_command = bool(opt('command') or opt('execute'))
    has_configjson = bool(opt('configjson'))
    return bool(explicit_layout or has_command or has_configjson)


def merge_window_fragments(layout, fragments):
    """D5: append buffered (already closed) windows to a live layout.

    Each fragment is a self-contained ``{name: node}`` tree describing one
    window (names from an independent describe, so they collide with the
    live layout).  Every node gets a fresh, non-colliding name and its
    ``parent`` is rewritten accordingly; the windows are appended as new
    top-level windows.
    """
    merged = dict(layout)
    used = set(merged)
    live_has_window = any(isinstance(n, dict) and n.get('type') == 'Window'
                          for n in merged.values())
    for idx, frag in enumerate(fragments or []):
        if not frag:
            continue
        mapping = {}
        for name in frag:
            new = 'd5w%d_%s' % (idx, name)
            while new in used:
                new += '_'
            used.add(new)
            mapping[name] = new
        for name, node in frag.items():
            if not isinstance(node, dict):
                continue
            node = stringify_leaves(deepcopy(node))
            parent = node.get('parent') or ''
            if parent:
                if parent not in mapping:
                    # Dangling parent: drop rather than attach to a live node
                    continue
                node['parent'] = mapping[parent]
            if node.get('type') == 'Window' and live_has_window:
                # The live window keeps focus on restore
                node['last_active_window'] = 'False'
            merged[mapping[name]] = node
    return merged


class SessionManager(Borg):
    """Persist and restore layout + cwd session state."""

    _timer = None
    _periodic_timer = None
    _last_change_hash = None
    _lock_fd = None
    _owns_session = None
    final_saving = None
    restored_this_run = None
    _closing_buffer = None
    _write_failures = None
    _disabled = None
    _loaded_session_uuids = None
    _finalize_done = None
    _crash_skipped = None
    _missing_dirs_notice = None
    _signals_installed = None
    _buffer_timer = None
    _config = None
    _rotated_this_run = None
    # m25: save requests dropped during layout / legacy zoom are replayed.
    # NOTE: these _pending_* flags are diagnostic only (dbg/tests); the
    # replay itself is driven by mark_dirty() from the layout-end / unzoom
    # call sites, not by reading these flags.
    _pending_after_layout = None
    _pending_after_zoom = None

    def __init__(self):
        Borg.__init__(self, self.__class__.__name__)
        self.prepare_attributes()

    def prepare_attributes(self):
        if self._timer is None:
            self._timer = None
        if self._periodic_timer is None:
            self._periodic_timer = None
        if self._last_change_hash is None:
            self._last_change_hash = None
        if self._lock_fd is None:
            self._lock_fd = None
        if self._owns_session is None:
            self._owns_session = False
        if self.final_saving is None:
            self.final_saving = False
        if self.restored_this_run is None:
            self.restored_this_run = False
        if self._closing_buffer is None:
            self._closing_buffer = None
        if self._write_failures is None:
            self._write_failures = 0
        if self._disabled is None:
            self._disabled = False
        if self._loaded_session_uuids is None:
            self._loaded_session_uuids = None
        if self._finalize_done is None:
            self._finalize_done = False
        if self._crash_skipped is None:
            self._crash_skipped = False
        if self._missing_dirs_notice is None:
            self._missing_dirs_notice = None
        if self._signals_installed is None:
            self._signals_installed = False
        if self._buffer_timer is None:
            self._buffer_timer = None
        if self._config is None:
            self._config = None
        if self._rotated_this_run is None:
            self._rotated_this_run = False

    # --- paths ----------------------------------------------------------

    def state_dir(self):
        path = get_state_dir()
        try:
            os.makedirs(path, mode=0o700, exist_ok=True)
            tighten_dir(path)
        except OSError as ex:
            err('SessionManager.state_dir: %s' % ex)
        return path

    def session_path(self):
        custom = ''
        try:
            custom = self._get_config_value('session_file', '') or ''
        except Exception:
            custom = ''
        if custom:
            return os.path.expanduser(custom)
        return os.path.join(self.state_dir(), 'session.json')

    def lock_path(self):
        return os.path.join(self.state_dir(), 'session.lock')

    def restoring_path(self):
        return os.path.join(self.state_dir(), 'restoring')

    def _get_config_value(self, key, default=None):
        try:
            from .config import Config
            cfg = Config()
            if key in cfg:
                return cfg[key]
        except Exception:
            pass
        return default

    def _delay_ms(self):
        try:
            return int(self._get_config_value('session_save_delay_ms', 1500) or 1500)
        except (TypeError, ValueError):
            return 1500

    # --- lock / ownership -----------------------------------------------

    def acquire_lock(self):
        """Non-blocking exclusive flock on session.lock. Returns True on success."""
        if self._lock_fd is not None:
            return True
        try:
            fd = os.open(self.lock_path(), os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lock_fd = fd
            dbg('SessionManager: acquired session lock')
            return True
        except (OSError, IOError) as ex:
            dbg('SessionManager: could not acquire lock: %s' % ex)
            try:
                if 'fd' in locals():
                    os.close(fd)
            except Exception:
                pass
            self._lock_fd = None
            return False

    def set_owner_from_options(self, options):
        """Decide session ownership (D10, revised in m21).

        The lock holder owns the session regardless of its own launch
        options.  Previously a first instance started with -e/-x/-l NAME/
        --working-directory took the lock but never wrote, so every later
        plain window (arriving over DBus into that process) went unsaved for
        the whole run.  Now such explicit windows are merely excluded from
        the saved layout (see exclude_windows), and launch options only
        affect whether the last session is *restored*.
        --no-restore skips restore only; the owner still writes.
        """
        if self._lock_fd is None:
            self._owns_session = False
            return
        self._owns_session = True
        dbg('SessionManager: this process owns the session')

    def exclude_windows(self, windows):
        """Leave windows created by an explicit launch out of the session."""
        for window in windows or []:
            try:
                window._session_excluded = True
            except Exception:
                pass

    def is_writer(self):
        return bool(self._owns_session and self._lock_fd is not None and
                    not self._disabled)

    def is_owner(self):
        """Same ownership as writer, ignoring temporary _disabled."""
        return bool(self._owns_session and self._lock_fd is not None)

    def writes_suspended(self):
        """True after suspend_writes (prefs clear / use-previous)."""
        return bool(self._disabled)

    def suspend_writes(self, reason=''):
        """Stop writing session.json (and scrollback) for the rest of this run.

        Used by the preferences "clear" / "use previous session" actions so
        that the running instance does not overwrite the result at exit.
        """
        dbg('SessionManager.suspend_writes: %s' % reason)
        self._disabled = True
        if self._timer is not None:
            try:
                from gi.repository import GLib
                GLib.source_remove(self._timer)
            except Exception:
                pass
            self._timer = None
        try:
            from .scrollback import ScrollbackCache
            ScrollbackCache().stop(join_timeout=1.0)
        except Exception as ex:
            dbg('SessionManager.suspend_writes scrollback: %s' % ex)

    # --- dirty / flush --------------------------------------------------

    def _any_legacy_zoom(self):
        try:
            from .terminator import Terminator
            for window in Terminator().windows:
                if not hasattr(window, 'is_zoomed'):
                    continue
                if not window.is_zoomed():
                    continue
                # Overlay maximise should NOT skip; only legacy/scaled zoom
                if getattr(window, 'is_overlay_maximised', lambda: False)():
                    continue
                return True
        except Exception as ex:
            dbg('SessionManager._any_legacy_zoom: %s' % ex)
        return False

    def mark_dirty(self, reason=''):
        """Schedule a debounced save. Existing timer is not reset."""
        try:
            from .terminator import Terminator
            if Terminator().doing_layout:
                # m25: remember; layout_done() replays one save
                self._pending_after_layout = True
                return
        except Exception:
            pass
        if self.final_saving or not self.is_writer():
            return
        if self._any_legacy_zoom():
            # m25: legacy zoom detaches other panes; defer until unzoom
            self._pending_after_zoom = True
            dbg('SessionManager.mark_dirty deferred (legacy zoom): %s' % reason)
            return
        self._pending_after_layout = False
        self._pending_after_zoom = False
        if self._timer is not None:
            return
        delay = max(100, self._delay_ms())
        if self._write_failures:
            # Back off after write failures (unwritable session_file)
            backoff = min(SAVE_BACKOFF_MAX_S,
                          2 ** min(self._write_failures, 9)) * 1000
            delay = max(delay, int(backoff))
        try:
            from gi.repository import GLib
            self._timer = GLib.timeout_add(delay, self._flush)
            dbg('SessionManager.mark_dirty(%s) timer %dms' % (reason, delay))
        except Exception as ex:
            err('SessionManager.mark_dirty: %s' % ex)
            # Fall back to immediate flush without GLib
            self._flush()

    def _flush(self):
        self._timer = None
        try:
            self.save_now(final=False)
        except Exception as ex:
            err('SessionManager._flush: %s' % ex)
        return False

    def _ensure_periodic(self):
        if self._periodic_timer is not None or not self.is_writer():
            return
        try:
            from gi.repository import GLib
            self._periodic_timer = GLib.timeout_add_seconds(
                PERIODIC_MARK_DIRTY_S, self._periodic_tick)
        except Exception as ex:
            dbg('SessionManager periodic timer: %s' % ex)

    def _periodic_tick(self):
        if not self.is_writer() or self.final_saving:
            self._periodic_timer = None
            return False
        self.mark_dirty('periodic')
        return True

    # --- describe / save ------------------------------------------------

    def _describe_current(self):
        from .terminator import Terminator
        term = Terminator()
        # Refresh paned ratios before describe when possible
        try:
            for window in term.windows:
                self._refresh_ratios(window)
        except Exception as ex:
            dbg('SessionManager ratio refresh: %s' % ex)
        return self._describe_windows(
            [w for w in term.windows
             if not getattr(w, '_session_excluded', False)])

    @staticmethod
    def _describe_windows(windows):
        layout = {}
        count = 0
        for window in windows:
            count = window.describe_layout(count, '', layout, 0, True)
        return layout

    def _refresh_ratios(self, widget):
        maker = None
        try:
            from .factory import Factory
            maker = Factory()
        except Exception:
            return
        try:
            if hasattr(widget, 'ratio') and hasattr(widget, 'ratio_by_position'):
                if hasattr(widget, 'get_realized') and widget.get_realized():
                    new_ratio = widget.ratio_by_position(
                        widget.get_length(), widget.get_handlesize(),
                        widget.get_position())
                    if new_ratio is not None:
                        widget.ratio = new_ratio
        except Exception:
            pass
        try:
            children = widget.get_children() if hasattr(widget, 'get_children') else []
            for child in children:
                if child is not None:
                    self._refresh_ratios(child)
        except Exception:
            pass

    def save_now(self, final=False):
        """Write session.json. Requires is_writer() even when final=True."""
        if not self.is_writer():
            dbg('SessionManager.save_now: not writer, skip (final=%s)' % final)
            return False
        if not final and self._any_legacy_zoom():
            # m25: a timer scheduled before zoom must not write the
            # detached (one-pane) tree; replay after unzoom instead.
            self._pending_after_zoom = True
            dbg('SessionManager.save_now: legacy zoom, deferred')
            return False
        if final and self._any_legacy_zoom():
            # m25: finalize() unzooms first; if that failed the tree is
            # still detached (one pane). Keep the last good file instead.
            err('SessionManager.save_now: still zoomed at final save, '
                'keeping previous session file')
            return False
        try:
            layout = self._describe_current()
        except Exception as ex:
            err('SessionManager.save_now describe: %s' % ex)
            return False

        fragments = []
        if final and self._closing_buffer:
            fragments = list(self._closing_buffer.get('windows') or [])
        if count_terminals_in_layout(layout) == 0 and not fragments:
            dbg('SessionManager.save_now: 0 terminals, not writing')
            return False

        layout = stringify_leaves(layout)
        # Window titles: Container.describe_layout only emits user-set
        # (persisted) forced titles, marked title_forced, so they are kept.
        if fragments:
            # D5: windows closed in the last few seconds; renamed so their
            # node names cannot collide with the live layout (P0-1).
            layout = merge_window_fragments(layout, fragments)

        if count_terminals_in_layout(layout) == 0:
            dbg('SessionManager.save_now: still 0 terminals after merge')
            return False

        change = layout_change_hash(layout)
        if not final and change == self._last_change_hash:
            dbg('SessionManager.save_now: unchanged, skip')
            return True

        payload = {
            'version': SESSION_VERSION,
            'saved_at': _now_iso(),
            'terminator_version': self._terminator_version(),
            'layout': layout,
        }
        path = self.session_path()
        try:
            if not self._rotated_this_run:
                # Keep the previous run's session as .prev before the first
                # write of this run (a failed/partial restore or
                # --no-restore must not silently replace it).
                self._rotate_session(path)
                self._rotated_this_run = True
            self._atomic_write_json(path, payload)
            self._last_change_hash = change
            self._write_failures = 0
            dbg('SessionManager.save_now: wrote %s (final=%s)' % (path, final))
            return True
        except OSError as ex:
            self._write_failures += 1
            err('SessionManager.save_now write failed (%d): %s' %
                (self._write_failures, ex))
            return False

    def _terminator_version(self):
        try:
            from .version import APP_VERSION
            return APP_VERSION
        except Exception:
            return 'unknown'

    def _rotate_session(self, path):
        prev = path + '.prev'
        prev2 = path + '.prev2'
        if not os.path.exists(path):
            return
        try:
            if os.path.exists(prev):
                os.replace(prev, prev2)
            if os.path.exists(path):
                os.replace(path, prev)
        except OSError as ex:
            dbg('SessionManager rotate: %s' % ex)

    def _atomic_write_json(self, path, payload):
        directory = os.path.dirname(path) or '.'
        os.makedirs(directory, mode=0o700, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix='.tmp',
                                   prefix='.session-')
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
            try:
                dirfd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(dirfd)
                finally:
                    os.close(dirfd)
            except OSError:
                pass
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # --- load / crash marker --------------------------------------------

    def load(self):
        """Load session.json. On parse/version errors → None and rename .bad."""
        path = self.session_path()
        if not os.path.isfile(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
        except Exception as ex:
            err('SessionManager.load: parse failed: %s' % ex)
            self._quarantine(path, '.bad')
            return None
        if not isinstance(data, dict):
            err('SessionManager.load: not a session object (%s)' %
                type(data).__name__)
            self._quarantine(path, '.corrupt')
            return None
        version = data.get('version')
        try:
            version = int(version)
        except (TypeError, ValueError):
            version = None
        if version is None or version > SESSION_VERSION:
            err('SessionManager.load: unsupported version %r' % version)
            self._quarantine(path, '.bad')
            return None
        if 'layout' not in data or not isinstance(data['layout'], dict):
            err('SessionManager.load: missing layout')
            self._quarantine(path, '.corrupt')
            return None
        return data

    def _quarantine(self, path, suffix):
        try:
            os.replace(path, path + suffix)
        except OSError as ex:
            dbg('SessionManager quarantine: %s' % ex)

    def restore_failed(self, ex=None):
        """create_layout of the restored session blew up: keep a copy of
        the file as .bad (the following writes would replace it) and do not
        try to feed caches for uuids that never got a terminal."""
        err('SessionManager: restoring the last session failed: %s' % ex)
        path = self.session_path()
        try:
            if os.path.isfile(path):
                import shutil
                shutil.copy2(path, path + '.bad')
        except OSError as e:
            dbg('SessionManager.restore_failed copy: %s' % e)
        self.restored_this_run = False
        self.clear_restoring_now()

    def sanitize_layout(self, layout):
        missing = []
        result = sanitize_layout(layout, missing_dirs=missing)
        if missing:
            self._missing_dirs_notice = missing
        return result

    def begin_restore(self):
        path = self.restoring_path()
        try:
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(_now_iso())
                fh.write('\n')
            os.chmod(path, 0o600)
        except OSError as ex:
            err('SessionManager.begin_restore: %s' % ex)

    def clear_restoring_now(self):
        path = self.restoring_path()
        try:
            if os.path.exists(path):
                os.unlink(path)
        except OSError as ex:
            dbg('SessionManager.clear_restoring_now: %s' % ex)

    def schedule_clear_restoring(self):
        try:
            from gi.repository import GLib
            GLib.timeout_add_seconds(RESTORING_CLEAR_DELAY_S,
                                     self._clear_restoring_cb)
        except Exception as ex:
            dbg('SessionManager.schedule_clear_restoring: %s' % ex)
            self.clear_restoring_now()

    def _clear_restoring_cb(self):
        self.clear_restoring_now()
        return False

    def check_crash_marker(self):
        """True if restoring marker still present (previous restore crashed)."""
        path = self.restoring_path()
        if not os.path.exists(path):
            return False
        session = self.session_path()
        try:
            if os.path.isfile(session):
                os.replace(session, session + '.crashed')
        except OSError as ex:
            dbg('SessionManager crash rename: %s' % ex)
        self.clear_restoring_now()
        self._crash_skipped = True
        return True

    def clear_session_files(self):
        path = self.session_path()
        for candidate in (path, path + '.prev', path + '.prev2',
                          path + '.bad', path + '.corrupt', path + '.crashed',
                          self.restoring_path()):
            try:
                if os.path.exists(candidate):
                    os.unlink(candidate)
            except OSError as ex:
                dbg('SessionManager.clear_session_files: %s' % ex)
        try:
            from .scrollback import ScrollbackCache
            ScrollbackCache().clear_all()
        except Exception as ex:
            dbg('SessionManager clear scrollback: %s' % ex)
        self._last_change_hash = None
        self._loaded_session_uuids = None

    def restore_prev_session(self):
        """Copy session.json.prev over session.json for next launch.

        Always suspends writes first so any caller (prefs UI or otherwise)
        cannot have this instance overwrite the restored file on exit.
        """
        path = self.session_path()
        prev = path + '.prev'
        if not os.path.isfile(prev):
            return False
        try:
            with open(prev, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
            if not isinstance(data, dict) or \
                    not isinstance(data.get('layout'), dict):
                raise ValueError('malformed %s' % prev)
        except Exception as ex:
            err('SessionManager.restore_prev_session: %s' % ex)
            return False
        # Only suspend once we know the copy can succeed
        self.suspend_writes('restore previous session')
        try:
            self._atomic_write_json(path, data)
            return True
        except Exception as ex:
            err('SessionManager.restore_prev_session: %s' % ex)
            return False

    # --- D5 buffer / will_persist ---------------------------------------

    def note_window_closing(self, window):
        """Capture a self-contained layout of a window about to close (D5)."""
        if not self.is_writer() or self.final_saving:
            return
        if getattr(window, '_session_excluded', False):
            return
        try:
            self._refresh_ratios(window)
        except Exception:
            pass
        try:
            fragment = stringify_leaves(self._describe_windows([window]))
        except Exception as ex:
            err('SessionManager.note_window_closing describe: %s' % ex)
            return
        if count_terminals_in_layout(fragment) == 0:
            return
        uuids = collect_terminal_uuids(fragment)

        if self._closing_buffer is None:
            self._closing_buffer = {
                'deadline': time.time() + QUIT_ALL_WINDOW_GRACE_S,
                'windows': [],
                'uuids': set(),
            }
        else:
            self._closing_buffer['deadline'] = (
                time.time() + QUIT_ALL_WINDOW_GRACE_S)
        self._closing_buffer['windows'].append(fragment)
        self._closing_buffer['uuids'].update(uuids)
        self._arm_buffer_timeout()
        dbg('SessionManager.note_window_closing: %d nodes, %d uuids' %
            (len(fragment), len(uuids)))

    def _arm_buffer_timeout(self):
        if self._buffer_timer is not None:
            try:
                from gi.repository import GLib
                GLib.source_remove(self._buffer_timer)
            except Exception:
                pass
            self._buffer_timer = None
        try:
            from gi.repository import GLib
            self._buffer_timer = GLib.timeout_add_seconds(
                int(QUIT_ALL_WINDOW_GRACE_S) + 1, self._buffer_timeout_cb)
        except Exception as ex:
            dbg('SessionManager buffer timer: %s' % ex)

    def _buffer_timeout_cb(self):
        self._buffer_timer = None
        buf = self._closing_buffer
        if not buf:
            return False
        if time.time() < buf.get('deadline', 0):
            # Reschedule remainder
            remaining = max(1, int(buf['deadline'] - time.time()) + 1)
            try:
                from gi.repository import GLib
                self._buffer_timer = GLib.timeout_add_seconds(
                    remaining, self._buffer_timeout_cb)
            except Exception:
                pass
            return False
        discard = set(buf.get('uuids') or set())
        # Keep uuids still open
        try:
            from .terminator import Terminator
            still = set()
            for term in Terminator().terminals:
                if getattr(term, 'uuid', None) is not None:
                    still.add(str(term.uuid))
            discard -= still
        except Exception:
            pass
        if discard:
            try:
                from .scrollback import ScrollbackCache
                ScrollbackCache().discard_uuids(discard)
            except Exception as ex:
                dbg('SessionManager discard_uuids: %s' % ex)
        self._closing_buffer = None
        dbg('SessionManager D5 buffer expired, discarded %d uuids' %
            len(discard))
        return False

    def will_persist(self, terminal):
        """Whether this terminal's uuid will appear in the next restored session."""
        uuid_obj = getattr(terminal, 'uuid', None)
        if uuid_obj is None:
            return False
        uid = str(uuid_obj)
        if self.final_saving and self.is_writer():
            return True
        if (self._closing_buffer and
                uid in (self._closing_buffer.get('uuids') or set())):
            return True
        # Still-open terminal during normal run → closing that one terminal
        # alone should NOT persist (B deletes). Caller asks at close time:
        # if terminal is being closed and not in D5/final, return False.
        # Convention from design: "uuid 属于仍打开窗口且 is_writer（常规运行中
        # close 某终端 → False）". So open terminals that are NOT being
        # closed aren't asked; when asked at close, only final/D5 → True.
        return False

    def session_uuids(self):
        if self._loaded_session_uuids is None:
            return None
        return set(self._loaded_session_uuids)

    # --- finalize / signals ---------------------------------------------

    def finalize(self):
        if self._finalize_done:
            return
        self._finalize_done = True
        try:
            if self.is_writer():
                self.final_saving = True
                try:
                    # Legacy zoom: unzoom before describe so tree is complete
                    self._unzoom_legacy_all()
                except Exception as ex:
                    dbg('SessionManager unzoom on finalize: %s' % ex)
                try:
                    self.save_now(final=True)
                except Exception as ex:
                    err('SessionManager.finalize save: %s' % ex)
                self.clear_restoring_now()
            try:
                from .scrollback import ScrollbackCache
                cache = ScrollbackCache()
                if self.is_writer():
                    cache.flush_all(sync=True, final=True)
                cache.stop(join_timeout=1.0)
            except Exception as ex:
                dbg('scrollback finalize: %s' % ex)
            try:
                from .terminator import Terminator
                for w in list(Terminator().windows):
                    if getattr(w, 'is_overlay_maximised', lambda: False)():
                        w.overlay_restore(animate=False)
            except Exception as ex:
                dbg('overlay restore on finalize: %s' % ex)
        finally:
            if self._closing_buffer is not None:
                self._closing_buffer = None
            if self._timer is not None:
                try:
                    from gi.repository import GLib
                    GLib.source_remove(self._timer)
                except Exception:
                    pass
                self._timer = None

    def _unzoom_legacy_all(self):
        from .terminator import Terminator
        for window in list(Terminator().windows):
            if not hasattr(window, 'is_zoomed'):
                continue
            if not window.is_zoomed():
                continue
            if getattr(window, 'is_overlay_maximised', lambda: False)():
                continue
            try:
                window.unzoom()
            except Exception as ex:
                dbg('legacy unzoom: %s' % ex)

    def install_signal_handlers(self):
        if self._signals_installed:
            return
        self._signals_installed = True
        # Warn if legacy session plugins are enabled
        try:
            from .config import Config
            enabled = Config()['enabled_plugins'] or []
            for name in ('SaveLastSessionLayout', 'SaveUserSessionLayout'):
                if name in enabled:
                    err('SessionManager: plugin %s is enabled; prefer built-in '
                        'session restore and disable the plugin' % name)
        except Exception:
            pass
        try:
            import signal
            from gi.repository import GLib
            for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
                try:
                    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig,
                                         self._on_unix_signal, sig)
                except AttributeError:
                    # Older bindings
                    try:
                        from gi.repository import GLibUnix
                        GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, sig,
                                            self._on_unix_signal, sig)
                    except Exception as ex:
                        dbg('unix_signal_add fallback: %s' % ex)
        except Exception as ex:
            err('SessionManager.install_signal_handlers: %s' % ex)
        self._ensure_periodic()

    def _on_unix_signal(self, sig):
        dbg('SessionManager: got signal %s' % sig)
        try:
            self.finalize()
        except Exception as ex:
            err('SessionManager signal finalize: %s' % ex)
        try:
            from gi.repository import Gtk
            Gtk.main_quit()
        except Exception as ex:
            err('SessionManager signal main_quit: %s' % ex)
        try:
            from gi.repository import GLib
            return GLib.SOURCE_REMOVE
        except Exception:
            return False


def try_mark_dirty(reason=''):
    """Convenience for call sites that should never raise."""
    try:
        SessionManager().mark_dirty(reason)
    except Exception as ex:
        dbg('try_mark_dirty: %s' % ex)
