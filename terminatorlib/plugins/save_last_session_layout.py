import os
import sys 

# Fix imports when testing this file directly
if __name__ == '__main__':
  sys.path.append( os.path.join(os.path.dirname(__file__), "../.."))

from terminatorlib.config import Config
import terminatorlib.plugin as plugin
from terminatorlib.util import get_config_dir, err, dbg, gerr
from terminatorlib.terminator import Terminator
from terminatorlib import util


# AVAILABLE must contain a list of all the classes that you want exposed
AVAILABLE = ['SaveLastSessionLayout']

class SaveLastSessionLayout(plugin.Plugin):
    capabilities = ['session']

    config = None
    conf_file = os.path.join(get_config_dir(),"save_last_session_cwd")
    conf_sessions = []
    emit_close_count = 0

    def __init__(self):
      dbg("SaveLastSessionLayout Init")
      self.connect_signals()

    #not used, but capability can be used to load automatically
    def load_session_layout(self, debugtab=False, widget=None, cwd=None, metadata=None, profile=None):
      dbg("SaveLastSessionLayout load layout")
      terminator = Terminator()
      util.spawn_new_terminator(terminator.origcwd, ['-u', '-l', 'SaveLastSessionLayout'])

    def save_session_layout(self, debugtab=False, widget=None, cwd=None, metadata=None, profile=None):

      config = Config()
      terminator = Terminator()
      current_layout = terminator.describe_layout(save_cwd = True)
      dbg("SaveLastSessionLayout: save layout(%s)" % current_layout)
      res = config.replace_layout("SaveLastSessionLayout", current_layout)
      if (not res):
        r = config.add_layout("SaveLastSessionLayout", current_layout)
      config.save()
      return True
    
    def connect_signals(self):
        dbg("SaveLastSessionLayout connect_signals")
        n = 0
        for term in Terminator().terminals:
            dbg("SaveLastSessionLayout connect_signals to term num:(%d)" % n)
            n = n + 1
            # event close-term works, and does not require an additional
            # event but has a race condition when
            # there is only one terminal we are unable to get the
            # describe_layout section

            #term.connect('close-term', self.close, None)
            term.connect('pre-close-term', self.close, None)

            #Can connect signal from terminal
            #term.connect('load-layout', self.load_session_layout, None)

    def close(self, term, event, arg1 = None):
        if (self.emit_close_count == 0):
            self.emit_close_count = self.emit_close_count + 1
            self.save_session_layout("", "")

