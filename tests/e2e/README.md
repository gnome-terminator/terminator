# End-to-end GUI suite (tests/e2e)

Runs the **real** `./terminator` (PYTHONPATH=repo, `-u -d`) under a private
Xvfb + xfwm4, one isolated HOME/XDG tree per scenario, drives it with
xdotool (default keybindings) and checks from the outside: `xprop` WM
titles, ffmpeg x11grab screenshots (Pillow pixel checks), `session.json`,
the scrollback cache and `/proc` (psutil: shells, cwds, child processes).

Not part of `tests/run_tests.sh`. Files are named so pytest collects no
tests from them; they are import-safe for `--doctest-modules`.

    tests/e2e/run_e2e.sh                 # all scenarios
    tests/e2e/run_e2e.sh -k 4 -k title   # name substring filter
    tests/e2e/run_e2e.sh --keep          # keep temp HOMEs (failures are always kept)

Env: `VENV` (default .venv-test, else /workspace/.venv-m1a), `E2E_WM`
(xfwm4|openbox|none), `E2E_SHOTS` (default /workspace/smoke/e2e),
`E2E_FORCE=1` to skip waiting for a running `tests/run_tests.sh` (the
runner waits for it by default to keep a single test lane).

Needs: Xvfb xdotool xprop xwininfo xdpyinfo ffmpeg, Pillow + psutil;
xfwm4 and tmux optional. About 2 minutes for the full run.

| scenario | what |
|---|---|
| 1-session-roundtrip | split H/V + tab + cd → debounced session.json → SIGTERM → relaunch restores layout/cwds; scrollback restored (markers survive a 2nd run); `cd` then SIGINT within the debounce is captured by the final save |
| 2-multiwindow | 2 windows, close first then last (Ctrl+Shift+Q) within 10s → both restored |
| 2b-multiwindow-exit | same, but windows close because their shell `exit`s — **known failing, real bug** |
| 3-close-confirm | idle pane closes without prompt; `sleep 1000` → dialog; Esc keeps it; Close kills it and quits |
| 4-overlay-maximise | Ctrl+Shift+Return dims the 12px margin; shrinking the window shrinks the pane; sibling exits while maximised → no lost terminals; Shift+Esc undims; closing a pane after that does not crash |
| 5-autofont | tier estimated from `stty size` vs window px: 1 pane 1.0, stacked 1.0, 2x2 grid 0.8 |
| 6-window-title | 3 panes emit OSC titles at 20Hz; WM title only ever shows the focused pane's |
| 7-altscreen | scrollbar strip hidden in `tput smcup` and tmux, restored after; SIGTERM during a TUI → cache keeps shell history, no TUI frame |
| 8-corrupt-session | `[1,2]` session.json → starts, moved to `.corrupt`, fresh valid session written |

Harness notes: use `xwininfo` for geometry (xdotool getwindowgeometry is
off by the WM frame); markers printed by panes are split (`TUI''SCREEN`) so
the typed command line in scrollback cannot match them; GtkMessageDialog
mnemonics are not delivered by xdotool, so the dialog's Close is clicked.
