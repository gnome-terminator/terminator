#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""plugin.py - Base plugin system

>>> registry = PluginRegistry()
>>> registry.load_plugins()
>>> registry.get_plugins_by_capability('test')
[<testplugin.TestPlugin object at ...>]
>>> registry.get_plugins_by_capability('this_should_not_ever_exist')
[]

"""

import sys
import os
import borg
from util import dbg, err

class Plugin(object):
    """Definition of our base plugin class"""
    capabilities = None

    def __init__(self):
        """Class initialiser."""
        pass

class PluginRegistry(borg.Borg):
    """Definition of a class to store plugin instances"""
    instances = None
    path = None

    def __init__(self):
        """Class initialiser"""
        borg.Borg.__init__(self)
        self.prepare_attributes()

    def prepare_attributes(self):
        """Prepare our attributes"""
        if not self.instances:
            self.instances = {}
        if not self.path:
            (head, tail) = os.path.split(borg.__file__)
            self.path = os.path.join(head, 'plugins')
            dbg('PluginRegistry::prepare_attributes: Plugin path: %s' % 
                self.path)

    def load_plugins(self):
        """Load all plugins present in the plugins/ directory in our module"""
        sys.path.insert(0, self.path)
        files = os.listdir(self.path)
        for plugin in files:
            if os.path.isfile(os.path.join(self.path, plugin)) and \
               plugin[-3:] == '.py':
                dbg('PluginRegistry::load_plugins: Importing plugin %s' % 
                    plugin)
                try:
                    __import__(plugin[:-3], None, None, [''])
                except Exception as e:
                    err('PluginRegistry::load_plugins: Importing plugin %s \
failed: %s' % (plugin, e))

    def get_plugins_by_capability(self, capability):
        """Return a list of plugins with a particular capability"""
        result = []
        dbg('PluginRegistry::get_plugins_by_capability: searching %d plugins \
for %s' % (len(Plugin.__subclasses__()), capability))
        for plugin in Plugin.__subclasses__():
            if capability in plugin.capabilities:
                if not plugin in self.instances:
                    self.instances[plugin] = plugin()
                result.append(self.instances[plugin])
        return result

if __name__ == '__main__':
    import doctest
    sys.path.insert(0, 'plugins')
    import testplugin
    (failed, attempted) = doctest.testmod()
    print "%d/%d tests failed" % (failed, attempted)
