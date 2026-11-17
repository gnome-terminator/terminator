#!/usr/bin/env bash
# Reproducible test runner for the Terminator fork (M0 test env).
#
# Usage:
#   tests/run_tests.sh                 # full suite (pytest.ini: --doctest-modules)
#   tests/run_tests.sh tests/test_session.py -q   # extra args go to pytest
#
# Environment knobs:
#   VENV=/path/to/venv     venv to use/create (default: .venv-test in repo root)
#   PYTHON=python3         interpreter used to create the venv
#   DISPLAY=:N             reuse an existing X display; otherwise Xvfb :99 is started
#
# System packages (Debian/Ubuntu), install once if missing:
#   sudo apt-get install python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
#        gir1.2-vte-2.91 xvfb libglib2.0-bin
#
# Gtk must be 3.0 in the pytest process before collection. A test module
# that imports Gtk without gi.require_version gets Gtk 4 on current
# gi, and terminatorlib.util then exits because Gdk 4 is already loaded.
# The repo-root conftest.py requests Gtk 3.0 and Vte 2.91 before collection.
# The import check below is a separate process and only verifies the
# system packages; it does not load Gtk into the pytest process.
#   Optional (enables the two ignored modules):
#   sudo apt-get install python3-dbus gir1.2-notify-0.7
#   Optional (real schema instead of the stub): gsettings-desktop-schemas
#
# Why the stub schema: Gio.Settings.new() aborts the process (SIGTRAP,
# exit 133) when org.gnome.desktop.interface is not installed. config.py
# now guards this, but the stub keeps font/focus lookups realistic on
# minimal boxes. It is only used when the real schema is missing.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# --- 1. venv -----------------------------------------------------------
VENV="${VENV:-$ROOT/.venv-test}"
PYTHON="${PYTHON:-python3}"
if [ ! -x "$VENV/bin/python" ]; then
    echo ">> creating venv $VENV (with system site-packages for gi)"
    "$PYTHON" -m venv --system-site-packages "$VENV"
fi
if ! "$VENV/bin/python" -c 'import pytest, configobj, psutil' 2>/dev/null; then
    echo ">> installing pytest configobj psutil into $VENV"
    "$VENV/bin/pip" install -q pytest configobj psutil
fi
if ! "$VENV/bin/python" -c "import gi; gi.require_version('Gtk','3.0'); gi.require_version('Vte','2.91')" 2>/dev/null; then
    echo "!! PyGObject/GTK3/VTE not importable. Install system packages listed at top of $0." >&2
    exit 2
fi

# --- 2. GSettings schema stub (only if the real one is missing) --------
have_schema() {
    "$VENV/bin/python" - <<'PY' 2>/dev/null
import sys, gi
from gi.repository import Gio
src = Gio.SettingsSchemaSource.get_default()
ok = src is not None and all(src.lookup(s, True) for s in
     ('org.gnome.desktop.interface', 'org.gnome.desktop.wm.preferences'))
sys.exit(0 if ok else 1)
PY
}
if ! have_schema; then
    SCHEMA_SRC="$ROOT/tests/fixtures/schemas"
    # m26 review: per-run dir; a shared one was rewritten (cp + compile)
    # under any concurrently running suite.
    SCHEMA_DIR="$(mktemp -d "${TMPDIR:-/tmp}/terminator-test-schemas.XXXXXX")"
    cp "$SCHEMA_SRC"/*.gschema.xml "$SCHEMA_DIR"/
    if ! command -v glib-compile-schemas >/dev/null; then
        echo "!! glib-compile-schemas missing (apt-get install libglib2.0-bin)" >&2
        exit 2
    fi
    glib-compile-schemas "$SCHEMA_DIR"
    export GSETTINGS_SCHEMA_DIR="$SCHEMA_DIR"
    export GSETTINGS_BACKEND=memory
    echo ">> using stub GSettings schemas from $SCHEMA_DIR"
fi

# --- 3. display ----------------------------------------------------------
# m26 review: always run on a private Xvfb.  Inheriting the desktop's
# DISPLAY (e.g. :2 with a WM, dock and other windows) or racing another
# suite for /tmp/.X99-lock made focus/geometry tests flaky.  Set
# TERMINATOR_TEST_DISPLAY=:N to deliberately reuse a display.
XVFB_PID=""
cleanup() {
    [ -n "$XVFB_PID" ] && kill "$XVFB_PID" 2>/dev/null || true
    [ -n "${SCHEMA_DIR:-}" ] && case "$SCHEMA_DIR" in *terminator-test-schemas.*) rm -rf "$SCHEMA_DIR";; esac
    true
}
trap cleanup EXIT
if [ -n "${TERMINATOR_TEST_DISPLAY:-}" ]; then
    export DISPLAY="$TERMINATOR_TEST_DISPLAY"
else
    if ! command -v Xvfb >/dev/null; then
        echo "!! Xvfb not installed (apt-get install xvfb)" >&2
        exit 2
    fi
    DFD_FILE="$(mktemp "${TMPDIR:-/tmp}/terminator-test-xvfb.XXXXXX")"
    # -displayfd: the server picks a free display number atomically
    Xvfb -displayfd 3 -screen 0 1280x800x24 3>"$DFD_FILE" >/dev/null 2>&1 &
    XVFB_PID=$!
    for _ in $(seq 1 100); do
        [ -s "$DFD_FILE" ] && break
        kill -0 "$XVFB_PID" 2>/dev/null || break
        sleep 0.1
    done
    n="$(tr -dc 0-9 < "$DFD_FILE")"
    rm -f "$DFD_FILE"
    [ -z "$n" ] && { echo "!! could not start Xvfb" >&2; exit 2; }
    export DISPLAY=":$n"
    echo ">> started private Xvfb on $DISPLAY"
fi

# --- 4. isolate user state and run -------------------------------------
TMPHOME="$(mktemp -d "${TMPDIR:-/tmp}/terminator-test-home.XXXXXX")"
export XDG_CONFIG_HOME="$TMPHOME/config"
export XDG_STATE_HOME="$TMPHOME/state"
export XDG_CACHE_HOME="$TMPHOME/cache"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

IGNORES=()
"$VENV/bin/python" -c 'import dbus' 2>/dev/null || IGNORES+=(--ignore=terminatorlib/ipc.py)
"$VENV/bin/python" -c "import gi; gi.require_version('Notify','0.7')" 2>/dev/null \
    || IGNORES+=(--ignore=terminatorlib/plugins/command_notify.py)
[ ${#IGNORES[@]} -gt 0 ] && echo ">> ignoring (missing optional deps): ${IGNORES[*]}"

set +e
"$VENV/bin/python" -m pytest -p no:cacheprovider "${IGNORES[@]}" "$@"
rc=$?
set -e
rm -rf "$TMPHOME"
exit $rc
