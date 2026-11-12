---
title: "r09 app-core 发现"
type: audit
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "布局展开失败会空转或拆坏窗口，关组确认失败仍会关终端，布局启动器加载失败会挂起。"
---

## r09-1

严重度：中

症状：布局里没有可用的 Window（条目全是找不到父节点的子项，或父节点成环）时，进程打开零个窗口并停在主循环里，界面不出现，也不会自己退出。已经成功挂上的窗口则会丢掉那些没挂上的窗格。

```254:268:terminatorlib/terminator.py
        if not layout:
            # User specified a non-existent layout. default to one Terminal
            err('layout %s not defined' % layout)
            self.new_window()
            return

        # Wind the flat objects into a hierarchy
        hierarchy = {}
        count = 0
        # Loop over the layout until we have consumed it, or hit 1000 loops.
        # This is a stupid artificial limit, but it's safe.
        while len(layout) > 0 and count < 1000:
            count = count + 1
            if count == 1000:
                err('hit maximum loop boundary. THIS IS VERY LIKELY A BUG')
```

```282:288:terminatorlib/terminator.py
                else:
                    # Now examine children to see if their parents exist yet
                    if 'parent' not in layout[obj]:
                        err('Invalid object: %s' % obj)
                        del(layout[obj])
                        continue
                    if layout[obj]['parent'] in objects:
```

```300:305:terminatorlib/terminator.py
                        objects[obj] = childobj
                        del(layout[obj])

        layout = hierarchy

        for windef in layout:
```

```211:217:terminator
        try:
            if open_fresh:
                dbg('clean exit kept no tabs; opening a new window')
                TERMINATOR.new_window()
            else:
                dbg('Creating a terminal with layout: %s' % OPTIONS.layout)
                TERMINATOR.create_layout(OPTIONS.layout)
```

```238:238:terminator
        TERMINATOR.layout_done()
```

为什么是问题：空布局或缺省布局会在 `if not layout` 里 `new_window()` 后返回。父节点始终不在 `objects` 里的条目不会被删除，循环到 1000 次后被 `layout = hierarchy` 丢掉，日志只打一行。若层次里没有任何 Window，后面的 `for windef` 一次都不进，函数正常返回。启动脚本只在 `create_layout` 抛错时补窗口，正常返回后直接 `layout_done()` 再 `Gtk.main()`。没有窗口时没有人调用 `Gtk.main_quit()`。

方向：层次展开结束后若没有创建任何窗口，按缺失布局同样开一个终端；仍挂不上的节点不要只靠循环上限静默丢掉。

## r09-2

严重度：中

症状：某个窗口的 `size` 不是两个可转成整数的元素时，这次布局在该窗口处中断，后面的窗口不再创建。若抛出的是 `ValueError`，启动器还会再开一个额外窗口。

```310:310:terminatorlib/terminator.py
            window, terminal = self.new_window()
```

```314:327:terminatorlib/terminator.py
            if 'position' in layout[windef] and window.can_set_position():
                parts = str(layout[windef]['position']).split(':')
                if len(parts) == 2:
                    try:
                        window.move(int(parts[0]), int(parts[1]))
                    except ValueError:
                        dbg('ignoring bad window position %r' %
                            layout[windef]['position'])
            if 'size' in layout[windef]:
                parts = layout[windef]['size']
                winx = int(parts[0])
                winy = int(parts[1])
                if winx > 1 and winy > 1:
                    window.resize(winx, winy)
```

```218:229:terminator
        except (KeyError,ValueError) as ex:
            err('layout creation failed, creating a window ("%s")' % ex)
            if restoring and sess is not None:
                sess.restore_failed(ex)
            TERMINATOR.new_window()
        except Exception as ex:
            # A malformed restored session must never stop startup
            err('layout creation crashed, creating a window ("%s")' % ex)
            if restoring and sess is not None:
                sess.restore_failed(ex)
            if not [w for w in TERMINATOR.windows if w not in windows_before]:
                TERMINATOR.new_window()
```

为什么是问题：同一函数里，非法 `position` 被接住并跳过；`size` 没有长度检查，也没有 `try`。`int(parts[0])` 在元素不是整数时抛 `ValueError`，元素个数不足时抛 `IndexError`，值不是序列时抛 `TypeError`。抛错点在 `new_window()` 之后、`window.create_layout()` 之前，当前窗口已经显示，循环却退出，后续窗口定义被丢掉。启动脚本对 `ValueError` 无条件再 `new_window()`，于是已有的半成品窗口旁边又多一个窗口。`IndexError` / `TypeError` 走另一个分支，因为已经有新窗口，不再补救，用户留下一份缺窗的布局。

方向：`size` 与 `position` 一样，解析失败就跳过该字段并继续建完其余窗口，不要在已创建窗口之后再无条件加窗。

## r09-3

严重度：中

症状：关闭一组终端时，确认步骤一旦抛错，组内终端仍会被关掉；若这组覆盖了全部终端，会先保存再逐个关闭，等于未经确认就退出。

```937:946:terminatorlib/terminator.py
    def closegroupedterms(self, group):
        """Close all terminals in a group (process-aware confirm first)"""
        members = [t for t in self.terminals[:] if t.group == group]
        try:
            from .close_confirm import confirm_close_terminals
            if not confirm_close_terminals(members):
                dbg('closegroupedterms: user cancelled')
                return False
        except Exception as ex:
            dbg('closegroupedterms confirm failed: %s' % ex)
```

```953:968:terminatorlib/terminator.py
        if members and not [t for t in self.terminals if t not in members]:
            # Round-2 P2-7: the group covers every terminal, i.e. this quits.
            # Save the whole layout once, up front (like closing the last
            # window), instead of finalizing mid-loop with one pane left.
            try:
                from .session import SessionManager
                SessionManager().finalize()
            except Exception as ex:
                dbg('closegroupedterms finalize: %s' % ex)
        for terminal in members:
            # Same path as exit / Ctrl+Shift+W: the parent removes and
            # deregisters the terminal and then calls close() exactly once
            # (calling close() directly re-entered through close-term).
            if terminal in self.terminals:
                terminal.emit('close-term')
        return True
```

为什么是问题：用户取消时 `confirm_close_terminals` 返回假，函数会 `return False`，终端保持不动。确认模块导入失败或对话框抛错时，异常只被记成调试日志，执行流落到后面的 `finalize()`（全组覆盖全部终端时）和 `emit('close-term')`。确认的目的是避免关掉仍有进程的终端；这条失败路径把确认失败当成同意关闭。

方向：确认过程失败时应中止关闭并让用户看见失败，不要在异常之后继续 `close-term`。

## r09-4

严重度：中

症状：对一组或全部终端插入编号时，只要目标里有一个不在当前窗口树中的终端，编号会在中途抛 `ValueError`，后面的终端写不进数字。

```947:949:terminatorlib/terminator.py
        # Hidden panes of a legacy zoom are detached from the window; put
        # them back so close-term reaches a parent that is in a window.
        hidden = [t for t in members if t.get_toplevel() not in self.windows]
```

```1011:1018:terminatorlib/terminator.py
        terminals = []
        for window in self.windows:
            containers, win_terminals = enumerate_descendants(window)
            terminals.extend(win_terminals)

        for term in self.get_target_terms(widget):
            idx = terminals.index(term)
            term.feed(numstr.encode() % (idx + 1))
```

```1037:1044:terminatorlib/terminator.py
    def get_target_terms(self, widget):
        """Get the terminals we should currently be broadcasting to"""
        if self.groupsend == self.groupsend_type['all']:
            return(self.terminals)
        elif self.groupsend == self.groupsend_type['group']:
            if widget.group != None:
                return(self.get_sibling_terms(widget))
        return([widget])
```

为什么是问题：编号列表只收集 `self.windows` 的后代。同文件写明，旧式缩放会把窗格从窗口上拆下，这些终端的 `get_toplevel()` 不在 `self.windows` 里，但它们仍在 `self.terminals` 中。`groupsend` 为 all 或 group 时，`get_target_terms` 会把它们算进目标。`list.index` 找不到就抛 `ValueError`，本次插入停止，已经喂过数字的终端不会撤销。

方向：给不在窗口树里的目标单独编号或跳过，不要让一次 `index` 失败打断其余终端。

## r09-5

严重度：中

症状：布局启动器找不到或读不出 glade 文件时，进程没有窗口，也不退出，一直停在 `Gtk.main()`。

```29:46:terminatorlib/layoutlauncher.py
    def __init__ (self):
        self.terminator = Terminator()
        self.terminator.register_launcher_window(self)

        self.config = config.Config()
        self.config.base.reload()
        self.builder = Gtk.Builder()
        self.builder.set_translation_domain(APP_NAME)
        try:
            # Figure out where our library is on-disk so we can open our UI
            (head, _tail) = os.path.split(config.__file__)
            librarypath = os.path.join(head, 'layoutlauncher.glade')
            gladefile = open(librarypath, 'r')
            gladedata = gladefile.read()
        except Exception as ex:
            print("Failed to find layoutlauncher.glade")
            print(ex)
            return
```

```67:70:terminatorlib/layoutlauncher.py
    def on_destroy_event(self, widget, data=None):
        """Handle window destruction"""
        dbg('destroying self')
        self.terminator.deregister_launcher_window(self)
```

```80:82:terminator
    if OPTIONS.select:
        # launch gui, return selection
        LAYOUTLAUNCHER=LayoutLauncher()
```

```249:250:terminator
    try:
        Gtk.main()
```

为什么是问题：`register_launcher_window(self)` 发生在打开 glade 之前。文件缺失、权限错误或解码失败被接住后，`__init__` 直接 `return`，没有注销，也没有创建 `self.window`，`on_destroy_event` 不会被接上。构造函数因此成功返回。`OPTIONS.select` 这条路径没有别的窗口，接着进入 `Gtk.main()`。主循环只在 `deregister_launcher_window` 发现启动器窗口和终端窗口都空了时才 `main_quit()`，这条失败路径不会走到那里。

方向：glade 加载失败时注销已登记的启动器并让进程退出，不要带着空的窗口列表进入主循环。
