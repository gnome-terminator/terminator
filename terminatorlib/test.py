#!/usr/bin/python

import gtk

from newterminator import Terminator
from window import Window

window = Window()
foo = Terminator()
term = foo.new_terminal()

window.add(term)
window.show()

gtk.main()
