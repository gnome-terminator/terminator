#!/bin/bash
set -x
export DISPLAY=:77 HOME=/workspace/smoke13/home XDG_CONFIG_HOME=/workspace/smoke13/home/.config XDG_CACHE_HOME=/workspace/smoke13/home/.cache
rm -rf $HOME; mkdir -p $HOME
pgrep -f "Xvfb :77" >/dev/null || (Xvfb :77 -screen 0 1280x800x24 >/dev/null 2>&1 & sleep 1)
cd /workspace/wt-m13
start(){ dbus-run-session -- /workspace/wt-int/.venv-test/bin/python ./terminator -u >/workspace/smoke13/log$1.txt 2>&1 & sleep 5; }
start 1
W=$(xdotool search --onlyvisible --class terminator | head -1); xdotool windowactivate $W; sleep 0.5
xdotool type --delay 20 'echo SHELLHIST_42; cd /tmp'; xdotool key Return; sleep 1
xdotool type --delay 20 'python3 $(dirname "$0")/fake_tui.py'; xdotool key Return; sleep 3
DISPLAY=:77 /workspace/smoke/shot.sh /workspace/smoke13/1-tui.png
xdotool key ctrl+shift+q; sleep 2
DISPLAY=:77 /workspace/smoke/shot.sh /workspace/smoke13/2-quit.png
xdotool mousemove 424 289 click 1; sleep 3
pkill -f "python3 $(dirname "$0")/fake_tui.py"
pgrep -f "./terminator -u" && echo STILL_RUNNING
echo ---- cache; grep -rl . $XDG_CACHE_HOME/terminator 2>/dev/null; grep -r "SHELLHIST\|TUIFRAME" $XDG_CACHE_HOME/terminator $XDG_CONFIG_HOME/terminator 2>/dev/null | cut -c1-200
mkdir -p /workspace/smoke13/snap; cp -r $XDG_CACHE_HOME/terminator/scrollback /workspace/smoke13/snap/ ; cp $HOME/.local/state/terminator/session.json /workspace/smoke13/snap/
start 2
DISPLAY=:77 /workspace/smoke/shot.sh /workspace/smoke13/3-restored.png
pkill -f "./terminator -u"
