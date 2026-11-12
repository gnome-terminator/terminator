---
title: "r01 terminal 发现"
type: audit
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "terminal.py 有 5 处用户可见缺陷：Flatpak 子进程 pid 丢失、拖放链接被执行、关闭背景图后不清屏、平滑滚轮误缩放、滚动条抢走焦点。"
---

## r01-1 中

**症状：** Flatpak 里启动的终端没有子进程号。关闭时不会给 shell 发 SIGHUP，也不会等它退出；启动失败时界面不提示；没有 OSC 7 时分屏和工作目录探测不再跟 shell 的当前目录。

**代码：**

```2413:2425:terminatorlib/terminal.py
            self.pid = self.vte.spawn_async(
                Vte.PtyFlags.NO_CTTY,
                self.cwd,
                args,
                envv,
                0,
                None,
                None,
                -1,
                None,
                None,
                None,
            )
```

```2444:2446:terminatorlib/terminal.py
        if self.pid == -1:
            self.vte.feed((_('Unable to start shell:') + shell).encode('utf-8'))
            return -1
```

```416:420:terminatorlib/terminal.py
        if self.pid is not None:
            try:
                dbg('close: killing %d' % self.pid)
                os.kill(self.pid, signal.SIGHUP)
```

```447:447:terminatorlib/terminal.py
            self._wait_for_shell_exit()
```

```354:357:terminatorlib/terminal.py
        if self.pid is None:
            # Child exited (m21 clears the pid) or never spawned:
            # psutil.Process(None) would report *Terminator's* own cwd.
            return getattr(self, '_last_session_cwd', None)
```

```3471:3472:terminatorlib/terminal.py
            if self.pid is None:
                return False
```

**为什么是问题：** `spawn_async` 立刻返回，子进程号只在回调里给出。这里回调三个参数都是 `None`，返回值被写进 `self.pid`，成功时也是 `None`，不是 `-1`。`pid == -1` 的失败提示因此走不到。`close()` 只在 `self.pid is not None` 时发 SIGHUP 并等待退出，Flatpak 终端整段被跳过。`get_cwd()` 和 `cwd_probe_check()` 见到 `pid is None` 就不再读该进程的目录，`_last_session_cwd` 也不会被探针写上。

**方向：** 在 spawn 完成回调里记下真实 pid，失败时走和非 Flatpak 分支一样的提示与关闭清理。

## r01-2 中

**症状：** 从 KDE 一类来源把链接拖进终端时，网址和页面标题会一起送进 shell，中间的换行会把网址当场当成命令执行。

**代码：**

```1984:1996:terminatorlib/terminal.py
            if info == self.TARGET_TYPE_MOZ:
                 txt = txt.decode('utf-16')
                 # KDE ends it's text/x-moz-url text with CRLF, :shrug:
                 if not txt.endswith('\r\n'):
                   txt = txt.split('\n')[0]
            else:
                 txt = txt.decode()

            txt_lines = txt.split( "\r\n" )
            if txt_lines[-1] == '':
                for line in txt_lines[:-1]:
                    if line[0:7] != 'file://':
                        txt = txt.replace('\r\n','\n')
```

```2007:2010:terminatorlib/terminal.py
            # Never send a CRLF to the terminal from here
            txt = txt.rstrip('\r\n')
            for term in self.terminator.get_target_terms(self):
                term.feed(txt)
```

**为什么是问题：** `text/x-moz-url` 的正文是「URL + 换行 + 标题」。注释写明 KDE 以 CRLF 结尾，但只有**不以** `\r\n` 结尾时才取第一行。以 `\r\n` 结尾的内容会落到下面的分支，把 CRLF 换成 LF。`rstrip` 只去掉末尾换行，URL 和标题之间的换行还在。`feed()` 看到换行就交给 PTY，行规程会提交这一行，标题成为下一条命令。

**方向：** 这种拖放只保留 URL 那一行，不要把标题和换行写进终端。

## r01-3 中

**症状：** 用过图片背景之后再改回纯色或透明，终端不再清背景，旧画面会残留或透出底下的内容。图片模式每重新应用一次配置，就多挂一个绘制回调。

**代码：**

```293:302:terminatorlib/terminal.py
    def set_background_image(self,image):
        try: 
            bg_pixbuf = GdkPixbuf.Pixbuf.new_from_file(image)
            self.background_image = Gdk.cairo_surface_create_from_pixbuf(bg_pixbuf, 1, None)
            self._bg_image_scale = 1
            self.vte.set_clear_background(False)
            self.vte.connect("draw", self.background_draw)
        except Exception as e:
            self.background_image = None
            self.vte.set_clear_background(True)
```

```1013:1016:terminatorlib/terminal.py
        if self.config['background_type'] == 'image' and self.config['background_image'] != '':
            self.set_background_image(self.config['background_image'])
        else:
            self.background_image = None
```

**为什么是问题：** `set_clear_background(False)` 之后 VTE 不再自己铺背景，要靠 `background_draw` 画。离开图片模式时只把 `background_image` 置空，不把 clear background 设回打开，也不拆掉已经连上的 draw。回调见到空图直接返回，谁都不画背景。`set_clear_background(True)` 只出现在加载失败的异常路径。另外，每次 `reconfigure()` 仍走图片分支时都会再 `connect` 一次，回调叠加上去；图片没铺满窗口时，半透明的 `bgcolor` 蒙层会一层层盖上去。

**方向：** 离开图片背景时恢复由 VTE 清背景并卸掉绘制回调，重复配置不要叠加连接。

## r01-4 中

**症状：** 按住 Ctrl 用触控板或平滑滚轮时，字体会一次跳很多档，垂直增量为 0 的事件也会放大。按住 Shift 时同样会一次翻很多页。Ctrl+Shift+滚轮不会缩放同组终端。

**代码：**

```1429:1459:terminatorlib/terminal.py
        SMOOTH_SCROLL_UP = event.direction == Gdk.ScrollDirection.SMOOTH and event.delta_y <= 0.
        SMOOTH_SCROLL_DOWN = event.direction == Gdk.ScrollDirection.SMOOTH and event.delta_y > 0.

        modifiers = event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK)
        if modifiers == Gdk.ModifierType.CONTROL_MASK:
            # Zoom the terminal(s) in or out if not disabled in config
            if self.config["disable_mousewheel_zoom"] is True:
                return False
            # Choice of target terminals depends on Shift and Super modifiers
            if event.state & Gdk.ModifierType.MOD4_MASK == Gdk.ModifierType.MOD4_MASK:
                targets = self.terminator.terminals
            elif event.state & Gdk.ModifierType.SHIFT_MASK == Gdk.ModifierType.SHIFT_MASK:
                targets = self.terminator.get_target_terms(self)
            else:
                targets = [self]
            if event.direction == Gdk.ScrollDirection.UP or SMOOTH_SCROLL_UP:
                for target in targets:
                    target.zoom_in()
                return True
            elif event.direction == Gdk.ScrollDirection.DOWN or SMOOTH_SCROLL_DOWN:
                for target in targets:
                    target.zoom_out()
                return True
        elif modifiers == Gdk.ModifierType.SHIFT_MASK:
            # Shift + mouse wheel up/down
            if event.direction == Gdk.ScrollDirection.UP or SMOOTH_SCROLL_UP:
                self.scroll_by_page(-1)
                return True
            elif event.direction == Gdk.ScrollDirection.DOWN or SMOOTH_SCROLL_DOWN:
                self.scroll_by_page(1)
                return True
```

**为什么是问题：** 平滑滚动每个事件的 `delta_y` 往往远小于一格，代码却只看符号，不看大小，每个事件都缩放一档或翻一整页。`delta_y <= 0` 把 0 也当成向上，纯水平或增量为 0 的平滑事件会放大字体、向上翻页。Ctrl+Shift 时 `modifiers` 同时含 Control 和 Shift，既不等于只有 Control，也不等于只有 Shift，缩放分支进不去；里面按 Shift 选同组终端的 `elif` 因此永远到不了，事件最后原样返回。

**方向：** 平滑滚动按 delta 累计并忽略 0；Ctrl+Shift 要能进入同组缩放，而不是被修饰键掩码挡在外面。

## r01-5 中

**症状：** 点击滚动条后键盘焦点离开终端，该分屏按未聚焦变色，随后按键不再进 shell。开启单击打开链接或按住 Ctrl 时，点在滚动条上还可能按错误坐标打开一个链接，并且这次点击不再滚动。

**代码：**

```623:623:terminatorlib/terminal.py
        self.scrollbar.connect('button-press-event', self.on_buttonpress)
```

```1357:1364:terminatorlib/terminal.py
    def on_buttonpress(self, widget, event):
        """Handler for mouse events"""
        # Any button event should grab focus
        widget.grab_focus()

        if type(widget) == Gtk.VScrollbar and event.type == Gdk.EventType._2BUTTON_PRESS:
            # Suppress double-click behavior
            return True
```

```1374:1383:terminatorlib/terminal.py
        if event.button == self.MOUSEBUTTON_LEFT:
            # Ctrl+leftclick on a URL should open it. Only the initial press
            # counts: GDK reports a double-click as BUTTON_PRESS followed by
            # _2BUTTON_PRESS, so acting on every event type would open the URL
            # once per event.
            if (event.type == Gdk.EventType.BUTTON_PRESS
                    and (self.config["link_single_click"]
                         or event.get_state() & Gdk.ModifierType.CONTROL_MASK == Gdk.ModifierType.CONTROL_MASK)):
                # Check new OSC-8 method first
                url = self.vte.hyperlink_check_event(event)
```

```1394:1397:terminatorlib/terminal.py
                    url = self.vte.match_check_event(event)
                    if url[0]:
                        self.open_url(url, prepare=True)
                        return True
```

```479:479:terminatorlib/terminal.py
        self.scrollbar = Gtk.Scrollbar.new(Gtk.Orientation.VERTICAL, adjustment=self._vadjustment)
```

**为什么是问题：** 滚动条的按下事件和 VTE 共用 `on_buttonpress`。第一行对事件里的 widget 调用 `grab_focus()`，点到的是滚动条，焦点就到了滚动条上，而不是 VTE。`Gtk.Range` 默认可聚焦，所以这次抢焦点会成功，并触发终端的 focus-out（未聚焦配色）。双击抑制比较的是 `type(widget) == Gtk.VScrollbar`，实际创建的是 `Gtk.Scrollbar`，条件恒为假，滚动条点击会继续往下走。链接检测用的是这份事件的坐标，那是滚动条局部坐标，却拿去对 VTE 做 `hyperlink_check_event` / `match_check_event`；一旦命中就 `return True`，滚动条自己的按下处理被吃掉。

**方向：** 滚动条点击把焦点还给 VTE，不要用滚动条坐标做链接命中，也不要吞掉滚动条自己的按下事件。
