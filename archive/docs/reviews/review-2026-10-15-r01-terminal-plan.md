---
title: "r01 terminal 方案"
type: plan
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "保留 4 条：Flatpak 在回调里记直接子进程 pid、拖放只送 URL、退出图片背景时恢复清屏、滚轮按 delta 累计；滚动条一条放下。"
---

## 核对

| 条目 | 标记 | 活码 |
| --- | --- | --- |
| r01-1 | weaken | `spawn_child` 的 Flatpak 分支把 `spawn_async` 的返回值赋给 `self.pid`。该函数在 GI 里是 `void`，回调三个位置（cancellable、callback、user_data）都是 `None`。`pid == -1` 的提示、`close()` 里的 `os.kill` / `_wait_for_shell_exit`、`cwd_probe_check` 的 `pid is None` 短路都还在。降级理由见该节。 |
| r01-2 | hold | `on_drag_data_received` 里 `TARGET_TYPE_MOZ` 只有在文本**不以** `\r\n` 结尾时才取第一行。以 `\r\n` 结尾会进入后面的 `split("\r\n")`，非 `file://` 时把 CRLF 换成 LF；`rstrip('\r\n')` 只去掉末尾。`feed()` 把中间换行交给 PTY。 |
| r01-3 | hold | `set_background_image` 成功路径 `set_clear_background(False)` 并 `vte.connect("draw", background_draw)`，不保存 handler。`reconfigure` 离开图片时只把 `background_image` 置空。`set_clear_background(True)` 只在加载异常里。`background_draw` 见空图直接返回。 |
| r01-4 | hold | `on_mousewheel` 用 `delta_y <= 0` 当向上，每个平滑事件调用一次 `zoom_in` / `zoom_out` 或 `scroll_by_page`。`zoom_font` 每档改 `Pango.SCALE`。外层 `modifiers == CONTROL_MASK` 把同时带 Shift 的事件挡在缩放之外。 |
| r01-5 | drop | 不改。反证：本机 GTK 3.24.33 上 `Gtk.Scrollbar.new` 的 `can_focus` 为假，对它 `grab_focus()` 后焦点仍留在原先的控件。VTE 0.68 的 `mouse_event_from_gdk` 在事件窗口不是终端事件窗口时把坐标写成 -1,-1，`grid_coords_visible` 不接受负坐标，`hyperlink_check_event` / `match_check_event` 不会命中，处理函数落到末尾 `return False`。`type(widget) == Gtk.VScrollbar` 与 `Gtk.Scrollbar` 确实不相等，但双击因此不会提前 `return True`，链接分支也不会因此吃掉按下。 |

## r01-1 Flatpak 子进程号（weaken）

**问题类：** Flatpak 启动后 `self.pid` 一直是 `None`，失败提示和关闭时对直接子进程的 SIGHUP 与等待都不会发生。

**反证（因此降级）：** `get_flatpak_args` 拼出来的 argv 以 `flatpak-spawn --host` 开头，VTE 的直接子进程是 `flatpak-spawn`。回调里能记下的 pid 是这个进程。`get_pid_cwd` 读的是该进程自己的目录，主机 shell 里的 `cd` 不会反映到这里。没有 OSC 7 时，分屏和工作目录探针跟 shell 当前目录，不是记下这个 pid 就能恢复的。另外 `close()` 在跳过 `os.kill` 之后仍会从 `terminalbox` 拿掉并删掉 VTE；同函数注释写明关掉 PTY master 时内核还会对前台进程组发 hangup。本路只补直接子进程的记录、失败提示，以及现有的显式 SIGHUP 加等待。

**不变量：**

- 非 Flatpak 仍走 `spawn_sync`，成功时 `self.pid` 为 shell pid；失败时 `self.pid == -1`，`vte.feed` 现有的 “Unable to start shell” 后 `return -1`。
- `spawn_async` 的参数个数和 timeout `-1` 保持不变。只把 callback 换成会写 pid 的回调；cancellable 与 user_data 可以仍是 `None`。返回值不再写入 `self.pid`。
- 回调到达前 `self.pid` 保持 `None`。成功时写成回调给出的正 pid。失败（错误或 pid `< 0`）时写成 `-1`，并 feed 与同步失败同一句提示。
- `close()` 仍只在 `self.pid is not None` 时 `os.kill(..., SIGHUP)` 并 `_wait_for_shell_exit`。`_note_child_exited` 仍把 pid 清成 `None`。
- 有 `vte.get_current_directory_uri()` 时 `get_cwd` 仍先用它。
- `cwd_probe_check` 在 `pid is None` 时仍返回 `False`。不要沿着 `flatpak-spawn` 去找主机 shell，也不要改探针去跟踪主机 shell 的目录。

**要动：** `Terminal.spawn_child` 的 `util.is_flatpak()` 分支，以及一个只给这条分支用的 spawn 完成回调（写在 `terminal.py` 里即可）。

**明确不改：** `get_cwd`、`cwd_probe_check`、`_on_contents_changed_cwd_probe`、`get_flatpak_args`、非 Flatpak 的 `spawn_sync`、`close()` 里等待 PTY 拆除的原因说明。

**验证：** 现有 `tests/test_cwd_probe.py::test_dead_pid_is_ignored`、`test_first_probe_only_records`、`test_change_marks_dirty_once` 保持通过，探针行为不改。`tests/test_m4_followups.py` 里对 `spawn_child(respawn=True)` 的断言保持通过。新增：把 `util.is_flatpak` 打成真、把 `vte.spawn_async` 打成“返回 `None` 并记住回调”；`spawn_child` 返回后 `pid is None`；用正 pid 调用回调后 `self.pid` 等于该值；用失败调用回调后 `self.pid == -1` 且 feed 的字节里含现有的无法启动 shell 文案；pid 已写成正数时 `close()` 会对该 pid 发 `signal.SIGHUP` 并调用 `_wait_for_shell_exit`。不要断言这个 pid 的目录等于 shell 的 `cd`。

## r01-2 拖放链接（hold）

**问题类：** `text/x-moz-url` 在以 CRLF 结尾时会把 URL 和标题一起送进 shell，中间的换行会提交当前行。

**不变量：**

- `TARGET_TYPE_MOZ` 解码 UTF-16 之后只留第一行 URL，行内不再有 `\n` 或 `\r`。以 `\r\n` 结尾和不以 `\r\n` 结尾同一规则。
- 标题不进入 `feed()`。
- 非 MOZ 的拖放仍走现有逻辑：末尾空行且每一行都是 `file://` 时加引号并用空格拼起来；否则把 CRLF 换成 LF；最后 `rstrip('\r\n')`。
- 仍对 `get_target_terms(self)` 里的每个终端 `feed`。

**要动：** `Terminal.on_drag_data_received` 里 `info == self.TARGET_TYPE_MOZ` 这一支。改完后的文本要在进入 `txt.split("\r\n")` 之前已经只剩一行 URL，这样后面的列表分支不会把标题拼回来。

**明确不改：** `feed()`、`_snapshot_before_input`、普通 `text/plain` 与 `file://` 列表、拖放分屏的后半段（`selection_data` 当终端编号的那条路径）。

**验证：** 没有现成测试。新增：伪造 `info == Terminal.TARGET_TYPE_MOZ` 的 selection，数据为 UTF-16 的 `http://example.com\r\nPage Title\r\n`，`get_target_terms` 返回带 `feed` 记录器的对象，断言送出的文本是 `http://example.com`，其中没有换行。再断言不以 `\r\n` 结尾的 `url\nTitle` 同样只剩 URL。再断言 `info` 不是 MOZ、正文为以 CRLF 结尾的多行 `file://` 时，仍是带引号、空格分隔、无换行的那条旧行为。

## r01-3 图片背景（hold）

**问题类：** 离开图片背景后 VTE 不再铺底，而且每次重新套用图片配置都会再挂一个 draw。

**不变量：**

- 图片模式成功加载后，`clear_background` 为关，窗口上只有一个 `background_draw`。再次 `reconfigure` 仍是图片时可以重新读文件，连接数仍是 1。
- 离开图片（`background_type` 不是带路径的 `image`）时 `background_image` 为 `None`，`set_clear_background(True)`，draw 已卸下。
- 加载抛错时同样恢复 `clear_background` 并卸下先前的 draw，再把 `background_image` 置空。
- `background_draw` 在图为 `None` 时直接返回。铺图、device scale、`bgcolor` 蒙层只画一次的算法不动。
- draw 交给现有的 `self.cnxids`（`Signalman`）。它一条信号只登记一个 handler，重复连接前要先 `remove_signal`。`close()` 里已有的 `remove_widget(self.vte)` 会一起卸掉它。

**要动：** `Terminal.set_background_image`，以及 `reconfigure` 里设置 `background_image` 的 if/else。

**明确不改：** `background_draw`、`_background_image_size`、调色板和 `set_colors`、`tests/test_m34_wayland_hidpi.py::test_background_image_native_resolution_at_scale2` 所覆盖的缩放行为。

**验证：** 上述 HiDPI 测试保持通过。新增：连续两次成功的 `set_background_image`（或两次走图片分支的 `reconfigure`）之后，`draw` 只连着一个 `background_draw`；随后把配置改成纯色或透明再 `reconfigure`，断言对 VTE 调用过 `set_clear_background(True)`，且 `draw` 上不再有 `background_draw`。加载失败的路径同样断言 clear 恢复为开、没有残留的 draw。

## r01-4 平滑滚轮（hold）

**问题类：** 平滑滚轮只看 `delta_y` 的符号，每一小步都缩放一档或翻一页；`delta_y == 0` 被当成向上；Ctrl+Shift 进不了同组缩放。

**不变量：**

- 离散 `ScrollDirection.UP` / `DOWN` 仍是一次事件一档或一页，不经过余量。
- 平滑事件按 `delta_y` 累加。增量为 0 时不缩放、不翻页，并返回 `False`（水平滚动不被吃掉）。
- 余量绝对值每满 1，缩放一档或翻一页，并减掉已经消费的 1。一次事件跨过几档就处理几档。方向反过来时余量从新方向重新计，不把反方向的余量折成一次反向操作。
- Ctrl（可以同时有 Shift）走缩放。仅 Shift 走 `scroll_by_page`。两套余量分开，修饰键组合变了就丢掉未消费的余量。
- 已经由 Ctrl 或 Shift 接管的垂直平滑事件，即使还没满 1，也返回 `True`，避免 VTE 再按同一 delta 滚一截。
- `disable_mousewheel_zoom` 为真时，Ctrl 滚轮仍立刻返回 `False`，不累计。
- Ctrl+Shift 缩放的目标是 `get_target_terms(self)`。比较必须写成 `(event.state & MASK) == MASK`。按现在的写法，`==` 比 `&` 紧，`SHIFT_MASK` 又是 1，Ctrl+Shift 会先满足写在前面的那一支，目标变成 `self.terminator.terminals`。加括号之后，只有 MOD4 才走全体终端；本路不改变“Super 表示全体终端”这一档的产品含义。

**要动：** `Terminal.on_mousewheel`。余量放在终端实例上。

**明确不改：** `zoom_font` 的步长、`scroll_by_page` / `scroll_by` 的页距、`disable_mousewheel_zoom` 的配置含义、自动字号。

**验证：** 没有现成滚轮测试。新增（可用 `Terminal.__new__` 配上假 `event`、假 `config`、可计数的 `zoom_in` / `zoom_out` / `scroll_by_page`）：

- Ctrl + 平滑且 `delta_y == 0`：不调用 `zoom_in`，返回 `False`。
- Ctrl + 若干次 `|delta_y| < 1`，累计未满 1 时不缩放且返回 `True`；满 1 时恰好一档。
- 一次 `delta_y == 1` 仍是一档。离散 `UP` / `DOWN` 仍是一档。
- Shift + 平滑同样按满 1 才 `scroll_by_page` 一次。
- Ctrl+Shift + `UP` 或已满 1 的平滑：调用 `get_target_terms` 得到的终端各缩放一档，不调用“全体终端”那条路径。
- `disable_mousewheel_zoom` 为真时 Ctrl + `UP` 返回 `False` 且不缩放。
