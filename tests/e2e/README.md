# End-to-end GUI suite (tests/e2e)

Runs the **real** `./terminator` (PYTHONPATH=repo, `-u -d`) under a private
Xvfb + xfwm4, one isolated HOME/XDG tree per scenario, drives it with
xdotool (default keybindings) and checks from the outside: `xprop` WM
titles, ffmpeg x11grab screenshots (Pillow pixel checks), `session.json`,
the scrollback cache and `/proc` (psutil: shells, cwds, child processes).

Opt-in from the unit channel (m30): `TERMINATOR_E2E=1 tests/run_tests.sh tests/test_m30_e2e_gui.py`
(optional `TERMINATOR_E2E_K=9-,10-` filter); skipped by default and when deps are missing.

Otherwise not part of `tests/run_tests.sh`: `tests/e2e/conftest.py` sets
`collect_ignore_glob` so the unit lane (pytest `--doctest-modules` over the
tree) neither collects nor imports anything here. Exception:
`roundtrip_driver.py` is a helper that the unit test
`tests/test_m21_restore_roundtrip.py` runs as a subprocess.

Isolation: each scenario gets a fresh temp HOME with all `XDG_*` dirs inside
it, no `DBUS_*` session bus, and `GSETTINGS_BACKEND=memory`, so the real `~`
and dconf are never touched (the WM gets its own temp HOME too). Xvfb picks a
free display itself (`-displayfd`). Every spawned process carries
`TERMINATOR_E2E_ROOT=<temp root>` in its environment; cleanup kills the
terminator process group and then sweeps `/proc` for that mark, so shells
(own sessions under VTE) and background loops they started cannot outlive a
scenario, including after a FAIL or the per-scenario `--timeout` (default
150s). SIGTERM/SIGHUP/Ctrl+C to the runner unwind the same cleanup and stop
Xvfb/WM. Temp roots are removed on PASS and kept on FAIL/XFAIL (or `--keep`);
screenshots go to `E2E_SHOTS`.

    tests/e2e/run_e2e.sh                 # all scenarios
    tests/e2e/run_e2e.sh -k 4 -k title   # name substring filter
    tests/e2e/run_e2e.sh --keep          # keep temp HOMEs (failures are always kept)

Env: `VENV` (default .venv-test, else /workspace/.venv-m1a), `E2E_WM`
(xfwm4|openbox|none), `E2E_SHOTS` (default /workspace/smoke/e2e),
`E2E_FORCE=1` to skip waiting for a running `run_tests.sh`. Single test
lane: the script takes a `flock` so two e2e runs never overlap, and by
default waits while any `run_tests.sh` is running.

Results: `PASS`, `FAIL`, `SKIP` (optional tool missing, e.g. weston; does not fail the run), `XFAIL` (scenario marked as a known real-app bug in
`scenarios.py` and it failed as expected) and `XPASS` (marked scenario
passed: the bug looks fixed, remove the marker). Exit 0 iff everything is
PASS, SKIP or XFAIL.

Needs: Xvfb xdotool xprop xwininfo xdpyinfo ffmpeg flock, Pillow + psutil;
xfwm4, tmux and weston (Wayland smoke) optional. About 3 minutes for the full run.

| scenario | what |
|---|---|
| 1-session-roundtrip | split H/V + tab + cd → debounced session.json → SIGTERM → relaunch restores layout/cwds; scrollback restored (markers survive a 2nd run); `cd` then SIGINT within the debounce is captured by the final save |
| 2-multiwindow | 2 windows, close first then last (Ctrl+Shift+Q) within 10s → both restored |
| 2b-multiwindow-exit | same, but windows close because their shell `exit`s — **xfail: known real bug** (shell-exit close bypasses the D5 10s multi-window buffer, session keeps only the last window); flips to XPASS when fixed |
| 3-close-confirm | idle pane closes without prompt; `sleep 1000` → dialog; Esc keeps it; Close kills it and quits |
| 4-overlay-maximise | Ctrl+Shift+Return dims the 12px margin; shrinking the window shrinks the pane; sibling exits while maximised → no lost terminals; Shift+Esc undims; closing a pane after that does not crash |
| 5-autofont | tier estimated from `stty size` vs window px: 1 pane 1.0, stacked 1.0, 2x2 grid 0.8 |
| 6-window-title | 3 panes emit OSC titles at 20Hz; WM title only ever shows the focused pane's |
| 7-altscreen | scrollbar strip hidden in `tput smcup` and tmux, restored after; SIGTERM during a TUI → cache keeps shell history, no TUI frame |
| 8-corrupt-session | `[1,2]` session.json → starts, moved to `.corrupt`, fresh valid session written |
| 9-sigkill-recovery | split+tab+cd, wait for debounced save + 5s scrollback interval flush → SIGKILL (no final save) → relaunch restores layout/cwds; SIGKILL again while `restoring` exists → named session quarantined to `*.crashed`, 3rd start is `load_crash_fallback` (layout and cwd) |
| 9b-sigkill-scrollback | same prep through the first relaunch; each pane's scrollback file then has its own `SB_KILO*_3` and the English separator, no second SIGKILL |
| 14-hidpi-scale2 | GDK_SCALE=2: same device-px window gives ~half the scale-1 columns; session size in logical px; overlay maximise dims the 24-device-px margin and restores |
| 15-hidpi-autofont | scenario 5 at GDK_SCALE=2 (1560x940 device px): tiers are decided in cells, so 1 pane / stacked 1.0, 2x2 grid 0.8 |
| 16-wayland-smoke | needs `weston` (else SKIP): session seeded on X11 (split, cd, maximised pane, position) restored natively under `weston --backend=headless` + `GDK_BACKEND=wayland` (no DISPLAY) at output scale 1 and 2: shells/cwds/maximised pane back, the Wayland save drops the position but keeps size/maximised/layout, no stale WINDOWID in shells, clean SIGTERM |
| 10-quit-relaunch | split+cd → Ctrl+Shift+Q → "Close multiple terminals?" → Close Terminals → relaunch restores split/cwds/scrollback |

Harness notes: use `xwininfo` for geometry (xdotool getwindowgeometry is
off by the WM frame); markers printed by panes are split (`TUI''SCREEN`) so
the typed command line in scrollback cannot match them; GtkMessageDialog
mnemonics are not delivered by xdotool, so the dialog's Close is clicked.

Guard-rail scenarios live in `scenarios_guards.py` (appended to the run by `run_e2e.py`):

| scenario | what |
|---|---|
| 11-missing-cwd | saved cwd deleted between runs → that pane restores in `~`, others keep their dirs, split kept, deleted dir not re-saved |
| 12-crash-marker | stale `restoring` marker → restore skipped, `session.json` kept as `.crashed`, marker cleared, fresh session saved and restored next launch |
| 13-lock-held | another process holds `session.lock` → no restore, `session.json` byte-identical after edits + SIGTERM; owner restores once lock released |
