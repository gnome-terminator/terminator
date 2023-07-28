# Changelog

## [v2.1.3](https://github.com/gnome-terminator/terminator/tree/v2.1.3) (2023-03-01)

[Full Changelog](https://github.com/gnome-terminator/terminator/compare/v2.1.2...v2.1.3)

**Implemented enhancements:**

- Option to set split ratio of terminals [\#708](https://github.com/gnome-terminator/terminator/issues/708)
- Add option to set given terminal to "read only" [\#649](https://github.com/gnome-terminator/terminator/issues/649)
- background image - respect ratio [\#644](https://github.com/gnome-terminator/terminator/issues/644)
- Shortcut for autosplit h/v depending on active terminal size [\#613](https://github.com/gnome-terminator/terminator/issues/613)
- Feature: Insert terminal name to terminal \(for broadcast\) [\#540](https://github.com/gnome-terminator/terminator/issues/540)
- Background image drawing modes and alignment [\#713](https://github.com/gnome-terminator/terminator/pull/713) ([Vulcalien](https://github.com/Vulcalien))
- Zoom on notebook even if there is only one terminal in the tab + keep tab position and label in notebook rotation [\#589](https://github.com/gnome-terminator/terminator/pull/589) ([Vulcalien](https://github.com/Vulcalien))

**Fixed bugs:**

- Resets the tab title on rotation [\#624](https://github.com/gnome-terminator/terminator/issues/624)
- - bug context menu \(right click\)-\>layouts-\>"Layout Name" always selec… [\#653](https://github.com/gnome-terminator/terminator/pull/653) ([vssdeo](https://github.com/vssdeo))
- Fix missing icons when started with Ctrl-Alt-T [\#628](https://github.com/gnome-terminator/terminator/pull/628) ([MihaiBabiac](https://github.com/MihaiBabiac))

**Closed issues:**

- Terminator not working with latest version of python-cairo [\#711](https://github.com/gnome-terminator/terminator/issues/711)
- \[Bug\]\[Fedora 36 KDE\]\[terminator v2.1.1\] "broadcast group" sends each terminal input/keystroke depending on the group's members count to everyone in the group [\#704](https://github.com/gnome-terminator/terminator/issues/704)
- reset\_clear doesn't show new prompt [\#703](https://github.com/gnome-terminator/terminator/issues/703)
- `-x`/`--execute` still broken [\#702](https://github.com/gnome-terminator/terminator/issues/702)
- Make unfocused terminal text transparent instead of blacker [\#694](https://github.com/gnome-terminator/terminator/issues/694)
- A translucent separation occurs between terminals [\#687](https://github.com/gnome-terminator/terminator/issues/687)
- \[2.1.2\] Foreground processes started in new window close immediately [\#673](https://github.com/gnome-terminator/terminator/issues/673)
- Is there a official page to maintain a offical/third-part plugin list? [\#668](https://github.com/gnome-terminator/terminator/issues/668)
- What happened to the change terminal titlebar under preferences? [\#664](https://github.com/gnome-terminator/terminator/issues/664)
- \[Feature Request\] - In the Context Menu\(Right-Click\) show keyboard shortcuts / accelarators  [\#662](https://github.com/gnome-terminator/terminator/issues/662)
- terminator: error: unrecognized arguments [\#660](https://github.com/gnome-terminator/terminator/issues/660)
- Plugin Submission : SaveLastSessionLayout Uses Layout to Auto-Save Last session and CWD on Terminal Window Close [\#654](https://github.com/gnome-terminator/terminator/issues/654)
- Loading layout loads only the last added layout from context menu \(right click\) [\#652](https://github.com/gnome-terminator/terminator/issues/652)
- When can we expect a new release? [\#650](https://github.com/gnome-terminator/terminator/issues/650)
- Profiles for different Shells - is it possible? how does it work? [\#640](https://github.com/gnome-terminator/terminator/issues/640)
- Double input to broadcasted group [\#623](https://github.com/gnome-terminator/terminator/issues/623)
- background images only  displaying on default profile [\#595](https://github.com/gnome-terminator/terminator/issues/595)
- The repository 'https://ppa.launchpadcontent.net/mattrose/terminator/ubuntu jammy Release' does not have a Release file. [\#594](https://github.com/gnome-terminator/terminator/issues/594)
- Increase the usage of augmented assignment statements [\#555](https://github.com/gnome-terminator/terminator/issues/555)

**Merged pull requests:**

- Better distinguishing of inactive windows from the active one, by changing the background brightness [\#709](https://github.com/gnome-terminator/terminator/pull/709) ([KKoovalsky](https://github.com/KKoovalsky))
- Ctrl+Click on group button automatically creates groups whenever needed [\#691](https://github.com/gnome-terminator/terminator/pull/691) ([nicbn](https://github.com/nicbn))
- \[bug 680\] Open up keybindings page on keypress \#680 [\#686](https://github.com/gnome-terminator/terminator/pull/686) ([vssdeo](https://github.com/vssdeo))
- Translate '/po/terminator.pot' in 'pt\_BR' [\#684](https://github.com/gnome-terminator/terminator/pull/684) ([transifex-integration[bot]](https://github.com/apps/transifex-integration))
- Plugin and Group menu item that inserts the name of the terminal. [\#683](https://github.com/gnome-terminator/terminator/pull/683) ([mattrose](https://github.com/mattrose))
- Add Readonly toggle to popup menu [\#679](https://github.com/gnome-terminator/terminator/pull/679) ([mattrose](https://github.com/mattrose))
- Fix argument handling of the --execute flag [\#678](https://github.com/gnome-terminator/terminator/pull/678) ([shawn-ogg](https://github.com/shawn-ogg))
- Remove all ibus workarounds [\#674](https://github.com/gnome-terminator/terminator/pull/674) ([mattrose](https://github.com/mattrose))
- \[bug 613\] -  Shortcut for autosplit h/v depending on active terminal … [\#671](https://github.com/gnome-terminator/terminator/pull/671) ([vssdeo](https://github.com/vssdeo))
- \[bug 662\] \[Feature Request\] - In the Context Menu\(Right-Click\) show k… [\#666](https://github.com/gnome-terminator/terminator/pull/666) ([vssdeo](https://github.com/vssdeo))
- \[bug 559\] Add menu autocomplete \#559 [\#665](https://github.com/gnome-terminator/terminator/pull/665) ([vssdeo](https://github.com/vssdeo))
- \[bug 662\] \[Feature Request\] - In the Context Menu\(Right-Click\) show k… [\#663](https://github.com/gnome-terminator/terminator/pull/663) ([vssdeo](https://github.com/vssdeo))
- \[bug 654\] - Plugin Submission : SaveLastSessionLayout Uses Layout to … [\#661](https://github.com/gnome-terminator/terminator/pull/661) ([vssdeo](https://github.com/vssdeo))
- Update terminal.py [\#659](https://github.com/gnome-terminator/terminator/pull/659) ([flaviosteimacher](https://github.com/flaviosteimacher))
- docs: Change number of columns in repology badge [\#657](https://github.com/gnome-terminator/terminator/pull/657) ([pktiuk](https://github.com/pktiuk))
- Plugin Submission : SaveLastSessionLayout Uses Layout to Auto-Save Last session and CWD [\#655](https://github.com/gnome-terminator/terminator/pull/655) ([vssdeo](https://github.com/vssdeo))
- Fix typos [\#651](https://github.com/gnome-terminator/terminator/pull/651) ([kianmeng](https://github.com/kianmeng))
- data: Remove GNOME branding [\#647](https://github.com/gnome-terminator/terminator/pull/647) ([sabriunal](https://github.com/sabriunal))
- this line has an extra ';' symbol [\#632](https://github.com/gnome-terminator/terminator/pull/632) ([xuezhixin](https://github.com/xuezhixin))
- Use the term 'zero padded' instead of 'padded'. [\#189](https://github.com/gnome-terminator/terminator/pull/189) ([phidebian](https://github.com/phidebian))

## [v2.1.2](https://github.com/gnome-terminator/terminator/tree/v2.1.2) (2022-10-19)

[Full Changelog](https://github.com/gnome-terminator/terminator/compare/v2.1.1...v2.1.2)

**Implemented enhancements:**

- \[Feature request\] move layout/session definitions into separate files with a dedicated extension in a dedicated directory [\#604](https://github.com/gnome-terminator/terminator/issues/604)
- Bash completion [\#495](https://github.com/gnome-terminator/terminator/issues/495)
- Changing cursor foreground color [\#467](https://github.com/gnome-terminator/terminator/issues/467)
- Wallpaper configuration option from terminal [\#466](https://github.com/gnome-terminator/terminator/issues/466)
- Launch a new command in a vertical or horizontal split. [\#446](https://github.com/gnome-terminator/terminator/issues/446)
- Separators is wider after upgrading to ubuntu 21.04 [\#445](https://github.com/gnome-terminator/terminator/issues/445)
- Broadcast profile changes to existing terminals [\#421](https://github.com/gnome-terminator/terminator/issues/421)
- How to deactivate the middle mouse button paste? [\#415](https://github.com/gnome-terminator/terminator/issues/415)
- Feature request: expose the window and terminal title setting features in context menu [\#405](https://github.com/gnome-terminator/terminator/issues/405)
- Integrate --layout-json command line parameter so that it can be passed to dbus [\#401](https://github.com/gnome-terminator/terminator/issues/401)
- Feature request: move titlebar colors config to profiles, rather than global settings [\#379](https://github.com/gnome-terminator/terminator/issues/379)
- Visual aids [\#367](https://github.com/gnome-terminator/terminator/issues/367)
- Feature Request: detach tab [\#302](https://github.com/gnome-terminator/terminator/issues/302)
- Pls add version on OS X [\#283](https://github.com/gnome-terminator/terminator/issues/283)

**Fixed bugs:**

- Ctrl+Shift+Mouse-Scroll triggers Ctrl+Mouse Scroll [\#606](https://github.com/gnome-terminator/terminator/issues/606)
- None isn't a valid value of keybindings config anymore [\#548](https://github.com/gnome-terminator/terminator/issues/548)
- psutil.AccessDenied: psutil.AccessDenied \(pid=1\) [\#539](https://github.com/gnome-terminator/terminator/issues/539)
- Find functionality does not show matches on same line [\#511](https://github.com/gnome-terminator/terminator/issues/511)
- Ratio and/or position on a config file's layout ignored [\#433](https://github.com/gnome-terminator/terminator/issues/433)
- Black background remains after hide\_window [\#425](https://github.com/gnome-terminator/terminator/issues/425)
- Cannot create working config file with 5 terminals [\#409](https://github.com/gnome-terminator/terminator/issues/409)
- Terminal loses focus versus tab title [\#400](https://github.com/gnome-terminator/terminator/issues/400)
- Terminal title-bars are transparent on first start [\#392](https://github.com/gnome-terminator/terminator/issues/392)

**Closed issues:**

- Hide window in waybar [\#633](https://github.com/gnome-terminator/terminator/issues/633)
- Split window profile incorrect inheritance  [\#631](https://github.com/gnome-terminator/terminator/issues/631)
- \[Question\] is there a way to prevent Terminator from dereferencing symbolic links? [\#617](https://github.com/gnome-terminator/terminator/issues/617)
- Terminator not working on RHEL 9  [\#616](https://github.com/gnome-terminator/terminator/issues/616)
- Is there a right-click menu in sway? [\#614](https://github.com/gnome-terminator/terminator/issues/614)
- Set Terminator tab title via command line [\#603](https://github.com/gnome-terminator/terminator/issues/603)
- Unable to launch KeyError: b'Rss:' [\#601](https://github.com/gnome-terminator/terminator/issues/601)
- Cannot view emoji [\#599](https://github.com/gnome-terminator/terminator/issues/599)
- Clickable filepath:rownumber [\#598](https://github.com/gnome-terminator/terminator/issues/598)
- Feature Request: set initial window size in preferences [\#593](https://github.com/gnome-terminator/terminator/issues/593)
- Update the authorship in README [\#586](https://github.com/gnome-terminator/terminator/issues/586)
- xbindkeys doesn't work in Terminator, but works in other apps [\#582](https://github.com/gnome-terminator/terminator/issues/582)
- Unable to load Keybinder module [\#580](https://github.com/gnome-terminator/terminator/issues/580)
- terminator for MacOS user [\#578](https://github.com/gnome-terminator/terminator/issues/578)
- UTF-8 character breaks terminator config file [\#577](https://github.com/gnome-terminator/terminator/issues/577)
- Terminator need to highlight search string [\#575](https://github.com/gnome-terminator/terminator/issues/575)
- Custom Commands NOT Working in Linux Mint 20.3 [\#573](https://github.com/gnome-terminator/terminator/issues/573)
- Can't add/remove terminal panes from layout editor [\#572](https://github.com/gnome-terminator/terminator/issues/572)
- Language not applied after build [\#569](https://github.com/gnome-terminator/terminator/issues/569)
- Moving Cursor Word By Word using ALT + Arrows [\#566](https://github.com/gnome-terminator/terminator/issues/566)
- Enabling "putty style paste" causes context menu to be unreachable with 2-button mouse [\#565](https://github.com/gnome-terminator/terminator/issues/565)
- Setting stty options [\#564](https://github.com/gnome-terminator/terminator/issues/564)
- Switch focus and splits don't work when terminal is zoomed [\#550](https://github.com/gnome-terminator/terminator/issues/550)
- Will terminator ever consider picking up ligature support? [\#543](https://github.com/gnome-terminator/terminator/issues/543)
- feature request: Implement line spacing as a configuration option [\#542](https://github.com/gnome-terminator/terminator/issues/542)
- Change separator color [\#538](https://github.com/gnome-terminator/terminator/issues/538)
- remotinator split and execute command — cannot determine uuid [\#537](https://github.com/gnome-terminator/terminator/issues/537)
- Split vertical keyboard don't work on debian 11 [\#535](https://github.com/gnome-terminator/terminator/issues/535)
- Vte.Terminal\(\).set\_encoding deprecated [\#534](https://github.com/gnome-terminator/terminator/issues/534)
- Fix Keyboard Input [\#533](https://github.com/gnome-terminator/terminator/issues/533)
- group broadcasting switched on/off for all groups [\#532](https://github.com/gnome-terminator/terminator/issues/532)
- Drop a file from nautilus onto terminator window no longer works \(it used to paste the path a la gnome terminal\) [\#530](https://github.com/gnome-terminator/terminator/issues/530)
- Crash everytime after encoding is changed to TCVN [\#529](https://github.com/gnome-terminator/terminator/issues/529)
- Change the color of the current tab to highlight it better [\#522](https://github.com/gnome-terminator/terminator/issues/522)
- Feature: Configuration to colorize split screens from default grey colour, Issue: Remove ability to select 0 and 1 handle\_size from configuration gui [\#518](https://github.com/gnome-terminator/terminator/issues/518)
- Error when using "Insert Terminal Number" \(Solved?\) [\#517](https://github.com/gnome-terminator/terminator/issues/517)
- Auto-scroll to the cursor position when typing [\#513](https://github.com/gnome-terminator/terminator/issues/513)
- hide\_window mapped with Shift+Control+Alt+$an\_alphabet catches Control+Alt+$an\_alphabet instead [\#509](https://github.com/gnome-terminator/terminator/issues/509)
- Cursor is blinking on inactive windows [\#508](https://github.com/gnome-terminator/terminator/issues/508)
- custom commands are not persisted [\#505](https://github.com/gnome-terminator/terminator/issues/505)
- Terminator slow to close if xclip was invoked [\#503](https://github.com/gnome-terminator/terminator/issues/503)
- terminator failing to open on ubuntu 21.04 [\#502](https://github.com/gnome-terminator/terminator/issues/502)
- Monospace Bold isn't working [\#497](https://github.com/gnome-terminator/terminator/issues/497)
- No prompt when closing terminator now, despite say vim running in terminal [\#496](https://github.com/gnome-terminator/terminator/issues/496)
- suppor for sixel graphics [\#492](https://github.com/gnome-terminator/terminator/issues/492)
- which is deprecated and should not be used [\#488](https://github.com/gnome-terminator/terminator/issues/488)
- could tmux Key bindings using in terminator? [\#474](https://github.com/gnome-terminator/terminator/issues/474)
- Support OpenType font features [\#473](https://github.com/gnome-terminator/terminator/issues/473)
- Crash on Terminal resize when using fish [\#458](https://github.com/gnome-terminator/terminator/issues/458)
- Incorrect layout sorting in notebook [\#453](https://github.com/gnome-terminator/terminator/issues/453)
- Coloring Tabs / Tabs Appearance [\#449](https://github.com/gnome-terminator/terminator/issues/449)
- Option to disable system notifications [\#448](https://github.com/gnome-terminator/terminator/issues/448)
- Window vanishes [\#447](https://github.com/gnome-terminator/terminator/issues/447)
- Multiple Terminator instances randomly crash on Ubuntu 20.04 [\#444](https://github.com/gnome-terminator/terminator/issues/444)
- Option to open URLs with just a click [\#434](https://github.com/gnome-terminator/terminator/issues/434)
- Doubled input from keyboard when broadcasting in tabs [\#432](https://github.com/gnome-terminator/terminator/issues/432)
- Does this tool support macOS Big Sur? [\#430](https://github.com/gnome-terminator/terminator/issues/430)
- terminator is slow [\#426](https://github.com/gnome-terminator/terminator/issues/426)
- Add more fundamental "editor-ish" feature [\#424](https://github.com/gnome-terminator/terminator/issues/424)
- Allow disabling and resetting keybindings in Preferences [\#423](https://github.com/gnome-terminator/terminator/issues/423)
- Project based layout [\#418](https://github.com/gnome-terminator/terminator/issues/418)
- Unable to Install from Source [\#412](https://github.com/gnome-terminator/terminator/issues/412)
- CTRL+A behaviour abnormal [\#384](https://github.com/gnome-terminator/terminator/issues/384)
- regexp/command hyperlink handler [\#381](https://github.com/gnome-terminator/terminator/issues/381)
- Update PPA to 2.1.0 [\#374](https://github.com/gnome-terminator/terminator/issues/374)
- Create Snap and Flatpak for Terminator [\#206](https://github.com/gnome-terminator/terminator/issues/206)
- Remove gtk-update-icon-cache handling in setup [\#102](https://github.com/gnome-terminator/terminator/issues/102)

**Merged pull requests:**

- update translations [\#656](https://github.com/gnome-terminator/terminator/pull/656) ([mattrose](https://github.com/mattrose))
- Terminal ctrl+mousewheel: do not try to zoom if shift is pressed [\#609](https://github.com/gnome-terminator/terminator/pull/609) ([Vulcalien](https://github.com/Vulcalien))
- More fixes to the Color pickers in the Preferences Editor [\#592](https://github.com/gnome-terminator/terminator/pull/592) ([mattrose](https://github.com/mattrose))
- Modification in the /terminatorlib/prefseditor.py file [\#590](https://github.com/gnome-terminator/terminator/pull/590) ([amaan211](https://github.com/amaan211))
- Various README fixes [\#588](https://github.com/gnome-terminator/terminator/pull/588) ([mattrose](https://github.com/mattrose))
- Remove duplicated info in some debug messages [\#576](https://github.com/gnome-terminator/terminator/pull/576) ([Vulcalien](https://github.com/Vulcalien))
- Added hotfix for \#78 that deletes GTK\_IM\_MODULE environment variable [\#574](https://github.com/gnome-terminator/terminator/pull/574) ([ozzdemir](https://github.com/ozzdemir))
- Fix POTFILES.in + update translation files [\#571](https://github.com/gnome-terminator/terminator/pull/571) ([Vulcalien](https://github.com/Vulcalien))
- Add initial flatpak-spawn support [\#570](https://github.com/gnome-terminator/terminator/pull/570) ([JayDoubleu](https://github.com/JayDoubleu))
- Fix: handle\_size treated as cell\_width [\#561](https://github.com/gnome-terminator/terminator/pull/561) ([Vulcalien](https://github.com/Vulcalien))
- Transifex translations from Dec 20 2021 [\#558](https://github.com/gnome-terminator/terminator/pull/558) ([mattrose](https://github.com/mattrose))
- Unzoom terminal on interaction [\#553](https://github.com/gnome-terminator/terminator/pull/553) ([Vulcalien](https://github.com/Vulcalien))
- Add ability to configure cell width \(font character spacing\) [\#552](https://github.com/gnome-terminator/terminator/pull/552) ([FernandoBasso](https://github.com/FernandoBasso))
- Improve and optimize the code for background images [\#551](https://github.com/gnome-terminator/terminator/pull/551) ([Vulcalien](https://github.com/Vulcalien))
- Fix: 'None' value for keybindings breaks editor [\#549](https://github.com/gnome-terminator/terminator/pull/549) ([Vulcalien](https://github.com/Vulcalien))
- don't traceback while searching through /proc [\#546](https://github.com/gnome-terminator/terminator/pull/546) ([mattrose](https://github.com/mattrose))
- os.environ does not have LANGUAGE in Centos8. [\#544](https://github.com/gnome-terminator/terminator/pull/544) ([xuezhixin](https://github.com/xuezhixin))
- Remove Encoding settings \(deprecated\) [\#536](https://github.com/gnome-terminator/terminator/pull/536) ([Vulcalien](https://github.com/Vulcalien))
- Allow multiline commands in Custom Commands plugin [\#525](https://github.com/gnome-terminator/terminator/pull/525) ([VDuchon](https://github.com/VDuchon))
- Add paste\_selection keybinding. [\#520](https://github.com/gnome-terminator/terminator/pull/520) ([rkitover](https://github.com/rkitover))
- Fix terminal separator size setting [\#519](https://github.com/gnome-terminator/terminator/pull/519) ([caprinux](https://github.com/caprinux))
- Automatically focus the Keybindings menu [\#516](https://github.com/gnome-terminator/terminator/pull/516) ([Vulcalien](https://github.com/Vulcalien))
- Fix hide\_window keybinding unset check [\#515](https://github.com/gnome-terminator/terminator/pull/515) ([tomty89](https://github.com/tomty89))
- Add 'Disable mouse paste' [\#512](https://github.com/gnome-terminator/terminator/pull/512) ([Vulcalien](https://github.com/Vulcalien))
- Bug Fix: hide\_window keybinding ignores Shift key [\#510](https://github.com/gnome-terminator/terminator/pull/510) ([Vulcalien](https://github.com/Vulcalien))
- Improve argument parser + implement bash completion [\#506](https://github.com/gnome-terminator/terminator/pull/506) ([Vulcalien](https://github.com/Vulcalien))
- add Set Window Title item to context menu [\#501](https://github.com/gnome-terminator/terminator/pull/501) ([mattrose](https://github.com/mattrose))
- BugFix: terminal won't restart if there is no custom command [\#500](https://github.com/gnome-terminator/terminator/pull/500) ([Vulcalien](https://github.com/Vulcalien))
- Add a "Copy" button to clone profiles [\#499](https://github.com/gnome-terminator/terminator/pull/499) ([Vulcalien](https://github.com/Vulcalien))
- Make tabs detachable + minor bugfix [\#494](https://github.com/gnome-terminator/terminator/pull/494) ([Vulcalien](https://github.com/Vulcalien))
- remove gtk-update-icon-cache from setup.py [\#493](https://github.com/gnome-terminator/terminator/pull/493) ([mattrose](https://github.com/mattrose))
- remove vsplit\_cmd and hsplit\_cmd from ipc.py, superseded by newer hsp… [\#491](https://github.com/gnome-terminator/terminator/pull/491) ([mattrose](https://github.com/mattrose))
- Update tr.po [\#490](https://github.com/gnome-terminator/terminator/pull/490) ([StephenPeringer](https://github.com/StephenPeringer))
- add bg\_img and bg\_img\_all commands to remotinator [\#487](https://github.com/gnome-terminator/terminator/pull/487) ([mattrose](https://github.com/mattrose))
- Cursor: make it possible to change foreground color \(\#467\) [\#486](https://github.com/gnome-terminator/terminator/pull/486) ([Vulcalien](https://github.com/Vulcalien))
- fixes for --config-json [\#484](https://github.com/gnome-terminator/terminator/pull/484) ([mattrose](https://github.com/mattrose))
- GUI: set all CheckButtons off to avoid blinking + remove grid empty rows/columns [\#482](https://github.com/gnome-terminator/terminator/pull/482) ([Vulcalien](https://github.com/Vulcalien))
- Move titlebar settings to profiles \(\#379\) [\#481](https://github.com/gnome-terminator/terminator/pull/481) ([Vulcalien](https://github.com/Vulcalien))
- Issue 365 [\#480](https://github.com/gnome-terminator/terminator/pull/480) ([mattrose](https://github.com/mattrose))
- Fix typo in `po/de.po` [\#476](https://github.com/gnome-terminator/terminator/pull/476) ([dennis-benzinger-hybris](https://github.com/dennis-benzinger-hybris))
- add parameters to remotinator split commands [\#472](https://github.com/gnome-terminator/terminator/pull/472) ([mattrose](https://github.com/mattrose))
- add switch\_profile\_all command to remotinator [\#471](https://github.com/gnome-terminator/terminator/pull/471) ([mattrose](https://github.com/mattrose))
- Set CAN\_FOCUS to False for notebook widgets [\#470](https://github.com/gnome-terminator/terminator/pull/470) ([marktimarev](https://github.com/marktimarev))
- tell titlebar to start focussed out if it does not have focus [\#462](https://github.com/gnome-terminator/terminator/pull/462) ([mattrose](https://github.com/mattrose))
- Update translation [\#460](https://github.com/gnome-terminator/terminator/pull/460) ([pktiuk](https://github.com/pktiuk))
- Add new plugin for opening current directory using right mouse button [\#459](https://github.com/gnome-terminator/terminator/pull/459) ([pktiuk](https://github.com/pktiuk))
- Fixed Issue \#425 \(hide\_window will try to show a destroyed window\) [\#456](https://github.com/gnome-terminator/terminator/pull/456) ([Vulcalien](https://github.com/Vulcalien))
- Incorrect layout sorting in notebook [\#454](https://github.com/gnome-terminator/terminator/pull/454) ([AsadJivani](https://github.com/AsadJivani))
- Closing tab on middle mouse button press [\#451](https://github.com/gnome-terminator/terminator/pull/451) ([kocho1984](https://github.com/kocho1984))
- Bug Fix: 'Clear selection on copy' is always unchecked [\#443](https://github.com/gnome-terminator/terminator/pull/443) ([Vulcalien](https://github.com/Vulcalien))
- Fixed issue \#433 \(layout sometimes ignores ratio\) [\#442](https://github.com/gnome-terminator/terminator/pull/442) ([Vulcalien](https://github.com/Vulcalien))
- Fix the background image loading exception handling [\#436](https://github.com/gnome-terminator/terminator/pull/436) ([GerbenWelter](https://github.com/GerbenWelter))
- Added set\_tab\_title command to remotinator. [\#435](https://github.com/gnome-terminator/terminator/pull/435) ([yusufgungor](https://github.com/yusufgungor))
- Ukrainianized by 93% [\#428](https://github.com/gnome-terminator/terminator/pull/428) ([balac-ode](https://github.com/balac-ode))
- Fixed geometry hints [\#416](https://github.com/gnome-terminator/terminator/pull/416) ([Vulcalien](https://github.com/Vulcalien))
- Feat+run cmd on match [\#399](https://github.com/gnome-terminator/terminator/pull/399) ([nojhan](https://github.com/nojhan))
- add feat: config to open links with single click [\#398](https://github.com/gnome-terminator/terminator/pull/398) ([nojhan](https://github.com/nojhan))
- Add new vsplit hsplit cmd dbus [\#390](https://github.com/gnome-terminator/terminator/pull/390) ([TheBigS](https://github.com/TheBigS))
- Added new get\_focused\_terminal dbus command which returns uuid of current focused terminal [\#389](https://github.com/gnome-terminator/terminator/pull/389) ([TheBigS](https://github.com/TheBigS))

## [v2.1.1](https://github.com/gnome-terminator/terminator/tree/v2.1.1) (2021-04-02)

[Full Changelog](https://github.com/gnome-terminator/terminator/compare/v2.1.0...v2.1.1)

**Implemented enhancements:**

- add "switch profile" command to remotinator [\#321](https://github.com/gnome-terminator/terminator/issues/321)

**Fixed bugs:**

- Terminal text isn't shown on lost focus of multiple tabs and hidden scroll bar [\#372](https://github.com/gnome-terminator/terminator/issues/372)

**Closed issues:**

- Terminator display freeze [\#411](https://github.com/gnome-terminator/terminator/issues/411)
- Albert hotkey \(shortcut\) didn't work in Gnome Terminal or Gnome Terminator [\#407](https://github.com/gnome-terminator/terminator/issues/407)
- ImportError: bad magic number in 'six': b'\x03\xf3\r\n' [\#404](https://github.com/gnome-terminator/terminator/issues/404)
- Last split in tab greyed out [\#402](https://github.com/gnome-terminator/terminator/issues/402)
- Using the `--debug-classes` option makes terminator crash [\#397](https://github.com/gnome-terminator/terminator/issues/397)
- cannot import name 'Validator' from 'validate' | arch community/terminator 2.1.0-2 [\#395](https://github.com/gnome-terminator/terminator/issues/395)
- Clicking on terminator title bars does not focus the terminal belonging to the title-bar [\#394](https://github.com/gnome-terminator/terminator/issues/394)
- Losing focus on a tabbed window will grey out the window [\#393](https://github.com/gnome-terminator/terminator/issues/393)
- Terminator turns white when using tabs [\#391](https://github.com/gnome-terminator/terminator/issues/391)
- unremovable background image [\#387](https://github.com/gnome-terminator/terminator/issues/387)
- Tab focus change causes white-out of console [\#383](https://github.com/gnome-terminator/terminator/issues/383)
- Allow hide title bar as global option [\#377](https://github.com/gnome-terminator/terminator/issues/377)
- Add project management tool [\#376](https://github.com/gnome-terminator/terminator/issues/376)
- module 'command\_notify' has no attribute 'AVAILABLE' [\#375](https://github.com/gnome-terminator/terminator/issues/375)
- weird bug with long commands [\#373](https://github.com/gnome-terminator/terminator/issues/373)
- Open in terminal [\#368](https://github.com/gnome-terminator/terminator/issues/368)
- Clipboard commands [\#366](https://github.com/gnome-terminator/terminator/issues/366)
- Background image not showing up on Xubuntu 20.04 [\#364](https://github.com/gnome-terminator/terminator/issues/364)
- Pasted text is highlighted [\#363](https://github.com/gnome-terminator/terminator/issues/363)
- \[FR\] Option to elide terminal title from the left [\#362](https://github.com/gnome-terminator/terminator/issues/362)
- Windows title are not udpated after ssh session disconnected [\#359](https://github.com/gnome-terminator/terminator/issues/359)
- No broadcast menu in sway [\#357](https://github.com/gnome-terminator/terminator/issues/357)
- Remove spaces between tabs [\#331](https://github.com/gnome-terminator/terminator/issues/331)
- Enhancement: Stjerm Layout Like Functionality [\#298](https://github.com/gnome-terminator/terminator/issues/298)
- Unwanted transparent pane separators [\#293](https://github.com/gnome-terminator/terminator/issues/293)
- clusterssh like behaviour via plugin [\#222](https://github.com/gnome-terminator/terminator/issues/222)

**Merged pull requests:**

- Release version 2.1.1 [\#413](https://github.com/gnome-terminator/terminator/pull/413) ([mattrose](https://github.com/mattrose))
- i18n: pt\_BR: add missing space in translations with shortcuts [\#406](https://github.com/gnome-terminator/terminator/pull/406) ([terceiro](https://github.com/terceiro))
- Fixed race condition when calling grab\_focus after underlying vte could be closed [\#388](https://github.com/gnome-terminator/terminator/pull/388) ([TheBigS](https://github.com/TheBigS))
- disable 2.7 tests until we can figure out how to run them in GH [\#386](https://github.com/gnome-terminator/terminator/pull/386) ([mattrose](https://github.com/mattrose))
- Revert 74 [\#385](https://github.com/gnome-terminator/terminator/pull/385) ([mattrose](https://github.com/mattrose))
- update spanish translation [\#370](https://github.com/gnome-terminator/terminator/pull/370) ([mattrose](https://github.com/mattrose))
- Remotinator "switch\_profile" command [\#361](https://github.com/gnome-terminator/terminator/pull/361) ([leandrost](https://github.com/leandrost))
- clarify config file sentences [\#360](https://github.com/gnome-terminator/terminator/pull/360) ([mattrose](https://github.com/mattrose))
- fix broadcast menu for sway and wayland [\#358](https://github.com/gnome-terminator/terminator/pull/358) ([mattrose](https://github.com/mattrose))

## [v2.1.0](https://github.com/gnome-terminator/terminator/tree/v2.1.0) (2021-01-04)

[Full Changelog](https://github.com/gnome-terminator/terminator/compare/v2.0.1...v2.1.0)

**Implemented enhancements:**

- Add bigger icon sizes [\#258](https://github.com/gnome-terminator/terminator/issues/258)
- Smart Copy option to clear selection after copy [\#242](https://github.com/gnome-terminator/terminator/issues/242)
- New feature: A Separate Json file for dynamic Layouts [\#213](https://github.com/gnome-terminator/terminator/issues/213)
- new feature: support for term://1.2.3.4/ 'links' that when clicked open a new terminator ssh'ed to 1.2.3.4. [\#178](https://github.com/gnome-terminator/terminator/issues/178)
- Add Transifex integration and documentation for translations [\#352](https://github.com/gnome-terminator/terminator/pull/352) ([lazyfrosch](https://github.com/lazyfrosch))

**Fixed bugs:**

- No \(visible\) context menu in sway [\#330](https://github.com/gnome-terminator/terminator/issues/330)
- ModuleNotFoundError: No module named 'validate' [\#324](https://github.com/gnome-terminator/terminator/issues/324)
- Saving a layout after changing it, it correctly updates the config file but does not update the UI [\#319](https://github.com/gnome-terminator/terminator/issues/319)

**Closed issues:**

- Won't open in latest Manjaro ARM [\#354](https://github.com/gnome-terminator/terminator/issues/354)
- Rethinking release artifacts [\#348](https://github.com/gnome-terminator/terminator/issues/348)
- Unable to launch terminator [\#346](https://github.com/gnome-terminator/terminator/issues/346)
- The Alt+L layout chooser is too small [\#345](https://github.com/gnome-terminator/terminator/issues/345)
- Open in Previous Location [\#337](https://github.com/gnome-terminator/terminator/issues/337)
- How to install terminator without root privilege? [\#332](https://github.com/gnome-terminator/terminator/issues/332)
- Improve separator between splitted terminals [\#329](https://github.com/gnome-terminator/terminator/issues/329)
- Using shift+Super+} for next\_tab key binding doesn't work [\#326](https://github.com/gnome-terminator/terminator/issues/326)
- "Copy email address" actually doesn't quite do that [\#323](https://github.com/gnome-terminator/terminator/issues/323)
- Can`t disable key binding [\#322](https://github.com/gnome-terminator/terminator/issues/322)
- Middle click does not paste selected text [\#320](https://github.com/gnome-terminator/terminator/issues/320)
- how to change colour of the tabs? [\#313](https://github.com/gnome-terminator/terminator/issues/313)
- Would you mind to add default keybindins about Switch\_to\_tab\_\[1-10\]  with Alt - \[1-10\]? [\#311](https://github.com/gnome-terminator/terminator/issues/311)
- Terminator does not read config file from /etc/xdg directory  [\#308](https://github.com/gnome-terminator/terminator/issues/308)
- Add a 'clear terminal' function [\#306](https://github.com/gnome-terminator/terminator/issues/306)
- terminator-2.0.1: vertical separator too big [\#305](https://github.com/gnome-terminator/terminator/issues/305)
- rewrap\_on\_resize is deprecated in vte-0.60.0 [\#303](https://github.com/gnome-terminator/terminator/issues/303)
- \<Alt\>period no longer usable as a shortcut keybinding: \<Alt\>comma and \<Alt\>minus still work \(!\) [\#301](https://github.com/gnome-terminator/terminator/issues/301)
- Terminator doesn't update until I switch windows  [\#299](https://github.com/gnome-terminator/terminator/issues/299)
- Geometry ignored [\#297](https://github.com/gnome-terminator/terminator/issues/297)
- hangs after update [\#292](https://github.com/gnome-terminator/terminator/issues/292)
- Groups in config file [\#290](https://github.com/gnome-terminator/terminator/issues/290)
- Help/suggestion: proc title. [\#289](https://github.com/gnome-terminator/terminator/issues/289)
- terminator fails to run and issues stack trace [\#288](https://github.com/gnome-terminator/terminator/issues/288)
- Unable to Set "Image" as Background [\#285](https://github.com/gnome-terminator/terminator/issues/285)
- Terminator window not recognized as running application in Ubuntu [\#276](https://github.com/gnome-terminator/terminator/issues/276)
- Terminator terminal gnome-terminator for Ubuntu 20.04 [\#274](https://github.com/gnome-terminator/terminator/issues/274)
- Adding custom command to layout causes AttributeError: 'UUID' object has no attribute 'replace' [\#273](https://github.com/gnome-terminator/terminator/issues/273)
- You need to run terminator in an X environment. Make sure $DISPLAY is properly set [\#272](https://github.com/gnome-terminator/terminator/issues/272)
- Option to make zooming in and out apply to all subterminals instead of just one [\#271](https://github.com/gnome-terminator/terminator/issues/271)
- Lack of documentation [\#268](https://github.com/gnome-terminator/terminator/issues/268)
- module 'command\_notify' has no attribute 'AVAILABLE' [\#264](https://github.com/gnome-terminator/terminator/issues/264)
- Using terminator natively on Windows 10 [\#263](https://github.com/gnome-terminator/terminator/issues/263)
- Broadcast all is broadcasting to all terminator windows [\#261](https://github.com/gnome-terminator/terminator/issues/261)
- Steps to install terminator [\#259](https://github.com/gnome-terminator/terminator/issues/259)
- Cannot set/use Broadcast Shortcuts [\#253](https://github.com/gnome-terminator/terminator/issues/253)
- Translations: some strings missing in pot file [\#250](https://github.com/gnome-terminator/terminator/issues/250)
- Save sessions [\#243](https://github.com/gnome-terminator/terminator/issues/243)
- No tests in tarball [\#238](https://github.com/gnome-terminator/terminator/issues/238)
- Ubuntu 20 "open in terminal" not replaced by terminator. [\#236](https://github.com/gnome-terminator/terminator/issues/236)
- symlinked config replaced with regular file [\#234](https://github.com/gnome-terminator/terminator/issues/234)
- Feature Request: Split window shell based on parent [\#229](https://github.com/gnome-terminator/terminator/issues/229)
- Create a new release? \(and maybe add easier-to-install workflow?\) [\#221](https://github.com/gnome-terminator/terminator/issues/221)
- Cannot "Drag and Drop" Folders or Files [\#159](https://github.com/gnome-terminator/terminator/issues/159)
- A new home for terminator [\#1](https://github.com/gnome-terminator/terminator/issues/1)

**Merged pull requests:**

- prep for release 2.1.0 [\#355](https://github.com/gnome-terminator/terminator/pull/355) ([mattrose](https://github.com/mattrose))
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
- Preserve searchbar case sensitivity state in config file on state change [\#249](https://github.com/gnome-terminator/terminator/pull/249) ([yoavp77](https://github.com/yoavp77))
- Polish translation update [\#248](https://github.com/gnome-terminator/terminator/pull/248) ([napcok](https://github.com/napcok))
- fix the handle on the divider between horizontal panes [\#247](https://github.com/gnome-terminator/terminator/pull/247) ([mattrose](https://github.com/mattrose))
- add tests to release tarball [\#246](https://github.com/gnome-terminator/terminator/pull/246) ([mattrose](https://github.com/mattrose))
- Change how config file is saved [\#235](https://github.com/gnome-terminator/terminator/pull/235) ([planet36](https://github.com/planet36))
- Updated Estonian translation [\#226](https://github.com/gnome-terminator/terminator/pull/226) ([ookull](https://github.com/ookull))
- Fix: Key Binding Clearing in `Preferences > Keybindings` [\#224](https://github.com/gnome-terminator/terminator/pull/224) ([dkmvs](https://github.com/dkmvs))
- layout file - initial commit - work in progress [\#214](https://github.com/gnome-terminator/terminator/pull/214) ([dvdlevanon](https://github.com/dvdlevanon))
- fast resize keyboard shortcuts [\#36](https://github.com/gnome-terminator/terminator/pull/36) ([waldner](https://github.com/waldner))

## [v2.0.1](https://github.com/gnome-terminator/terminator/tree/v2.0.1) (2020-10-11)

[Full Changelog](https://github.com/gnome-terminator/terminator/compare/v2.0...v2.0.1)

TODO

## Package maintainers

With pull request #70, we removed the need for gettext binaries and switched to Python Babel.

* `gettext` and `intltool` packages are now no longer needed
* Python package `babel` is now required for building, `BabelGladeExtractor` only for updating POT

**Fixed bugs:**

- config settings lost when I cancel "Close multiple terminals" dialog [\#210](https://github.com/gnome-terminator/terminator/issues/210)

**Closed issues:**

- Feature Suggestion: Splitted screen shells based on parent [\#230](https://github.com/gnome-terminator/terminator/issues/230)
- Release 2.0 does not have signed assets [\#228](https://github.com/gnome-terminator/terminator/issues/228)
- Some files install to the wrong location [\#227](https://github.com/gnome-terminator/terminator/issues/227)
- Multi tab breaks transparent background [\#225](https://github.com/gnome-terminator/terminator/issues/225)

**Merged pull requests:**

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
- Duplicate Key Bindings are Allowed in `Preferences > Keybindings` [\#190](https://github.com/gnome-terminator/terminator/issues/190)
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
- Fix: Forbid Duplicate Key Bindings in `Preferences > Keybindings` [\#196](https://github.com/gnome-terminator/terminator/pull/196) ([dkmvs](https://github.com/dkmvs))
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
