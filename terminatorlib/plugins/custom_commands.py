#!/usr/bin/env python2
# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""custom_commands.py - Terminator Plugin to add custom command menu entries"""
import sys
import os

# Fix imports when testing this file directly
if __name__ == '__main__':
  sys.path.append( os.path.join(os.path.dirname(__file__), "../.."))

from gi.repository import Gtk
from gi.repository import GObject
import terminatorlib.plugin as plugin
from terminatorlib.config import Config
from terminatorlib.translation import _
from terminatorlib.util import get_config_dir, err, dbg, gerr

(CC_COL_ENABLED, CC_COL_NAME, CC_COL_COMMAND) = range(0,3)

# Every plugin you want Terminator to load *must* be listed in 'AVAILABLE'
AVAILABLE = ['CustomCommandsMenu']

class CustomCommandsMenu(plugin.MenuItem):
    """Add custom commands to the terminal menu"""
    capabilities = ['terminal_menu']
    cmd_list = {}
    conf_file = os.path.join(get_config_dir(),"custom_commands")

    def __init__( self):
      config = Config()
      sections = config.plugin_get_config(self.__class__.__name__)
      if not isinstance(sections, dict):
          return
      noord_cmds = []
      for part in sections:
        s = sections[part]
        if not (s.has_key("name") and s.has_key("command")):
          print "CustomCommandsMenu: Ignoring section %s" % s
          continue
        name = s["name"]
        command = s["command"]
        enabled = s["enabled"] and s["enabled"] or False
        if s.has_key("position"):
          self.cmd_list[int(s["position"])] = {'enabled' : enabled,
                                               'name' : name,
                                               'command' : command
                                              }
        else:
          noord_cmds.append(
                              {'enabled' : enabled,
                                'name' : name,
                                'command' : command
                              }
                            )
        for cmd in noord_cmds:
            self.cmd_list[len(self.cmd_list)] = cmd

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
        command = command['command']
       
        item = {}
        item['enabled'] = enabled
        item['name'] = name
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
        terminal.vte.feed_child(command,  len(command))

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

      store = Gtk.ListStore(bool, str, str)

      for command in [ self.cmd_list[key] for key in sorted(self.cmd_list.keys()) ]:
        store.append([command['enabled'], command['name'], command['command']])
 
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
          (enabled, name, command) = store.get(iter,
                                              CC_COL_ENABLED,
                                              CC_COL_NAME,
                                              CC_COL_COMMAND)
          self.cmd_list[i] = {'enabled' : enabled,
                            'name': name,
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

    def _create_command_dialog(self, enabled_var = False, name_var = "", command_var = ""):
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

      label = Gtk.Label(label=_("Name:"))
      table.attach(label, 0, 1, 1, 2)
      name = Gtk.Entry()
      name.set_text(name_var)
      table.attach(name, 1, 2, 1, 2)
      
      label = Gtk.Label(label=_("Command:"))
      table.attach(label, 0, 1, 2, 3)
      command = Gtk.Entry()
      command.set_text(command_var)
      table.attach(command, 1, 2, 2, 3)

      dialog.vbox.pack_start(table, True, True, 0)
      dialog.show_all()
      return (dialog,enabled,name,command)

    def on_new(self, button, data):
      (dialog,enabled,name,command) = self._create_command_dialog()
      res = dialog.run()
      item = {}
      if res == Gtk.ResponseType.ACCEPT:
        item['enabled'] = enabled.get_active()
        item['name'] = name.get_text()
        item['command'] = command.get_text()
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
          store = data['treeview'].get_model()
          iter = store.get_iter_first()
          name_exist = False
          while iter != None:
            if store.get_value(iter,CC_COL_NAME) == item['name']:
              name_exist = True
              break
            iter = store.iter_next(iter)
          if not name_exist:
            store.append((item['enabled'], item['name'], item['command']))
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
       
      (dialog,enabled,name,command) = self._create_command_dialog(
                                                enabled_var = store.get_value(iter, CC_COL_ENABLED),
                                                name_var = store.get_value(iter, CC_COL_NAME),
                                                command_var = store.get_value(iter, CC_COL_COMMAND)
                                                                  )
      res = dialog.run()
      item = {}
      if res == Gtk.ResponseType.ACCEPT:
        item['enabled'] = enabled.get_active()
        item['name'] = name.get_text()
        item['command'] = command.get_text()
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
                      CC_COL_COMMAND, item['command']
                      )
          else:
            gerr(_("Name *%s* already exist") % item['name'])

      dialog.destroy()
 
      
if __name__ == '__main__':
  c = CustomCommandsMenu()
  c.configure(None, None)
  Gtk.main()

