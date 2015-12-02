.. |br| raw:: html

   <br />

.. image:: imgs/icon_gettingstarted.png
   :align: right
   :alt: Because this is the symbol learner drivers use in the UK.

.. _getting-started:

===============
Getting Started
===============

This page is an introduction and tutorial that will get you familiar
with Terminator's features. Additional functional areas are explored
in other pages, but at the end of this page you'll be getting a good
idea of the power of Terminator.

When you first start Terminator you will get a default, minimal window,
looking something like the following:

.. image:: imgs/basic_window.png

There may be some cosmetic differences, but it should look fairly
similar. It may in fact look a little too minimal to some of you, but
this is a deliberate policy. Keep the focus on the terminal, not on a
cluttered interface. This is why we don't waste space on a traditional
menu bar and toolbar. Even the terminal scrollbar and titlebar (the
red strip) can be turned off, although you do lose ease-of-access to
some of Terminators more powerful features if you do.

Many functions are triggered with keyboard shortcuts. But mousers aren't
completely abandoned. Lets look again at the basic interface, but with
the two primary menus showing:

.. image:: imgs/window_breakdown.png

.. note:: You will never see a window that looks like this, as it is
          impossible to have both menus up at the same time.

#. :ref:`context-menu` - 
   This is the main menu reached with ``right-click`` over a terminal, and
   will let you access all the settings, profiles, shortcuts and 
   configurations. It is however kept brief to avoid the mega-menus that
   sometimes grow unchecked.
#. :ref:`grouping-menu` - 
   This is reached with a ``click`` on the trio of coloured boxes in the
   titlebar. Later, when we cover Grouping and broadcasting to multiple
   terminals we will cover this properly. For now it is enough to know
   where it is and how to trigger it.

   .. note:: By default titlebars are shown. If the titlebar has been
             hidden :ref:`grouping-menu` functions will be added as a
             sub-menu to :ref:`context-menu`.

.. _context-menu:

----------------
The Context Menu
----------------

The context menu is split into five parts. The first part is the standard
Copy and Paste for text that has been highlighted with the mouse. There
are shortcuts too:

+--------+----------------------------------+
| Action | Default Shortcut                 |
+========+==================================+
| Copy   | ``Shift``\ +\ ``Ctrl``\ +\ ``C`` |
+--------+----------------------------------+
| Paste  | ``Shift``\ +\ ``Ctrl``\ +\ ``V`` |
+--------+----------------------------------+

The second section is where the fun starts. **Split Horizontally** and **Split
Vertically** are used to divide the current space for the current terminal
half. Your original terminal takes the top/left half, and a new terminal
is started and placed in the right/bottom half. You can repeat this as
often as you wish, sub-dividing down until the terminals are completely
impractical. Here's a window that is split Horizontally, Vertically, and
Horizontally again:

.. image:: imgs/split_window.png

Between the terminals you can see a space that is a splitter grab handle.
You can grab these and drag them, and the terminals will resize. In this
way Terminator acts a lot like a tiling window manger. It lets you arrange
many terminals in a single view, allowing adjustments as your needs change.

The last item in this part of the menu is to **Open tab**. This will give
you a tab like most other terminal programs. Unlike most other terminals,
in Terminator you can also split the terminals in each tab as often as you
like.

.. note:: The same effects could have been achieved with :ref:`shortcuts
          <layout-shortcuts>`, and is the case for most actions.

The third part of the menu will **Close** the current terminal. It's on
its own to prevent accidents.

The entries in the fourth part allow you to temporarily focus on one
terminal. **Zoom terminal** will zoom into the current terminal hiding all
other terminals and tabs, and increasing the the size of the font. This can
be handy to eliminate distractions, give yourself a bit more space for the
current task, or even when giving presentations or training. **Maximise
terminal** is almost identical, except that it does not increase the size of
the terminal font.

When you are zoomed or maximised it is not possible to split terminals,
or create new tabs, so the entries for those actions disappear from
the menu. So too do the zoom and maximise options, and in their place is
a **Restore all terminals** entry. This will take you back to your windows
original layout, and restore the font size if necessary.

.. warning:: An outstanding issue is that sometimes the font size
             selected when zooming in can be a bit extreme. You can use
             ``Ctrl``\ +\ ``wheelup``\ /\ ``wheeldown`` to increase and
             decrease the font size if this happens. This will not
             affect the restored font size.

The fifth part of the menu has three items. **Show scrollbar** will toggle
the scrollbar on a per terminal basis. There is also a way to define this
in the Profiles. **Preferences** lets you configure and tune Terminator to
better  suit your needs and is further described :ref:`here <preferences>`.
Lastly, **Encodings** will allow you to select a different encoding to the
default of UTF-8.

There are actually additional optional items that can be added to the
menu that will only be shown if you enable those :ref:`plugins` that
add menu items.

-----------------
Navigating around
-----------------

Apart from the obvious of clicking the terminal for focus, there are a number
of shortcuts that will move the focus around:

+-------------------+-----------------------+--------------------------------------------+
| Action            | Options               | Default Shortcut                           |
+===================+=======================+============================================+
| Move focus        | Up, Down, Left, Right | ``Alt``\ +\ ``<Arrow>``                    |
+-------------------+-----------------------+--------------------------------------------+
| Cycle to terminal | Next, Prev            | (``Shift``\ +)\ ``Ctrl``\ +\ ``Tab``       |
+-------------------+-----------------------+--------------------------------------------+
| Focus to terminal | Next, Prev            | ``Shift``\ +\ ``Ctrl``\ +\ ``N``\ /\ ``P`` |
+-------------------+-----------------------+--------------------------------------------+
| Switch to tab #   | 1 to 10               |                                            |
+-------------------+-----------------------+--------------------------------------------+
| Switch tab        | Previous, Next        | ``Ctrl``\ +\ ``PgUp``\ /\ ``PgDn``         |
+-------------------+-----------------------+--------------------------------------------+
| Context menu      |                       | ``Menu Key``                               |
+-------------------+-----------------------+--------------------------------------------+
| Help [#]_         |                       | ``F1``                                     |
+-------------------+-----------------------+--------------------------------------------+

.. [#] Although as you're reading this, I guess you figured that one out!

Once the Context menu is visible, it can be navigated with the arrow keys.

.. note:: For me the two different sets of next/prev shortcuts are a bit of a
          mystery. Something to look into.

.. _clickable-items:

^^^^^^^^^^^^^^^^^^^
Click-able items
^^^^^^^^^^^^^^^^^^^


.. image:: imgs/plugins_links.png

Terminator can make strings of text that match a pattern click-able.
The user can perform two additional actions on these when the mouse
pointer hovers overs the item:

- ``Ctrl``\ +\ ``click``
    Will try to open the item in a suitable
    program depending on what the type of the item is (see below).

- ``right-click``
    Will add two entries to :ref:`context-menu`:

    - *Open link* - Same as ``Ctrl``\ +\ ``click``

      The description might be different depending on the type of the
      item (see below).

    - *Copy address* - Copies the URL to the clipboard

      In some types this may be converted into a different form
      depending on what the item represents.

Here are the built-in formats understood:

+------------------------------+-------------+---------------------------------------------+
| **URL**                      | **Note**    | **Made up example, Don't use!**             |
+------------------------------+-------------+---------------------------------------------+
| news://user@host:port/path   |             | news://steve@news.example.org:1234/announce |
+------------------------------+-------------+---------------------------------------------+
| telnet://user@host:port/path |             | telnet://steve@insecure.example.,org:1234   |
+------------------------------+-------------+---------------------------------------------+
| nntp://user@host:port/path   |             | nntp://steve@news.example.org:1234/announce |
+------------------------------+-------------+---------------------------------------------+
| file://user@host:port/path   |             | file://steve@localhost/var/log/syslog |br|  |
|                              |             | file:///var/log/syslog                      |
+------------------------------+-------------+---------------------------------------------+
| http://user@host:port/path   | \+ https:// | http://steve@www.example.org/index.html     |
+------------------------------+-------------+---------------------------------------------+
| ftp://user@host:port/path    | \+ ftps://  | ftp://steve@ftp.example.org/var/log/        |
+------------------------------+-------------+---------------------------------------------+
| webcal://user@host:port/path |             | webcal://steve@webcal.example.org/today     |
+------------------------------+-------------+---------------------------------------------+
| wwwhostname.domain:port/path |             | www-server.example.org/index.html |br|      |
|                              |             | www.example.org                             |
+------------------------------+-------------+---------------------------------------------+
| ftphostname.domain:port/path |             | ftp-server.example.org/var/log/ |br|        |
|                              |             | ftp.example.org                             |
+------------------------------+-------------+---------------------------------------------+
| **VoIP**                                                                                 |
+------------------------------+-------------+---------------------------------------------+
| callto:user:number@path      |             | callto:steve:0123456789@not/sure/here       |
+------------------------------+-------------+---------------------------------------------+
| h323:user:number@path        |             | h323:steve:0123456789@not/sure/here         |
+------------------------------+-------------+---------------------------------------------+
| sip:user:number@path         |             | sip:steve:0123456789@not/sure/here          |
+------------------------------+-------------+---------------------------------------------+
| **E-Mail**                                                                               |
+------------------------------+-------------+---------------------------------------------+
| mailto:name@host             |             | mailto:steve@example.org                    |
+------------------------------+-------------+---------------------------------------------+
| **News**                                                                                 |
+------------------------------+-------------+---------------------------------------------+
| news:name@host:port          |             | news:steve@news.example.org:1234            |
+------------------------------+-------------+---------------------------------------------+

These are just the ones built-in by default to Terminator. The
:ref:`plugins` can extend this further with a **URL Handler**,
although strictly speaking it does not have to be a *URL* - as can be
seen from some of the above - just a well defined pattern that can be
matched.

---------------------------
Changing the current layout
---------------------------

I've already used the term *layout* a few times in this page already.
I should define what exactly is meant by a layout.

A layout describes the collection of windows in the current process,
the tabs, and how the windows and tabs are divided up into terminals.
It also includes the positions, dimensions, as well as other aspects
related to how Terminator looks.

Besides the items in the :ref:`context-menu` there are three main
methods to adjust the layout.

^^^^^^^^^^^^^^^^^^^
Using the splitters
^^^^^^^^^^^^^^^^^^^

So, by now you've probably made a few splits and used the mouse to drag them
about, and you now have something resembling the following, minus the highlights:

.. image:: imgs/rebalance_01.png

Terminator lets us *rebalance* the terminals, equally dividing the available
space between the *siblings*.
 
The different highlighting shows the siblings. The key thing to understand is
that the blue splitters are considered siblings, which are *children* of the
green *parent*. The green is itself a child of the red parent.  By double-clicking
the splitter, the space will be divided evenly between the siblings. So,
double-clicking any of the blue splitters will give:

.. image:: imgs/rebalance_02.png

If instead we ``double-click`` on the green splitter, we get:

.. image:: imgs/rebalance_03.png

But there's more! We can use two modifier keys to rebalance more collections of
siblings. ``Shift``\ +\ ``double-click`` the splitter and all children,
grandchildren, and so on, will be rebalanced. ``Super``\ +\ ``double-click`` and
all parents, grandparents, and so, on, will be re-balanced. You guessed it! 
``Shift``\ +\ ``Super``\ +\ ``double-click`` and all visible terminals
will be rebalanced. It will not affect terminals in other windows or tabs.

``Shift``\ +\ ``double-click`` on green:

.. image:: imgs/rebalance_04.png

``Super``\ +\ ``double-click`` on green:

.. image:: imgs/rebalance_05.png

``Shift``\ +\ ``Super``\ +\ ``double-click`` on green:

.. image:: imgs/rebalance_06.png

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Dragging and dropping a terminal
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

There are two ways to drag a terminal from one location to another with in the
window. The simplest is to use the titlebar at the top of each terminal. Simply
``click-drag``\ , and you will be able to hover over the other terminals and drop
the dragged terminal to move it:

.. image:: imgs/dragterminal_01.png

Here you can see a preview of the dragged terminal - scaled if large - and shading
to show which area it will cover, which can be the top, bottom, left or right of
an existing terminal.

The above action results in the following:

.. image:: imgs/dragterminal_02.png

The other way to drag a terminal can be done from within the terminal with
``Ctrl``\ +\ ``right-click-drag``\ . With this method once you start the
drag, you *must* release the ``Ctrl`` key *before* releasing the
``right-mouse-button``. If you do not the drag will cancel.

You can drag between tabs by initiating a drag and hovering over the tab.
Terminator will switch to the tab under the cursor, you can then drag to the
desired position, and the terminal can be dropped.

You can also drag between Terminator windows *provided the windows are part
of the same process*. By default all windows will be part of the same process.
Windows will not be part of the same process if you deliberately turn off
the :ref:`DBus` interface with the :ref:`Preferences <preferences>` or the
:ref:`command-line-options` when starting Terminator up. :ref:`Layouts <layouts>`
are also currently isolated at a process level for technical reasons.

.. _layout-shortcuts:

^^^^^^^^^^^^^^^^^^
Using the keyboard
^^^^^^^^^^^^^^^^^^

Of course, with Terminator being a terminal application, it makes sense to keep
your hands on the keyboard as much as possible. So there are many shortcuts that
you can tailor to your own preference. Here are the ones that will affect the
layout:

+-------------------+--------------------------+--------------------------------------------------+
| Action            | Options                  | Default Shortcut                                 |
+===================+==========================+==================================================+
| New instance [#]_ |                          | ``Super``\ +\ ``I``                              |
+-------------------+--------------------------+--------------------------------------------------+
| New window        |                          | ``Shift``\ +\ ``Ctrl``\ +\ ``I``                 |
+-------------------+--------------------------+--------------------------------------------------+
| New Tab           |                          | ``Shift``\ +\ ``Ctrl``\ +\ ``T``                 |
+-------------------+--------------------------+--------------------------------------------------+
| Split terminal    | Horizontally, Vertically | ``Shift``\ +\ ``Ctrl``\ +\ ``O``\ /\ ``E``       |
+-------------------+--------------------------+--------------------------------------------------+
| Hide window [#]_  |                          | ``Shift``\ +\ ``Ctrl``\ +\ ``Alt``\ +\ ``A``     |
+-------------------+--------------------------+--------------------------------------------------+
| Close window      |                          | ``Shift``\ +\ ``Ctrl``\ +\ ``Q``                 |
+-------------------+--------------------------+--------------------------------------------------+
| Close terminal    |                          | ``Shift``\ +\ ``Ctrl``\ +\ ``W``                 |
+-------------------+--------------------------+--------------------------------------------------+
| Toggle fullscreen |                          | ``F11``                                          |
+-------------------+--------------------------+--------------------------------------------------+
| Resize terminal   | Up, Down, Left, Right    | ``Shift``\ +\ ``Ctrl``\ +\ ``<Arrow>``           |
+-------------------+--------------------------+--------------------------------------------------+
| Rotate terminals  | (Anti-)Clockwise         | (\ ``Shift``\ +\ )\ ``Super``\ +\ ``R``          |
+-------------------+--------------------------+--------------------------------------------------+
| Move Tab          | Left, Right              | ``Shift``\ +\ ``Ctrl``\ +\ ``PgUp``\ /\ ``PgDn`` |
+-------------------+--------------------------+--------------------------------------------------+
| Zoom terminal     |                          | ``Shift``\ +\ ``Ctrl``\ +\ ``Z``                 |
+-------------------+--------------------------+--------------------------------------------------+
| Maximise terminal |                          | ``Shift``\ +\ ``Ctrl``\ +\ ``X``                 |
+-------------------+--------------------------+--------------------------------------------------+

.. [#] This is a separate process. As such, drag and drop will not work
       to or from this new window, or subsequent windows launched using
       the ``Shift``\ +\ ``Ctrl``\ +\ ``I`` while the focus is in the
       new instance.

.. [#] Hide window will currently only work on the first window of the
       first terminator instance that you start. That is because at
       present it binds the shortcut globally (it has to, or it cannot
       unhide) and this can only be done once. This may change in
       future.

-----------------------------------
Resetting the terminal
-----------------------------------

There are two shortcuts available for fixing the terminal if it
starts to misbehave.

+---------------+----------------------------------+
| Action        | Default Shortcut                 |
+===============+==================================+
| Reset         | ``Shift``\ +\ ``Ctrl``\ +\ ``R`` |
+---------------+----------------------------------+
| Reset + Clear | ``Shift``\ +\ ``Ctrl``\ +\ ``G`` |
+---------------+----------------------------------+

-----------------------------------
The scrollbar and scrollback buffer
-----------------------------------

As already mentioned, there is a :ref:`Context Menu <context-menu>`
item to toggle the scrollbar. There is also a shortcut listed here.

In addition there are shortcuts for moving up and down in the
scrollback buffer with more flexibility:


+---------------------+----------+-------------------------------------+
| Action              | Options  | Default Shortcut                    |
+=====================+==========+=====================================+
| Toggle scrollbar    |          | ``Shift``\ +\ ``Ctrl``\ +\ ``S``    |
+---------------------+----------+-------------------------------------+
| Page [VS]_          | Up, Down | ``Shift``\ +\ ``PgUp``\ /\ ``PgDn`` |
+---------------------+----------+-------------------------------------+
| X Lines [VS]_ [XL]_ | Up, Down | ``wheelup``\ /\ ``wheeldown``       |
+---------------------+----------+-------------------------------------+
| Page [TS]_          | Up, Down |                                     |
+---------------------+----------+-------------------------------------+
| Half page [TS]_     | Up, Down |                                     |
+---------------------+----------+-------------------------------------+
| Line [TS]_ [MS]_    | Up, Down |                                     |
+---------------------+----------+-------------------------------------+

.. [VS] **VTE Shortcuts:** Default actions from VTE that are not configurable.
.. [XL] **X Lines:** Where X may vary depending on distribution. On mine
        it is 4.
.. [TS] **Terminator Shortcuts:** Additional movement options from Terminator
        that are configurable.
.. [MS] **Masked Shortcuts:** VTE provides default shortcuts for line up/down,
        on ``Shift``\ +\ ``Ctrl``\ +\ ``Arrow Up/Dn``, but they are masked
        by shortcuts for resizing terminals. You can disable or reassign
        the resizing shortcuts to regain access to the VTE default.

-----------------------------------
Search the buffer
-----------------------------------

It is possible to search the buffer, although at this time there is
a limitation that the found string is not highlighted.

+--------------+----------------------------------+
| Action       | Default Shortcut                 |
+==============+==================================+
| Begin search | ``Super``\ +\ ``Ctrl``\ +\ ``F`` |
+--------------+----------------------------------+

Resulting in a search bar at the bottom of the focused terminal:

.. image:: imgs/search.png

This has buttons for moving back and forward through the results, as
well as an option to wrap the search around.

-----------------------------------
Zooming the terminal
-----------------------------------

As mentioned above it is possible to zoom into and out of a terminal.
There are also some modifiers to zoom more than just the current
terminal.

+------------------+------------------------------------------+
| Action           | Default Shortcut                         |
+==================+==========================================+
| Target in [#]_   | ``Ctrl``\ +\ ``+``\ /\ ``wheelup``       |
+------------------+------------------------------------------+
| Target out       | ``Ctrl``\ +\ ``-``\ /\ ``wheeldown``     |
+------------------+------------------------------------------+
| Target reset     | ``Ctrl``\ +\ ``0``                       |
+------------------+------------------------------------------+
| +Receivers in    | ``Shift``\ +\ ``Ctrl``\ +\ ``wheelup``   |
+------------------+------------------------------------------+
| +Receivers out   | ``Shift``\ +\ ``Ctrl``\ +\ ``wheeldown`` |
+------------------+------------------------------------------+
| +Receivers reset | N/A (TBD, plus in/out)                   |
+------------------+------------------------------------------+
| All in           | ``Super``\ +\ ``Ctrl``\ +\ ``wheelup``   |
+------------------+------------------------------------------+
| All out          | ``Super``\ +\ ``Ctrl``\ +\ ``wheeldown`` |
+------------------+------------------------------------------+
| All reset        | N/A (TBD, plus in/out)                   |
+------------------+------------------------------------------+

.. [#] Target terminal is the current terminal when using the
       keyboard shortcuts, or the terminal under the mouse when using
       the ``wheelup``\ /\ ``wheeldown``. 

--------------
Setting Titles
--------------

If you're anything like me, you've spent time clicking among the half a
dozen different terminals in the taskbar, trying to find the right one.
Or maybe for you it is with tabs.

In Terminator you can rename three things:

+----------------+---------------------------+--------------------------------+
| Edit           | Mouse                     | Default Shortcut               |
+================+===========================+================================+
| Window title   | N/A                       | ``Ctrl``\ +\ ``Alt``\ +\ ``W`` |
+----------------+---------------------------+--------------------------------+
| Tab title      | ``double-click`` tab      | ``Ctrl``\ +\ ``Alt``\ +\ ``A`` |
+----------------+---------------------------+--------------------------------+
| Terminal title | ``double-click`` titlebar | ``Ctrl``\ +\ ``Alt``\ +\ ``X`` |
+----------------+---------------------------+--------------------------------+

Additionally all three can be saved/loaded from a :ref:`layout <layouts>`,
or the window title can be set using a
:ref:`command line option <command-line-options>`.

.. _insert-termnum_shortcut:

-----------------------------------
Insert terminal number
-----------------------------------

These shortcuts let you enumerate your terminals. It is handy if you
need to login to a number of sequentially numbered machines. With
multiple terminals the ordering may seem strange, but this is due to
the nature of the splitting and the order in which the splits were
performed.

+------------------------------------+---------------------+
| Action                             | Default Shortcut    |
+====================================+=====================+
| Insert terminal number             | ``Super``\ +\ ``1`` |
+------------------------------------+---------------------+
| Insert zero padded terminal number | ``Super``\ +\ ``0`` |
+------------------------------------+---------------------+

These actions can also be done from :ref:`grouping-menu`.

-----------------------------------
Next/Prev profile
-----------------------------------

It is possible to cycle back and forth through the available profiles
that are defined in the :ref:`prefs-profiles` tab of the :ref:`preferences`,
changing the behaviour and appearance of the current terminal.

+------------------+------------------+
| Action           | Default Shortcut |
+==================+==================+
| Next profile     |                  |
+------------------+------------------+
| Previous profile |                  |
+------------------+------------------+

In both cases there is currently no default shortcut set. I'm not
convinced they would be used often enough to warrant assigning
them. For those that find it useful, the feature is there to be
configured.

