#!/usr/bin/python
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""plugin.py - Base plugin system
   Inspired by Armin Ronacher's post at
   http://lucumr.pocoo.org/2006/7/3/python-plugin-system
   Used with permission (the code in that post is to be
   considered BSD licenced, per the authors wishes)

>>> registry = PluginRegistry()
>>> registry.instances
{}
>>> registry.load_plugins(True)
>>> plugins = registry.get_plugins_by_capability('test')
>>> len(plugins)
1
>>> plugins[0] #doctest: +ELLIPSIS
<testplugin.TestPlugin object at 0x...>
>>> registry.get_plugins_by_capability('this_should_not_ever_exist')
[]
>>> plugins[0].do_test()
'TestPluginWin'

"""

import sys
import os
import borg
from config import Config
from util import dbg, err, get_config_dir
from terminator import Terminator

class Plugin(object):
    """Definition of our base plugin class"""
    capabilities = None

    def __init__(self):
        """Class initialiser."""
        pass

    def unload(self):
        """Prepare to be unloaded"""
        pass

class PluginRegistry(borg.Borg):
    """Definition of a class to store plugin instances"""
    available_plugins = None
    instances = None
    path = None
    done = None

    def __init__(self):
        """Class initialiser"""
        borg.Borg.__init__(self, self.__class__.__name__)
        self.prepare_attributes()

    def prepare_attributes(self):
        """Prepare our attributes"""
        if not self.instances:
            self.instances = {}
        if not self.path:
            self.path = []
            (head, _tail) = os.path.split(borg.__file__)
            self.path.append(os.path.join(head, 'plugins'))
            self.path.append(os.path.join(get_config_dir(), 'plugins'))
            dbg('PluginRegistry::prepare_attributes: Plugin path: %s' % 
                self.path)
        if not self.done:
            self.done = False
        if not self.available_plugins:
            self.available_plugins = {}

    def load_plugins(self, testing=False):
        """Load all plugins present in the plugins/ directory in our module"""
        if self.done:
            dbg('PluginRegistry::load_plugins: Already loaded')
            return

        config = Config()

        for plugindir in self.path:
            sys.path.insert(0, plugindir)
            try:
                files = os.listdir(plugindir)
            except OSError:
                sys.path.remove(plugindir)
                continue
            for plugin in files:
                pluginpath = os.path.join(plugindir, plugin)
                if os.path.isfile(pluginpath) and plugin[-3:] == '.py':
                    dbg('PluginRegistry::load_plugins: Importing plugin %s' % 
                        plugin)
                    try:
                        module = __import__(plugin[:-3], None, None, [''])
                        for item in getattr(module, 'AVAILABLE'):
                            if item not in self.available_plugins.keys():
                                func = getattr(module, item)
                                self.available_plugins[item] = func

                            if not testing and item not in config['enabled_plugins']:
                                dbg('plugin %s not enabled, skipping' % item)
                                continue
                            if item not in self.instances:
                                self.instances[item] = func()
                    except Exception, ex:
                        err('PluginRegistry::load_plugins: Importing plugin %s \
failed: %s' % (plugin, ex))

        self.done = True

    def get_plugins_by_capability(self, capability):
        """Return a list of plugins with a particular capability"""
        result = []
        dbg('PluginRegistry::get_plugins_by_capability: searching %d plugins \
for %s' % (len(self.instances), capability))
        for plugin in self.instances:
            if capability in self.instances[plugin].capabilities:
                result.append(self.instances[plugin])
        return result

    def get_all_plugins(self):
        """Return all plugins"""
        return(self.instances)

    def get_available_plugins(self):
        """Return a list of all available plugins whether they are enabled or
        disabled"""
        return(self.available_plugins.keys())

    def is_enabled(self, plugin):
        """Return a boolean value indicating whether a plugin is enabled or
        not"""
        return(self.instances.has_key(plugin))

    def enable(self, plugin):
        """Enable a plugin"""
        if plugin in self.instances:
            err("Cannot enable plugin %s, already enabled" % plugin)
        dbg("Enabling %s" % plugin)
        self.instances[plugin] = self.available_plugins[plugin]()

    def disable(self, plugin):
        """Disable a plugin"""
        dbg("Disabling %s" % plugin)
        self.instances[plugin].unload()
        del(self.instances[plugin])

# This is where we should define a base class for each type of plugin we
# support

# URLHandler - This adds a regex match to the Terminal widget and provides a
#               callback to turn that into a URL.
class URLHandler(Plugin):
    """Base class for URL handlers"""
    capabilities = ['url_handler']
    handler_name = None
    match = None

    def __init__(self):
        """Class initialiser"""
        Plugin.__init__(self)
        terminator = Terminator()
        for terminal in terminator.terminals:
            terminal.match_add(self.handler_name, self.match)

    def callback(self, url):
        """Callback to transform the enclosed URL"""
        raise NotImplementedError

    def unload(self):
        """Handle being removed"""
        if not self.match:
            err('unload called without self.handler_name being set')
            return
        terminator = Terminator()
        for terminal in terminator.terminals:
            terminal.match_remove(self.handler_name)

# MenuItem - This is able to execute code during the construction of the
#             context menu of a Terminal.
class MenuItem(Plugin):
    """Base class for menu items"""
    capabilities = ['terminal_menu']

    def callback(self, menuitems, menu, terminal):
        """Callback to transform the enclosed URL"""
        raise NotImplementedError

