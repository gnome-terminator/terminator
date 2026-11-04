---
title: "r04 window 发现"
type: audit
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "发现 5 处：缩放时关终端会拆掉其余窗格，覆盖层里分屏会换掉布局，几何提示、分组切换和 KDE 模糊属性行为错误。"
---

# r04 window 发现

审阅范围仅 `terminatorlib/window.py`。

## r04-1

- 严重度：高
- 症状：放大（legacy zoom）状态下关掉当前终端，窗口里其余被摘走的窗格和它们的 shell 一起被关掉。

```1044:1063:terminatorlib/window.py
    def closeterm(self, widget):
        """Handle a terminal closing"""
        was_overlay_term = (self.is_overlay_maximised() and
                            self.is_maximised_pane(widget))
        leave_zoom(self, legacy=False, overlay=True, reason='closeterm')
        if was_overlay_term:
            from .util import logical_parent
            parent = logical_parent(widget)
            if parent is not None and parent is not self:
                if hasattr(parent, 'wrapcloseterm'):
                    parent.wrapcloseterm(widget)
                elif hasattr(parent, 'closeterm'):
                    parent.closeterm(widget)
                self.hoover()
                return
        Container.closeterm(self, widget)
        self.hoover()
```

```1039:1042:terminatorlib/window.py
    def hoover(self):
        """Ensure we still have a reason to exist"""
        if not self.get_child():
            self.emit('destroy')
```

```1256:1259:terminatorlib/window.py
        self.remove(self.zoom_data['old_child'])
        old_parent.remove(widget)
        self.add(widget)
        self.set_property('term_zoomed', True)
```

`_legacy_zoom` 把原来的整棵布局从窗口摘下，只放在 `zoom_data['old_child']`，窗口上只剩被放大的那一个终端。`add()` 把该终端的 `close-term` 接到 `Window.closeterm`。关闭时 `leave_zoom(..., legacy=False)` 明确不恢复这棵树；本文件里把 `old_child` 装回去的只有 `_legacy_unzoom`。接着基类关掉窗口上这唯一的子终端。子终端被移走后 `get_child()` 为空，`hoover()` 同步 `emit('destroy')`。销毁流程里的 `leave_zoom(legacy=True)` 会把其余窗格装回来再逐个 `close()`。用户只关了一个终端，其余窗格的会话一起没了。

- 方向：先按 legacy 把布局装回窗口，再只关闭当前这一个终端。

## r04-2

- 严重度：高
- 症状：覆盖层最大化时分屏，当前终端被拆出画面，原有分屏布局不再是这扇窗口的布局根，并多出一个 shell。

```1213:1221:terminatorlib/window.py
    def zoom(self, widget, font_scale=True):
        """Dispatch: overlay maximise (default) or legacy reparent zoom."""
        try:
            overlay_on = bool(self.config['pane_overlay_maximise'])
        except Exception:
            overlay_on = True
        if (not font_scale) and overlay_on:
            return self.overlay_maximise(widget, animate=True)
        return self._legacy_zoom(widget, font_scale)
```

```1067:1076:terminatorlib/window.py
        if self.is_zoomed():
            leave_zoom(self, reason='window', quiet=False)
            from .util import logical_parent
            parent = logical_parent(widget)
            parent.split_axis(widget, vertical, cwd, sibling, widgetfirst)
            return

        order = None
        maker = Factory()
        self.remove(widget)
```

```1085:1096:terminatorlib/window.py
        if not sibling:
            sibling = maker.make('Terminal')
            sibling.set_cwd(cwd)
            if self.config['always_split_with_profile']:
                sibling.force_set_profile(None, widget.get_profile())
            sibling.spawn_child()
            if widget.group and self.config['split_to_group']:
                sibling.set_group(None, widget.group)
        elif self.config['always_split_with_profile']:
            sibling.force_set_profile(None, widget.get_profile())

        self.add(container)
```

```1004:1017:terminatorlib/window.py
        if getattr(self, '_overlay', None) is not None and self._overlay.is_active():
            overlay = self._overlay.data['overlay']
            main = self._overlay.main()
            if widget is main:
                try:
                    overlay.remove(widget)
                    self._overlay.note_main_replaced(None)
                except Exception:
                    Gtk.Window.remove(self, widget)
            else:
                Gtk.Window.remove(self, widget)
        else:
            Gtk.Window.remove(self, widget)
        self.disconnect_child(widget)
```

```979:986:terminatorlib/window.py
        if getattr(self, '_overlay', None) is not None and self._overlay.is_active():
            overlay = self._overlay.data['overlay']
            try:
                overlay.add(widget)
                self._overlay.note_main_replaced(widget)
            except Exception:
                Gtk.Window.add(self, widget)
```

`overlay_maximise` 不设置 `term_zoomed`，`is_zoomed()` 仍为假。覆盖层终端的分屏信号由 `terminal_signals` / `_connect_overlay_terminal_signals` 接到窗口的 `split_*`，进入 `split_axis`。被分的终端不是布局根，`Gtk.Window.remove` 摘不掉非直接子控件，但 `disconnect_child` 仍会拆掉它的窗口级信号。随后新终端 `spawn_child()`，`self.add(container)` 在覆盖层激活时按注释把新 paned 记成布局根（`note_main_replaced`）。`container.add` 再把原终端重父到这个 paned。原布局不再是 main，用户看到的窗格被换掉。`tab_new`、`rotate`、`tab_change`、`move_tab`、`detach_tab_to_new_window` 同样只判断 `is_zoomed()`，覆盖层下会改到被挡住的那棵树。

- 方向：覆盖层最大化时先恢复布局，再在终端原来的父控件上分屏或改标签，不要走窗口的 remove/add。

## r04-3

- 严重度：中
- 症状：窗口里一旦有分割，按字符步进缩放时的几何提示把行数和列数重复累加，窗口吸附尺寸是错的。

```1420:1427:terminatorlib/window.py
        for terminal in terminals:
            rect = terminal.get_allocation()
            if rect.x == 0:
                cols, rows = terminal.get_size()
                row_sum = row_sum + rows
            if rect.y == 0:
                cols, rows = terminal.get_size()
                column_sum = column_sum + cols
```

```1438:1454:terminatorlib/window.py
        font_width, font_height = terminal.get_font_size()
        total_font_width = font_width * column_sum
        total_font_height = font_height * row_sum

        win_width, win_height = self.get_size()
        extra_width = win_width - total_font_width
        extra_height = win_height - total_font_height

        dbg('setting geometry hints: (ewidth:%s)(eheight:%s),\
(fwidth:%s)(fheight:%s)' % (extra_width, extra_height, 
                            font_width, font_height))
        geometry = Gdk.Geometry()
        geometry.base_width = extra_width
        geometry.base_height = extra_height
        geometry.width_inc = font_width
        geometry.height_inc = font_height
        self.set_geometry_hints(None, geometry, Gdk.WindowHints.BASE_SIZE | Gdk.WindowHints.RESIZE_INC)
```

这里把 `get_allocation()` 的 `x == 0`、`y == 0` 当成贴着窗口左缘和上缘。GTK3 里 paned 的每个子控件 allocation 原点都是 `(0, 0)`，相对窗口的位置要另做坐标变换。水平分割后左右两个终端都会同时进入 `row_sum` 和 `column_sum`，字符区被算成大约两倍，`base_width` / `base_height` 变成负数或明显偏小，`set_geometry_hints` 仍会拿去约束缩放。

- 方向：用相对这扇窗口的坐标判断左缘和上缘，再累加行列。

## r04-4

- 严重度：中
- 症状：界面语言不是英语时，「全部分组」和「标签分组」的切换关不掉；窗口分组的名字也不会被翻译。

```1502:1514:terminatorlib/window.py
    def group_all(self, widget):
        """Group all terminals"""
        group = _('All')
        self.terminator.create_group(group)
        self.set_groups(group, self.terminator.terminals)

    def group_all_toggle(self, widget):
        """Toggle grouping to all"""
        if widget.group == 'All':
            self.ungroup_all(widget)
        else:
            self.group_all(widget)
```

```1548:1561:terminatorlib/window.py
        pagenum = notebook.get_current_page()
        while True:
            group = _('Tab %d') % pagenum
            if group not in self.terminator.groups:
                break
            pagenum += 1
        self.set_groups(group, self.get_visible_terminals())

    def group_tab_toggle(self, widget):
        """Blah"""
        if widget.group and widget.group[:4] == 'Tab ':
            self.ungroup_tab(widget)
        else:
            self.group_tab(widget)
```

```1520:1526:terminatorlib/window.py
    def group_win(self, widget):
        """Group all terminals in the current window"""
        dbg("Group Windows")
        group = _('Window group %s' % (len(self.terminator.groups) + 1))
        self.terminator.create_group(group)
        self.set_groups(group, self.get_terminals())
```

组名用 `_()` 写成翻译后的字符串，切换却和英文字面量 `'All'`、`'Tab '` 比较。译本一旦不是这两个前缀，条件永远为假，再次触发只会再建组，不会 `ungroup_*`。`group_win` 则先把数字插进英文字符串再交给 `_()`，词条对不上翻译，窗口组名一直是英文 `Window group N`。

- 方向：先对格式串做 gettext 再插值，切换时与翻译后的组名比较。

## r04-5

- 严重度：中
- 症状：打开背景模糊后，窗口上的 KDE 模糊区域是一段不合法的属性，合成器不会按整窗模糊；而且只要别的 profile 开了模糊，当前窗口也会去设这个属性。

```892:901:terminatorlib/window.py
    def on_window_realize(self, widget):
        """Apply window hints once the window is realized"""
        profiles = self.config.base.profiles
        should_blur = False
        for profile in profiles.values():
            if (profile.get('background_blur', False) and
                    profile.get('background_type', 'solid') in ('transparent', 'image')):
                should_blur = True
                break
        self.set_blur_behind(should_blur)
```

```944:947:terminatorlib/window.py
            if enable:
                data = (ctypes.c_ubyte * 4)(0, 0, 0, 0)
                libx11.XChangeProperty(display, xid, blur_atom, cardinal_atom,
                                       32, 0, data, 1)
```

`_KDE_NET_WM_BLUR_BEHIND_REGION` 要的是空属性（整窗模糊）或每 4 个 CARDINAL 一组的矩形。这里 format 为 32、元素个数为 1。format 32 在 64 位上按 `long` 读取，每个元素 8 字节，缓冲区只有 4 字节，会多读 4 字节。读出来也不是空属性，也不是完整矩形，合成器不会按代码意图打开模糊。`on_window_realize` 还扫描全部 profile，任一 profile 同时开了模糊和透明/图片背景，就给这个窗口设 hint，跟当前可见终端用的是不是纯色无关。

- 方向：只按当前窗口正在使用的 profile 决定是否模糊，并用空属性或完整的 long 矩形写入该 hint。
