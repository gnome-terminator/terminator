---
title: "r02 prefseditor 发现"
type: audit
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "布局 profile 会被写错；调色板重复弹窗；当前布局为 __last_session__ 时偏好页填不完；快捷键搜索失真；配色色块与方案脱节。"
---

# r02 prefseditor 发现

范围内 5 条。

## r02-1

- 严重度：高
- 症状：新增或删除 profile 之后，在布局树里点一个终端，该终端保存的 profile 会变成下拉框里另一个 profile。

`prepare()` 会先填一次下拉框。之后每次加、删 profile 都再调用 `update_profiles()`，只 `append_text`，不清空：

```2663:2676:terminatorlib/prefseditor.py
    def update_profiles(self):
        """Update the list of profiles"""
        self.profile_ids_to_profile = {}
        self.profile_profile_to_ids= {}
        chooser = self.builder.get_object('layout_profile_chooser')

        profiles = self.config.list_profiles()
        profiles.sort()
        i = 0
        for profile in profiles:
            self.profile_ids_to_profile[i] = profile
            self.profile_profile_to_ids[profile] = i
            chooser.append_text(profile)
            i = i + 1
```

调用点在添加成功与否之后，以及删除之后：

```2093:2123:terminatorlib/prefseditor.py
        if self.config.add_profile(newprofile, toclone):
            res = model.append([newprofile, True])
            if res:
                path = model.get_path(res)
                treeview.set_cursor(path, column=treeview.get_column(0),
                                    start_editing=True)

        self.layouteditor.update_profiles()
    ...
        self.config.del_profile(profile)
        model.remove(rowiter)
        selection.select_iter(model.get_iter_first())
        self.layouteditor.update_profiles()
```

点选终端时用重建后的下标 `set_active`。下标是新列表从 0 起算的，下拉框里前面还留着旧条目，选中的不是这个 profile：

```2740:2757:terminatorlib/prefseditor.py
        if 'profile' in layout_item and layout_item['profile'] != '':
            chooser.set_active(self.profile_profile_to_ids[layout_item['profile']])
        else:
            chooser.set_active(0)
        ...
    def on_layout_profile_chooser_changed(self, widget):
        """A new profile has been selected for this item"""
        if not self.layout_item:
            return
        profile = widget.get_active_text()
        layout = self.config.layout_get_config(self.layout_name)
        layout[self.layout_item]['profile'] = profile
        self.config.save()
```

`preferences.glade` 里 `layout_profile_chooser` 的 `changed` 接到了这个回调（约第 4561 行）。`set_active` 换了下标就会发 `changed`，`get_active_text()` 拿到的是错误行上的名字，然后写入布局并 `save()`。

- 方向：刷新 profile 下拉前先清空，或按条目文本选中，不要用追加后重新从 0 编号的下标。

## r02-2

- 严重度：中
- 症状：切换过 profile 之后，点一次调色板色块，关掉颜色对话框还会再弹出，多切换一次就多一个。

`set_profile_values()` 每次都会再 `connect` 一次点击，没有先断开：

```921:926:terminatorlib/prefseditor.py
        for palette_id in range(0, NUM_PALETTE_COLORS):
            widget = self.get_palette_widget(palette_id)
            widget.set_events(Gdk.EventMask.BUTTON_PRESS_MASK)
            def on_palette_click(event, data, widget=widget):
                self.edit_palette_button(widget)
            widget.connect('button-press-event', on_palette_click)
```

打开偏好设置时 `select_iter` 会进 `on_profile_selection_changed()`，其中调用 `set_profile_values()`（第 2332 行）。之后每换一个 profile 再走一遍。glade 里这些色块只有 `draw`，点击只来自这段 `connect`。同一信号上的处理函数会顺序执行，而 `edit_palette_button()` 用 `dialog.run()` 卡住，所以上一个对话框关掉后下一个才出现。

- 方向：调色板点击只连接一次，加载另一个 profile 时不要再次 `connect`。

## r02-3

- 严重度：中
- 症状：当前布局名是 `__last_session__`（或其它不在列表里的名字）时，快捷键和插件两页是空的。

列表里故意去掉了 `__last_session__`，高亮当前布局时却仍用 `layoutname` 去下标，只排除了 `__internal_json_layout__`：

```654:672:terminatorlib/prefseditor.py
        if '__internal_json_layout__' in layouts:
            layouts.remove('__internal_json_layout__')
        if '__last_session__' in layouts:
            layouts.remove('__last_session__')
        self.layoutiters = {}
        for layout in layouts:
            ...
            self.layoutiters[layout] = liststore.append([layout, editable])
        ...
        if terminator.layoutname and terminator.layoutname != '__internal_json_layout__':
            layout_to_highlight = terminator.layoutname
        else:
            layout_to_highlight = 'default'
        selection.select_iter(self.layoutiters[layout_to_highlight])
```

键不在 `layoutiters` 里会 `KeyError`。`set_values()` 包在 try 里，异常只打日志，窗口仍打开（第 321–326 行）。抛出点在第 672 行，快捷键从第 678 行才填，插件从第 743 行才填，这两段不会执行。

- 方向：要高亮的布局名若不在 `layoutiters` 里，就退回 `default`，不要直接下标。

## r02-4

- 严重度：中
- 症状：快捷键搜索框里看到的字和列表过滤结果对不上：要多打一个字符才开始滤，继续输入或退格后列表仍是上一拍的结果，搜到大约 10 个字符就不再变。

过滤接在 `key-press-event` 上，读的是 `get_text()`，并且长度不到 2 或不小于 10 就不 `refilter`。退格另接 `backspace`，回调里立刻 `refilter`，同样不看删完后的文本：

```704:718:terminatorlib/prefseditor.py
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

        kbsearch.connect('key-press-event', on_search)
        kbsearch.connect('backspace', on_search_refilter)
```

这两个信号都在 GtkEntry 默认处理之前发出，字符还没插入、退格也还没删掉。`visible` 函数用的就是这个滞后的 `keybind_filter_str`（第 694–696 行）。粘贴同样只在 key-press 里看到粘贴前的内容。

- 方向：在条目文本已经改变之后，用当前全文 `refilter`，不要在按键默认处理前读文本，也不要在长度边界上直接跳过刷新。

## r02-5

- 严重度：中
- 症状：选了内置配色后，前景/背景色块仍可点，点开会改颜色，但方案下拉还停在该内置方案上；连续换两个内置方案时，色块经常仍显示上一个方案的颜色。勾着「使用系统主题颜色」时，只要方案下标相对初始值有变化，色块也会被重新放开。

加载时先按是否 custom 禁用色块，紧接着 `set_active`。glade 里该组合框 `active` 为 11（Deep teal，第 2821 行），`changed` 接到 `on_color_scheme_combobox_changed`（第 2822 行）。下标真的变了就会进回调：

```894:907:terminatorlib/prefseditor.py
        if scheme == 'custom':
            widget.set_sensitive(True)
        else:
            widget.set_sensitive(False)
        # Background color
        widget = guiget('background_colorbutton')
        widget.set_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        if scheme == 'custom':
            widget.set_sensitive(True)
        else:
            widget.set_sensitive(False)
        # Now actually set the scheme
        widget = guiget('color_scheme_combobox')
        widget.set_active(self.colorschemevalues[scheme])
```

回调无条件把两个色块设为敏感，改的是配置里的颜色并 `reconfigure()`，没有 `queue_draw`。色块是 DrawingArea，`draw` 才从配置读色（第 1411–1420 行、第 1442–1450 行）。`set_sensitive(True)` 在已经敏感时不会再触发重绘，所以第二次切换方案色块不更新。点击处理（`on_foreground_colorbutton_click` / `on_background_colorbutton_click`）只改对应颜色，不把方案下拉改成 Custom。

系统主题色在第 869 行 `set_active`，方案在第 907 行。主题色回调若把色块禁用，后面的方案回调又把它们设回可点。

```2450:2464:terminatorlib/prefseditor.py
        fore = guiget('foreground_colorbutton')
        back = guiget('background_colorbutton')
        fore.set_sensitive(True)
        back.set_sensitive(True)

        forecol = None
        backcol = None
        if value in self.colourschemes:
            forecol = self.colourschemes[value][0]
            backcol = self.colourschemes[value][1]
            self.config['foreground_color'] = forecol
            self.config['background_color'] = backcol
        self.config.save()
        terminator = Terminator()
        terminator.reconfigure()
```

- 方向：方案变化时按「是否 custom、是否使用系统主题色」设置色块能否点击，改完颜色后让两个色块重绘，并让下拉与实际颜色一致。
