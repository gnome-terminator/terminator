#!/usr/bin/env bash
# End-to-end GUI suite (NOT part of tests/run_tests.sh / the unit lane).
# Launches the real ./terminator under a private Xvfb (+xfwm4), drives it
# with xdotool, checks xprop titles, screenshots, session.json, scrollback
# cache and /proc.
#
# Usage: tests/e2e/run_e2e.sh [-k NAME_SUBSTR]... [--keep] [--timeout S]
# Env:   VENV=/path/to/venv (default .venv-test, falls back to /workspace/.venv-m1a)
#        E2E_WM=xfwm4|openbox|none   E2E_SHOTS=/workspace/smoke/e2e
#        E2E_FORCE=1 to run even while tests/run_tests.sh is running
# Needs: Xvfb xdotool xprop ffmpeg (x11grab) python3-PIL psutil; xfwm4/tmux optional.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
VENV="${VENV:-$ROOT/.venv-test}"
[ -x "$VENV/bin/python" ] || VENV=/workspace/.venv-m1a
for t in Xvfb xdotool xprop ffmpeg; do
  command -v $t >/dev/null || { echo "!! missing $t (apt-get install xvfb xdotool x11-utils ffmpeg)"; exit 2; }
done
"$VENV/bin/python" -c 'import PIL, psutil' || { echo "!! need Pillow + psutil in $VENV"; exit 2; }
# single test lane: don't overlap with the unit suite
if [ -z "${E2E_FORCE:-}" ]; then
  while pgrep -f "tests/run_tests.sh" >/dev/null; do
    echo ">> waiting for tests/run_tests.sh to finish (single test lane)"; sleep 10
  done
fi
# stub GSettings schema like the unit runner (only when the real one is missing)
SCHEMA_DIR="${TMPDIR:-/tmp}/terminator-test-schemas-$(id -u)"
if [ ! -f "$SCHEMA_DIR/gschemas.compiled" ] && [ -d tests/fixtures/schemas ]; then
  mkdir -p "$SCHEMA_DIR"; cp tests/fixtures/schemas/*.gschema.xml "$SCHEMA_DIR"/
  glib-compile-schemas "$SCHEMA_DIR" || true
fi
unset DISPLAY
exec env PYTHONPATH="$ROOT" "$VENV/bin/python" -m tests.e2e.run_e2e --python "$VENV/bin/python" "$@"
