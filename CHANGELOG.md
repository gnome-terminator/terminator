# Changelog

## [v2.1.0](https://github.com/gnome-terminator/terminator/tree/v2.1.0) (2021-01-04)

[Full Changelog](https://github.com/gnome-terminator/terminator/compare/v2.0.1...v2.1.0)

**Package Maintainers**

- We have changed the tarball format, and it should now include all the files in the tarball, rather than just a subset.  See [\#348](https://github.com/gnome-terminator/terminator/issues/348)

**Implemented enhancements:**

- Add bigger icon sizes [\#258](https://github.com/gnome-terminator/terminator/issues/258)
- Smart Copy option to clear selection after copy [\#242](https://github.com/gnome-terminator/terminator/issues/242)
- New feature: A Separate Json file for dynamic Layouts [\#213](https://github.com/gnome-terminator/terminator/issues/213)
- new feature: support for term://1.2.3.4/ 'links' that when clicked open a new terminator ssh'ed to 1.2.3.4. [\#178](https://github.com/gnome-terminator/terminator/issues/178)
- Reimplement "unfocused dim" using overpainting [\#74](https://github.com/gnome-terminator/terminator/issues/74)
- Add Transifex integration and documentation for translations [\#352](https://github.com/gnome-terminator/terminator/pull/352) ([lazyfrosch](https://github.com/lazyfrosch))

**Fixed bugs:**

- No \(visible\) context menu in sway [\#330](https://github.com/gnome-terminator/terminator/issues/330)
- Saving a layout after changing it, it correctly updates the config file but does not update the UI [\#319](https://github.com/gnome-terminator/terminator/issues/319)

**Closed issues:**

- Rethinking release artifacts [\#348](https://github.com/gnome-terminator/terminator/issues/348)
- The Alt+L layout chooser is too small [\#345](https://github.com/gnome-terminator/terminator/issues/345)
- Open in Previous Location [\#337](https://github.com/gnome-terminator/terminator/issues/337)
- Improve separator between splitted terminals [\#329](https://github.com/gnome-terminator/terminator/issues/329)
- Using shift+Super+} for next\_tab key binding doesn't work [\#326](https://github.com/gnome-terminator/terminator/issues/326)
- "Copy email address" actually doesn't quite do that [\#323](https://github.com/gnome-terminator/terminator/issues/323)
- Can't disable key binding [\#322](https://github.com/gnome-terminator/terminator/issues/322)
- Middle click does not paste selected text [\#320](https://github.com/gnome-terminator/terminator/issues/320)
- Terminator does not read config file from /etc/xdg directory  [\#308](https://github.com/gnome-terminator/terminator/issues/308)
- Add a 'clear terminal' function [\#306](https://github.com/gnome-terminator/terminator/issues/306)
- terminator-2.0.1: vertical separator too big [\#305](https://github.com/gnome-terminator/terminator/issues/305)
- rewrap\_on\_resize is deprecated in vte-0.60.0 [\#303](https://github.com/gnome-terminator/terminator/issues/303)
- Geometry ignored [\#297](https://github.com/gnome-terminator/terminator/issues/297)
- hangs after update [\#292](https://github.com/gnome-terminator/terminator/issues/292)
- Unable to Set "Image" as Background [\#285](https://github.com/gnome-terminator/terminator/issues/285)
- module 'command\_notify' has no attribute 'AVAILABLE' [\#264](https://github.com/gnome-terminator/terminator/issues/264)
- symlinked config replaced with regular file [\#234](https://github.com/gnome-terminator/terminator/issues/234)
- Cannot "Drag and Drop" Folders or Files [\#159](https://github.com/gnome-terminator/terminator/issues/159)

**Merged pull requests:**

- Update RELEASE docs [\#353](https://github.com/gnome-terminator/terminator/pull/353) ([lazyfrosch](https://github.com/lazyfrosch))
- German language updated [\#351](https://github.com/gnome-terminator/terminator/pull/351) ([Brambleberry4](https://github.com/Brambleberry4))
- Update terminator.appdata.xml.in [\#350](https://github.com/gnome-terminator/terminator/pull/350) ([jooola](https://github.com/jooola))
- Fix \#345 The Alt+L layout chooser is too small [\#349](https://github.com/gnome-terminator/terminator/pull/349) ([evandrocoan](https://github.com/evandrocoan))
- fix 319: refresh layout after save [\#344](https://github.com/gnome-terminator/terminator/pull/344) ([mattrose](https://github.com/mattrose))
- feat: refactoring terminal file [\#343](https://github.com/gnome-terminator/terminator/pull/343) ([JAugusto42](https://github.com/JAugusto42))
- Local user install: terminator.desktop and terminator.metainfo.xml [\#342](https://github.com/gnome-terminator/terminator/pull/342) ([zothar](https://github.com/zothar))
- update to non-deprecated Gtk.Menu popup call [\#341](https://github.com/gnome-terminator/terminator/pull/341) ([mattrose](https://github.com/mattrose))
- feat: Migrating from hbox to GtkBox [\#340](https://github.com/gnome-terminator/terminator/pull/340) ([JAugusto42](https://github.com/JAugusto42))
- remove rewrap on resize from option and remove functions too [\#339](https://github.com/gnome-terminator/terminator/pull/339) ([JAugusto42](https://github.com/JAugusto42))
- fix: \#323 [\#338](https://github.com/gnome-terminator/terminator/pull/338) ([JAugusto42](https://github.com/JAugusto42))
- Revert pr36 [\#336](https://github.com/gnome-terminator/terminator/pull/336) ([mattrose](https://github.com/mattrose))
- Feature: Relaunch command option on held open after child exit [\#333](https://github.com/gnome-terminator/terminator/pull/333) ([zothar](https://github.com/zothar))
- add note aboug moving config file out of the way [\#328](https://github.com/gnome-terminator/terminator/pull/328) ([mattrose](https://github.com/mattrose))
- issue 271: add keybindings to zoom all terminals at once [\#314](https://github.com/gnome-terminator/terminator/pull/314) ([mattrose](https://github.com/mattrose))
- load config from XDG\_CONFIG\_DIRS if user config file doesn't exist [\#310](https://github.com/gnome-terminator/terminator/pull/310) ([mattrose](https://github.com/mattrose))
- Update README with install instructions [\#309](https://github.com/gnome-terminator/terminator/pull/309) ([tomeksabala](https://github.com/tomeksabala))
- add a commandline flag to unhide any windows [\#307](https://github.com/gnome-terminator/terminator/pull/307) ([mattrose](https://github.com/mattrose))
- fix background image profile preferences ui [\#296](https://github.com/gnome-terminator/terminator/pull/296) ([mattrose](https://github.com/mattrose))
- Minor fixes [\#295](https://github.com/gnome-terminator/terminator/pull/295) ([strottie](https://github.com/strottie))
- fix issue with older vte lib [\#294](https://github.com/gnome-terminator/terminator/pull/294) ([mattrose](https://github.com/mattrose))
- replace feed\_child\_binary\(\) calls with feed\_child\(\) [\#291](https://github.com/gnome-terminator/terminator/pull/291) ([mattrose](https://github.com/mattrose))
- Update German and Croatian [\#287](https://github.com/gnome-terminator/terminator/pull/287) ([milotype](https://github.com/milotype))
- fix issue \#74 [\#286](https://github.com/gnome-terminator/terminator/pull/286) ([mattrose](https://github.com/mattrose))
- support for SSH URIs [\#280](https://github.com/gnome-terminator/terminator/pull/280) ([mattrose](https://github.com/mattrose))
- add bigger icon sizes [\#279](https://github.com/gnome-terminator/terminator/pull/279) ([mattrose](https://github.com/mattrose))
- fix stupid debugging error [\#278](https://github.com/gnome-terminator/terminator/pull/278) ([mattrose](https://github.com/mattrose))
- multiple small documentation fixes [\#277](https://github.com/gnome-terminator/terminator/pull/277) ([mattrose](https://github.com/mattrose))
- fix drag and drop issues on KDE [\#275](https://github.com/gnome-terminator/terminator/pull/275) ([mattrose](https://github.com/mattrose))
- pass original working directory to dbus\_options as well [\#270](https://github.com/gnome-terminator/terminator/pull/270) ([mattrose](https://github.com/mattrose))
- fix new upstream vte warning [\#267](https://github.com/gnome-terminator/terminator/pull/267) ([mattrose](https://github.com/mattrose))
- suppress warning if the vte capability is not there [\#266](https://github.com/gnome-terminator/terminator/pull/266) ([mattrose](https://github.com/mattrose))
- remove workaround for https://github.com/ibus/ibus/issues/1802 [\#265](https://github.com/gnome-terminator/terminator/pull/265) ([mattrose](https://github.com/mattrose))
- Add support for inverted search [\#257](https://github.com/gnome-terminator/terminator/pull/257) ([yoavp77](https://github.com/yoavp77))
- update translations [\#255](https://github.com/gnome-terminator/terminator/pull/255) ([mattrose](https://github.com/mattrose))
- Clear selection on smart copy [\#254](https://github.com/gnome-terminator/terminator/pull/254) ([mattrose](https://github.com/mattrose))
- Polish translation update [\#252](https://github.com/gnome-terminator/terminator/pull/252) ([napcok](https://github.com/napcok))
- update terminator.pot [\#251](https://github.com/gnome-terminator/terminator/pull/251) ([napcok](https://github.com/napcok))
- Polish translation update [\#248](https://github.com/gnome-terminator/terminator/pull/248) ([napcok](https://github.com/napcok))
- fix the handle on the divider between horizontal panes [\#247](https://github.com/gnome-terminator/terminator/pull/247) ([mattrose](https://github.com/mattrose))
- add tests to release tarball [\#246](https://github.com/gnome-terminator/terminator/pull/246) ([mattrose](https://github.com/mattrose))
- Change how config file is saved [\#235](https://github.com/gnome-terminator/terminator/pull/235) ([planet36](https://github.com/planet36))
- Updated Estonian translation [\#226](https://github.com/gnome-terminator/terminator/pull/226) ([ookull](https://github.com/ookull))
- Fix: Key Binding Clearing in `Preferences \> Keybindings` [\#224](https://github.com/gnome-terminator/terminator/pull/224) ([dkmvs](https://github.com/dkmvs))
- layout file - initial commit - work in progress [\#214](https://github.com/gnome-terminator/terminator/pull/214) ([dvdlevanon](https://github.com/dvdlevanon))
- fast resize keyboard shortcuts [\#36](https://github.com/gnome-terminator/terminator/pull/36) ([waldner](https://github.com/waldner))

## [v2.0.1](https://github.com/gnome-terminator/terminator/tree/v2.0.1) (2020-10-11)

[Full Changelog](https://github.com/gnome-terminator/terminator/compare/v2.0...v2.0.1)

TODO

## Package maintainers



**Fixed bugs:**

- config settings lost when I cancel "Close multiple terminals" dialog [\#210](https://github.com/gnome-terminator/terminator/issues/210)

**Closed issues:**

- Feature Suggestion: Splitted screen shells based on parent [\#230](https://github.com/gnome-terminator/terminator/issues/230)
- Release 2.0 does not have signed assets [\#228](https://github.com/gnome-terminator/terminator/issues/228)
- Some files install to the wrong location [\#227](https://github.com/gnome-terminator/terminator/issues/227)
- Multi tab breaks transparent background [\#225](https://github.com/gnome-terminator/terminator/issues/225)

**Merged pull requests:**

- Preserve searchbar case sensitivity state in config file on state change [\#249](https://github.com/gnome-terminator/terminator/pull/249) ([yoavp77](https://github.com/yoavp77))
- make sure data/\*.in files are there for distributors [\#237](https://github.com/gnome-terminator/terminator/pull/237) ([mattrose](https://github.com/mattrose))
- only set clear background when background\_image in config [\#233](https://github.com/gnome-terminator/terminator/pull/233) ([mattrose](https://github.com/mattrose))
- fix INSTALL instructions for setuptools [\#232](https://github.com/gnome-terminator/terminator/pull/232) ([mattrose](https://github.com/mattrose))

## [v2.0](https://github.com/gnome-terminator/terminator/tree/v2.0) (2020-10-06)

[Full Changelog](https://github.com/gnome-terminator/terminator/compare/v1.92...v2.0)

**Implemented enhancements:**

- Feature Request: "broadcast-only" option in profile preferences [\#157](https://github.com/gnome-terminator/terminator/issues/157)
- Feature Request: Key binding option for creating group in current tab [\#156](https://github.com/gnome-terminator/terminator/issues/156)
- Terminator should use XDG\_CONFIG\_HOME environment variable if it's available. [\#152](https://github.com/gnome-terminator/terminator/issues/152)
- align maximize option spelling with gnome-terminal [\#125](https://github.com/gnome-terminator/terminator/issues/125)
- Putty style paste makes it impossible to reach preferences [\#120](https://github.com/gnome-terminator/terminator/issues/120)
- Adjust Line Height [\#111](https://github.com/gnome-terminator/terminator/issues/111)
- Allow to open layout in a new tab [\#106](https://github.com/gnome-terminator/terminator/issues/106)
- Use VTE api instead of python psutil to get cwd. [\#82](https://github.com/gnome-terminator/terminator/issues/82)
- Make a submenu of Layouts in the popup menu. [\#63](https://github.com/gnome-terminator/terminator/issues/63)
- Search should have a case-sensitive option [\#44](https://github.com/gnome-terminator/terminator/issues/44)
- Remove default keybindings for enabling terminal broadcast [\#40](https://github.com/gnome-terminator/terminator/issues/40)
- \[Feature Request\] Make bold-is-bright option configurable [\#38](https://github.com/gnome-terminator/terminator/issues/38)
-  No option for background image in gtk3 version  [\#5](https://github.com/gnome-terminator/terminator/issues/5)
-  Terminator need to highlight search string  [\#4](https://github.com/gnome-terminator/terminator/issues/4)
- rely on python psutil to get the cwd [\#83](https://github.com/gnome-terminator/terminator/pull/83) ([mattrose](https://github.com/mattrose))
- Propagate tab-swictch events if there is only one tab [\#61](https://github.com/gnome-terminator/terminator/pull/61) ([blackm0re](https://github.com/blackm0re))
- Install AppStream data as .metainfo.xml [\#53](https://github.com/gnome-terminator/terminator/pull/53) ([DarthGandalf](https://github.com/DarthGandalf))
- Added option to disable ctrl+mousewheel zoom [\#46](https://github.com/gnome-terminator/terminator/pull/46) ([filipkilibarda](https://github.com/filipkilibarda))
- Add layout launcher to terminal popup menu. [\#42](https://github.com/gnome-terminator/terminator/pull/42) ([nbeaver](https://github.com/nbeaver))
- \#38: Add option for configuring bold-is-bright setting of VTE [\#39](https://github.com/gnome-terminator/terminator/pull/39) ([JakubVanek](https://github.com/JakubVanek))
- Only import GdkX11 when available [\#19](https://github.com/gnome-terminator/terminator/pull/19) ([mattrose](https://github.com/mattrose))
- Removing packaging files from the repository [\#7](https://github.com/gnome-terminator/terminator/pull/7) ([lazyfrosch](https://github.com/lazyfrosch))

**Fixed bugs:**

- Fails to run for LDAP user [\#128](https://github.com/gnome-terminator/terminator/issues/128)
- Crash in paned.py:311  [\#68](https://github.com/gnome-terminator/terminator/issues/68)
- terminator runs in network namespace only with -u option \(dbus\) [\#65](https://github.com/gnome-terminator/terminator/issues/65)
- dbus FileNotFoundError [\#58](https://github.com/gnome-terminator/terminator/issues/58)
- Middle click does not paste selected text [\#24](https://github.com/gnome-terminator/terminator/issues/24)
- Fix crash when GdkX11 module is not available when creating layout [\#113](https://github.com/gnome-terminator/terminator/pull/113) ([mattrose](https://github.com/mattrose))
- Do not crash when dbus server is unavailable, just emit an error message [\#88](https://github.com/gnome-terminator/terminator/pull/88) ([mattrose](https://github.com/mattrose))
- Fix fallback for getting the current working directory [\#87](https://github.com/gnome-terminator/terminator/pull/87) ([terceiro](https://github.com/terceiro))
- fix FileNotFound error when terminator is run from a directory that no longer exists [\#81](https://github.com/gnome-terminator/terminator/pull/81) ([mattrose](https://github.com/mattrose))
- Fix layout launcher error [\#59](https://github.com/gnome-terminator/terminator/pull/59) ([FernandoBasso](https://github.com/FernandoBasso))
- fix traceback on dragging and dropping files from a file manager [\#54](https://github.com/gnome-terminator/terminator/pull/54) ([mattrose](https://github.com/mattrose))
- Disable special logic for pasting on Wayland [\#51](https://github.com/gnome-terminator/terminator/pull/51) ([lazyfrosch](https://github.com/lazyfrosch))
- searchbar: Implement modern/glib regexp support [\#43](https://github.com/gnome-terminator/terminator/pull/43) ([lazyfrosch](https://github.com/lazyfrosch))
- fix exception when feeding terminal number to terminal [\#35](https://github.com/gnome-terminator/terminator/pull/35) ([mattrose](https://github.com/mattrose))
- terminal: Improve compat for Vte Regex [\#28](https://github.com/gnome-terminator/terminator/pull/28) ([lazyfrosch](https://github.com/lazyfrosch))

**Closed issues:**

- Feature request: Preference to disable Ctrl + Scroll font size change [\#219](https://github.com/gnome-terminator/terminator/issues/219)
- AttributeError: 'Terminal' object has no attribute 'spawn\_async' [\#218](https://github.com/gnome-terminator/terminator/issues/218)
- Question - custom command line [\#212](https://github.com/gnome-terminator/terminator/issues/212)
- Terminator overwrite shortcut of console Applications [\#204](https://github.com/gnome-terminator/terminator/issues/204)
- Gap between windows [\#203](https://github.com/gnome-terminator/terminator/issues/203)
- Search does not work [\#199](https://github.com/gnome-terminator/terminator/issues/199)
- Selecting first char of a line for copy-paste is impossible [\#191](https://github.com/gnome-terminator/terminator/issues/191)
- Duplicate Key Bindings are Allowed in `Preferences \> Keybindings` [\#190](https://github.com/gnome-terminator/terminator/issues/190)
- Cannot open terminator windows with different configs [\#184](https://github.com/gnome-terminator/terminator/issues/184)
- Feature request: reenable broadcast keybindings and warn on their first use instead [\#183](https://github.com/gnome-terminator/terminator/issues/183)
- Add Terminator version in About screen [\#169](https://github.com/gnome-terminator/terminator/issues/169)
- Feature Request: Add hyperlink support [\#164](https://github.com/gnome-terminator/terminator/issues/164)
- ctrl-alt-a activates even when terminal has no focus [\#163](https://github.com/gnome-terminator/terminator/issues/163)
- TypeError in terminal.py [\#162](https://github.com/gnome-terminator/terminator/issues/162)
- Active tab identification [\#158](https://github.com/gnome-terminator/terminator/issues/158)
- Is terminator is rolling for Windows Subsystem For Linux \(WSL\)??? [\#154](https://github.com/gnome-terminator/terminator/issues/154)
- broken mouse events in fullscreen applications [\#151](https://github.com/gnome-terminator/terminator/issues/151)
- Key Bindigs That Contain a Key Modified by a Shift Key Don't Work [\#149](https://github.com/gnome-terminator/terminator/issues/149)
- move translation of ConfigObj from main terminator code to the only method that uses it. [\#148](https://github.com/gnome-terminator/terminator/issues/148)
- Gnome session support no longer works [\#147](https://github.com/gnome-terminator/terminator/issues/147)
- Errors in prefseditor.py [\#137](https://github.com/gnome-terminator/terminator/issues/137)
- PuTTY style paste is pasting from x-selection instead of clipboard [\#134](https://github.com/gnome-terminator/terminator/issues/134)
- Terminator separator size cannot be changed [\#133](https://github.com/gnome-terminator/terminator/issues/133)
- update dependencies in INSTALL.md [\#127](https://github.com/gnome-terminator/terminator/issues/127)
- Feature request: show bold text in bright colors \(option\) [\#122](https://github.com/gnome-terminator/terminator/issues/122)
- Feature request: configurable shortcut to open Prefs [\#121](https://github.com/gnome-terminator/terminator/issues/121)
- Support desktop dark/light theme [\#119](https://github.com/gnome-terminator/terminator/issues/119)
- conflicting UUID when cloning layout [\#115](https://github.com/gnome-terminator/terminator/issues/115)
- Add support for tmux integration \(like iTerm2\)  [\#107](https://github.com/gnome-terminator/terminator/issues/107)
- Ubuntu 20.04 drag and drop crashes  [\#103](https://github.com/gnome-terminator/terminator/issues/103)
- When opening a new window, terminator automatically switch to the last tab of the first window. [\#99](https://github.com/gnome-terminator/terminator/issues/99)
- Why we use python in shebang [\#98](https://github.com/gnome-terminator/terminator/issues/98)
- Ubuntu 20.04 split terminal broadcast duplicate keys [\#96](https://github.com/gnome-terminator/terminator/issues/96)
- ubuntu 18.04 Install ok but no desktop icon [\#95](https://github.com/gnome-terminator/terminator/issues/95)
- There are still translation commits to launchpad [\#85](https://github.com/gnome-terminator/terminator/issues/85)
- cwd.get\_pid\_cwd is a mess. [\#80](https://github.com/gnome-terminator/terminator/issues/80)
- Resize borderless window [\#75](https://github.com/gnome-terminator/terminator/issues/75)
- Add distribution info into INSTALL [\#45](https://github.com/gnome-terminator/terminator/issues/45)
- Alt+ScrollWheel ? [\#29](https://github.com/gnome-terminator/terminator/issues/29)
- Switch to setuptools [\#14](https://github.com/gnome-terminator/terminator/issues/14)
- Improve gettext integration [\#13](https://github.com/gnome-terminator/terminator/issues/13)

**Merged pull requests:**

- Revert "Merge pull request \#208 from mattrose/update-vte-spawn" [\#220](https://github.com/gnome-terminator/terminator/pull/220) ([mattrose](https://github.com/mattrose))
- Background image [\#217](https://github.com/gnome-terminator/terminator/pull/217) ([mattrose](https://github.com/mattrose))
- fix spacing [\#215](https://github.com/gnome-terminator/terminator/pull/215) ([mattrose](https://github.com/mattrose))
- Fix: Allow `Shift+Tab` Key Binding [\#211](https://github.com/gnome-terminator/terminator/pull/211) ([dkmvs](https://github.com/dkmvs))
- add preferences keybindings [\#209](https://github.com/gnome-terminator/terminator/pull/209) ([mattrose](https://github.com/mattrose))
- fix login\_shell option so that it sends -l rather than -shell [\#207](https://github.com/gnome-terminator/terminator/pull/207) ([mattrose](https://github.com/mattrose))
- Command notify [\#205](https://github.com/gnome-terminator/terminator/pull/205) ([mattrose](https://github.com/mattrose))
- Dbus options [\#200](https://github.com/gnome-terminator/terminator/pull/200) ([mattrose](https://github.com/mattrose))
- Fix: Forbid Duplicate Key Bindings in `Preferences \> Keybindings` [\#196](https://github.com/gnome-terminator/terminator/pull/196) ([dkmvs](https://github.com/dkmvs))
- Key binding option for creating group in current terminal [\#195](https://github.com/gnome-terminator/terminator/pull/195) ([mattrose](https://github.com/mattrose))
- Add 'wide\_handle' property  [\#193](https://github.com/gnome-terminator/terminator/pull/193) ([mattrose](https://github.com/mattrose))
- Exit remotinator with an explicit error message when terminator is needed but not running [\#185](https://github.com/gnome-terminator/terminator/pull/185) ([phidebian](https://github.com/phidebian))
- Add a 'title bar at bottom' option [\#182](https://github.com/gnome-terminator/terminator/pull/182) ([phidebian](https://github.com/phidebian))
- Format shortcuts [\#181](https://github.com/gnome-terminator/terminator/pull/181) ([aadrian](https://github.com/aadrian))
- add support for OSC-8 [\#176](https://github.com/gnome-terminator/terminator/pull/176) ([mattrose](https://github.com/mattrose))
- add packages to install doc [\#174](https://github.com/gnome-terminator/terminator/pull/174) ([mattrose](https://github.com/mattrose))
- Fix readme [\#173](https://github.com/gnome-terminator/terminator/pull/173) ([mattrose](https://github.com/mattrose))
- remove unused gnome session code [\#172](https://github.com/gnome-terminator/terminator/pull/172) ([mattrose](https://github.com/mattrose))
- Add version string to "Preferences -\> About" [\#171](https://github.com/gnome-terminator/terminator/pull/171) ([mattrose](https://github.com/mattrose))
- Update README.md [\#166](https://github.com/gnome-terminator/terminator/pull/166) ([br0kenbuild](https://github.com/br0kenbuild))
- Allow live previewing of profile color changes [\#160](https://github.com/gnome-terminator/terminator/pull/160) ([dafrito](https://github.com/dafrito))
- Fix: Allow Key Bindings with Shift-Modified Keys [\#150](https://github.com/gnome-terminator/terminator/pull/150) ([dkmvs](https://github.com/dkmvs))
- Fixed bug in prefseditor.py [\#146](https://github.com/gnome-terminator/terminator/pull/146) ([robertoetcheverryr](https://github.com/robertoetcheverryr))
- fix traceback on paned.py [\#145](https://github.com/gnome-terminator/terminator/pull/145) ([mattrose](https://github.com/mattrose))
- issue 44, add option for case sensitive search [\#144](https://github.com/gnome-terminator/terminator/pull/144) ([dugb](https://github.com/dugb))
- fix line height config variable location to match ui [\#142](https://github.com/gnome-terminator/terminator/pull/142) ([mattrose](https://github.com/mattrose))
- Issue 111, add line\_height slider [\#141](https://github.com/gnome-terminator/terminator/pull/141) ([dugb](https://github.com/dugb))
- replaces the handle\_size property that was deprecated in gtk3.20 [\#140](https://github.com/gnome-terminator/terminator/pull/140) ([mattrose](https://github.com/mattrose))
- update apt repos before installing packages [\#136](https://github.com/gnome-terminator/terminator/pull/136) ([mattrose](https://github.com/mattrose))
- Added putty\_paste\_style\_source\_clipboard [\#135](https://github.com/gnome-terminator/terminator/pull/135) ([robertoetcheverryr](https://github.com/robertoetcheverryr))
- launch new layouts directly from right-click menu [\#132](https://github.com/gnome-terminator/terminator/pull/132) ([mattrose](https://github.com/mattrose))
- Issue99 [\#131](https://github.com/gnome-terminator/terminator/pull/131) ([mattrose](https://github.com/mattrose))
- Adding maximize option [\#126](https://github.com/gnome-terminator/terminator/pull/126) ([qckzr](https://github.com/qckzr))
- add line\_height config variable [\#124](https://github.com/gnome-terminator/terminator/pull/124) ([mattrose](https://github.com/mattrose))
- fix cwd for non-vte shells [\#123](https://github.com/gnome-terminator/terminator/pull/123) ([mattrose](https://github.com/mattrose))
- fix detection of whether or not ibus is running [\#114](https://github.com/gnome-terminator/terminator/pull/114) ([mattrose](https://github.com/mattrose))
- fix traceback when closing a window [\#112](https://github.com/gnome-terminator/terminator/pull/112) ([mattrose](https://github.com/mattrose))
- add debug logging to searchbar [\#110](https://github.com/gnome-terminator/terminator/pull/110) ([mattrose](https://github.com/mattrose))
- fix io errors on debugserver [\#109](https://github.com/gnome-terminator/terminator/pull/109) ([mattrose](https://github.com/mattrose))
- Fix TODO for documenting vte regex matching constants [\#105](https://github.com/gnome-terminator/terminator/pull/105) ([GerbenWelter](https://github.com/GerbenWelter))
- Revert "replace gettext and intltool with Babel" [\#100](https://github.com/gnome-terminator/terminator/pull/100) ([lazyfrosch](https://github.com/lazyfrosch))
- Import Launchpad translations [\#91](https://github.com/gnome-terminator/terminator/pull/91) ([lazyfrosch](https://github.com/lazyfrosch))
- Gentoo: github is only a mirror [\#86](https://github.com/gnome-terminator/terminator/pull/86) ([DarthGandalf](https://github.com/DarthGandalf))
- update the INSTALL.md for Ubuntu installation [\#77](https://github.com/gnome-terminator/terminator/pull/77) ([yosoufe](https://github.com/yosoufe))
- Update AUTHORS with a full list from GIT history [\#67](https://github.com/gnome-terminator/terminator/pull/67) ([lazyfrosch](https://github.com/lazyfrosch))
- docs: Update INSTALL.md and add distributions [\#66](https://github.com/gnome-terminator/terminator/pull/66) ([lazyfrosch](https://github.com/lazyfrosch))
- Make LayoutLauncher window a little larger by default [\#60](https://github.com/gnome-terminator/terminator/pull/60) ([FernandoBasso](https://github.com/FernandoBasso))
- fix up language strings in .po files [\#52](https://github.com/gnome-terminator/terminator/pull/52) ([mattrose](https://github.com/mattrose))
- Switch to setuptools and use pytest [\#50](https://github.com/gnome-terminator/terminator/pull/50) ([lazyfrosch](https://github.com/lazyfrosch))
- \#40: remove default key bindings for input broadcasting [\#41](https://github.com/gnome-terminator/terminator/pull/41) ([JakubVanek](https://github.com/JakubVanek))
- Add FreeBSD [\#33](https://github.com/gnome-terminator/terminator/pull/33) ([h-ume](https://github.com/h-ume))
- Update pt\_BR.po [\#30](https://github.com/gnome-terminator/terminator/pull/30) ([chclxds](https://github.com/chclxds))
- Remove obsolete terminator.wrapper [\#27](https://github.com/gnome-terminator/terminator/pull/27) ([lazyfrosch](https://github.com/lazyfrosch))
- Add Gentoo, sort the order of distributions [\#23](https://github.com/gnome-terminator/terminator/pull/23) ([DarthGandalf](https://github.com/DarthGandalf))

## [v1.92](https://github.com/gnome-terminator/terminator/tree/v1.92) (2020-04-18)

[Full Changelog](https://github.com/gnome-terminator/terminator/compare/1.91...v1.92)

This is the first release since 2017, while we are now a few years later a few things changed.

* New home on GitHub https://github.com/gnome-terminator/terminator
* New team under the lead of https://github.com/lazyfrosch
* Python 3 support finally released
* Some tedious bugs solved for current GTK and VTE

There is still a lot to do, and we need more help to keep Terminator available for
your daily use.

If you are interested in contributing to the project, please contact us, open issues,
discuss issues or help with whatever you can! Any help is welcome!

**Notes for packagers:**

* All scripts now use `#!/usr/bin/env python` as shebang, when you are using
  `python3 setup.py install` or similar all binary scripts should be automatically
   modified to the correct shebang
* Any feedback is welcome, please open an issue or join the community channels

**Implemented enhancements:**

- Implement support for Python 3 [\#6](https://github.com/gnome-terminator/terminator/pull/6) ([lazyfrosch](https://github.com/lazyfrosch))

**Fixed bugs:**

- VTE Regexp should work with older VTE releases as well [\#10](https://github.com/gnome-terminator/terminator/issues/10)
- ctrl+click should open links [\#3](https://github.com/gnome-terminator/terminator/issues/3)
- Ensure Python 3 support [\#2](https://github.com/gnome-terminator/terminator/issues/2)
- terminal: Add compat detection for Vte regexp feature [\#22](https://github.com/gnome-terminator/terminator/pull/22) ([lazyfrosch](https://github.com/lazyfrosch))
- Fix some compat issues for Python 2.7 [\#18](https://github.com/gnome-terminator/terminator/pull/18) ([lazyfrosch](https://github.com/lazyfrosch))
- Converting to python 3 and making all tests pass. [\#9](https://github.com/gnome-terminator/terminator/pull/9) ([JAugusto42](https://github.com/JAugusto42))

**Merged pull requests:**

- Add GitHub action for Python [\#17](https://github.com/gnome-terminator/terminator/pull/17) ([lazyfrosch](https://github.com/lazyfrosch))
- Updating URLs in application and appdata [\#16](https://github.com/gnome-terminator/terminator/pull/16) ([mattrose](https://github.com/mattrose))
- update the INSTALL file [\#15](https://github.com/gnome-terminator/terminator/pull/15) ([mattrose](https://github.com/mattrose))



\* *This Changelog was automatically generated by [github_changelog_generator](https://github.com/github-changelog-generator/github-changelog-generator)*
