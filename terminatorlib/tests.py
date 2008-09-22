#!/usr/bin/python
"""Terminator test suite. This uses the nosetest testing framework. See http://somethingaboutorange.com/mrl/projects/nose/"""

def test_version():
  import version

  assert version.APP_NAME == 'terminator'

def test_debug ():
  from config import debug

  assert debug == False

class test_encodings():
  encoding = None

  def setup (self):
    import gettext
    gettext.install ('test')
    import encoding
    self.encoding = encoding.TerminatorEncoding

  def test_length (self):
    assert len (self.encoding.encodings) == 74

  def test_get_list (self):
    assert self.encoding.get_list () == self.encoding.encodings

class test_config():
  config = None

  def setup (self):
    import config
    self.config = config

  def test_defaults_lengths (self):
    assert len(self.config.Defaults) > 1
    assert len(self.config.Defaults['keybindings']) > 1

  def test_TerminatorConfValuestore (self):
    store = self.config.TerminatorConfValuestore ()
    assert store.type == "Base"
    store.values['test_key'] = 'test_value'
    assert store['test_key'] == 'test_value'

  def test_TerminatorConfValuestoreDefault (self):
    store = self.config.TerminatorConfValuestoreDefault ()
    assert store.type == "Default"
    assert store['extreme_tabs'] == False
    assert store['titletips'] == False
    assert store['enable_real_transparency'] == False # until the bug is fixed

class test_configfile():
  configfile = None

  def setup (self):
    import configfile
    self.configfile = configfile

  def test_ConfigSyntaxError (self):
    class _testcf ():
      errors_are_fatal = False
      filename = 'test_filename'
      _lnum = 123456789
      _pos = 5
      _line = ' test line '

    testcf = _testcf ()
    testobject = self.configfile.ConfigSyntaxError ('test_message', testcf)
    assert str(testobject) == ''' * test_message, line 123456789:
     test line
    -----^
'''

