# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""plugin.py - Base plugin system
   Inspired by Armin Ronacher's post at
   http://lucumr.pocoo.org/2006/7/3/python-plugin-system
   Used with permission (the code in that post is to be
   considered BSD licenced, per the authors wishes)

>>> registry = PluginRegistry()
>>> isinstance(registry.instances, dict)
True
>>> registry.enable('TestPlugin')
>>> registry.load_plugins()
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
from . import borg
from .config import Config
from .util import dbg, err, get_config_dir
from .terminator import Terminator

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
            dbg('Plugin path: %s' % self.path)
        if not self.done:
            self.done = False
        if not self.available_plugins:
            self.available_plugins = {}

    def load_plugins(self, force=False):
        """Load all plugins present in the plugins/ directory in our module"""
        if self.done and (not force):
            dbg('Already loaded')
            return

        dbg('loading plugins, force:(%s)' % force)

        config = Config()

        for plugindir in self.path:
            sys.path.insert(0, plugindir)
            try:
                files = os.listdir(plugindir)
            except OSError:
                sys.path.remove(plugindir)
                continue
            for plugin in files:
                if plugin == '__init__.py':
                    continue
                pluginpath = os.path.join(plugindir, plugin)
                if os.path.isfile(pluginpath) and plugin[-3:] == '.py':
                    dbg('Importing plugin %s' % plugin)
                    try:
                        module = __import__(plugin[:-3], None, None, [''])
                        for item in getattr(module, 'AVAILABLE'):
                            func = getattr(module, item)
                            if item not in list(self.available_plugins.keys()):
                                self.available_plugins[item] = func

                            if item not in config['enabled_plugins']:
                                dbg('plugin %s not enabled, skipping' % item)
                                continue
                            if item not in self.instances:
                                self.instances[item] = func()
                            elif force:
                                #instead of multiple copies of loaded
                                #plugin objects, unload where plugins
                                #can clean up and then re-init so there
                                #is one plugin object
                                self.instances[item].unload()
                                self.instances.pop(item, None)
                                self.instances[item] = func()
                    except Exception as ex:
                        err('PluginRegistry::load_plugins: Importing plugin %s \
failed: %s' % (plugin, ex))

        self.done = True

    def get_plugins_by_capability(self, capability):
        """Return a list of plugins with a particular capability"""
        result = []
        dbg('searching %d plugins \
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
        return(list(self.available_plugins.keys()))

    def is_enabled(self, plugin):
        """Return a boolean value indicating whether a plugin is enabled or
        not"""
        return(plugin in self.instances)

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
    nameopen = None
    namecopy = None

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
        if not self.handler_name:
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


"""
-Basic plugin util for key-press handling, has all mapping to be used
in layout keybindings

Vishweshwar Saran Singh Deo vssdeo@gmail.com
"""

from gi.repository import Gtk, Gdk
from terminatorlib.keybindings import Keybindings, KeymapError

PLUGIN_UTIL_DESC = 0
PLUGIN_UTIL_ACT  = 1
PLUGIN_UTIL_KEYS = 2

class KeyBindUtil:

    keybindings = Keybindings()

    map_key_to_act  = {}
    map_act_to_keys = {}
    map_act_to_desc = {}

    def __init__(self, config=None):
        self.config = config

    #Example
    #  bind
    #  first param is desc, second is action str
    #  self.keyb.bindkey([PluginUrlFindNext , PluginUrlActFindNext, "<Alt>j"])
    #
    #  get action name
    #  act = self.keyb.keyaction(event)

    #  if act == "url_find_next":


    #check map key_val_mask -> action
    def _check_keybind_change(self, key):
        act = key[PLUGIN_UTIL_ACT]
        for key_val_mask in self.map_key_to_act:
            old_act = self.map_key_to_act[key_val_mask]
            if act == old_act:
                return key_val_mask
        return None

    #check in config before binding
    def bindkey_check_config(self, key):
        if not self.config:
            raise Warning("bindkey_check_config called without config init")

        actstr = key[PLUGIN_UTIL_ACT]
        kbsect = self.config.base.get_item('keybindings')
        keystr = kbsect[actstr] if actstr in kbsect else ""
        dbg("bindkey_check_config:action (%s) key str:(%s)" % (actstr, keystr))
        if len(keystr):
            key[PLUGIN_UTIL_KEYS] = keystr
            dbg("found new Action->KeyVal in config: (%s, %s)"
                                              % (actstr, keystr));
        self.bindkey(key)

    def bindkey(self, key):
        (keyval, mask)  = self.keybindings._parsebinding(key[PLUGIN_UTIL_KEYS])
        keyval = Gdk.keyval_to_lower(keyval)
        mask = Gdk.ModifierType(mask)

        ret = (keyval, mask)
        dbg("bindkey: (%s) (%s)" %  (key[PLUGIN_UTIL_KEYS], str(ret)))

        #remove if any old key_val_mask
        old_key_val_mask = self._check_keybind_change(key)
        if old_key_val_mask:
            dbg("found old key binding, removing: (%s)" % str(old_key_val_mask))
            del self.map_key_to_act[old_key_val_mask]

        #map key-val-mask to action, used to ease key-press management
        self.map_key_to_act[ret] = key[PLUGIN_UTIL_ACT]


        #map action to key-combo-str, used in preferences->keybinding
        self.map_act_to_keys[key[PLUGIN_UTIL_ACT]]   = key[PLUGIN_UTIL_KEYS]
        #map action to key-combo description, in used preferences->keybinding
        self.map_act_to_desc[key[PLUGIN_UTIL_ACT]] = key[PLUGIN_UTIL_DESC]

    def unbindkey(self, key):

        # Suppose user changed the key-combo and its diff from
        # what the plugin had set by default, we need to get
        # current key-combo
        act      = key[PLUGIN_UTIL_ACT]
        act_keys = self.map_act_to_keys[act]

        (keyval, mask)  = self.keybindings._parsebinding(act_keys)
        keyval = Gdk.keyval_to_lower(keyval)
        mask = Gdk.ModifierType(mask)

        ret = (keyval, mask)
        dbg("unbindkey: (%s) (%s)" %  (key[PLUGIN_UTIL_KEYS], str(ret)))

        # FIXME keys should always be there, can also use .pop(key, None)
        # lets do it after testing
        del self.map_key_to_act[ret]
        del self.map_act_to_keys[key[PLUGIN_UTIL_ACT]]
        del self.map_act_to_desc[key[PLUGIN_UTIL_ACT]]


    def keyaction(self, event):
        #FIXME MOD2 mask comes in the event, remove
        event.state  &= ~Gdk.ModifierType.MOD2_MASK

        keyval = Gdk.keyval_to_lower(event.keyval)
        ret = (keyval, event.state)
        dbg("keyaction: (%s)" % str(ret))
        return self.map_key_to_act.get(ret, None)

    def get_act_to_keys(self, key):
        return self.map_act_to_keys.get(key)

    def get_all_act_to_keys(self):
        return self.map_act_to_keys

    def get_all_act_to_desc(self):
        return self.map_act_to_desc

    def get_act_to_desc(self, act):
        return self.map_act_to_desc.get(act)

    #get action to key binding from config
    def get_act_to_keys_config(self, act):
        if not self.config:
            raise Warning("get_keyvalmask_for_act called without config init")

        keybindings = self.config["keybindings"]
        return keybindings.get(act)
