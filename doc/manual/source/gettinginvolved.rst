.. image:: imgs/icon_gettinginvolved.png
   :align: right
   :alt: Saefty first when breaking out the power tools.

=============================
Getting involved
=============================

There are many ways to help out, and they don't all involve coding.

-----------------------------
Translations
-----------------------------

Sprechen Sie Deutsch?

Awesome! I've been getting my head around the whole translation
bit (English monoglot I'm afraid), and as a result there has been
a lot of churn in the translations. So what are you waiting for?

Speak some other language? Take a look at
https://translations.launchpad.net/terminator because you might
just be the <insert language here> speaker that we're looking for.

-----------------------------
Improve icons/artwork
-----------------------------

OK, so while the main icon contributed by Cory Kontros is really
good, my hacks of it are... not so good. I'm no artist, but I do
appreciate them. So if you think you could apply some polish and
a cohesive design to this manuals page header images, please, give
it a go. It may only be to take the existing icon and to make it
suck less.

The only thing I would ask is that you maintain the main icon as
a base like I have done.

-----------------------------
Terminator action shots
-----------------------------

This one's just for "PR" purposes. I want to see famous/awesome
people kicking ass *and* chewing bubble-gum with Terminator in the
mix.

If you spot it in a TV show, movie, or a news article I want to
know. Maybe you're even the famous/awesome person, in which case
drop me a note.

It will warm the cockles of my heart to know that Terminator made
life easier for people who do the really important stuff like
discovering new particles (CERN? Hello?), boldly going (NASA? Come
in Houston), or wrangle 2 more frames per second from Half-Life 3
(Valve? Confirmed?)

Here's the ones I've spotted and noted (I've seen quite a few others
previously, but never thought to note them)

- `MindMaze`_ - VR / mind-reading.
    Visible in the background of the video, and in an image lower down
    the page. (The Verge)

.. _MindMaze: http://www.theverge.com/2015/3/3/8136405/mind-maze-mind-leap-thought-reading-virtual-reality-headset

-----------------------------
Manual updates
-----------------------------

This manual is a new endeavour to fully document all the nooks and
crannies of Terminator. As such, there may be things that are missing,
incorrect, not explained clearly, or need expanding.

Suggestions, or updates are welcome.

I had a little exposure at work to Sphinx, so I thought I'd dig in
a bit deeper and learn  a bit about it. So far I'm happy enough, so
till further notice this manual will remain in this format.

If you're feeling like a loquacious polyglot you could attempt to
translate the whole manual. So far I haven't tested it, but in
principle, just do a checkout of the trunk, and do a full copy of
the ``doc/manual`` folder to ``doc/manual_XXXX`` where XXXX is the
i18n language code. This is usually just the two or three letters of
the language code, but sometimes has the region too... Or something
else entirely in a couple of cases.  A couple of examples::

  pt            - Portugese
  pt_BR         - Brazilian Portugese
  ca            - Catalan
  ca@valencia   - Catalan (Dialect specific to Valencia?)
  
Then just translate away, and take new screen grabs to replace the
British English ones I've done. If someone was to make a serious
effort to translate the manual, I'm sure we can get it included.

The Help shortcut checks the LANGUAGE environment variable, and tries
those folders in order, before falling back gracefully to the default
manual, which is British English anyway::

  LANGUAGE=en_GB:en

So this is going to try:

+ *html_en_GB* - the non-existent British English folder
+ *html_en* - the non-existent generic English folder
+ *html* - the default document that happens to be in British English

.. note:: Although the source is in a folder beginning with ``manual``,
          that gets replaced with ``html`` for installation.

.. note:: If there are any Americans offended by correct spelling,
          they are more than welcome to create an Americanised
          version, and I'll relegate it to the en_US folder. The
          default will remain British English.

In order to create the html for the manual, you must have the
sphinx_rtd_theme package installed. This does not appear to be
packaged for Ubuntu 14.04 LTS as far as I can tell. This means you
must install it using the pip tool. This may need installing on your
system too with::

    sudo apt-get install python-pip

Once that is installed you can install the theme with::

    sudo pip install sphinx-rtd-theme

This will take care of installing the theme and it's dependencies.

.. warning:: On Ubuntu this also installed a newer version of *Sphinx*
             under the ``/usr/local`` folder. This caused a bit of
             confusion at one point, so be aware.

-----------------------------
Testing
-----------------------------

Just use it, explore the features, and complain when they don't work.

We actually have quite a lots of outstanding issues, and in many
cases I can't reproduce due to either lack of info, differences in
environment, lack of information, or because the bug is so old the
original raiser has moved on and not available for questions.

I'm particularly interested in cases where I can't even see that
something is an issue, such as:

- *Right-to-Left* - I can force Terminator to Arabic, and everything
  flips around, but I have no idea if it looks "right" to a native
  speaker. Frankly it just looks *weird!*
- *HighContrast* - Again, I can switch to it, but perhaps I'm not
  appreciating the needs of that group.
- *Accessibility* - People using only a keyboard, or only a mouse,
  on-screen keyboards, text-to-speech, speech-to-text, and so on.

-----------------------------
Bugs
-----------------------------

- **Fixing** - OK, so yeah, this is coding.
- **Reproduce and improving** - Sometimes bugs are lacking info to
  reproduce, or my system is too different. Or perhaps the original
  poster has moved on because we haven't fixed their pet peeve fast
  enough.
- **Triaging** - It's one of the less glamorous jobs, but someone's
  gotta do it. Shepherd bugs to the point where it has a priority,
  a milestone, reproduction steps, confirmation, submitted patches
  validated, and so on.

See https://bugs.launchpad.net/terminator

-----------------------------
Plugins
-----------------------------

Ahem... Yeah... More coding...  

Some :ref:`plugins` may have room for improvement, or perhaps you have
an idea for a neat plugin no-one else has done.

-----------------------------
Main Application Development
-----------------------------

Oh come on... Coding? Again!

I see lots of people say how Terminator is really good, and it is,
but like anything, it could be better!

To give an idea, as I write this manual in July 2015, there are 83
`wishlist items`_.

.. note:: Just because an item is marked as wishlist, it doesn't
          mean that a great deal of thought has been put into the
          appropriateness of the idea on my side. It may be impossible,
          or not a good fit, or just plain bat-sh!t crazy. If you
          want to pick up a wishlist item that looks like a lot of
          work (especially if it makes fundamental changes to the
          Terminator ethos) it's probably best to check first that
          your approach is good, and has a realistic chance of being
          merged.

Some of these wishlist items are also in my own text file of "Things
to do" / "Big bag of crazy", which as of August 2015, revision 1598,
looks like this::

    Enhancements which may or may not have a wishlist item
    ======================================================
    Completely new features
        Add libunity quicklist of saved layouts
            https://wiki.ubuntu.com/Unity/LauncherAPI#Python_Example
            http://www.techques.com/question/24-64436/Refreshing-of-Dynamic-Quicklist-doesn%27t-work-after-initialization
            http://people.canonical.com/~dpm/api/devel/GIR/python/Unity-3.0.html
            Possibly use the progress bar and or counter for something too.
        Add an appindicator menu for launching sessions.

    Layouts
        Layout Launcher
            Could bind the shortcut as a global toggle to hide show
            Could save
                window position/size
                hidden status
                always on top
                pin to visible workspace
        Layout needs to save/load more settings
            Per layout?
                Group mode status (all, group, off)
                Split to this group
                Autoclean groups
            Per window
                always on top
                pin to visible workspace
            Per tab
            Per terminal
                Store the custom command and working directory when we load a layout, so making small changes and saving doesn't lose everything.
                It could be possible to detect the current command and working directory with psutil, but could be tricky. (i.e. do we ignore bash?)
        A per layout "save on exit" option to always remember last setup/positions etc. Probably requires above to be done first.

    Missing shortcuts:
        Just shortcut:
            Context menu (in addition to Windows menu button - not always available on all keyboards)
            Group menu
            Open preferences
            Change tab text (#1054300-patch), titlebar text, group name
            Toggle titlebar visibility
            Equalise the splitters (siblings/siblings+children/siblings+parents,all)
            Zoom +receiver in/out/reset
            Zoom all in/out/reset
        New code:
            Open a shortcut help overlay (Ctrl-F1?)
            Insert tab text, titlebar text, group name value into terminal(s)
            Last terminal / tab / window(again to jump back to original) #1440049
            Limit broadcast group/all to current tab / window (toggle)
            Broadcast temporarily off when maximised or zoomed to single term (toggle)

    Titlebar
        Add large action/status icons for when titlebar is bigger.
        Improve the look/spacing of the titlebar, i.e. the spacing around/between elements

    Tabs
        right-click menu replicating GNOME-Terminals (move left/right, close, rename)

    Menus
        Add acellerators (i.e. "Shift+Ctr+O") might look too cluttered.

    Preferences
        Profiles
            Add preselection to the profile tab
        Layouts
            Have changing widgets depending on what is selected in the tree
            Terminal title editable
            Button in prefs to duplicate a layout
            Ordering in list
        Keybindings
            Add a list of the default keybindings to the Preferences -> Keybindings window?
        Option for close_button_on_tab in prefs. (needs tab right-click menu first
        Option to rebalance siblings on a split (don't think children or ancestors make sense)
        Figure out how to get the tree view to jump to selected row for prefseditor

    Config file
        Items should be sorted for saving. Easier for comparing and spotting changes.

    Plugins
        Give plugins ability to register shortcuts
        Custom Commands is blocking, perhaps make non-blocking

    Drag and Drop
        Terminal without target opens new window
        Tab to different/new window depending on target

    Major architectural
        Improve DBus interface, add coordination between sessions, i.e.:
            multiple DBus ports? register them with a master DBus session, be able to query these, etc
            be able to drive them more with command line commands, and not just from within own shell
            Remotinator improvements
        Abstract out the session/layout allowing multiple logical layouts in the same process to reduce resource used
            This is a big piece of work, as a lot of the Terminator class would need seperating out.
        Hide window should find the last focussed window and hide that. Second hit unhides and focusses it
            Add a power hide to hide all of shortcut bound instances windows
            Use the dbus if available to hide the current active window, then unhide it on second shortcut press
            If the dbus is available:
                The hide will go to the focussed instance, instead of the first to grab the shortcut
                Add a super power hide to hide all Terminator windows
                In both cases a second shortcut unhides whatever was hidden

    Split with command / Inherit command/workdir/groups etc

    Somehow make Layout Launcher, Preferences, & poss. Custom Commands singleton/borg (possibly use dbus)

    When in zoomed/maximised mode
        Perhaps the menu could contain a quick switch sub menu, rather than having to Restore, right-click, maximise
        Shortcuts for next/prev,up/down/left/right, etc. How should they behave

    All non main windows to be changed to glade files

    For me the two different sets of next/prev shortcuts are a bit of a mystery.

    Let window title = terminal titlebar - perhaps other combos. Some kind of %T %G %W substitution?

    If we can figure out how to do arbritrary highlighting, perhaps we can get a "highlight differences" mode like used to exist in ClusTerm.
        This could also be limted to highlighting diffs between those in the same group.


    Issues encountered where not aware of any LP bug
    ================================================

    BUG: Zoom and maximise do not work if single terminal in a tab, gtk2 & gtk3. Intentional?

    BUG: Zoom on a split non-maximised window on just one terminal causes window size changes if zoomed terminal font is
         bigger that the non-zoomed window.

    BUG: Groups: Create two tabs with splits. Super+G (group all), move to other tab and Super+T (group tabs), move back and type
        Output in tab group too. Also for custom groups.
        Ungrouping all also nukes changed groups. Right?
        Also with Super+T and changing one terms group, still receives input, and loses custom group when turning off tab group.

    BUG: Hide on lose focus broken. LP#843674
        focus-out signal callback defers (idle_add) the call to hide.
        If one of our own windows/menus pops up, an inhibit flag is set.
        When the window/menu is closed we call a deferred hide on the main window
        In the deferred function, we check if we now have focus, and do not hide
        In the deferred function, we check if inhibit is set and do not hide
        Could create a popup_menu subclass that sets the inhibiter

So as you can see, still lots of room for improvements, and plenty of
ideas if you are trying to find small starter tasks.

.. _wishlist items: https://bugs.launchpad.net/terminator/+bugs?field.searchtext=&orderby=-importance&search=Search&field.status%3Alist=NEW&field.status%3Alist=CONFIRMED&field.status%3Alist=TRIAGED&field.status%3Alist=INPROGRESS&field.status%3Alist=INCOMPLETE_WITH_RESPONSE&field.status%3Alist=INCOMPLETE_WITHOUT_RESPONSE&field.importance%3Alist=WISHLIST&assignee_option=any&field.assignee=&field.bug_reporter=&field.bug_commenter=&field.subscriber=&field.structural_subscriber=&field.tag=&field.tags_combinator=ANY&field.has_cve.used=&field.omit_dupes.used=&field.omit_dupes=on&field.affects_me.used=&field.has_patch.used=&field.has_branches.used=&field.has_branches=on&field.has_no_branches.used=&field.has_no_branches=on&field.has_blueprints.used=&field.has_blueprints=on&field.has_no_blueprints.used=&field.has_no_blueprints=on

-----------------------------
GTK3 Port
-----------------------------

Last coding one, I promise!

After some sterling work by Egmont Koblinger, one of the VTE
developers, he came up with a very large patch for rudimentary GTK3
support. A number of things were incomplete or broken, but it got it
far enough along that it was no longer an insurmountable cliff face.

Since then I have resolved to port fixes and features between the
two versions. As I do this I explore and find outstanding issues with
the port, and it is slowly becoming more usable.

Eventually the GTK2 version of Terminator will go into a
deprecated/maintenance mode. Unfortunately due to needing a relatively
new version of libvte, that switch will not be in the immediate
future. I'm running trusty (14.04 LTS) and even there I had to build
libvte 0.38 from source. This makes the GTK3 out of reach for the
"Joe Bloggs" of the world. I could try and maintain my own PPA of the
component, but that doesn't help Fedora/OpenSUSE/Arch etc. users.
Even getting "Joe Bloggs" to add a PPA can be a struggle.

And for a real nightmare, I tried to compile the 0.40 version and the
thing lit up with a smorgasbord of items where my installed packages
were not new enough.

If you are feeling brave and adventurous, there are some instructions
in `comment #15`_ of the `porting bug`_ that will help you get the
GTK3 version running. Assistance knocking off the remaining rough
edges will be very much appreciated.

For the record, as of August 2015, with the `gtk3 branch`_ at revision
1577, these are the outstanding items::

    Outstanding GTK3 tasks/items/reviews etc remaining
    ===================================================
    Outstanding trunk revisions: 1599-1602 (minus manual, that comes later), 1613-1615, 1617
    If titlebar text wider than window, the visual bell icon does not appear
    If editing label in titlebar, the whole layout gets distorted until finished, then snaps back to mostly correct layout
    In High contrast mode the titlebar background only works over the group button
    In High contrast mode the titles are invisible for terminals with a group
    Fix/reimplement the DBUS for GTK3. GI seems incomplete with no Server. Try to get old style working again.
    Need to go through all the Gtk.STOCK_* items and remove. Deprecated.
    Homogeneous_tabbar removed? Why?
    Need to set the version requirements - how? needed?
    terminal.py:on_vte_size_allocate, check for self.vte.window missing. Consequences?
    terminal.py:understand diff in args between old fork and new spawn of bash. Consequences?
    VERIFY(8)/FIXME(7) FOR GTK3 items to be dealt with

    For future with vte0.40+ - reimplement/restore the word_chars stuff.

    Not fixable so far as I can see
    ===============================
    [Function N/A in 0.38+, will it return?] visible_bell - removed and not mentioned. Check capability not possible, or can be faked.

Once the GTK3 port is done there is also a long overdue port to
Python3, especially in light of some distributions trying to
eliminate Python2 from the base installs. Yes, Python2 will be with
us for a long time yet, but this should serve as a warning.

.. _comment #15: https://bugs.launchpad.net/terminator/+bug/1030562/comments/15
.. _porting bug: https://bugs.launchpad.net/terminator/+bug/1030562
.. _gtk3 branch: https://code.launchpad.net/~gnome-terminator/terminator/gtk3

--------------------------
Terminator API Docs
--------------------------

Strictly speaking this isn't an API as such, because it is just using
sphinx-apidoc over the Terminator code base. It's perhaps helpful to
have this as a document that can be browsed.

`Terminator API docs`_

As it stands, this is rather incomplete, or too terse with no examples
given. If you look at the terminatorlib.configobj package, you will
see fairly extensive documentation, along with walk-throughs, etc. This
particular package was written elsewhere, and brought into Terminator
to provide configuration handling.

There are also some aspects of the way this document builds that I'm
not too happy about. The seemingly unnecessary ``terminatorlib``
root-node in the side bar; the lack of class/method links in the
sidebar; all ``.py`` files on the same page (this can be changed, but
then even less is displayed in the sidebar.) If you can help, join
the A-Team... Or better yet, send me some changes that fix this.

.. _Terminator API docs: ../apidoc/index.html

--------------------------
Other Docs for Developers
--------------------------

Here is a list of some useful sets of documentation:

+---------------------------+-------------------------------------------------------------------+
| **General**                                                                                   |
+---------------------------+-------------------------------------------------------------------+
| Python                    | https://docs.python.org/release/2.7/index.html                    |
+---------------------------+-------------------------------------------------------------------+
| GNOME Dev. Center         | https://developer.gnome.org/                                      |
+---------------------------+-------------------------------------------------------------------+
| Bazaar DVCS               | http://doc.bazaar.canonical.com/en/                               |
+---------------------------+-------------------------------------------------------------------+
| **GTK 2**                                                                                     |
+---------------------------+-------------------------------------------------------------------+
| PyGTK                     | https://developer.gnome.org/pygtk/stable/                         |
+---------------------------+-------------------------------------------------------------------+
| VTE for GTK 2             | https://developer.gnome.org/vte/0.28/                             |
+---------------------------+-------------------------------------------------------------------+
| **GTK 3**                                                                                     |
+---------------------------+-------------------------------------------------------------------+
| GObject Introspection     | https://wiki.gnome.org/Projects/GObjectIntrospection              |
+---------------------------+-------------------------------------------------------------------+
| GObject                   | https://developer.gnome.org/gobject/stable/                       |
+---------------------------+-------------------------------------------------------------------+
| PyGObject Introspection   | https://wiki.gnome.org/Projects/PyGObject                         |
+---------------------------+-------------------------------------------------------------------+
| PyGObject                 | https://developer.gnome.org/pygobject/stable/                     |
+---------------------------+-------------------------------------------------------------------+
| Many PIGO autodocs        | http://lazka.github.io/pgi-docs/                                  |
+---------------------------+-------------------------------------------------------------------+
| GDK3 Ref. Manual          | https://developer.gnome.org/gdk3/stable/                          |
+---------------------------+-------------------------------------------------------------------+
| GTK3 Ref. Manual          | https://developer.gnome.org/gtk3/stable/index.html                |
+---------------------------+-------------------------------------------------------------------+
| Python GTK+ 3 Tutorial    | http://python-gtk-3-tutorial.readthedocs.org/en/latest/index.html |
+---------------------------+-------------------------------------------------------------------+
| VTE for GTK 3             | https://developer.gnome.org/vte/0.38/                             |
+---------------------------+-------------------------------------------------------------------+

















