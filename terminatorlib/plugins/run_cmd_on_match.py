import re
import os
import sys
import subprocess

from gi.repository import Gtk
from gi.repository import GObject

from terminatorlib.util import dbg
import terminatorlib.plugin as plugin
from terminatorlib.config import Config
from terminatorlib.translation import _
from terminatorlib.util import get_config_dir, err, dbg, gerr

(CC_COL_ENABLED, CC_COL_REGEXP, CC_COL_COMMAND) = list(range(0,3))

AVAILABLE = ['RunCmdOnMatchMenu']

# For example, open scripts names outputted by python in Vim at the given line number:
# match = r'\B(/\S+?\.py)\S{2}\sline\s(\d+)' # Python's log file matching
# cmd = "gvim --servername IDE --remote +{1} {0}"

# This class is not useful as is, it needs to be forged through MetaRCOM metaclass to be useful
# (because the API use static class properties).
class RunCmdOnMatch(plugin.URLHandler):
    """Template for a class that run a command when a regexp match something printed on the terminal screen."""
    capabilities = ['url_handler']
    nameopen = "Open file"
    namecopy = "Copy file path"

    handler_name = None
    match = None
    cmd = None

    def callback(self, url):
        assert(self.__class__.match)
        assert(self.__class__.cmd)

        try:
            found = re.search(self.__class__.match, url)
        except Exception as e:
            dbg("ERROR while searching in the captured URL: {}".format(e))
            return None

        if not found:
            dbg("ERROR pattern not found")
            return None

        try:
            groups = found.groups()
            dbg("Groups: {}".format(groups))
        except Exception as e:
            dbg("ERROR while accessing groups: {}".format(e))
            return None

        for group in groups:
            if not group:
                dbg("ERROR groups not captured correctly: {groups}".format(groups=groups))
                return None

        try:
            runcmd = self.__class__.cmd.format(*groups)
        except Exception as e:
            err("Exception occurred while formatting the command: {} {}".format(type(e).__name__, e))

        dbg("run: {cmd}".format(cmd=runcmd))
        subprocess.run(runcmd.split())

        # To avoid the fallback to the default URL handler, use the `terminator://` protocol tag.
        # Terminator will not try to open the URL, so any string after is just for debugging.
        return "terminator://{cmd}".format(cmd=runcmd)


# This metaclass is used to populate RunCmdOnMatch's static members.
class MetaRCOM(type):
    """A meta-class for creating RunCmdOnMatch plugins on the fly."""
    def __new__(cls, name, regexp, cmd):
        return super().__new__(cls, name, (RunCmdOnMatch,), {"match":regexp, "cmd":cmd, "handler_name":name})


# Add a contextual menu for opening a preference window to configure regexp/commands.
# FIXME this is essentially the same code than custom_commands, one need to refactor to keep a single codebase
# (and waiting for a plugin's preference window).
class RunCmdOnMatchMenu(plugin.MenuItem):
    """Add custom match/commands preference setting to the terminal menu"""
    capabilities = ['terminal_menu']
    cmd_list = {}
    conf_file = os.path.join(get_config_dir(),"run_cmd_on_match")

    def __init__( self):
      config = Config()
      sections = config.plugin_get_config(self.__class__.__name__)
      if not isinstance(sections, dict):
          return
      noord_cmds = []
      for part in sections:
        s = sections[part]
        if not ("regexp" in s and "command" in s):
          dbg("Ignoring section %s" % s)
          continue
        regexp = s["regexp"]
        command = s["command"]
        enabled = s["enabled"] and s["enabled"] or False
        if "position" in s:
          self.cmd_list[int(s["position"])] = {'enabled' : enabled,
                                               'regexp' : regexp,
                                               'command' : command
                                              }
        else:
          noord_cmds.append(
                              {'enabled' : enabled,
                                'regexp' : regexp,
                                'command' : command
                              }
                            )
        for cmd in noord_cmds:
            self.cmd_list[len(self.cmd_list)] = cmd

        self._load_configured_handlers()


    def callback(self, menuitems, menu, terminal):
        """Add our menu items to the menu"""
        submenus = {}
        item = Gtk.MenuItem.new_with_mnemonic(_('_Run command on matches'))
        menuitems.append(item)

        submenu = Gtk.Menu()
        item.set_submenu(submenu)

        menuitem = Gtk.MenuItem.new_with_mnemonic(_('_Preferences'))
        menuitem.connect("activate", self.configure)
        submenu.append(menuitem)

        menuitem = Gtk.SeparatorMenuItem()
        submenu.append(menuitem)

        theme = Gtk.IconTheme.get_default()


    def _save_config(self):
        config = Config()
        config.plugin_del_config(self.__class__.__name__)
        i = 0
        for command in [ self.cmd_list[key] for key in sorted(self.cmd_list.keys()) ] :
            enabled = command['enabled']
            regexp = command['regexp']
            command = command['command']

            item = {}
            item['enabled'] = enabled
            item['regexp'] = regexp
            item['command'] = command
            item['position'] = i

            config.plugin_set(self.__class__.__name__, regexp, item)
            i = i + 1
        config.save()
        self._load_configured_handlers()


    def _load_configured_handlers(self):
        """Forge an URLhandler plugin and hide it in the available ones."""
        me = sys.modules[__name__] # Current module.
        config = Config()

        for key,handler in [ (key,self.cmd_list[key]) for key in sorted(self.cmd_list.keys()) ] :
            # Forge a hidden/managed plugin
            # (names starting with an underscore will not be displayed in the preference/plugins window).
            rcom_name = "_RunCmdOnMatch_{}".format(key) # key is just the index
            # Make a handler class.
            RCOM = MetaRCOM(rcom_name, handler["regexp"], handler["command"])
            # Instantiate the class.
            setattr(me, rcom_name, RCOM)

            if rcom_name not in AVAILABLE:
                AVAILABLE.append(rcom_name)
                dbg("add {} to the list of URL handlers: '{}' -> '{}'".format(rcom_name, RCOM.match, RCOM.cmd))

            if handler['enabled'] and rcom_name not in config["enabled_plugins"]:
                config["enabled_plugins"].append(rcom_name)

        config.save()


    def _execute(self, widget, data):
      command = data['command']
      if command[-1] != '\n':
        command = command + '\n'
      for terminal in data['terminals']:
        terminal.vte.feed_child(command.encode())

    def configure(self, widget, data = None):
      ui = {}
      dbox = Gtk.Dialog(
                      _("Run command on match Configuration"),
                      None,
                      Gtk.DialogFlags.MODAL,
                      (
                        _("_Cancel"), Gtk.ResponseType.REJECT,
                        _("_OK"), Gtk.ResponseType.ACCEPT
                      )
                    )
      dbox.set_transient_for(widget.get_toplevel())

      icon_theme = Gtk.IconTheme.get_default()
      if icon_theme.lookup_icon('terminator-run-cmd-on-match', 48, 0):
        dbox.set_icon_name('terminator-run-cmd-on-match')
      else:
        dbg('Unable to load Terminator run-cmd-on-match icon')
        icon = dbox.render_icon(Gtk.STOCK_DIALOG_INFO, Gtk.IconSize.BUTTON)
        dbox.set_icon(icon)

      store = Gtk.ListStore(bool, str, str)

      for command in [ self.cmd_list[key] for key in sorted(self.cmd_list.keys()) ]:
        store.append([command['enabled'], command['regexp'], command['command']])

      treeview = Gtk.TreeView(store)
      #treeview.connect("cursor-changed", self.on_cursor_changed, ui)
      selection = treeview.get_selection()
      selection.set_mode(Gtk.SelectionMode.SINGLE)
      selection.connect("changed", self.on_selection_changed, ui)
      ui['treeview'] = treeview

      renderer = Gtk.CellRendererToggle()
      renderer.connect('toggled', self.on_toggled, ui)
      column = Gtk.TreeViewColumn(_("Enabled"), renderer, active=CC_COL_ENABLED)
      treeview.append_column(column)

      renderer = Gtk.CellRendererText()
      column = Gtk.TreeViewColumn(_("regexp"), renderer, text=CC_COL_REGEXP)
      treeview.append_column(column)

      renderer = Gtk.CellRendererText()
      column = Gtk.TreeViewColumn(_("Command"), renderer, text=CC_COL_COMMAND)
      treeview.append_column(column)

      scroll_window = Gtk.ScrolledWindow()
      scroll_window.set_size_request(500, 250)
      scroll_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
      scroll_window.add_with_viewport(treeview)

      hbox = Gtk.HBox()
      hbox.pack_start(scroll_window, True, True, 0)
      dbox.vbox.pack_start(hbox, True, True, 0)

      button_box = Gtk.VBox()

      button = Gtk.Button(_("Top"))
      button_box.pack_start(button, False, True, 0)
      button.connect("clicked", self.on_goto_top, ui)
      button.set_sensitive(False)
      ui['button_top'] = button

      button = Gtk.Button(_("Up"))
      button_box.pack_start(button, False, True, 0)
      button.connect("clicked", self.on_go_up, ui)
      button.set_sensitive(False)
      ui['button_up'] = button

      button = Gtk.Button(_("Down"))
      button_box.pack_start(button, False, True, 0)
      button.connect("clicked", self.on_go_down, ui)
      button.set_sensitive(False)
      ui['button_down'] = button

      button = Gtk.Button(_("Last"))
      button_box.pack_start(button, False, True, 0)
      button.connect("clicked", self.on_goto_last, ui)
      button.set_sensitive(False)
      ui['button_last'] = button

      button = Gtk.Button(_("New"))
      button_box.pack_start(button, False, True, 0)
      button.connect("clicked", self.on_new, ui)
      ui['button_new'] = button

      button = Gtk.Button(_("Edit"))
      button_box.pack_start(button, False, True, 0)
      button.set_sensitive(False)
      button.connect("clicked", self.on_edit, ui)
      ui['button_edit'] = button

      button = Gtk.Button(_("Delete"))
      button_box.pack_start(button, False, True, 0)
      button.connect("clicked", self.on_delete, ui)
      button.set_sensitive(False)
      ui['button_delete'] = button



      hbox.pack_start(button_box, False, True, 0)
      self.dbox = dbox
      dbox.show_all()
      res = dbox.run()
      if res == Gtk.ResponseType.ACCEPT:
        self.update_cmd_list(store)
        self._save_config()
      del(self.dbox)
      dbox.destroy()
      return


    def update_cmd_list(self, store):
        iter = store.get_iter_first()
        self.cmd_list = {}
        i=0
        while iter:
          (enabled, regexp, command) = store.get(iter,
                                              CC_COL_ENABLED,
                                              CC_COL_REGEXP,
                                              CC_COL_COMMAND)
          self.cmd_list[i] = {'enabled' : enabled,
                            'regexp': regexp,
                            'command' : command}
          iter = store.iter_next(iter)
          i = i + 1


    def on_toggled(self, widget, path, data):
      treeview = data['treeview']
      store = treeview.get_model()
      iter = store.get_iter(path)
      (enabled, regexp, command) = store.get(iter,
                                    CC_COL_ENABLED,
                                    CC_COL_REGEXP,
                                    CC_COL_COMMAND
                                        )
      store.set_value(iter, CC_COL_ENABLED, not enabled)


    def on_selection_changed(self,selection, data=None):
      treeview = selection.get_tree_view()
      (model, iter) = selection.get_selected()
      data['button_top'].set_sensitive(iter is not None)
      data['button_up'].set_sensitive(iter is not None)
      data['button_down'].set_sensitive(iter is not None)
      data['button_last'].set_sensitive(iter is not None)
      data['button_edit'].set_sensitive(iter is not None)
      data['button_delete'].set_sensitive(iter is not None)

    def _create_command_dialog(self, enabled_var = False, regexp_var = "", command_var = ""):
      dialog = Gtk.Dialog(
                        _("New Command"),
                        None,
                        Gtk.DialogFlags.MODAL,
                        (
                          _("_Cancel"), Gtk.ResponseType.REJECT,
                          _("_OK"), Gtk.ResponseType.ACCEPT
                        )
                      )
      dialog.set_transient_for(self.dbox)
      table = Gtk.Table(3, 2)

      label = Gtk.Label(label=_("Enabled:"))
      table.attach(label, 0, 1, 0, 1)
      enabled = Gtk.CheckButton()
      enabled.set_active(enabled_var)
      table.attach(enabled, 1, 2, 0, 1)

      label = Gtk.Label(label=_("regexp:"))
      table.attach(label, 0, 1, 1, 2)
      regexp = Gtk.Entry()
      regexp.set_text(regexp_var)
      table.attach(regexp, 1, 2, 1, 2)

      label = Gtk.Label(label=_("Command:"))
      table.attach(label, 0, 1, 2, 3)
      command = Gtk.Entry()
      command.set_text(command_var)
      table.attach(command, 1, 2, 2, 3)

      dialog.vbox.pack_start(table, True, True, 0)
      dialog.show_all()
      return (dialog,enabled,regexp,command)

    def on_new(self, button, data):
      (dialog,enabled,regexp,command) = self._create_command_dialog()
      res = dialog.run()
      item = {}
      if res == Gtk.ResponseType.ACCEPT:
        item['enabled'] = enabled.get_active()
        item['regexp'] = regexp.get_text()
        item['command'] = command.get_text()
        if item['regexp'] == '' or item['command'] == '':
          err = Gtk.MessageDialog(dialog,
                                  Gtk.DialogFlags.MODAL,
                                  Gtk.MessageType.ERROR,
                                  Gtk.ButtonsType.CLOSE,
                                  _("You need to define a regexp and command")
                                )
          err.run()
          err.destroy()
        else:
          # we have a new command
          store = data['treeview'].get_model()
          iter = store.get_iter_first()
          regexp_exist = False
          while iter != None:
            if store.get_value(iter,CC_COL_REGEXP) == item['regexp']:
              regexp_exist = True
              break
            iter = store.iter_next(iter)
          if not regexp_exist:
            store.append((item['enabled'], item['regexp'], item['command']))
          else:
            gerr(_("regexp *%s* already exist") % item['regexp'])
      dialog.destroy()

    def on_goto_top(self, button, data):
      treeview = data['treeview']
      selection = treeview.get_selection()
      (store, iter) = selection.get_selected()

      if not iter:
        return
      firstiter = store.get_iter_first()
      store.move_before(iter, firstiter)

    def on_go_up(self, button, data):
      treeview = data['treeview']
      selection = treeview.get_selection()
      (store, iter) = selection.get_selected()

      if not iter:
        return

      tmpiter = store.get_iter_first()

      if(store.get_path(tmpiter) == store.get_path(iter)):
        return

      while tmpiter:
        next = store.iter_next(tmpiter)
        if(store.get_path(next) == store.get_path(iter)):
          store.swap(iter, tmpiter)
          break
        tmpiter = next

    def on_go_down(self, button, data):
      treeview = data['treeview']
      selection = treeview.get_selection()
      (store, iter) = selection.get_selected()

      if not iter:
        return
      next = store.iter_next(iter)
      if next:
        store.swap(iter, next)

    def on_goto_last(self, button, data):
      treeview = data['treeview']
      selection = treeview.get_selection()
      (store, iter) = selection.get_selected()

      if not iter:
        return
      lastiter = iter
      tmpiter = store.get_iter_first()
      while tmpiter:
        lastiter = tmpiter
        tmpiter = store.iter_next(tmpiter)

      store.move_after(iter, lastiter)


    def on_delete(self, button, data):
      treeview = data['treeview']
      selection = treeview.get_selection()
      (store, iter) = selection.get_selected()
      if iter:
        store.remove(iter)

      return

    def on_edit(self, button, data):
      treeview = data['treeview']
      selection = treeview.get_selection()
      (store, iter) = selection.get_selected()

      if not iter:
        return

      (dialog,enabled,regexp,command) = self._create_command_dialog(
                                                enabled_var = store.get_value(iter, CC_COL_ENABLED),
                                                regexp_var = store.get_value(iter, CC_COL_REGEXP),
                                                command_var = store.get_value(iter, CC_COL_COMMAND)
                                                                  )
      res = dialog.run()
      item = {}
      if res == Gtk.ResponseType.ACCEPT:
        item['enabled'] = enabled.get_active()
        item['regexp'] = regexp.get_text()
        item['command'] = command.get_text()
        if item['regexp'] == '' or item['command'] == '':
          err = Gtk.MessageDialog(dialog,
                                  Gtk.DialogFlags.MODAL,
                                  Gtk.MessageType.ERROR,
                                  Gtk.ButtonsType.CLOSE,
                                  _("You need to define a regexp and a command")
                                )
          err.run()
          err.destroy()
        else:
          tmpiter = store.get_iter_first()
          regexp_exist = False
          while tmpiter != None:
            if store.get_path(tmpiter) != store.get_path(iter) and store.get_value(tmpiter,CC_COL_REGEXP) == item['regexp']:
              regexp_exist = True
              break
            tmpiter = store.iter_next(tmpiter)
          if not regexp_exist:
            store.set(iter,
                      CC_COL_ENABLED,item['enabled'],
                      CC_COL_REGEXP, item['regexp'],
                      CC_COL_COMMAND, item['command']
                      )
          else:
            gerr(_("regexp *%s* already exist") % item['regexp'])

      dialog.destroy()
