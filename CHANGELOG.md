# Changelog

## 2.1.6+fork.1 (unreleased): fork of 2.1.6 (TIIEHenry/terminator, branch integration/m1)

The five new features below are **on by default**. Each one can be turned off in Preferences or in the config file (see `terminator_config(5)`).

**New features**

- **Session save and restore.** Windows, tabs, splits, working directories, the maximised pane and any manually set window title are saved automatically (debounced) while Terminator runs. A plain `terminator` launch restores them.
  - New options `--restore`, `--no-restore` and `--clear-session`.
  - New Preferences > Session page with "Save as layout", "Use previous session next time" and "Clear session and cache…".
  - Config keys: `restore_last_session`, `session_save_delay_ms`, `session_file`.
  - The session is stored in `$XDG_STATE_HOME/terminator/session.json`.
- **Close confirmation for running processes.** Closing a terminal, tab or window asks for confirmation when programs other than shells are still running. Config key: `close_confirm_ignore`.
- **Scrollback cache.** The last lines of each terminal, with colours, are cached in `~/.cache/terminator/scrollback/` and replayed after a session restore. The screens of fullscreen programs are never cached. Config keys: `scrollback_cache*`.
- **Wave-style pane titlebars.**
  - Dark titlebars with a gear menu, maximise/restore and close buttons. Right-click opens the terminal menu.
  - A 1px accent border marks the focused pane.
  - Config keys: `titlebar_buttons`, `titlebar_density`, `pane_accent_color`.
  - Double-clicking a titlebar now maximises the pane. Renaming moved to the menu and to Ctrl+Alt+X.
- **Overlay maximise.**
  - A single pane is maximised as an animated overlay above the dimmed layout.
  - New default shortcut **Ctrl+Shift+Return** for `maximise`, which upstream left unbound. Ctrl+Shift+X does the same.
  - New shortcut **Shift+Escape** (`restore_maximised`) restores the pane. It only acts while a pane is maximised.
  - Config keys: `pane_overlay_maximise`, `pane_animation_expand_ms`, `pane_animation_restore_ms`, `reduce_motion`.
- **Automatic per-terminal font scaling.**
  - Small panes step down through 100% / 90% / 80% based on a 60-column reading measure (width first, then a minimum of 8 rows). A pane taking at least 45% of its window or tab (either pane of any two-pane split) always stays at 100%.
  - A titlebar badge shows the current scale and lets you lock the font size for a terminal.
  - Config keys: `auto_font_scale*`, `reading_measure_*`.
- **Hide the scrollbar in fullscreen programs.** While a program uses the alternate screen (vim, less, htop, tmux) the scrollbar is hidden. Config key: `scrollbar_hide_in_alt_screen`.
- **The window title follows the focused pane.** Title changes from other panes no longer overwrite the window title. Config keys: `window_title_mode` (`focused`/`fixed`) and `window_title_fixed`.

**Behaviour changes when upgrading**

- **Default layout.** If you have a custom `[layouts][default]`, it is used only until the first session is saved. After that, a plain launch restores the last session. Use `--no-restore`, or set `restore_last_session = False`, to keep using the default layout.
- **Shortcut clash.** `<Ctrl><Shift>Return` is now bound to `maximise`. If you or a plugin used that key for something else, rebind one of them in Preferences > Keybindings.
- **Titlebar colours.** The default titlebar colours changed from red/grey to dark:
  - Focused: `#e6edf3` on `#21262d`.
  - Unfocused: `#8b949e` on `#161b22`.
  - Profiles that never changed these keep following the defaults. To get the old look back, set `title_transmit_fg_color = "#ffffff"`, `title_transmit_bg_color = "#c80003"`, `title_inactive_fg_color = "#000000"` and `title_inactive_bg_color = "#c0bebf"`.
- **Pane titlebar icons and Grouping menu.** The terminal icon and the grouping/broadcast icon at the left of each pane titlebar are now hidden by default (`titlebar_show_icon = False`). Because that icon was the usual way into grouping, the terminal right-click menu now shows a **Grouping** submenu by default. The group name and a "Broadcast: all/group" text stay clickable, and the group keybindings are unchanged. Set `titlebar_show_icon = True` (Preferences > Panes) to get the icons back; the right-click Grouping submenu then disappears again, as upstream.
- **Config saving.** The config file is now written atomically: a temporary file is written and then renamed over the original. Symlinks and file permissions are preserved.

**Fixes**

- Splitting or closing a terminal inside a tab no longer crashes. This bug was also present upstream.
- The `maximise` shortcut no longer raises an error.
- Fixed the window title showing "None" at startup.
- Missing GNOME gsettings schemas no longer abort startup.
- **Wayland.** The backend is detected from the display GTK actually opened, so XWayland (`GDK_BACKEND=x11`) still gets the X11 features.
  - On native Wayland the window position is neither saved nor restored, because the compositor places windows. Size, maximised/fullscreen state, layout and the maximised pane are still restored.
  - Without a global hotkey, hide-on-lose-focus and the hide toggle minimise the window instead of hiding it beyond reach. The toggle brings it back.
  - Shells no longer inherit a stale `WINDOWID` on Wayland.
  - Upstream bug: `WINDOWID` was never set on X11, and the "minimise instead" fallback for a taken hide hotkey was overwritten. Both are fixed.
- **HiDPI.**
  - Background images are drawn at native resolution under `GDK_SCALE=2`, so they are no longer upscaled and blurry.
  - The narrow-titlebar collapse widths grow with the text size (`GDK_DPI_SCALE`, Xft.dpi, a large UI font).

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
