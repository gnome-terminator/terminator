#!/usr/bin/python

import gtk
from factory import Factory

maker = Factory()
window = maker.make('Window')
term = maker.make('Terminal')

window.add(term)
window.show()
term.spawn_child()

try:
  gtk.main()
except KeyboardInterrupt:
  pass
