Terminator
==========

by Chris Jones <cmsj@tenshu.net> and others

## New home on GitHub

In April of 2020 we started moving Terminator to GitHub. A new team wanted to continue the work of the original authors.

Unfortunately we are not able to adopt the Launchpad project, so we could only inform users were possible. 

You can find the project on https://github.com/gnome-terminator/terminator

## Description

The goal of this project is to produce a useful tool for arranging terminals. 
It is inspired by programs such as gnome-multi-term, quadkonsole, etc. in that
the main focus is arranging terminals in grids (tabs is the most common default
method, which Terminator also supports).

When you run Terminator, you will get a terminal in a window, just like almost 
every other terminal emulator available. There is also a titlebar which will
update as shells/programs inside the terminal tell it to. Also on the titlebar
is a small button that opens the grouping menu. From here you can put terminals
into groups, which allows you to control multiple terminals simultaneously.

You can create more terminals by right clicking on one and choosing to split 
it vertically or horizontally. You can get rid of a terminal by right 
clicking on it and choosing Close. Ctrl-Shift-o and Ctrl-Shift-e will also 
effect the splitting.
Also from the right mouse menu you can access Terminator's preferences window.

Ctrl-Shift-n and Ctrl-Shift-p will Shift focus to the next/previous terminal 
respectively, and Ctrl-Shift-w will close the current terminal and 
Ctrl-Shift-q the current window.

For more keyboard shortcuts and also the command line options, please see the
manpage "terminator". For configuration options, see the manpage 
"terminator_config".

## Contributing

Any help is welcome with the Terminator project.

* [Open issues for bugs or enhancements](https://github.com/gnome-terminator/terminator/issues/new)
* [Join our chat room on gitter.im for general questions](https://gitter.im/gnome-terminator/community)

You can find old bugs and questions in the launchpad project, but please don't post anything new there.

* https://answers.launchpad.net/terminator
* https://bugs.launchpad.net/terminator

## Origins

Terminator began by shamelessly copying code from the vte-demo.py in the vte 
widget package, and the gedit terminal plugin (which was fantastically 
useful at figuring out vte's API).

vte-demo.py was not my code and is copyright its original author. While it 
does not contain any specific licensing information in it, the VTE package 
appears to be licenced under LGPL v2.

## Licensing

The gedit terminal plugin is part of the gedit-plugins package, which is 
licenced under GPL v2 or later.

I am thus licensing Terminator as GPL v2 only.

Cristian Grada provided the old icon under the same licence.
Cory Kontros provided the new icon under the CC-by-SA licence.
For other authorship information, see debian/copyright
