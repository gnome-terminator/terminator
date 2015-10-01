.. image:: imgs/icon_faq.png
   :align: right
   :alt: Because curious cats ask clever code monkeys.

==========================
Frequently Asked Questions
==========================

Here I'll try to list some common questions that get asked for.

------
Why...
------

...is there another terminal program called Terminator?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

There is `another terminal`_ project programmed in Java. It was begun a
bit before this project, but when this projects creator searched the
name I guess the other project did not come up. I don't know the details,
but this project was always Terminator to me. I haven't received
complaints from the other project, although they do get some people
asking in their Groups for support on this project. Please don't do that
folks.

I have contemplated a name change, although this project has a lot of
visibility with it's current name, and it is hard to come up with a decent
`alternative`_.

.. _another terminal: https://code.google.com/p/jessies/wiki/Terminator
.. _alternative: http://gnometerminator.blogspot.com/2015/09/whats-in-name.html

...write in Python? It's slow/bloated/bad?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Performance
~~~~~~~~~~~

Profiles were configured with command ``bash -c exit``, and the
 commands run a couple of times to get the caches loaded up.

GNOME-Terminal::

  time for i in {1..30} ; do gnome-terminal --profile=Quickexit; done
  
  real    0m10.606s

Terminator::

  time for i in {1..30} ; do terminator -g deletemeconfig -p Quickexit; done
  
  GTK2: real    0m11.928s A smidgen slower.
  GTK3: real    0m10.885s Yeah, basically identical!

Cold start, using ``sync && echo 3 > /proc/sys/vm/drop_caches`` before
each run, then launching a single timed instance.

Gnome-Terminal::

  time gnome-terminal --profile=Quickexit
  
  real    0m7.628s (approx median, there was a strange variance for GT, between 5 and 9 secs)

Terminator::

  time terminator -g deletemeconfig -p Quickexit
  
  GTK2: real    0m11.390s (median of 3x)
  GTK3: real    0m11.264s (median of 3x)

OK, so this is the once place you would notice an appreciable
difference. How often do you start these things with completely empty
caches/buffers?

In GTK2 there is a known issue which slows the cat'ing of large files
quite a bit. The VTE in GTK3 Terminator is the *exact* same widget
GNOME-Terminal uses, so this will get better, as and when we move
fully to the in-progress GTK3 port. I should point out that this
performance deficit is not due to the Python interpreter, or the
Terminator Python code, but is solely down to the compiled C code VTE
widget.

Memory use - The dumb way
~~~~~~~~~~~~~~~~~~~~~~~~~

GNOME-Terminal:: 

    for i in {1..100} ; do gnome-terminal --disable-factory & done

   root@pinpoint:~# sync && echo 3 > /proc/sys/vm/drop_caches && free           # Before startup
                 total       used       free     shared    buffers     cached
    Mem:       3102404    1388776    1713628       4052        164      45340
    -/+ buffers/cache:    1343272    1759132
    Swap:      3121996     788704    2333292
    root@pinpoint:~# sync && echo 3 > /proc/sys/vm/drop_caches && free          # After startup
                 total       used       free     shared    buffers     cached
    Mem:       3102404    2439524     662880      57196       1240      99212
    -/+ buffers/cache:    2339072     763332
    Swap:      3121996     751440    2370556
    root@pinpoint:~# sync && echo 3 > /proc/sys/vm/drop_caches && free          # After kill
                 total       used       free     shared    buffers     cached
    Mem:       3102404    1466536    1635868       4796        160      45912
    -/+ buffers/cache:    1420464    1681940
    Swap:      3121996     751020    2370976

    Used (used mem -buffers/cache + swap)
        Before start: 2131976
        After start : 3090512 = 958536 kbytes, 936 Mbytes / 9.36 MBytes/instance
        After kill  : 2171484 =  39508 kbytes,  38 Mbytes not recovered

Terminator GTK2::

    for i in {1..100} ; do terminator -g deletemeconfig -u & done

    root@pinpoint:~# sync && echo 3 > /proc/sys/vm/drop_caches && free
                 total       used       free     shared    buffers     cached
    Mem:       3102404    1313456    1788948       4284        152      43844
    -/+ buffers/cache:    1269460    1832944
    Swap:      3121996     736844    2385152
    root@pinpoint:~# sync && echo 3 > /proc/sys/vm/drop_caches && free
                 total       used       free     shared    buffers     cached
    Mem:       3102404    2866552     235852      19484       1084      65408
    -/+ buffers/cache:    2800060     302344
    Swap:      3121996     736340    2385656
    root@pinpoint:~# sync && echo 3 > /proc/sys/vm/drop_caches && free
                 total       used       free     shared    buffers     cached
    Mem:       3102404    1317724    1784680       4284        152      43464
    -/+ buffers/cache:    1274108    1828296
    Swap:      3121996     736304    2385692

    Used (used mem -buffers/cache + swap)
        before start: 2006304
        after start : 3536400 = 1530096 kbytes, 1494 Mbytes / 14.94 MBytes/instance
        after kill  : 2010412 =    4108 kbytes,    4 Mbytes not recovered

Terminator GTK3::

    for i in {1..100} ; do terminator -g deletemeconfig -u & done

    root@pinpoint:~# sync && echo 3 > /proc/sys/vm/drop_caches && free
             total       used       free     shared    buffers     cached
    Mem:       3102404    1467204    1635200       4816        120      46132
    -/+ buffers/cache:    1420952    1681452
    Swap:      3121996     751000    2370996
    root@pinpoint:~# sync && echo 3 > /proc/sys/vm/drop_caches && free
                 total       used       free     shared    buffers     cached
    Mem:       3102404    2848372     254032       7216        960      52652
    -/+ buffers/cache:    2794760     307644
    Swap:      3121996     750016    2371980
    root@pinpoint:~# sync && echo 3 > /proc/sys/vm/drop_caches && free
                 total       used       free     shared    buffers     cached
    Mem:       3102404    1483388    1619016       4820        148      46084
    -/+ buffers/cache:    1437156    1665248
    Swap:      3121996     749828    2372168

    Used (used mem -buffers/cache + swap)
        before start: 2171952
        after start : 3544776 = 1372824 kbytes, 1340 Mbytes / 13.41 MBytes/instance
        after kill  : 2186984 =   15032 kbytes,   15 Mbytes not recovered

OK, so yes, there is more overhead. We did just start 100 Python
interpreters! As titled, this is dumb, and even if you use this dumb
method, are you really going to have a hundred of them?...

Memory use - The sensible way
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

GNOME-Terminal:: 

    gnome-terminal &
    for i in {1..100} ; do gnome-terminal & done

    root@pinpoint:~# sync && echo 3 > /proc/sys/vm/drop_caches && free          # Before 100
                 total       used       free     shared    buffers     cached
    Mem:       3102404    1490996    1611408       5344        172      47580
    -/+ buffers/cache:    1443244    1659160
    Swap:      3121996     749776    2372220
    root@pinpoint:~# sync && echo 3 > /proc/sys/vm/drop_caches && free          # After 100
                 total       used       free     shared    buffers     cached
    Mem:       3102404    1878228    1224176       5344        172      47388
    -/+ buffers/cache:    1830668    1271736
    Swap:      3121996     733396    2388600
    root@pinpoint:~# sync && echo 3 > /proc/sys/vm/drop_caches && free          # After kill
                 total       used       free     shared    buffers     cached
    Mem:       3102404    1491888    1610516       4840        272      46088
    -/+ buffers/cache:    1445528    1656876
    Swap:      3121996     733240    2388756

    Used (used mem -buffers/cache + swap)
        Before start: 2193020
        After start : 2564064 = 371044 kbytes, 362 Mbytes / 3.59 MBytes/instance
        After kill  : 2178768 = −14252 kbytes, -13.92 Mbytes recovered (first process)
  
Terminator GTK2::

    terminator -g deletemeconfig &
    for i in {1..100} ; do terminator -g deletemeconfig -u & done

    root@pinpoint:~# sync && echo 3 > /proc/sys/vm/drop_caches && free
                 total       used       free     shared    buffers     cached
    Mem:       3102404    1324492    1777912       4388        152      49688
    -/+ buffers/cache:    1274652    1827752
    Swap:      3121996     744528    2377468
    root@pinpoint:~# sync && echo 3 > /proc/sys/vm/drop_caches && free
                 total       used       free     shared    buffers     cached
    Mem:       3102404    1652112    1450292       4756        860      49968
    -/+ buffers/cache:    1601284    1501120
    Swap:      3121996     744224    2377772
    root@pinpoint:~# sync && echo 3 > /proc/sys/vm/drop_caches && free
                 total       used       free     shared    buffers     cached
    Mem:       3102404    1305376    1797028       4236        124      42836
    -/+ buffers/cache:    1262416    1839988
    Swap:      3121996     744116    2377880

    Used (used mem -buffers/cache + swap)
        before start: 2019180
        after start : 2345508 = 326328 kbytes, 319 Mbytes / 3.16 MBytes/instance
        after kill  : 2006532 = −12648 kbytes,  -12.35 Mbytes recovered (first process)

Terminator GTK3::

    Not possible at the moment because the DBus interface still needs fixing.

So that one surprised me a bit. The fact that when using the single
process we are **more** memory efficient. Python + 100 terminals is
using <90% of the GNOME-Terminal + 100 terminals.

Some may think that this is something to do with the different version
of the VTE widget, but hang on a second. In the dumb method GTK2
Terminator used **more** memory than GTK3. Once the DBus is fixed for
GTK3 there could potentially be more savings.

"Python sucks!"
~~~~~~~~~~~~~~~

Yeah, whatever. The fact is that I'm a helluva lot more productive in
Python than I ever was, am, or will be, in C. In my totally biased
and uninformed opinion, I also think certain things are *much* easier
to get working in Python because you can iterate faster. With the
:ref:`debugging` option to run an interactive terminal you even
have the ability to try out ideas and explore the running instance
directly. Results don't get more immediate than that!

In summary
~~~~~~~~~~

It's a bit slower on startup, it takes a bit more memory, but that's
when you use the dumb method. In normal use, where you're likely to
be using the existing process to open a new window, it is for all
practical purposes as fast as the compiled GNOME-Terminal. It may
even (according to the last memory section) be a little lighter
memory wise, and more obliging about giving it back!

I didn't compare to things like xterm, because frankly we're not
aimed at the same people. Personally I'd rather have the more
extensive features saving me *lots* of time over the course of the
day when using it, than save a handful of seconds every few days
when I restart it, or worrying about an extra 5 or 10 MBytes.

-----------
How do I...
-----------

...make Terminator work like Quake style terminals?
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

  You can get close, but it isn't a perfect recreation, as Terminator
  was not designed with this in mind, but improvements are always welcome!

  - Window state: Hidden
  - Always on top: On
  - Show on all workspaces: On
  - Hide on lose focus: On
  - Hide from taskbar
  - Window borders: Off (use ``Alt``\ +\ ``click-drag`` and 
    ``Alt``\ +\ ``middle-click-drag`` to position and size window.)
  - Set the Toggle window visibility shortcut to your preference

  .. note:: It must be the first Terminator instance started, because
            at present only the first instance can bind to the Window 
            toggle.

  This will give you a terminal hidden at startup that appears with a
  keypress and disappears, either with another keypress, or losing focus.
  It will stay on top, and appear on whichever workspace you are on.

  Something that we don't have is the slide in action of a true Quake
  style terminal. The terminal will simply flick into view, and flick
  out of view.

  .. warning:: The Hide on lose focus option is problematic at this
               time. You will probably find it very frustrating.
