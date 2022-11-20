from gi.repository import Gtk

import terminatorlib.plugin as plugin
from terminatorlib.terminator import Terminator

AVAILABLE = ['InsertTermName']

class InsertTermName(plugin.MenuItem):
   capabilities = ['terminal_menu']
   config = None

   def __init__(self):
      # self.connect_signals()
      plugin.MenuItem.__init__(self)

   def callback(self, menuitems, menu, terminal):
      item = Gtk.MenuItem.new_with_label('Insert terminal name')
      item.connect('activate', lambda x: terminal.emit('insert-term-name'))
      menuitems.append(item)

