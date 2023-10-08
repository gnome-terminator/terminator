# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
#
# -added keybinding, bookmark functionality
# -made name parsing to menu, optional
#   - Vishweshwar Saran Singh Deo vssdeo@gmail.com
# TODO: tags

"""custom_commands.py - Terminator Plugin to add custom command menu entries"""
import sys
import os
import time

# Fix imports when testing this file directly
if __name__ == '__main__':
  sys.path.append( os.path.join(os.path.dirname(__file__), "../.."))

from gi.repository import Gtk
from gi.repository import GObject
import terminatorlib.plugin as plugin
from terminatorlib.config import Config
from terminatorlib.translation import _
from terminatorlib.util import get_config_dir, err, dbg, gerr
from terminatorlib.terminator import Terminator

from terminatorlib.plugin import KeyBindUtil

(CC_COL_ENABLED, CC_COL_NAME, CC_COL_NAME_PARSE, CC_COL_COMMAND) = list(range(0,4))

PluginActAdd = "plugin_add"
PluginActBmk = "plugin_bmk"

PluginAddDesc = "Plugin Add Bookmark"
PluginBmkDesc = "Plugin Open Bookmark Preferences"

# Every plugin you want Terminator to load *must* be listed in 'AVAILABLE'
AVAILABLE = ['CustomCommandsMenu']

class CustomCommandsMenu(plugin.MenuItem):
    """Add custom commands to the terminal menu"""
    capabilities = ['terminal_menu']
    cmd_list = {}
    conf_file = os.path.join(get_config_dir(),"custom_commands")
    keyb = None

    def __init__( self):

      # In prev code dbox is needed if _create_command_dialog func is called
      # after configure func where dbox is init. In case we call
      # _create_command_dialog without calling configure func, like in quick
      # bookmark add then we need to check.
      self.dbox = None

      config = Config()
      sections = config.plugin_get_config(self.__class__.__name__)

      self.connect_signals()
      self.keyb = KeyBindUtil(config)
      self.keyb.bindkey_check_config(
        [PluginAddDesc , PluginActAdd, "<Alt>b"])

      self.keyb.bindkey_check_config(
        [PluginBmkDesc , PluginActBmk, "<Shift><Alt>b"])

      if not isinstance(sections, dict):
          return
      noord_cmds = []
      for part in sections:
        s = sections[part]
        if not ("name" in s and "command" in s):
          print("CustomCommandsMenu: Ignoring section %s" % s)
          continue
        name = s["name"]
        name_parse = s.get("name_parse", "True")
        command = s["command"]
        enabled = s["enabled"] and s["enabled"] or False
        if "position" in s:
          self.cmd_list[int(s["position"])] = {'enabled' : enabled,
                                               'name' : name,
                                               'name_parse' : name_parse,
                                               'command' : command
                                              }
        else:
          noord_cmds.append(
                              {'enabled' : enabled,
                                'name' : name,
                                'name_parse' : name_parse,
                                'command' : command
                              }
                            )
        for cmd in noord_cmds:
            self.cmd_list[len(self.cmd_list)] = cmd


    def unload(self):
      dbg("unloading")
      for window in self.windows:
          try:
              window.disconnect_by_func(self.on_keypress)
          except:
              dbg("no connected signals")

      self.keyb.unbindkey(
              [PluginAddDesc , PluginActAdd, "<Alt>b"])
      self.keyb.unbindkey(
              [PluginBmkDesc , PluginActBmk, "<Shift><Alt>b"])

    def connect_signals(self):
      self.windows = Terminator().get_windows()
      for window in self.windows:
        window.connect('key-press-event', self.on_keypress)

    def get_last_exe_cmd(self):
        cur_win  = Terminator().last_focused_term.get_toplevel()

        #TODO: there has to be a better way to get the last command executed
        focus_term = cur_win.get_focussed_terminal()
        tmp_file   = os.path.join(os.sep, 'tmp', 'term_cmd')
        command    = 'fc -n -l -1 -1 > ' + tmp_file + '; #bookmark last cmd\n'
        focus_term.vte.feed_child(str(command).encode("utf-8"))

        fsz     = 0
        count   = 0
        while not (count == 2 or fsz):
            time.sleep(0.1)
            if os.path.exists(tmp_file):
                fsz = os.path.getsize(tmp_file)
                count += 1

        last_cmd   = None
        try:
            with open(tmp_file, 'r') as file:
                last_cmd = file.read()
                file.close()
        except Exception as ex:
             err('Unable to open ‘%s’ ex: (%s)' % (tmp_file, ex))

        if os.path.exists(tmp_file):
            os.remove(tmp_file)

        if last_cmd:
            last_cmd = last_cmd.rstrip()
        dbg('last exec cmd: (%s)' % last_cmd)
        return last_cmd

    def get_last_exe_cmd_dialog_vars(self):
      last_exe_cmd = self.get_last_exe_cmd()

      dialog_vars = { 'enabled'   : True,
                      'name'      : last_exe_cmd,
                      'name_parse': False,
                      'command'   : last_exe_cmd }
      return dialog_vars


    def on_keypress(self, widget, event):
      act = self.keyb.keyaction(event)
      dbg("keyaction: (%s) (%s)" % (str(act), event.keyval))

      if act == PluginActAdd:
          dbg("add bookmark")

          dialog_vars = self.get_last_exe_cmd_dialog_vars()
          self.on_new(None, {'dialog_vars' : dialog_vars })
          self.update_cmd_list(self.store)
          self._save_config()
          return True

      if act == PluginActBmk:
          dbg("open bookmark preferences")
          cur_win  = Terminator().last_focused_term.get_toplevel()
          self.configure(cur_win)
          return True


    def callback(self, menuitems, menu, terminal):
        """Add our menu items to the menu"""
        submenus = {}
        item = Gtk.MenuItem.new_with_mnemonic(_('_Custom Commands'))
        menuitems.append(item)

        submenu = Gtk.Menu()
        item.set_submenu(submenu)

        menuitem = Gtk.MenuItem.new_with_mnemonic(_('_Preferences'))
        menuitem.connect("activate", self.configure)
        submenu.append(menuitem)

        menuitem = Gtk.SeparatorMenuItem()
        submenu.append(menuitem)

        theme = Gtk.IconTheme.get_default()
        for command in [ self.cmd_list[key] for key in sorted(self.cmd_list.keys()) ] :
          if not command['enabled']:
            continue
          exe = command['command'].split(' ')[0]
          iconinfo = theme.choose_icon([exe], Gtk.IconSize.MENU, Gtk.IconLookupFlags.USE_BUILTIN)
          leaf_name = command['name'].split('/')[-1]
          branch_names = command['name'].split('/')[:-1]
          target_submenu = submenu
          parent_submenu = submenu
          if not command['name_parse']:
            leaf_name = command['name']
            branch_names = ''
          else:
            for idx in range(len(branch_names)):
              lookup_name = '/'.join(branch_names[0:idx+1])
              target_submenu = submenus.get(lookup_name, None)
              if not target_submenu:
                item = Gtk.MenuItem(_(branch_names[idx]))
                parent_submenu.append(item)
                target_submenu = Gtk.Menu()
                item.set_submenu(target_submenu)
                submenus[lookup_name] = target_submenu
              parent_submenu = target_submenu
          if iconinfo:
            image = Gtk.Image()
            image.set_from_icon_name(exe, Gtk.IconSize.MENU)
            menuitem = Gtk.ImageMenuItem(leaf_name)
            menuitem.set_image(image)
          else:
            menuitem = Gtk.MenuItem(leaf_name)
          terminals = terminal.terminator.get_target_terms(terminal)
          menuitem.connect("activate", self._execute, {'terminals' : terminals, 'command' : command['command'] })
          target_submenu.append(menuitem)
        
    def _save_config(self):
      config = Config()
      config.plugin_del_config(self.__class__.__name__)
      i = 0
      for command in [ self.cmd_list[key] for key in sorted(self.cmd_list.keys()) ] :
        enabled = command['enabled']
        name = command['name']
        name_parse = command['name_parse']
        command = command['command']
       
        item = {}
        item['enabled'] = enabled
        item['name'] = name
        item['name_parse'] = name_parse
        item['command'] = command
        item['position'] = i

        config.plugin_set(self.__class__.__name__, name, item)
        i = i + 1
      config.save()

    def _execute(self, widget, data):
      command = data['command']
      if command[-1] != '\n':
        command = command + '\n'
      for terminal in data['terminals']:
        terminal.vte.feed_child(command.encode())

    def setup_store(self):
      self.store = Gtk.ListStore(bool, str, bool, str)
      for command in [ self.cmd_list[key] for key in sorted(self.cmd_list.keys()) ]:
        self.store.append([command['enabled'], command['name'],
                      command['name_parse'], command['command']])
      return self.store

    def configure(self, widget, data = None):
      ui = {}
      dbox = Gtk.Dialog(
                      _("Custom Commands Configuration"),
                      None,
                      Gtk.DialogFlags.MODAL,
                      (
                        _("_Cancel"), Gtk.ResponseType.REJECT,
                        _("_OK"), Gtk.ResponseType.ACCEPT
                      )
                    )
      dbox.set_transient_for(widget.get_toplevel())

      icon_theme = Gtk.IconTheme.get_default()
      if icon_theme.lookup_icon('terminator-custom-commands', 48, 0):
        dbox.set_icon_name('terminator-custom-commands')
      else:
        dbg('Unable to load Terminator custom command icon')
        icon = dbox.render_icon(Gtk.STOCK_DIALOG_INFO, Gtk.IconSize.BUTTON)
        dbox.set_icon(icon)

      store = self.setup_store()

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
      column = Gtk.TreeViewColumn(_("Name"), renderer, text=CC_COL_NAME)
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

      button = Gtk.Button(_("Bookmark Last Cmd"))
      button_box.pack_start(button, False, True, 0)
      ui['dialog_vars'] =  self.get_last_exe_cmd_dialog_vars()
      button.connect("clicked", self.on_new, ui)
      ui['button_save_last_cmd'] = button

      hbox.pack_start(button_box, False, True, 0)
      self.dbox = dbox
      dbox.show_all()
      res = dbox.run()
      if res == Gtk.ResponseType.ACCEPT:
        self.update_cmd_list(store)
        self._save_config()
      del(self.dbox)
      dbox.destroy()
      self.dbox = None
      return


    def update_cmd_list(self, store):
        iter = store.get_iter_first()
        self.cmd_list = {}
        i=0
        while iter:
          (enabled, name, name_parse, command) = store.get(iter,
                                              CC_COL_ENABLED,
                                              CC_COL_NAME,
                                              CC_COL_NAME_PARSE,
                                              CC_COL_COMMAND)
          self.cmd_list[i] = {'enabled' : enabled,
                            'name': name,
                            'name_parse' : name_parse,
                            'command' : command}
          iter = store.iter_next(iter)
          i = i + 1
      

    def on_toggled(self, widget, path, data):
      treeview = data['treeview']
      store = treeview.get_model()
      iter = store.get_iter(path)
      (enabled, name, command) = store.get(iter,
                                    CC_COL_ENABLED,
                                    CC_COL_NAME,
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

    def _create_command_dialog(self, enabled_var    = False, name_var = "",
                                     name_parse_var = "", command_var = ""):
      dialog = Gtk.Dialog(
                        _("New Command"),
                        None,
                        Gtk.DialogFlags.MODAL,
                        (
                          _("_Cancel"), Gtk.ResponseType.REJECT,
                          _("_OK"), Gtk.ResponseType.ACCEPT
                        )
                      )
      # dbox is init in configure function, in case we want to
      # create dialog directly
      if self.dbox:
        dialog.set_transient_for(self.dbox)

      table = Gtk.Table(4, 2)
      table.set_row_spacings(5)
      table.set_col_spacings(5)

      label = Gtk.Label(label=_("Enabled:"))
      label.set_alignment(0, 0)
      table.attach(label, 0, 1, 0, 1)
      enabled = Gtk.CheckButton()
      enabled.set_active(enabled_var)
      table.attach(enabled, 1, 2, 0, 1)

      label = Gtk.Label(label=_("Parse Name into SubMenu's:"))
      label.set_alignment(0, 0)
      table.attach(label, 0, 1, 1, 2)
      name_parse = Gtk.CheckButton()
      name_parse.set_active(name_parse_var)
      table.attach(name_parse, 1, 2, 1, 2)

      label = Gtk.Label(label=_("Name:"))
      table.attach(label, 0, 1, 2, 3)
      name = Gtk.Entry()
      name.set_text(name_var)
      table.attach(name, 1, 2, 2, 3)
      
      label = Gtk.Label(label=_("Command:"))
      table.attach(label, 0, 1, 3, 4)
      command = Gtk.TextView()
      command.get_buffer().set_text(command_var)
      table.attach(command, 1, 2, 3, 4)

      dialog.vbox.pack_start(table, True, True, 10)
      dialog.show_all()
      return (dialog,enabled,name,name_parse,command)

    def on_new(self, button, data):

      #default values can be passed to dialogue window if required
      enabled_var   = ''
      name_var      = ''
      name_parse_var= ''
      command_var   = ''

      if data and 'dialog_vars' in data:
        dialog_vars   = data.get('dialog_vars', {})
        enabled_var   = dialog_vars.get('enabled', True)
        name_var      = dialog_vars.get('name', '')
        name_parse_var= dialog_vars.get('name_parse', False)
        command_var   = dialog_vars.get('command', '')

      (dialog,enabled,name,name_parse,command) = self._create_command_dialog(
                                            enabled_var    = enabled_var,
                                            name_var       = name_var,
                                            name_parse_var = name_parse_var,
                                            command_var    = command_var)

      res = dialog.run()
      item = {}
      if res == Gtk.ResponseType.ACCEPT:
        item['enabled'] = enabled.get_active()
        item['name'] = name.get_text()
        item['name_parse'] = name_parse.get_active()
        item['command'] = command.get_buffer().get_text(command.get_buffer().get_start_iter(), command.get_buffer().get_end_iter(), True)
        if item['name'] == '' or item['command'] == '':
          err = Gtk.MessageDialog(dialog,
                                  Gtk.DialogFlags.MODAL,
                                  Gtk.MessageType.ERROR,
                                  Gtk.ButtonsType.CLOSE,
                                  _("You need to define a name and command")
                                )
          err.run()
          err.destroy()
        else:
          # we have a new command
          store = data['treeview'].get_model() if 'treeview' in data else None
          if not store:
            store = self.setup_store()
          iter = store.get_iter_first()
          name_exist = False
          while iter != None:
            if store.get_value(iter,CC_COL_NAME) == item['name']:
              name_exist = True
              break
            iter = store.iter_next(iter)
          if not name_exist:
            store.append((item['enabled'], item['name'],
                          item['name_parse'], item['command']))
          else:
            gerr(_("Name *%s* already exist") % item['name'])
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
       
      (dialog,enabled,name,name_parse,command) = self._create_command_dialog(
                      enabled_var = store.get_value(iter, CC_COL_ENABLED),
                      name_var = store.get_value(iter, CC_COL_NAME),
                      name_parse_var = store.get_value(iter, CC_COL_NAME_PARSE),
                      command_var = store.get_value(iter, CC_COL_COMMAND))
      res = dialog.run()
      item = {}
      if res == Gtk.ResponseType.ACCEPT:
        item['enabled'] = enabled.get_active()
        item['name'] = name.get_text()
        item['name_parse'] = name_parse.get_active()
        item['command'] = command.get_buffer().get_text(command.get_buffer().get_start_iter(), command.get_buffer().get_end_iter(), True)
        if item['name'] == '' or item['command'] == '':
          err = Gtk.MessageDialog(dialog,
                                  Gtk.DialogFlags.MODAL,
                                  Gtk.MessageType.ERROR,
                                  Gtk.ButtonsType.CLOSE,
                                  _("You need to define a name and command")
                                )
          err.run()
          err.destroy()
        else:
          tmpiter = store.get_iter_first()
          name_exist = False
          while tmpiter != None:
            if store.get_path(tmpiter) != store.get_path(iter) and store.get_value(tmpiter,CC_COL_NAME) == item['name']:
              name_exist = True
              break
            tmpiter = store.iter_next(tmpiter)
          if not name_exist:
            store.set(iter,
                      CC_COL_ENABLED,item['enabled'],
                      CC_COL_NAME, item['name'],
                      CC_COL_NAME_PARSE, item['name_parse'],
                      CC_COL_COMMAND, item['command']
                      )
          else:
            gerr(_("Name *%s* already exist") % item['name'])

      dialog.destroy()


if __name__ == '__main__':
  c = CustomCommandsMenu()
  c.configure(None, None)
  Gtk.main()

