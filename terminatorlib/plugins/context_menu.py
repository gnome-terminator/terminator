"""
- Context Menu Plugin - Vishweshwar Saran Singh Deo <vssdeo@gmail.com>
- 
- Adds a context menu (right click) 
- Gives an UI under Preferences->Plugins with capability to organize items
- Supported by PluginEventRegistry which helps to add plugin actions to menu
-   apart from other plugins using this, for eg. this context_menu_plugin can
-   register its menu functions while itself creating a menu
- ContextMenu items will appear in the order of plugin loading, so may be later
    we can have a priority / order in plugin loading
- Supported by KeyBindUtil for action key / desc matching
- Changes made to prefseditor.py for selection of plugin preferences, 
- update_gui etc
- Cleans and identifies common dependencies which can we further worked on
-
- Gradual removal of menuitems to be done with checking logic and removal of if
- based conditions. All cases are being compiled in class Filter below which
- have to be removed
-
"""

import gi
import os
import time
gi.require_version('Vte', '2.91')  # vte-0.38 (gnome-3.14)
from gi.repository import Vte

from gi.repository import Gtk, Gdk
from terminatorlib.terminator import Terminator

from terminatorlib.config import Config
from terminatorlib import config

import terminatorlib.plugin as plugin
from terminatorlib.keybindings import Keybindings, KeymapError

from terminatorlib.util import get_config_dir, err, dbg, gerr
from terminatorlib import regex

from terminatorlib.prefseditor import PrefsEditor

from terminatorlib.translation import _



AVAILABLE = ['PluginContextMenu']

PluginContextMenuAct = '(Plugin) Edit_menu'
PluginContextMenuDesc= 'Plugin Edit Menu' 

#Main Plugin

class PluginContextMenu(plugin.MenuItem):

    capabilities = ['terminal_menu']
    handler_name = 'PluginContextMenu'
    nameopen     = None
    namecopy     = None

    filter       = None #TODO: REMOVE

    config       = Config()
    plugin_gui   = plugin.PluginGUI()
    prev_widget  = None

    #this won't have all keybinds, eg of plugins as all plugins
    #are being loaded now so we will reload it again
    keybindutil  = plugin.KeyBindUtil()

    event_registry = plugin.PluginEventRegistry()

    #UI elements <> are handled specially as left->right won't append
    #to right but a single copy will be there on right
    #for left<-right the item in right will remain and an instance of
    #that element will be copied to left

    UI_SEPARATOR = '<Separator>'
    ui_elements  = { UI_SEPARATOR : {
                                     'count' : 0, 
                                     'widget': Gtk.SeparatorMenuItem()
                                     }
                   }

    #PluginContextMenuAct (edit context menu) action will be appended to this
    DEFAULT_MENU = {k: v for v, k in 
                    enumerate(['copy',      'paste',       'edit_window_title',
                               'split_auto','split_horiz', 'split_vert',
                               'new_tab',   'close_term',   'toggle_scrollbar',
                               'zoom',      'maximise',     'unzoom', 
                               'open_debug_tab'
                              ])}

    #TODO:move this to a better place / redo once code is stabilized 
    MAP_ACTION_ICONS = {

        'split_vert' : 'terminator_vert',
        'split_horiz': 'terminator_horiz'
    }

    def __init__(self):

        dbg('loading context_menu plugin')
        self.connect_signals()

        #call PluginContext Editor in Preferences for action PluginContextMenuAct
        self.keybindutil.bindkey_check_config(
                [PluginContextMenuDesc, PluginContextMenuAct, "<Alt>m"])

        PluginContextMenu.event_registry.register(
                                PluginContextMenuAct, 
                                self.lauch_pref_context_menu,
                                self.handler_name)

        self.reload_plugin_config()

        self.accelgrp    = Gtk.AccelGroup()
        self.left_select_actions  = {}


    def reload_plugin_config(self):
        self.config_keyb = self.config.plugin_get_config(self.handler_name)
        if not self.config_keyb:
            self.config_keyb = {}


    def connect_signals(self):

        self.windows = Terminator().get_windows()
        for window in self.windows:
            window.connect('key-press-event', self.on_keypress)


    def update_gui(self, widget, visible):

        #restore prev UI to Prefs->Plugins->ContextMenu
        if not visible and self.prev_widget:
            self.plugin_gui.add_gui(widget, self.prev_widget)
            return

        plugin = self.__class__.__name__

        plugin_builder      = self.plugin_gui.get_glade_builder(plugin)
        self.plugin_builder = plugin_builder

        self.plugin_window = plugin_builder.get_object('PluginContextMenu')

        tview_left  = plugin_builder.get_object('PluginContextMenuListLeft')
        tview_right = plugin_builder.get_object('PluginContextMenuListRight')

        self.tview_left  = tview_left
        self.tview_right = tview_right

        self.store_left  = plugin_builder.get_object('KeybindingListStoreLeft')
        self.store_right = plugin_builder.get_object('KeybindingListStoreRight')


        TARGETS = [ ('TREE_MODEL_ROW', Gtk.TargetFlags.SAME_WIDGET, 0) ]
        self.tview_left.enable_model_drag_source( Gdk.ModifierType.BUTTON1_MASK,
                                                TARGETS,
                                                Gdk.DragAction.DEFAULT|
                                                Gdk.DragAction.MOVE)

        tview_left.enable_model_drag_dest(TARGETS, Gdk.DragAction.DEFAULT)

        tview_left.connect("drag-data-get",     self.on_drag_data_get)
        tview_left.connect("drag-data-received",self.on_drag_data_received)
        
        button_mv_left = plugin_builder.get_object('ContextMenuPluginMoveLeft')
        button_mv_left.connect('clicked', self.on_button_mv_left,
                                                tview_left, tview_right)

        button_mv_right = plugin_builder.get_object('ContextMenuPluginMoveRight')
        button_mv_right.connect('clicked', self.on_button_mv_right, 
                                                tview_left, tview_right)

        button_discard = plugin_builder.get_object('PluginContextMenuButtonDiscard')
        button_discard.connect('clicked', self.on_button_discard_clicked)

        button_add = plugin_builder.get_object('PluginContextMenuButtonApply')
        button_add.connect('clicked', self.on_button_add_clicked)

        #add UI to Prefs->Plugins->ContextMenu
        prev_widget = self.plugin_gui.add_gui(widget, self.plugin_window)
        if not self.prev_widget:
            self.prev_widget = prev_widget

        self.setup_data()


    def setup_data(self):
        self.left_select_actions  = {}
        self.store_left.clear()
        self.store_right.clear()

        self.set_context_menu_items(self.tview_left)

        #reset filter layer before setting up
        self.tview_right.set_model(self.store_right)
        self.set_act_menu_items(self.tview_right)

        
    def on_drag_data_get(self, tv, drag_context, selection, info, time):
        treeselection = tv.get_selection()
        model, iter = treeselection.get_selected()
        path = model.get_path(iter)
        row  = path.get_indices()[0]
        dbg('on_drag_data_get :%s model:%s row:%s' % (selection, model, row))
        selection.set(selection.get_target(), 8, b'%d' % (row))


    def on_drag_data_received(self, tv, context, x, y, selection, info, time):

        model    = tv.get_model()
        sel_row  = int(selection.get_data())
        sel_iter = model.get_iter(sel_row)
        drop_info = tv.get_dest_row_at_pos(x, y)
        data = list(model[sel_iter])
        if drop_info:
            path, position = drop_info
            dbg('on_drag_data_received: data: %s path:%s pos: %s' 
                                        % (data, path, position))
            iter = model.get_iter(path)
            if (position == Gtk.TreeViewDropPosition.BEFORE
                or position == Gtk.TreeViewDropPosition.INTO_OR_BEFORE):
                model.insert_before(iter, data)
            else:
                model.insert_after(iter, data)
            model.remove(sel_iter)
        #else:
        #    model.append(data)
        if context.get_actions() == Gdk.DragAction.MOVE:
            context.finish(True, True, etime)

        return


    def get_cfg_context_menu_items(self):

        self.reload_plugin_config()
        plugin_keybindings  = self.config_keyb.get('plugin_keybindings', {})

        #if any entries in section else use default 
        cfg_keys = list(plugin_keybindings.keys())
        plugin_keybindings_len = len(list(plugin_keybindings.keys()))

        if not plugin_keybindings_len:
            cfg_keys = list(self.DEFAULT_MENU.keys())
            #edit of context menu should be default
            cfg_keys.append(PluginContextMenuAct)

        return cfg_keys


    def set_context_menu_items(self, widget):

        liststore = widget.get_model()
        #liststore.set_sort_column_id(0, Gtk.SortType.ASCENDING)

        keybindings         = Keybindings()
        key_action_map      = self.keybindutil.get_all_act_to_keys()
        key_action_desc_map = self.keybindutil.get_all_act_to_desc()

        plugin_keybindings  = self.config_keyb.get('plugin_keybindings', {})

        
        cfg_keys = self.get_cfg_context_menu_items()
        for action in cfg_keys:

            actkey  = key_action_map.get(action, '')

            if len(plugin_keybindings):
                position = int(plugin_keybindings.get(action,{}).get('position', 0))
                dbg('inserting at config pos:%s action:%s' % (position, action))
            else:
                position = self.DEFAULT_MENU.get(action, -1)
                dbg('inserting at default:%s action:%s' % (position, action))

            self.left_select_actions[action] = True

            keyval = 0
            mask   = 0
            try:
                (keyval, mask) = keybindings._parsebinding(actkey)
            except KeymapError:
                dbg('no keyval for:%s' % actkey)
                pass

            (parsed_action, count) = self.parse_ui_element(action)
            actdesc = key_action_desc_map.get(parsed_action, '')

            if parsed_action and count:
                actdesc = parsed_action #for ui elements action and desc same
                saved_count = PluginContextMenu.ui_elements[parsed_action]['count']
                if count > saved_count:
                    PluginContextMenu.ui_elements[parsed_action]['count'] = count

            liststore.insert(position, [action, actdesc, keyval, mask])


    def set_act_menu_items(self, widget):
        ## Keybindings tab

        self.treemodelfilter = None
        right_kbsearch  = self.plugin_builder.get_object('PluginContextMenuSearchRight')
        self.keybind_filter_str = ""

        #lets hide whatever we can in nested scope
        def filter_visible(model, treeiter, data):
            act  = model[treeiter][0]
            keys = data[act] if act in data else ""
            desc = model[treeiter][1]
            kval = model[treeiter][2]
            mask = model[treeiter][3]
            #so user can search for disabled keys also
            if not (len(keys) and kval and mask):
                act = "Disabled"

            self.keybind_filter_str = self.keybind_filter_str.lower()
            searchtxt = (act + " " + keys + " " + desc).lower()
            pos = searchtxt.find(self.keybind_filter_str)
            if (pos >= 0):
                dbg("filter find:%s in search text: %s" %
                                (self.keybind_filter_str, searchtxt))
                return True

            return False

        #local scoped func
        def on_search(widget, text):
            MAX_SEARCH_LEN = 10
            self.keybind_filter_str = widget.get_text()
            ln = len(self.keybind_filter_str)
            #its a small list & we are eager for quick search, but limit
            if (ln >=2 and ln < MAX_SEARCH_LEN):
                dbg("filter search str: %s" % self.keybind_filter_str)
                self.treemodelfilter.refilter()

        def on_search_refilter(widget):
            dbg("refilter")
            self.treemodelfilter.refilter()

        right_kbsearch.connect('key-press-event', on_search)
        right_kbsearch.connect('backspace', on_search_refilter)

        liststore = widget.get_model()
        liststore.set_sort_column_id(0, Gtk.SortType.ASCENDING)
        liststore.append([
                    PluginContextMenu.UI_SEPARATOR,
                    PluginContextMenu.UI_SEPARATOR, 0, 0])

        #to keep separator and other items first
        def compare(model, row1, row2, user_data):
            sort_column, _ = model.get_sort_column_id()
            value1 = model.get_value(row1, sort_column)
            value2 = model.get_value(row2, sort_column)
            if value1 < value2:
                return -1
            elif value1 == value2:
                return 0
            else:
                return 1

        liststore.set_sort_func(0, compare, None)

        keyb = Keybindings()
                
        key_action_map       = self.keybindutil.get_all_act_to_keys()
        key_action_desc_map  = self.keybindutil.get_all_act_to_desc()
        for action in key_action_map:
            keyval  = 0
            mask    = 0
            actkey  = key_action_map[action]
            if actkey is not None and actkey != '':
                try:
                    (keyval, mask) = keyb._parsebinding(actkey)
                except KeymapError:
                    dbg('no keyval for:%s act:%s' % (actkey, action))
                    pass

            if not action in self.left_select_actions:
                desc = key_action_desc_map[action]
                liststore.append([action, desc, keyval, mask])
            else:
                dbg('skipping item:%s' % action)

        self.treemodelfilter = liststore.filter_new()
        self.treemodelfilter.set_visible_func(filter_visible, key_action_map)
        widget.set_model(self.treemodelfilter)


    def parse_ui_element(self, actstr):
        s = actstr.find('<')
        e = actstr.rfind('>')

        count = 0
        if s == 0 and e > 0:
            act = actstr[s:e+1]
            if e+1 < len(actstr):
                count = int(actstr[e+1:])
            dbg('action string: %s count: %s' % (act, count))
            return (act, count)

        dbg('action string: %s count: %s' % (actstr, count))
        return (actstr, count)


    #ui items may have to be repeated like <Separator> since we store
    #items in config, we need to make these unique
    def append_count_ui_act(self, actstr):

        (parsed_action, count) = self.parse_ui_element(actstr)

        ui_element = PluginContextMenu.ui_elements.get(parsed_action, None)
        if ui_element:
            ui_element['count'] += 1
            dbg('ui_elements: (%s)' % PluginContextMenu.ui_elements)
            return parsed_action + str(ui_element['count'])

        return actstr


    def on_button_mv_left(self, button, tview_left, tview_right):
        #left<-right
        right_select = tview_right.get_selection()
        model, paths = right_select.get_selected_rows()

        for path in paths:
            iter = model.get_iter(path)
            # Remove the ListStore row referenced by iter
            row = model.get(iter, 0,1,2,3)
            index = path.get_indices()[0]
            dbg('moving right->left item :%s ui index:%s' % (row, index))

            # append number to ui elements so they are unique 
            row = list(row)
            checked_actstr  = self.append_count_ui_act(row[0])
            row[0] = checked_actstr

            tview_left.get_model().append(row)

            tview_right_filt = tview_right.get_model()
            tview_right_filt_iter = tview_right_filt.convert_iter_to_child_iter(iter)

            actstr = row[0]
            (parsed_action, count)  = self.parse_ui_element(actstr)

            #ui items have a single entry <Separator>
            #are not moved they remain in list but are copied
            if not (parsed_action in PluginContextMenu.ui_elements):
                tview_right_filt.get_model().remove(tview_right_filt_iter)


    #re-index the ui_elements 
    def refresh_ui_counts(self, actstr, store):
        rindex = 0
        for row in store:
            actstr = row[0]
            (parsed_action, count)  = self.parse_ui_element(actstr)
            if parsed_action in PluginContextMenu.ui_elements:
                edited_actstr = self.append_count_ui_act(parsed_action)
                store[rindex][0] =  edited_actstr
            rindex += 1


    def on_button_mv_right(self, button, tview_left, tview_right):
        #left->right
        left_select  = tview_left.get_selection()
        model, paths = left_select.get_selected_rows()

        for path in paths:
            iter = model.get_iter(path)
            # Remove the ListStore row referenced by iter
            row = model.get(iter, 0,1,2,3)
            index = path.get_indices()[0]
            dbg('moving right<-left item:%s ui index:%s' % (row, index))

            tview_right_filt = tview_right.get_model()

            #ui items have a single entry ensure <Separator>1 ...
            #are not added only <Separator> exists

            actstr = row[0]
            (parsed_action, count)  = self.parse_ui_element(actstr)
        
            tview_left.get_model().remove(iter)

            if not (parsed_action in PluginContextMenu.ui_elements):
                tview_right_filt.get_model().append(row)
            else:
                saved_count = PluginContextMenu.ui_elements[parsed_action]['count']
                if saved_count > 0:
                    PluginContextMenu.ui_elements[parsed_action]['count'] = 0
                    self.refresh_ui_counts(actstr, model)



    def on_button_discard_clicked(self, button):
        dbg('on_button_discard_clicked')
        self.setup_data()
        pass


    def on_button_add_clicked(self, button):
        position = 0
        self.config_keyb = {}
        for row in self.store_left:

            dbg('adding to config: %s' % row[0])
            actstr = row[0]
            desc   = row[1]
            key    = row[2]
            mods   = row[3]

            accel  = Gtk.accelerator_name(key, Gdk.ModifierType(mods))

            config_key_sec = {}

            config_key_sec['accel']     = accel
            config_key_sec['desc']      = desc
            config_key_sec['position']  = position
            self.config_keyb[actstr]    = config_key_sec

            position += 1

        dbg('saving config: [%s] (%s)' % (self.handler_name, self.config_keyb))

        #Note: we can't keep the name of section 'keybindings' else it throw error
        #in config.save which calls dict_diff, TODO: clean up old code 
        self.config.plugin_set_config(self.handler_name, 
                            {'plugin_keybindings' : self.config_keyb})
        self.config.save()


    #menu label that gets displayed to user
    def get_menu_label(self, actstr):
        desc = self.keybindutil.get_act_to_desc(actstr)
        desc = desc.title()
        return desc


    #we get a callback for menu
    def callback(self, menuitems, menu, terminal):
        self.terminal = terminal

        cfg_keys = self.get_cfg_context_menu_items()

        for row in cfg_keys:
            dbg('adding to menu: %s' % row)
            actstr  = row
            item    = self.menu_item(Gtk.ImageMenuItem, actstr)
            if not item:
                continue

            img_name = PluginContextMenu.MAP_ACTION_ICONS.get(actstr, None)
            if (img_name):
                image = Gtk.Image()
                image.set_from_icon_name(img_name, Gtk.IconSize.MENU)
                item.set_image(image)
                if hasattr(item, 'set_always_show_image'):
                    item.set_always_show_image(True)

            menuitems.append(item)


    #intercept function, handle as per PluginEventRegistry else
    #allow to propogate to terminal key_ mappings
    def on_keypress_external(self, widget, actstr):

        if self.event_registry.call_action_handlers(actstr):
            dbg('handler found and called, not propogating event to terminal')
            return True

        try:
            terminal = self.terminal
            terminal.on_keypress(terminal.get_window(), None, actstr)
        except:
            gerr(_("Action not registered by termial/plugin for action: %s")
                                                                    % actstr)

    
    #TODO from terminal_popup_menu may require futher cleanup
    def menu_item(self, menutype, actstr):

    
        #this won't have all keybinds, eg of plugins as all plugins
        #are being loaded now so we will reload it again
        self.keybindutil.load_merge_key_maps() 

        key_action_map   = self.keybindutil.get_all_act_to_keys()

        maskstr = key_action_map.get(actstr, '')

        (actstr, count)  = self.parse_ui_element(actstr)
        #check ui element using desc
        menu_ui = PluginContextMenu.ui_elements.get(actstr, None)
        if menu_ui:
            dbg('adding ui_element: %s' % actstr)
            return menu_ui['widget'].new()

        keybindings = Keybindings()

        keyval = 0
        mask   = 0
        try:
            (keyval, mask) = keybindings._parsebinding(maskstr)
        except KeymapError:
            dbg('no keyval :%s action:%s' % (maskstr, actstr))
            pass

        mask    = Gdk.ModifierType(mask)

        menustr = self.get_menu_label(actstr)

        accelchar = ""
        pos = menustr.lower().find("_")
        if (pos >= 0 and pos+1 < len(menustr)):
            accelchar = menustr.lower()[pos+1]

        #this may require tweak. what about shortcut function keys ?
        if maskstr:
            mpos = maskstr.rfind(">")
            #can't have a char at 0 position as <> is len 2
            if mpos >= 0 and mpos+1 < len(maskstr):
                configaccelchar = maskstr[mpos+1:]
                #ensure to take only 1 char else ignore
                if len(configaccelchar) == 1:
                    dbg("found accelchar in config:%s  override:%s"
                                    %  (configaccelchar, accelchar))
                    accelchar = configaccelchar

        dbg("action from config:%s for item:%s with shortcut accelchar:(%s)"
                                    % (maskstr, menustr, accelchar))

        item = menutype.new_with_mnemonic(_(menustr))

        #TODO:REMOVE
        #filter use cases for now, will be removed once
        #all if-then else from terminal_popup_menu are 
        #cleaned and refactored
        if not self.filter:
            self.filter = Filter(self.terminal)
        if not self.filter.filter_act(actstr, item):
            item = None
            return item

        item.connect('activate', self.on_keypress_external, actstr)
        if mask:
            item.add_accelerator("activate",
                                self.accelgrp,
                                Gdk.keyval_from_name(accelchar),
                                mask,
                                Gtk.AccelFlags.VISIBLE)
        return item


    def unload(self):
        dbg("unloading")
        for window in self.windows:
            try:
                window.disconnect_by_func(self.on_keypress)
            except:
                dbg("no connected signals")

        self.keybindutil.unbindkey(
                [PluginContextMenuDesc , PluginContextMenuAct, "<Alt>m"])

        PluginContextMenu.event_registry.unregister(
                                PluginContextMenuAct, 
                                self.lauch_pref_context_menu,
                                self.handler_name)


    def get_term(self):
        return  Terminator().last_focused_term


    def lauch_pref_context_menu(self, actstr):
        dbg("open context menu preferences")
        pe = PrefsEditor(self.get_term(), cur_page = 4)
        pe.select_plugin_in_pref(self.handler_name)


    def on_keypress(self, widget, event):
        act = self.keybindutil.keyaction(event)
        dbg("keyaction: (%s) (%s)" % (str(act), event.keyval))

        if act == PluginContextMenuAct:
            self.lauch_pref_context_menu(act)
            return True




#TODO:REMOVE ,if-then based conditions from terminal_popup_menu, 
#lets get them together first #to check all conditions and start cleaning up
#
#this also show cases how PluginEventRegistry comes handy and actions can be 
#intercepted and action be taken we intercept these because these dont have 
#a key_ mapping in terminal
#
#DO NOT ADD new dependencies here this will be REMOVED

class Filter:
    terminal = None

    def __init__(self, terminal):

       self.terminal  = terminal
       event_registry = plugin.PluginEventRegistry()
       act_id = 'context_menu'
       PluginContextMenu.event_registry.register('zoom',    terminal.zoom, act_id)
       PluginContextMenu.event_registry.register('maximise',terminal.maximise, act_id)
       PluginContextMenu.event_registry.register('unzoom',  terminal.unzoom, act_id)
       PluginContextMenu.event_registry.register('open_debug_tab',
                            lambda x: terminal.emit('tab-new', True, terminal),
                            act_id)

    def filter_act(self, actstr, menuitem):

       #following actions were missing from config and from key_ mapping in
       #terminal so to get them working temp
       terminal = self.terminal
       if actstr == 'copy':
            menuitem.set_sensitive(terminal.vte.get_has_selection())
            return True
                
       acts =  ['split_auto', 'split_horiz', 'split_vert', 
                'new_tab', 'open_debug_tab', 
                'zoom', 'maximise',
                'unzoom' ]

       if actstr in acts:
            if not terminal.is_zoomed():
                if actstr in ['zoom', 'maximise']:
                    sensitive = not terminal.get_toplevel() == terminal.get_parent()
                    menuitem.set_sensitive(sensitive)
                    return True
                elif actstr in ['open_debug_tab']:
                    return Terminator().debug_address
                elif actstr in ['unzoom']:
                    return False

            elif actstr in ['unzoom']:
                return True
            else:
                dbg('terminal zoomed remove actstr: %s' % actstr)
                return False
        
       return True

