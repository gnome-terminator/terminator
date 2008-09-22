#!/usr/bin/python
"""Terminator test suite. This uses the nosetest testing framework. See http://somethingaboutorange.com/mrl/projects/nose/"""

def test_version():
  import version

  assert version.APP_NAME == 'terminator'

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
