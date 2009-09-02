#!/usr/bin/python

import gtk

from newterminator import Terminator
from window import Window
from terminal import Terminal

window = Window()
foo = Terminator()
term = Terminal()
foo.register_terminal(term)

window.add(term)
window.show()

gtk.main()
