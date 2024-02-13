import os
import sys 

# Fix imports when testing this file directly
if __name__ == '__main__':
  sys.path.append( os.path.join(os.path.dirname(__file__), "../.."))

from gi.repository import Gtk,Vte

from terminatorlib.config import Config
import terminatorlib.plugin as plugin
from terminatorlib.translation import _
from terminatorlib.util import get_config_dir, err, dbg, gerr
from terminatorlib.terminator import Terminator
from terminatorlib import util


# AVAILABLE must contain a list of all the classes that you want exposed
AVAILABLE = ['SaveUserSessionLayout']

class SaveUserSessionLayout(plugin.MenuItem):
    capabilities = ['terminal_menu', 'session']

    config = None
    conf_file = os.path.join(get_config_dir(),"save_last_session_cwd")
    conf_sessions = []
    emit_close_count = 0

    vte_version = Vte.get_minor_version()

    def __init__(self):
      dbg("SaveUserSessionLayout Init")
      plugin.MenuItem.__init__(self)

    def callback(self, menuitems, menu, terminal):
        """ Add save menu item to the menu"""
        vte_terminal = terminal.get_vte()
        item = Gtk.MenuItem.new_with_mnemonic(_('Save _UserSessionLayout'))
        item.connect("activate", self.save_all_session_layouts, terminal)
        menuitems.append(item)
        
    def save_all_session_layouts(self, menuitem, terminal):
        for term in Terminator().terminals:
          self.save_session_layout("", "")

    #not used, but capability can be used to load automatically
    def load_session_layout(self, debugtab=False, widget=None, cwd=None, metadata=None, profile=None):
      dbg("SaveUserSessionLayout load layout")
      terminator = Terminator()
      util.spawn_new_terminator(terminator.origcwd, ['-u', '-l', 'SaveUserSessionLayout'])

    def save_session_layout(self, debugtab=False, widget=None, cwd=None, metadata=None, profile=None):

      config = Config()
      terminator = Terminator()
      current_layout = terminator.describe_layout(save_cwd = True)
      dbg("SaveUserSessionLayout: save layout(%s)" % current_layout)
      res = config.replace_layout("SaveUserSessionLayout", current_layout)
      if (not res):
        r = config.add_layout("SaveUserSessionLayout", current_layout)
      config.save()
      return True
    
   
    def close(self, term, event, arg1 = None):
        if (self.emit_close_count == 0):
            self.emit_close_count = self.emit_close_count + 1
            self.save_session_layout("", "")

