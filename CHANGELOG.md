# Changelog

## 2.1.6+fork.1 (unreleased): fork of 2.1.6 (TIIEHenry/TerminatorX)

The five new features below are **on by default**. Each one can be turned off in Preferences or in the config file (see `terminator_config(5)`).

**New features**

- **Session save and restore.** Windows, tabs, splits, working directories, the maximised pane and any manually set window title are saved automatically (debounced) while Terminator runs. A plain `terminator` launch restores them.
  - New options `--restore`, `--no-restore` and `--clear-session`.
  - New Preferences > Session page with "Save as layout", "Use previous session next time" and "Clear session and cache…".
  - The full terminal menu has "Don't restore next launch". Checked, it pauses saving and the next plain launch opens a new window once. Uncheck to keep saving. Quit and start Terminator again; a second window opened while this one is still running is not that next launch.
  - Config keys: `restore_last_session`, `session_save_delay_ms`, `session_file`.
  - The session is stored in `$XDG_STATE_HOME/terminator/session.json`.
- **Close confirmation for running processes.** Closing a terminal, tab or window asks only when a program other than the shell is still running, and the dialog names that program. Closing a child pane/layout (`_Close Pane` / 关闭布局, titlebar close button, terminal menu) anchors a focused `Gtk.Popover` to the trigger widget instead of showing a modal dialog. Closing a window or tab without an anchor widget uses a modal confirmation dialog. Several idle shells close with no prompt. `ask_before_closing = always` still asks when every terminal is only a shell. `never` never asks. Config key: `close_confirm_ignore`.
- **Scrollback cache.** The last lines of each terminal, with colours, are cached in `~/.cache/terminator/scrollback/` and replayed after a session restore. The screens of fullscreen programs are never cached. Config keys: `scrollback_cache*`.
- **Wave-style pane titlebars.**
  - Dark titlebars with a gear menu, maximise/restore and close buttons. Right-click opens the terminal menu.
  - A 1px accent border marks the focused pane.
  - Config keys: `titlebar_buttons`, `titlebar_density`, `pane_accent_color`.
  - Double-clicking a titlebar now maximises the pane. Renaming moved to the menu and to Ctrl+Alt+X.
- **Overlay maximise.**
  - A single pane is maximised as an animated overlay above the dimmed panes. The tab list (left sidebar, or the native tab strip) stays visible and clickable.
  - New default shortcut **Ctrl+Shift+Return** for `maximise`, which upstream left unbound. Ctrl+Shift+X does the same.
  - New shortcut **Shift+Escape** (`restore_maximised`) restores the pane. It only acts while a pane is maximised.
  - Config keys: `pane_overlay_maximise`, `pane_animation_expand_ms`, `pane_animation_restore_ms`, `reduce_motion`.
- **Automatic per-terminal font scaling.**
  - Small panes step down through 100% / 90% / 80% based on a 60-column reading measure (width first, then a minimum of 8 rows). A pane taking at least 45% of its window or tab (either pane of any two-pane split) always stays at 100%.
  - A titlebar badge shows the current scale and lets you lock the font size for a terminal.
  - Config keys: `auto_font_scale*`, `reading_measure_*`.
- **Hide the scrollbar in fullscreen programs.** While a program uses the alternate screen (vim, less, htop, tmux) the scrollbar is hidden and that width goes to the terminal. Config key: `scrollbar_hide_in_alt_screen`.
- **The window title follows the focused pane.** Title changes from other panes no longer overwrite the window title. Config keys: `window_title_mode` (`focused`/`fixed`) and `window_title_fixed`.

**Behaviour changes when upgrading**

- **Name.** The desktop entry, the about page and the default window title say TerminatorX. The command is still `terminator`.
- **Default layout.** If you have a custom `[layouts][default]`, it is used only until the first session is saved. After that, a plain launch restores the last session. Use `--no-restore`, or set `restore_last_session = False`, to keep using the default layout.
- **Tabs are one-time unless locked.** Each tab row has a lock (also "Keep for next launch" in the tab menu). A normal exit restores locked tabs only. Unlocked tabs are forgotten, and the next launch is one new window. It does not fall back to `[layouts][default]`. A kill or a crash still restores every tab that was open. A window with no tab list is still restored.
- **Shortcut clash.** `<Ctrl><Shift>Return` is now bound to `maximise`. If you or a plugin used that key for something else, rebind one of them in Preferences > Keybindings.
- **Empty scrollback is not replayed.** A cached pane that contains only a shell prompt (and earlier "previous session" separator lines) is not fed back on restore, so the separator is not shown when there was no output.
- **Terminal colours.** The default profile is the built-in Deep teal scheme: foreground `#c6d3d5`, background `#163841`, Tango palette. Profiles that never set these follow the new default. To keep the old look, set `foreground_color = "#aaaaaa"`, `background_color = "#000000"` and the previous palette (first colour `#2e3436`).
- **Titlebar colours.** Pane titlebars use a white background, the same ground as the window header:
  - Focused: `#1d1d1f` on `#ffffff`.
  - Unfocused: `#6e6e73` on `#ffffff`.
  - Profiles that never changed these keep following the defaults. To get the old red/grey look back, set `title_transmit_fg_color = "#ffffff"`, `title_transmit_bg_color = "#c80003"`, `title_inactive_fg_color = "#000000"` and `title_inactive_bg_color = "#c0bebf"`.
- **Pane titlebar buttons.** The bar is the original height: 24px, or 20px when `titlebar_density` is compact. The gear, maximise and close marks are scaled to one ink size inside those buttons so they line up.
- **Pane titlebar icons and Grouping menu.** The extra terminal icon at the left of each pane titlebar is hidden by default (`titlebar_show_icon = False`). The grouping icon stays, and the pane title is drawn immediately to its right. Titlebar colours are applied with CSS so that title stays readable when the theme ignores the older colour overrides. Grouping is on that icon, on the titlebar right-click and on the gear menu. Set `titlebar_show_icon = True` (Preferences > Panes) to also show the terminal icon; the Grouping submenu then disappears again, as upstream.
- **Focus border only with multiple panes.** The outline is drawn on the focused pane only while another pane is visible. A single pane has no outline. With several panes, only the focused one keeps the outline; the others are cleared. The outline is painted on top of the pane, so unfocused panes do not keep a black frame. Its colour is that pane's titlebar background (`title_transmit_bg_color`, white by default), not `pane_accent_color`. `pane_accent_color` still colours an overlay-maximised pane.
- **Startup.** Setting the window title no longer loops with the header bar. A launch used to sit there and never open a window.
- **Window header bar visibility.** The header bar is shown with the window. `Gtk.Window.show()` was leaving it unmapped, so a maximised window opened with the terminal flush to the top and no action bar.
- **Window header bar.** The window uses a client-side title bar like GNOME Terminal: a sidebar-icon toggle that shows or hides the tab list, find, and the terminal menu, with the theme's own minimise, maximise and close buttons. The toggle stays down while the list is open. The bar is white (`window_decoration_style = light`). The line before the traffic lights is the same white; it used to pick up the dark pane-split colour. The drop shadow is the compositor's, the same one around Ubuntu's terminal; it is not painted inside the window, and it is absent while maximised. `borderless = True` keeps the old undecorated window.
- **Thin pane split.** The divider between panes is a flat 1px line. It used to be a grooved gutter about 5px wide. `handle_size` still sets that width (0–20).
- **Pane titlebar only when split.** A single pane has no pane titlebar. Splitting shows one on each pane; closing back to one pane hides it again. The window header's menu button still opens the full terminal menu. `show_titlebar = False` still hides the pane titlebar always.
- **Scrollbar only when it can move.** The default side is still the right, but the bar stays hidden until the scrollback is taller than the terminal. Choosing "Hidden" in Preferences still turns it off entirely. A manual "Show scrollbar" toggle (Ctrl+Shift+S) sticks for that terminal until preferences are applied again.
- **Tabs.** Tabs are a tree on the left (`tab_position = left`), and that list fills the window height. Each tab is one row, named from that tab's focused pane's directory unless you renamed it. When the tab is split, each pane is a child under that row, named from its own directory. Above the tree, a plus opens a new tab and the arrows move back and forward. The plus and the arrows sit in 24px buttons, the same box as a pane titlebar button. Back and forward do not wrap. Set `tab_position = top` for the dark chip strip instead. The close mark on the current tab row is the same height as the row text. Drag a tab to reorder it or onto another tab to nest it. Drag a child pane to reorder it, move it into another tab, or pull it out into its own tab. A tab can also be dragged onto another window's list; the window closes when its last tab leaves. Detaching a tab into a new window leaves the tab list open on both windows.
- **Tab context menu.** Right-clicking a tab offers move left, move right, detach into a new window and close. The end tabs cannot move further, and the only tab cannot be detached. Right-clicking a child pane offers move up, move down, detach into its own tab, and close. The first child cannot move up, and the last cannot move down. Middle-click still closes the tab.
- **Find dialog.** Ctrl+Shift+F opens a Find window: match case, whole word, regular expression, and wrap around. The text is matched literally unless regular expression is checked. Match case now defaults to off.
- **Shorter terminal menu.** Right-clicking the terminal keeps copy, paste, horizontal/vertical split, new tab, close and maximise. Window title, edit title, auto-split, detach tab, zoom, read-only, scrollbar, font lock, preferences, colours, profiles, layouts and grouping are on the window header's menu button, the pane titlebar's right-click and the gear. A borderless window with no pane titlebar still puts those items on the terminal menu.
- **Config saving.** The config file is now written atomically: a temporary file is written and then renamed over the original. Symlinks and file permissions are preserved.

**Fixes**

- Splitting or closing a terminal inside a tab no longer crashes. This bug was also present upstream.
- The `maximise` shortcut no longer raises an error.
- Fixed the window title showing "None" at startup.
- Missing GNOME gsettings schemas no longer abort startup.
- **Wayland.** The backend is detected from the display GTK actually opened, so XWayland (`GDK_BACKEND=x11`) still gets the X11 features.
  - On native Wayland the window position is neither saved nor restored, because the compositor places windows. Size, maximised/fullscreen state, layout and the maximised pane are still restored.
  - On X11, a restored window whose saved position misses every connected monitor is moved onto the primary monitor's work area and shrunk to fit. A maximised or fullscreen window is moved there without shrinking, and the window manager applies that state.
  - Without a global hotkey, hide-on-lose-focus and the hide toggle minimise the window instead of hiding it beyond reach. The toggle brings it back.
  - Shells no longer inherit a stale `WINDOWID` on Wayland.
  - Upstream bug: `WINDOWID` was never set on X11, and the "minimise instead" fallback for a taken hide hotkey was overwritten. Both are fixed.
- **HiDPI.**
  - Background images are drawn at native resolution under `GDK_SCALE=2`, so they are no longer upscaled and blurry.
  - The narrow-titlebar collapse widths grow with the text size (`GDK_DPI_SCALE`, Xft.dpi, a large UI font).
- **Mouse wheel.** Ctrl zoom and Shift page-scroll require the whole modifier mask. Ctrl+Shift+Super scrolls every terminal. Turning mouse-wheel zoom off leaves the wheel alone.
- **Shell start.** A Flatpak shell that fails to start is reported once. Closing a terminal only signals a real process id.
- **Drag and drop.** A multi-line URI list pastes the first line only.
- **Background image.** Leaving image mode disconnects the draw handler.
- **Copy address.** The menu copies the prepared URL.
- **Close confirmation.** With `ask_before_closing = always`, several idle shells ask once. `flatpak-spawn` itself does not count as a running program. A group close that cannot show its dialog leaves the terminals open.
- **Splits.** A saved ratio is applied after the pane has a size. Collapsing an inner split keeps the outer pane order. Closing a pane when the window has no last-focused terminal no longer raises.
- **Overlay maximise.** Restoring a pane puts it back in the slot it left. A session-marked pane still maximises once the window is mapped, including when the terminal was not in the window on the first attempt. The placeholder ghost follows the slot when that slot changes size. Resizing the window during the expand animation leaves the automatic font size on the final pane size.
- **Window blur.** The blur hint follows the focused terminal.
- **remotinator.** `new_tab -x` runs that command in the new tab. Set-tab-title updates the page that holds the terminal. A D-Bus string prints as one line. A remote new window or new tab puts the process command line back afterwards.
- **Alternate screen.** Leaving the inactive fast path ends that scrollbar episode.
- **Titles and Find.** Confirming a title without changing the text does not lock a custom title. Reopening Find keeps the previous pattern, and a non-ASCII regular expression is compiled in full. The bell icon does not stack timers.
- **Preferences.** A missing layout name falls back to `default`. Keybinding search filters on the whole string as it is typed. Loading a profile does not paint the previous profile's colours onto it. Cancelling a colour dialog restores the colours that were open. Renaming a profile or layout onto a reserved or existing name is refused. The `default` profile cannot be deleted.
- **Config.** `cell_width` and `cell_height` stay global. A plugin setting writes only that plugin's tree. `--debug-classes` or `--debug-methods` without `-d` starts.
- **Debug console.** The debug server listens on a private user socket, and a debug terminal connects to that socket.
- **Startup.** An empty layout opens one window. A bad window size is skipped and the rest of that window is still created. A layout error does not open a second window when one was already created. If the layout launcher cannot find its interface file, it exits only when no other window is open.
- **Session.** A rotated or unreadable previous-session file is set aside, and a good `session.json` is kept. Restoring the previous session suspends later writes only after the replacement file is on disk. Layout nodes whose parent is missing are dropped.
- **Scrollback cache.** A failed write stays dirty and is retried. Closing a terminal still flushes once while the error cooldown is active. Line trimming keeps the tail of the text. VTE before 0.72 has no HTML export; the cache reads each cell's colour from `get_text_range` and replays it, so a restored session keeps palette colours. Bold is not available from that API.
- **Preferences.** Reconfiguring skips a terminal whose titlebar has already been destroyed, so opening preferences does not crash on that leftover.

- **Plugins.** The logger writes the whole captured block. Docker `exec` and `attach` lines with no container name no longer print a usage error every second. Custom Commands reads the last shell command without blocking the terminal. Auto Theme applies the saved theme once, and cancelling its dialog restores the previous profiles.

**Translations and docs**

- Simplified Chinese (zh_CN) translations for all new strings.
- `terminator.pot` regenerated.
- Man pages updated.

## [v2.1.6](https://github.com/gnome-terminator/terminator/tree/v2.1.6) (2026-09-05)

[Full Changelog](https://github.com/gnome-terminator/terminator/compare/v2.1.5...v2.1.6)

**Implemented enhancements:**

- New Tab Opens Next to Current Tab [\#990](https://github.com/gnome-terminator/terminator/issues/990)

**Closed issues:**

- Select-by-word characters to select part of content preference does not work \(adding "="\) [\#1085](https://github.com/gnome-terminator/terminator/issues/1085)
- Add command history search across all terminal panes [\#1064](https://github.com/gnome-terminator/terminator/issues/1064)
- session manager to save/restore terminal layouts and working directories [\#1063](https://github.com/gnome-terminator/terminator/issues/1063)
- feat: add session autosave and crash recovery [\#1061](https://github.com/gnome-terminator/terminator/issues/1061)
- session save and restore support [\#1060](https://github.com/gnome-terminator/terminator/issues/1060)
- Add session save/restore functionality [\#1059](https://github.com/gnome-terminator/terminator/issues/1059)
- feat: Add command palette for quick actions and settings access [\#1058](https://github.com/gnome-terminator/terminator/issues/1058)
- feat: Session snapshot and restore with automatic recovery [\#1053](https://github.com/gnome-terminator/terminator/issues/1053)
- Drag and drop file to get path does not work [\#1051](https://github.com/gnome-terminator/terminator/issues/1051)
- Follow up on terminator 2.1.4 cannot split pane \(Ubuntu 25.10 shipped version\): g\_convert\_error: The hostname of the URI is invalid \(4\) [\#1048](https://github.com/gnome-terminator/terminator/issues/1048)
- remote plugin doesn't work well in zh\_CN [\#1043](https://github.com/gnome-terminator/terminator/issues/1043)
- GPG Key missing for the 2.1.5 release [\#1042](https://github.com/gnome-terminator/terminator/issues/1042)
- Crash report \(non-fatal\) when searching for invalid regex phrase [\#1038](https://github.com/gnome-terminator/terminator/issues/1038)
- Syslog error message on popup menu [\#1031](https://github.com/gnome-terminator/terminator/issues/1031)
- terminator 2.1.4 cannot split pane \(Ubuntu 25.10 shipped version\): g\_convert\_error: The hostname of the URI is invalid \(4\) [\#1024](https://github.com/gnome-terminator/terminator/issues/1024)
- Add AI support/features [\#1019](https://github.com/gnome-terminator/terminator/issues/1019)
- Auto-Arrange Panes Like Tmux \(Ctrl-B Space Equivalent\) [\#1011](https://github.com/gnome-terminator/terminator/issues/1011)
- Terminator 2.1.3 segfault when displaying binary data [\#1010](https://github.com/gnome-terminator/terminator/issues/1010)
- The Terminator window doesn’t split horizontally or vertically, nor does it create new tabs. [\#1005](https://github.com/gnome-terminator/terminator/issues/1005)
- Disabling window borders does not work [\#999](https://github.com/gnome-terminator/terminator/issues/999)
- French translation improvement [\#992](https://github.com/gnome-terminator/terminator/issues/992)
- copy\_on\_selection does not copy to primary, messing up middle-button paste [\#980](https://github.com/gnome-terminator/terminator/issues/980)
- KeyError when a single window layout is selected after selecting a multiple tab layouts second terminal [\#973](https://github.com/gnome-terminator/terminator/issues/973)
- Tiling commands broken [\#953](https://github.com/gnome-terminator/terminator/issues/953)
- Fix the Save button behavior for Layouts [\#949](https://github.com/gnome-terminator/terminator/issues/949)
- Alt+1 Alt+2 ... custom shortcuts don't work \(for switching tabs\) [\#945](https://github.com/gnome-terminator/terminator/issues/945)
- configurable terminal tab background color and font size [\#940](https://github.com/gnome-terminator/terminator/issues/940)
- using new\_tab\_cmd and hsplit,vsplit from terminatorlib causes an error. [\#938](https://github.com/gnome-terminator/terminator/issues/938)
- Pressing CTRL+SHIFT clears current selected, SHIFT+CTRL doesnt, issue with MouseFreeURLHandler [\#932](https://github.com/gnome-terminator/terminator/issues/932)
- Custom the width of tab to 4 or 2 spaces [\#931](https://github.com/gnome-terminator/terminator/issues/931)
- change color of active pane [\#929](https://github.com/gnome-terminator/terminator/issues/929)
- New feature: Switch tabs while maximized [\#921](https://github.com/gnome-terminator/terminator/issues/921)
- Titlebar is lost when moving a terminal [\#914](https://github.com/gnome-terminator/terminator/issues/914)
- buggy client sending inaccurate timestamps in messages such as \_NET\_ACTIVE\_WINDOW [\#911](https://github.com/gnome-terminator/terminator/issues/911)
- --config-json not working [\#864](https://github.com/gnome-terminator/terminator/issues/864)
- The title of the "save" button in Preferences \> Layouts is misleading [\#858](https://github.com/gnome-terminator/terminator/issues/858)
- Plugin MouseFreeURLHandler fails to extract text and clear search between commands [\#846](https://github.com/gnome-terminator/terminator/issues/846)
- \[Plugin SaveLastSessionLayout\] not saving layout when user logs out or shutdown or restart [\#843](https://github.com/gnome-terminator/terminator/issues/843)
- toggle-visibility option is opening a new window everytime, even if Terminator is running [\#827](https://github.com/gnome-terminator/terminator/issues/827)
- Terminator prints raw \(user input\) root password while connected with sudo executing Terminator with `broadcast all` flag [\#744](https://github.com/gnome-terminator/terminator/issues/744)
- Update install method for Ubuntu [\#699](https://github.com/gnome-terminator/terminator/issues/699)
- Title field not seem to be working with JSON profile [\#676](https://github.com/gnome-terminator/terminator/issues/676)
- RFE - https://github.com/dequis/tmux-url-select [\#675](https://github.com/gnome-terminator/terminator/issues/675)
- Multi-byte emojis are not displayed correctly [\#672](https://github.com/gnome-terminator/terminator/issues/672)
- Seems to be ignoring some settings, including layout-based custom commands [\#643](https://github.com/gnome-terminator/terminator/issues/643)
- Window size in settings.  [\#641](https://github.com/gnome-terminator/terminator/issues/641)
- Clipboard COPY function does not work after a couple of weeks [\#611](https://github.com/gnome-terminator/terminator/issues/611)

**Merged pull requests:**

- Prevent background terminals from flickering the window title [\#1105](https://github.com/gnome-terminator/terminator/pull/1105) ([ret2basic](https://github.com/ret2basic))
- Add window decoration style setting \(Dark/Light/Auto\) [\#1098](https://github.com/gnome-terminator/terminator/pull/1098) ([RedLeavesSun](https://github.com/RedLeavesSun))
- more keyboard fixes for macos [\#1097](https://github.com/gnome-terminator/terminator/pull/1097) ([mattrose](https://github.com/mattrose))
- Add mod4 key binding to keybindings.py [\#1095](https://github.com/gnome-terminator/terminator/pull/1095) ([remijouannet](https://github.com/remijouannet))
- fix macos keybinding [\#1093](https://github.com/gnome-terminator/terminator/pull/1093) ([mattrose](https://github.com/mattrose))
- tests: fix accelerator\_parse hash mismatch on Python 3.14 [\#1092](https://github.com/gnome-terminator/terminator/pull/1092) ([blshkv](https://github.com/blshkv))
- Fix SIGHUP/PTY race in Terminal.close\(\) that loses bash history [\#1090](https://github.com/gnome-terminator/terminator/pull/1090) ([kristofszeles](https://github.com/kristofszeles))
- revert PR 1075 [\#1087](https://github.com/gnome-terminator/terminator/pull/1087) ([mattrose](https://github.com/mattrose))
- add meta key [\#1086](https://github.com/gnome-terminator/terminator/pull/1086) ([mattrose](https://github.com/mattrose))
- Add new keybinding action - Shift+Enter = new line [\#1084](https://github.com/gnome-terminator/terminator/pull/1084) ([mattrose](https://github.com/mattrose))
- Adds custom color selection and theme presets [\#1080](https://github.com/gnome-terminator/terminator/pull/1080) ([vvbv](https://github.com/vvbv))
- Add plugin to resolve commit hashes to URLs [\#1075](https://github.com/gnome-terminator/terminator/pull/1075) ([Duranzed](https://github.com/Duranzed))
- Pass terminal to URLHandler plugins [\#1074](https://github.com/gnome-terminator/terminator/pull/1074) ([bangbangsheshotmedown](https://github.com/bangbangsheshotmedown))
- Fix keypress focus check for non-window toplevels [\#1073](https://github.com/gnome-terminator/terminator/pull/1073) ([antomicx](https://github.com/antomicx))
- Background blur [\#1071](https://github.com/gnome-terminator/terminator/pull/1071) ([Sotilrac](https://github.com/Sotilrac))
- fix: remove unused GObject and Gtk imports with legacy aliases [\#1057](https://github.com/gnome-terminator/terminator/pull/1057) ([dmzoneill](https://github.com/dmzoneill))
- fix: handle both string and bytes in feed method for drag-and-drop [\#1055](https://github.com/gnome-terminator/terminator/pull/1055) ([dmzoneill](https://github.com/dmzoneill))
- fix: handle invalid regex gracefully in search [\#1054](https://github.com/gnome-terminator/terminator/pull/1054) ([dmzoneill](https://github.com/dmzoneill))
- Fix incompatibility issues between remote plugins and localization modules [\#1044](https://github.com/gnome-terminator/terminator/pull/1044) ([dylanorz](https://github.com/dylanorz))
- Update TRANSLATION.md [\#1033](https://github.com/gnome-terminator/terminator/pull/1033) ([hugok79](https://github.com/hugok79))
- fix: Use Menlo as default mono font on macOS [\#1028](https://github.com/gnome-terminator/terminator/pull/1028) ([JAugusto42](https://github.com/JAugusto42))
- add Add Auto Theme Plugin [\#1017](https://github.com/gnome-terminator/terminator/pull/1017) ([mattrose](https://github.com/mattrose))
- Bug \#904 Decouple the copy/paste from PRIMARY or Clipboard  [\#1016](https://github.com/gnome-terminator/terminator/pull/1016) ([mattrose](https://github.com/mattrose))
- fix ci [\#1009](https://github.com/gnome-terminator/terminator/pull/1009) ([mattrose](https://github.com/mattrose))
- Tmux-like navigation feature [\#1002](https://github.com/gnome-terminator/terminator/pull/1002) ([siamak-amo](https://github.com/siamak-amo))
- Updates for file po/terminator.pot in hu [\#994](https://github.com/gnome-terminator/terminator/pull/994) ([transifex-integration[bot]](https://github.com/apps/transifex-integration))
- Updates for file po/terminator.pot in fr [\#991](https://github.com/gnome-terminator/terminator/pull/991) ([transifex-integration[bot]](https://github.com/apps/transifex-integration))



\* *This Changelog was automatically generated by [github_changelog_generator](https://github.com/github-changelog-generator/github-changelog-generator)*
