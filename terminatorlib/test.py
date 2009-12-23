#!/usr/bin/python

import gtk

from newterminator import Terminator
from window import Window
from factory import Factory

def on_window_destroyed(widget):
    """Window destroyed, so exit"""
    gtk.main_quit()

maker = Factory()
window = Window()
foo = Terminator()
term = maker.make('Terminal')
foo.register_terminal(term)

window.add(term)
window.show()
term.spawn_child()

window.connect("destroy", on_window_destroyed)

try:
  gtk.main()
except KeyboardInterrupt:
  pass
