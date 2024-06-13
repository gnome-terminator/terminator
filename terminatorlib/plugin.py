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

from .version import APP_NAME

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

    def get_plugin_instance(self, plugin):
        instance = self.instances.get(plugin, None)
        dbg('get plugin: %s instance: %s' % (plugin, instance))
        return instance

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

    #merged keybindings and plugin key bindings
    map_all_act_to_keys = {}
    map_all_act_to_desc = {}

    config = Config()

    def __init__(self, config=None):
        self.load_merge_key_maps()

    #Example
    #  bind
    #  first param is desc, second is action str
    #  self.keyb.bindkey([PluginUrlFindNext , PluginUrlActFindNext, "<Alt>j"])
    #
    #  get action name
    #  act = self.keyb.keyaction(event)

    #  if act == "url_find_next":

    def load_merge_key_maps(self):

        cfg_keybindings = KeyBindUtil.config['keybindings']

        #TODO need to check if cyclic dep here, we only using keybindingnames
        from terminatorlib.prefseditor import PrefsEditor
        pref_keybindingnames = PrefsEditor.keybindingnames

        #merge give preference to main bindings over plugin
        KeyBindUtil.map_all_act_to_keys  = {**self.map_act_to_keys, **cfg_keybindings}
        KeyBindUtil.map_all_act_to_desc  = {**self.map_act_to_desc, **pref_keybindingnames}

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

    #functions to get actstr to keys / key mappings or desc / desc mapppings
    #for plugins or merged keybindings

    def get_act_to_keys(self, key):
        return self.map_all_act_to_keys.get(key)

    def get_plugin_act_to_keys(self, key):
        return self.map_act_to_keys.get(key)

    def get_all_plugin_act_to_keys(self):
        return self.map_act_to_keys

    def get_all_act_to_keys(self):
        return self.map_all_act_to_keys

    def get_act_to_desc(self, act):
        return self.map_all_act_to_desc.get(act)

    def get_plugin_act_to_desc(self, act):
        return self.map_act_to_desc.get(act)

    def get_all_plugin_act_to_desc(self):
        return self.map_act_to_desc

    def get_all_act_to_desc(self):
        return self.map_all_act_to_desc

    #get action to key binding from config
    def get_act_to_keys_config(self, act):
        if not self.config:
            raise Warning("get_keyvalmask_for_act called without config init")

        keybindings = self.config["keybindings"]
        return keybindings.get(act)




#-PluginEventRegistry utility: Vishweshwar Saran Singh Deo <vssdeo@gmail.com>
#
#
#use-case: so if a plugin wants to get an action added to context-menu
#it can be done as plugins register their keybindings, but their actions
#are not understood by terminal on_keypress mapping since pluings are
#external to core working.
#
#So for eg: PluginContextMenuAct we are detecting and handling it first before
#passing to terminal on_keypress, but what about if an other Plugin Key Press
#needs to be handled locally in its context. May be we can register
#its function and pass the action to it

#this class keeps the events to local function instead of sending to
#terminal, since for things like plugins, the terminal key mapper won't
#have the context. lets see what dependencies come up and all Plugin actions
#can be added to Context Menu eg:
#
#  so for action PluginUrlActFindNext which is understood by MouseFreeURLHandler
#  the plugin can register its action and if that action is added to
#  menu, that action will be passed to the plugin
#
#  import terminatorlib.plugin as plugin
#
#  event_registry = plugin.PluginEventRegistry()
#  ...
#  MouseFreeURLHandler.event_registry.register(PluginUrlActFindNext,
#                                              self.on_action,
#                                              'custom-tag')
#  ...
#  def on_action(self, act):
#      self.on_keypress(None, 'event', act)
#

class PluginEventRegistry:

    Map_Act_Event_Handlers = {}

    def __init__(self):
        pass

    def register(self, action, handler, tag_id):

        dbg('register action:(%s) tag_id:(%s)' % (action, tag_id))

        if action not in PluginEventRegistry.Map_Act_Event_Handlers:
            dbg('adding new handler for: %s' % action)
            PluginEventRegistry.Map_Act_Event_Handlers[action] = {tag_id: handler}
        else:
            dbg('appending handler for: %s' % action)
            handlers = PluginEventRegistry.Map_Act_Event_Handlers[action]
            handlers[tag_id] =  handler

        """
        dbg('register: (%s) total_events:(%s)' %
                    (len(PluginEventRegistry.Map_Act_Event_Handlers),
                    PluginEventRegistry.Map_Act_Event_Handlers))
        """

    def call_action_handlers(self, action):
        if action not in PluginEventRegistry.Map_Act_Event_Handlers:
            dbg('no handers found for action:%s' % action)
            return False

        act_items = PluginEventRegistry.Map_Act_Event_Handlers[action].copy()
        for key, handler in act_items.items():
            dbg('calling handers: %s for action:%s' % (handler,action))
            handler(action)

        return True


    def unregister(self, action, handler, tag_id):

        if action not in PluginEventRegistry.Map_Act_Event_Handlers:
            dbg('action not found: %s' % action)
            return False

        lst = PluginEventRegistry.Map_Act_Event_Handlers[action]
        if tag_id in lst:
            dbg('removing tag_id:(%s) for act: (%s)' % (tag_id, action))
            del lst[tag_id]
            if not len(lst):
                dbg('removing empty action:(%s) from registry' % action)
                del PluginEventRegistry.Map_Act_Event_Handlers[action]
            return True

        return False


#
# -PluginGUI utility: Vishweshwar Saran Singh Deo <vssdeo@gmail.com>
#
# -To assist in injecting and restoring of Plugin UI interfaces
# -Loading of Glade Files and Glade Data
#
# -Eg.
#
#    plugin_builder = self.plugin_gui.get_glade_builder(plugin)
#    plugin_window  = plugin_builder.get_object('PluginContextMenu')
#
#   ...
#   ...
#
#    #call back from prefseditor.py if func defined
#
#    def update_gui(self, widget, visible):
#
#           #add UI to Prefs->Plugins->ContextMenu
#           prev_widget = self.plugin_gui.add_gui(widget, self.plugin_window)
#           #use return value to add back when not visible, later we can
#           #handle this automatically

from . import config

class PluginGUI:

    def __init__(self):
        self.save_prev_child = None

    #adds new UI and saves previous UI
    def add_gui(self, parent_widget, child_widget):

        hpane_widget = parent_widget.get_child2()
        if hpane_widget:
            #if not self.save_prev_child:
            self.save_prev_child = hpane_widget
            hpane_widget.destroy()
            #add plugin gui to prefs
            parent_widget.add2(child_widget)
            parent_widget.show_all()
            return hpane_widget


    def get_glade_data(self, plugin):
        gladedata = ''
        try:
            # Figure out where our library is on-disk so we can open our
            (head, _tail) = os.path.split(config.__file__)
            if plugin:
                filename = plugin + '.glade'
                plugin_glade_file = os.path.join(head, 'plugins', filename)
                gladefile = open(plugin_glade_file, 'r')
                gladedata = gladefile.read()
                gladefile.close()
        except Exception as ex:
            dbg("Failed to find: ex:%s" % (ex))

        return gladedata


    def get_glade_builder(self, plugin):

        gladedata = self.get_glade_data(plugin)
        if not gladedata:
            return

        plugin_builder = Gtk.Builder()
        plugin_builder.set_translation_domain(APP_NAME)
        plugin_builder.add_from_string(gladedata)

        return plugin_builder


