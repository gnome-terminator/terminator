#!/usr/bin/python

import gtk

from newterminator import Terminator
from window import Window
from terminal import Terminal

def on_window_destroyed(widget):
    """Window destroyed, so exit"""
    gtk.main_quit()

window = Window()
foo = Terminator()
term = Terminal()
foo.register_terminal(term)

window.add(term)
window.show()
term.spawn_child()

window.connect("destroy", on_window_destroyed)

gtk.main()
