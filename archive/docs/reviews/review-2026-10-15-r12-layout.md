---
title: "r12 layout 发现"
type: audit
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "非 ASCII 链接复制被截断；超链接菜单配错类型；上侧嵌套分屏关闭后 children 顺序反了；批量关闭忽略「总是询问」；布局阶段分割宽度为 1 会空转卡死。"
---

# r12 layout 发现

通读 `terminatorlib/paned.py`、`terminatorlib/container.py`、`terminatorlib/terminal_popup_menu.py`、`terminatorlib/close_confirm.py`。下面 5 条都是这些文件里能走通的行为错误。

## r12-1

- 严重度：中
- 症状：右键「复制地址」时，链接里只要有非 ASCII（国际化域名、中文路径、带重音的路径），剪贴板里的文本会被截断并变成非法 UTF-8，粘出来的不是原来的地址。

`Gtk.Clipboard.set_text` 的长度单位是字节。这里用 Python 的 `len()`，计的是字符数，而且 `prepare_url` 算了两次：

```240:241:terminatorlib/terminal_popup_menu.py
            item.connect('activate',
                         lambda x: terminal.clipboard.set_text(terminal.prepare_url(url), len(terminal.prepare_url(url))))
```

纯 ASCII 时字符数和字节数相同，看不出问题。UTF-8 下多字节字符会使传入的长度小于真实字节数，GTK 按这个长度切字符串，剪贴板内容损坏。在本机 GTK 3.24 上用字符长度写入 `https://example.com/café/路径`，读回的文本已经不是原串。

- 方向：长度传 `-1`，或传 UTF-8 字节数。

## r12-2

- 严重度：中
- 症状：右键一个 VTE 超链接时，菜单上的「打开 / 复制」动作会变成错误的类型：普通 `mailto:` 不会走「发送邮件」，一个都对不上的链接会显示成 `matches` 里最后一种处理器的动作。

超链接先取出 URL，再用 `terminal.matches` 的键去做 `re.search`。同一个字典的键是名字：`'email'`、`'voip'`，以及和 `handler_name` 比较的插件名；值才是匹配 id。

```170:180:terminatorlib/terminal_popup_menu.py
                for pattern, tag in terminal.matches.items():
                    try:
                        if re.search(pattern, url):
                            tag = tag

                            break
                    except Exception:
                        continue

                if tag is not None:
                    url = [url, tag]
```

```200:210:terminatorlib/terminal_popup_menu.py
            if url[1] == terminal.matches['email']:
                nameopen = _('_Send email to...')
                namecopy = _('_Copy email address')
            elif url[1] == terminal.matches['voip']:
                nameopen = _('Ca_ll VoIP address')
                namecopy = _('_Copy VoIP address')
            elif url[1] in list(terminal.matches.values()):
                # This is a plugin match
                for pluginname in terminal.matches:
                    if terminal.matches[pluginname] == url[1]:
                        break
```

`re.search('email', 'mailto:foo@bar.com')` 不会中。名字只要是 URL 的子串又会误中（地址里出现字母 email 就被当成邮箱）。一个键都没中时，`for` 仍然把 `tag` 留成最后一项，不是循环前设的 `None`，于是不会退回 `match_check_event`，菜单按最后一种匹配器来标。

- 方向：用单独的命中标志，未命中必须保持「没有 tag」并退回 VTE 的 match；名字键不能直接当正则。

## r12-3

- 严重度：中
- 症状：上下或左右嵌套时，关掉靠第一槽那一侧的内层分屏后，父分割的 `children` 顺序和屏幕上的第一槽、第二槽相反。同文件写明 sidebar 按 `children` 走，侧栏顺序会和窗口里的上下/左右不一致。

`split_axis` 知道追加顺序和 `child1`/`child2` 会分叉，所以拆分结束时按 GTK 槽位重写 `children`：

```120:126:terminatorlib/paned.py
        # self.children is appended as slots empty out, so it can disagree
        # with child1/child2. The sidebar walks children.
        self.children[:] = [child for child in (self.get_child1(),
                                                self.get_child2()) if child]
        container.children[:] = [child for child in (container.get_child1(),
                                                     container.get_child2())
                                 if child]
```

关闭路径没有做同样的重写。内层 Paned 被拿掉之后，父 Paned 若第一槽空了，`add` 会把幸存终端 `pack1`，但 `children` 仍是先留下原来的第二槽再追加：

```148:153:terminatorlib/paned.py
        elif len(self.children) == 1:
            if self.get_child1():
                self.pack2(widget, False, True)
            else:
                self.pack1(widget, False, True)
            self.children.append(widget)
```

```415:423:terminatorlib/paned.py
            self.remove(sibling)

            metadata = None
            parent = logical_parent(self)
            metadata = parent.get_child_metadata(self)
            dbg('metadata obtained for %s: %s' % (self, metadata))
            parent.remove(self)
            self.cnxids.remove_all()
            parent.add(sibling, metadata)
```

父容器是 Paned、被折叠的是它的 `child1` 时：屏幕上幸存终端在第一槽，`children` 却是 `[原来的 child2, 幸存终端]`。关掉第二槽不会反序。`describe_layout` 走的是 `get_children()`，保存的布局顺序不受这次反序影响。

- 方向：`parent.add` 之后按 `get_child1()` / `get_child2()` 重写父 Paned 的 `children`。

## r12-4

- 严重度：中
- 症状：`ask_before_closing` 设为 `always` 时，关掉只有 shell 的单个终端仍会弹出旧确认框；对一组终端做批量关闭（函数自己写的例子是 Close group）却直接放行，不询问。

单个关闭在「没有需要点名的进程」时把 `always` 交回旧对话框：

```344:353:terminatorlib/close_confirm.py
def no_process_close_result(ask_mode):
    """How to close when nothing but shells (and ignored helpers) is running.

    ``'accept'`` closes with no dialog. ``'legacy'`` is only for
    ``ask_before_closing = always``, which still uses the old prompt.
    """
    if ask_mode == 'always':
        return 'legacy'
    return 'accept'
```

```380:386:terminatorlib/close_confirm.py
    need, procs = should_confirm_processes(terminals)
    if need:
        return show_process_close_dialog(window, terminals, procs)

    if no_process_close_result(_ask_before_closing()) == 'accept':
        return Gtk.ResponseType.ACCEPT
    return None
```

批量门闩在同样「只有 shell」时直接允许关闭，没有读 `ask_before_closing`，也没有旧确认框。`should_confirm_processes` 在没有非 shell 进程时本来就是 `need=False`（`never` 也会如此）；`always` 和 `multiple_terminals` 在这里被当成同一种「可以关」：

```411:422:terminatorlib/close_confirm.py
def confirm_close_terminals(terminals, parent_window=None):
    """Bulk-close gate (e.g. 'Close group'): one aggregated process dialog.

    Returns True when closing may proceed.
    """
    from gi.repository import Gtk
    terminals = [t for t in terminals if t is not None]
    if not terminals:
        return True
    need, procs = should_confirm_processes(terminals)
    if not need:
        return True
```

- 方向：批量关闭在没有额外进程时走同一套 `no_process_close_result`，`always` 不要直接返回可以关。

## r12-5

- 严重度：中
- 症状：加载布局或按比例摆分割条时，如果这个 Paned 还没分配到真实尺寸（未实现时 `get_allocated_width/height` 就是 1）并且 GDK 事件队列是空的，界面会占满一颗 CPU 并不再返回。

等待条件写明是为了布局阶段 `get_length()==1` 的竞态，但只有队列里已经有事件才调用 `main_iteration`。队列空时内层循环不跑，外层条件不变，变成空转：

```634:644:terminatorlib/paned.py
    def set_position_by_ratio(self):
        # For reasons unknown to me, self.ratio often changes when the following loop is executed
        ratio = self.ratio

        # Fix for strange race condition where every so often get_length returns 1. (LP:1655027)
        while self.terminator.doing_layout and self.get_length() == 1:
            while Gtk.events_pending():
                Gtk.main_iteration()

        self.ratio = ratio
        self.set_pos(self.position_by_ratio(self.get_length(), self.get_handlesize(), self.ratio))
```

尺寸要等这次调用返回、或等 idle/配置事件被处理才会离开 1。`events_pending()` 为假时那些回调根本排不上。`doing_layout` 又要等布局函数返回才会清。结果是：队列一旦被抽干，循环自己等不到宽度变化。`create_layout` 和 `new_size` 都会进 `set_position_by_ratio`。未放上窗口的 `Gtk.HPaned` 在本机 GTK 3.24 上分配宽度就是 1，此时 `events_pending()` 为假。

- 方向：不要在事件队列为空时空等；给这个等待一个次数或超时，超时后用当前比例设位置并返回。
