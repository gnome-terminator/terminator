# Windows Port — Acceptance Matrix (M5)

This is the manual verification matrix for the native Windows port. The
automated tests (`tests/test_platform.py`, `tests/test_terminal_backend.py`,
`tests/test_conpty_screen.py`) cover the pure-Python and contract layers on
both platforms; the matrix below covers the things that require a live
Windows desktop session with a ConPTY child.

## Environment

* Windows 10 1809+ (ConPTY).
* GTK3 runtime + PyGObject (MSYS2 `mingw-w64-x86_64-gtk3` + `python3-gobject`).
* `pip install pyte pywin32 psutil configobj`.
* Built per `PACKAGING-WINDOWS.md`.

## Shells

Run each scenario against three shells:

| Shell | `use_custom_command` value |
|-------|----------------------------|
| PowerShell | `pwsh.exe -NoLogo` (or `powershell.exe`) |
| cmd | `cmd.exe` |
| WSL bash | `wsl.exe ~` |

## Feature matrix

For each shell, verify:

| Feature | How to test | Pass criteria |
|---------|------------|---------------|
| Launch | Start `terminator.exe` | A window opens, the shell prompt renders |
| Echo | `echo hello` | `hello` appears on the next line |
| Colours | `Write-Host -Foreground Red x` / ANSI | Red glyph renders |
| True colour | `printf '\e[38;2;255;0;0mR\e[0m'` | Cell fg = red |
| Bold | `printf '\e[1mB\e[0m'` | B cell rendered bold |
| Resize | Drag window border | Grid reflows; ConPTY resized; no truncation |
| Scrollback | `for($i=0;$i -lt 200;$i++){echo $i}` then scroll | History scrolls correctly |
| Cursor | Type then backspace | Block cursor follows input |
| Split horizontal | `Ctrl+Shift+O` | New pane appears side-by-side, both spawn shells |
| Split vertical | `Ctrl+Shift+E` | New pane stacked, both spawn shells |
| Tab | `Ctrl+Shift+T` | New tab, spawns a shell |
| Broadcast (all) | Toggle group, type | Input goes to all grouped panes |
| Copy | Select + `Ctrl+Shift+C` | Selected text copied to clipboard |
| Paste | `Ctrl+Shift+V` | Clipboard text sent to shell |
| URL open | Ctrl+click a URL | Opens in default browser |
| URL hover | Hover a URL | Cursor changes to pointer |
| Search | `Ctrl+Shift+F`, type | Highlights matches, navigable |
| Single instance | Run `terminator.exe` again | Second invocation forwards `new_window` to first |
| Child exit | `exit` | Pane handled per `child-exited` (respawn/hold) |
| Dark titlebar | Set `window_decoration_style = dark` | Title bar dark |
| Light titlebar | `window_decoration_style = light` | Title bar light |
| Background transparency | Set profile background transparent | Compositing works where supported |

## Known gaps (tracked, not blockers for alpha)

* SIXEL graphics: unsupported by pyte.
* OSC-8 hyperlink hover metadata: not exposed (regex URL matching still works).
* Cursor shape variants (underline/beam): rendered as a block.
* Full per-cell colour runs in the renderer: simplified; plain-text lines
  render in default fg (per-run colour is an M5 hardening item).
* IME composition (CJK input): not yet wired.
* `WINDOWID` env: not set on Windows (X11-only); shells that need it degrade.

## Backend contract

`tests/test_terminal_backend.py` asserts that whatever
`terminal_backend.make_terminal_widget()` returns on the running platform
exposes every method `terminal.py` calls. Re-run it on the Windows build to
confirm `ConPtyTerminal` satisfies the contract before each release.
