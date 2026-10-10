#!/bin/bash
set -x
# Xvfb end-to-end: TUI running at quit -> restart restores shell history, not TUI frame.
# Env: OUT=dir PY=python SHOT=screenshot script. Expect snap/ cache to contain SHELLHIST_42, no TUIFRAME.
export DISPLAY=:77 HOME=${OUT:-/tmp}/home XDG_CONFIG_HOME=${OUT:-/tmp}/home/.config XDG_CACHE_HOME=${OUT:-/tmp}/home/.cache
rm -rf $HOME; mkdir -p $HOME
pgrep -f "Xvfb :77" >/dev/null || (Xvfb :77 -screen 0 1280x800x24 >/dev/null 2>&1 & sleep 1)
cd "$(dirname "$0")/../.."; REPO=$(pwd)
start(){ dbus-run-session -- ${PY:-.venv-test/bin/python} ./terminator -u ${2:-} >${OUT:-/tmp}/log$1.txt 2>&1 & sleep 5; }
start 1 -d
FAIL=0
W=$(xdotool search --onlyvisible --class terminator | head -1); xdotool windowactivate $W; sleep 0.5
xdotool type --delay 20 'seq 1 80; echo SHELLHIST_42; cd /tmp'; xdotool key Return; sleep 1
xdotool type --delay 20 "python3 $REPO/tests/smoke/fake_tui.py"; xdotool key Return; sleep 3
DISPLAY=:77 ${SHOT:-/workspace/smoke/shot.sh} ${OUT:-/tmp}/1-tui.png
# M8: the fullscreen TUI must have hidden the scrollbar (altscreen debug log).
grep -q "altscreen: False -> True" ${OUT:-/tmp}/log1.txt || { echo "FAIL: altscreen not detected in TUI"; FAIL=1; }
# Direct widget-state assertion: logged from Gtk.Scrollbar.get_visible() right after hide().
grep "altscreen: scrollbar visible=" ${OUT:-/tmp}/log1.txt | tail -1 | grep -q "visible=False" || { echo "FAIL: scrollbar still visible in TUI"; FAIL=1; }
xdotool key ctrl+shift+q; sleep 2
DISPLAY=:77 ${SHOT:-/workspace/smoke/shot.sh} ${OUT:-/tmp}/2-quit.png
# Find the running-process confirm dialog (new visible terminator-class window) instead of fixed coords,
# then press its _Close button via mnemonic (default/focus stays Cancel).
D=; for i in 1 2 3 4 5; do D=$(xdotool search --onlyvisible --class terminator 2>/dev/null | grep -vx "$W" | tail -1); [ -n "$D" ] && break; sleep 1; done
[ -n "$D" ] || { echo "FAIL: confirm dialog not found"; FAIL=1; }
# No WM on Xvfb, so keyboard mnemonics are unreliable: click the right-hand
# (Close) button computed from the dialog's own geometry.
eval $(xdotool getwindowgeometry --shell $D)
xdotool mousemove $((X + WIDTH*3/4)) $((Y + HEIGHT - 12)) click 1; sleep 3
pkill -f "tests/smoke/fake_tui.py"
pgrep -f "./terminator -u" && { echo "FAIL: STILL_RUNNING"; FAIL=1; pkill -f "./terminator -u"; sleep 1; }
echo ---- cache; grep -rl . $XDG_CACHE_HOME/terminator 2>/dev/null; grep -r "SHELLHIST\|TUIFRAME" $XDG_CACHE_HOME/terminator $XDG_CONFIG_HOME/terminator 2>/dev/null | cut -c1-200
mkdir -p ${OUT:-/tmp}/snap; cp -r $XDG_CACHE_HOME/terminator/scrollback ${OUT:-/tmp}/snap/ ; cp $HOME/.local/state/terminator/session.json ${OUT:-/tmp}/snap/
start 2
DISPLAY=:77 ${SHOT:-/workspace/smoke/shot.sh} ${OUT:-/tmp}/3-restored.png
pkill -f "./terminator -u"
grep -rq SHELLHIST_42 ${OUT:-/tmp}/snap/scrollback || { echo "FAIL: shell history not cached"; FAIL=1; }
grep -rq TUIFRAME ${OUT:-/tmp}/snap/scrollback && { echo "FAIL: TUI frame cached"; FAIL=1; }
[ $FAIL = 0 ] && echo SMOKE_PASS; exit $FAIL
