---
title: "r13 display-ipc 发现"
type: audit
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "短命令后全屏滚动条不再隐藏；dbus 开窗替换掉进程内命令行选项；remotinator 改错标签、丢掉 -x，并多打印 None。"
---

通读 `terminatorlib/altscreen.py`、`terminatorlib/autofont.py`、`terminatorlib/zoomguard.py`、`terminatorlib/ipc.py` 和仓库根上的 `remotinator`。`autofont.py` 与 `zoomguard.py` 未形成条目。

## r13-1

**严重度：** 中

**症状：** 空历史或刚清过屏的终端里，先跑一条会刷出滚动历史、并且在大约 150ms 去抖时仍在前台的普通命令，再进入 vim / less / htop 时滚动条不再自动隐藏；这次全屏期间会一直可见。

**代码：**

```327:336:terminatorlib/altscreen.py
    def _on_change(self, adj=None, *_args):
        # Fast path: plain output growing the history on the normal screen
        # fires 'changed' for every line; no timer needed for that.
        if (adj is not None and not self.detector.active
                and not self.auto_hidden):
            try:
                if not adjustment_collapsed(adj.get_lower(), adj.get_upper(),
                                            adj.get_page_size()):
                    self.detector.had_history = True
                    return
```

```244:266:terminatorlib/altscreen.py
        if not collapsed:
            self.had_history = True
            self.active = False
            self.episode_start = None
        elif busy is False:
            self.had_history = False
            self.active = False
            self.episode_start = None
        elif busy is None:
            # Foreground unknown (no child pid, e.g. flatpak spawn_async,
            # or tcgetpgrp/proc failed).  An idle readline prompt is also
            # in raw mode, so we cannot tell a TUI from the prompt: never
            # hide on guesswork.  Keep had_history untouched.
            self.active = False
            self.episode_start = None
        else:
            now = self._clock()
            if self.episode_start is None:
                self.episode_start = now
                self.active = False
            if not self.active and now - self.episode_start <= self.GRACE_S:
                self.active = bool((self.had_history or cursor_beyond)
                                   and raw is not False)
```

```360:369:terminatorlib/altscreen.py
        if self._latched():
            # TUI redraws: only watch for the exit, at a slow rate. The
            # adjustment 'changed' path still reacts immediately.
            self.schedule(LATCHED_POLL_MS)
            return
        adj = self._adj
        try:
            if adj is not None and not adjustment_collapsed(
                    adj.get_lower(), adj.get_upper(), adj.get_page_size()):
                return
```

**为什么：** `update()` 在调整区离开折叠时会把 `episode_start` 清成 `None`。`changed` 的快速路径在检测器还没 `active` 时只记 `had_history` 就返回，不调用 `update()`，也不再 `schedule()`。折叠观察里前台已不是 shell（`busy` 为 True）、终端仍是规范模式（`raw` 为 False）时，宽限起点会被记下，`active` 仍是 False。输出超过一屏后走这条快速路径，起点就留在对象上。命令若在 `GRACE_S`（1 秒）内结束，提示符的 `contents-changed` 里 `_latched()` 仍为假，`_on_contents` 见未折叠也直接返回，没有 `evaluate()`。用户停在提示符阅读输出时不再产生内容事件。之后进入全屏程序，调整区再次折叠，起点已经早于 1 秒，`update()` 只在宽限内才把 `active` 置真，滚动条保持可见。全屏期间调整区一直折叠，过期的 episode 也不会从「未折叠」分支结束。

**方向：** 调整区从折叠变为可滚动时，走和 `update()` 未折叠分支相同的收尾，清掉 `episode_start`。

## r13-2

**严重度：** 中

**症状：** `remotinator` 的 `hsplit`、`vsplit`、`get_terminals`、`get_window`、`get_tab_title` 等命令在正常结果后再打印一行 `None`；包装函数里的 `print` 把 dbus 返回值吃掉了。

**代码：**

```105:113:remotinator
    if uuid_required:
        uuid = options.get('uuid', os.environ.get('TERMINATOR_UUID'))
        if uuid:
            print(str(func(uuid, options)))
        else:
            err("$TERMINATOR_UUID is not set, or passed as an option.")
            sys.exit(1)
    else:
        print(str(func(options)))
```

```379:391:terminatorlib/ipc.py
def new_window(session, options):
    """Call the dbus method to open a new window"""
    print(session.new_window())

@with_proxy
def new_tab(session, uuid, options):
    """Call the dbus method to open a new tab in the first window"""
    print(session.new_tab(uuid))

@with_proxy
def hsplit(session, uuid, options):
    """Call the dbus method to horizontally split a terminal"""
    print(session.hsplit(uuid,options))
```

```399:411:terminatorlib/ipc.py
def get_terminals(session, options):
    """Call the dbus method to return a list of all terminals"""
    print('\n'.join(session.get_terminals()))

@with_proxy
def get_focused_terminal(session, options):
    """Call the dbus method to return the currently focused terminal"""
    return session.get_focused_terminal()

@with_proxy
def get_window(session, uuid, options):
    """Call the dbus method to return the toplevel tab for a terminal"""
    print(session.get_window(uuid))
```

**为什么：** `remotinator` 对每个命令都 `print(str(func(...)))`。`ipc` 里多数客户端包装自己又 `print` 了 dbus 结果，`print` 的返回值是 `None`，外层就把字符串 `None` 打出来。`get_focused_terminal` 把 uuid 返回给调用方，所以只有它不会多这一行。把整段标准输出当成 uuid 或终端列表的脚本会带上这个 `None`。

**方向：** 客户端包装只返回 dbus 结果，由 `remotinator` 一处打印。

## r13-3

**严重度：** 中

**症状：** `remotinator set_tab_title` 改的是该窗口当前可见标签的标题，uuid 所在的标签页保持原标题。

**代码：**

```292:304:terminatorlib/ipc.py
    def get_tab_title(self, uuid=None):
        """Return the title of a parent tab of a given terminal"""
        maker = Factory()
        terminal = self.terminator.find_terminal_by_uuid(uuid)
        window = terminal.get_toplevel()
        root_widget = window.get_children()[0]
        if maker.isinstance(root_widget, "Notebook"):
            for tab_child in root_widget.get_children():
                terms = [tab_child]
                if not maker.isinstance(terms[0], "Terminal"):
                    terms = enumerate_descendants(tab_child)[1]
                if terminal in terms:
                    return root_widget.get_tab_label(tab_child).get_label()
```

```307:322:terminatorlib/ipc.py
    def set_tab_title(self, uuid=None, options=dbus.Dictionary()):
        """Set the title of a parent tab of a given terminal"""
        tab_title = options.get('tab-title')

        maker = Factory()
        terminal = self.terminator.find_terminal_by_uuid(uuid)
        window = terminal.get_toplevel()

        if not window.is_child_notebook():
            return

        notebook = window.get_children()[0]
        n_page = notebook.get_current_page()
        page = notebook.get_nth_page(n_page)
        label = notebook.get_tab_label(page)
        label.set_custom_label(tab_title, force=True)
```

**为什么：** uuid 只用来找到顶层窗口。写入使用 `get_current_page()`，也就是当前可见页。同文件的 `get_tab_title` 会遍历每个标签页，确认终端在哪一页。多标签时，在非当前标签的 shell 里执行，或把后台标签的 uuid 传进来，标题写到前台标签上。

**方向：** 按 `get_tab_title` 的遍历找到 uuid 所在页，再改那一页的标签。

## r13-4

**严重度：** 中

**症状：** `remotinator new_tab -x <命令>` 打开的新标签跑的是默认 shell，给出的命令不会执行。

**代码：**

```85:86:remotinator
    parser.add_argument('-x', '--execute', dest='execute', type=str, default=argparse.SUPPRESS,
                help=_('Command to run in new terminal'))
```

```136:138:terminatorlib/ipc.py
    def new_tab(self, uuid=None):
        """Create a new tab"""
        return self.new_terminal(uuid, 'tab')
```

```156:161:terminatorlib/ipc.py
    def hsplit(self, uuid=None,options=None):
        """Split a terminal horizontally, by UUID"""
        if options:
            cmd = options.get('execute')
            title = options.get('title')
            return self.new_terminal_cmd(uuid=uuid, title=title, cmd=cmd, split_vert=True)
```

```384:386:terminatorlib/ipc.py
def new_tab(session, uuid, options):
    """Call the dbus method to open a new tab in the first window"""
    print(session.new_tab(uuid))
```

**为什么：** `-x` 的帮助写明要在新终端里运行命令。`hsplit` / `vsplit` 把 `options` 交给服务端，并由 `new_terminal_cmd` 把 `execute` 交给 `spawn_child`。`new_tab` 的客户端丢掉 `options`，服务端方法只接收 uuid，再调用 `key_new_tab()`，命令参数没有传递路径。

**方向：** `new_tab` 把 `execute` 交到新建终端，和分屏命令同一条传递路径。

## r13-5

**严重度：** 高

**症状：** dbus 方法 `new_window_cmdline` 或 `new_tab_cmdline` 开窗、开标签之后，本进程的命令行选项对象被来访的字符串字典整份换掉；原来的布尔值和列表消失，调用结束后也不会回到调用前的内容。

**代码：**

```72:89:terminatorlib/ipc.py
    @dbus.service.method(BUS_NAME, in_signature='a{ss}')
    def new_window_cmdline(self, options=dbus.Dictionary()):
        """Create a new Window"""
        dbg('dbus method called: new_window with parameters %s'%(options))
        if options['configjson']:
            dbg(options['configjson'])
            configjson = ConfigJson()
            layoutname = configjson.extend_config(options['configjson'])
            if layoutname and ((not options['layout']) or options['layout'] == 'default'):
                options['layout'] = layoutname
                if not options['profile']:
                    options['profile'] = configjson.get_profile_to_use()

        oldopts = self.terminator.config.options_get()
        oldopts.__dict__ = options
        self.terminator.config.options_set(oldopts)
        windows_before = list(self.terminator.windows)
        self.terminator.create_layout(oldopts.layout)
```

```100:108:terminatorlib/ipc.py
    @dbus.service.method(BUS_NAME, in_signature='a{ss}')
    def new_tab_cmdline(self, options=dbus.Dictionary()):
        """Create a new tab"""
        dbg('dbus method called: new_tab with parameters %s'%(options))
        oldopts = self.terminator.config.options_get()
        oldopts.__dict__ = options
        self.terminator.config.options_set(oldopts)
        window = self.terminator.get_windows()[0]
        window.tab_new()
```

**为什么：** 签名 `a{ss}` 里每个值都是字符串。`oldopts.__dict__ = options` 用这份字典替换选项对象的全部属性，再 `options_set` 装回去。字典里出现的开关会从布尔值变成字符串，非空的 `"False"` 在布尔上下文里为真；字典里没有的属性（例如原来的命令列表）从对象上消失。`create_layout` / `tab_new` 之后没有把旧 `__dict__` 换回来，所以这次 IPC 之后整个进程都留在这份被替换的选项上。替换发生在 `create_layout(oldopts.layout)` 之前，`layout` 不在字典里时这里会抛 `AttributeError`，选项对象此时已经被换掉。

**方向：** 把本次开窗需要的字段抄进副本，调用结束后恢复原来的选项对象。
