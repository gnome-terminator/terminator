---
title: "r11 plugins 方案"
type: plan
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "五条全部保留：日志原样落盘，容器参数解析失败不退出，书签改私有临时文件并可结束等待，缺 position 的命令读完再补位，右键不再改 profile 且取消预览要恢复。"
---

# r11 plugins 方案

核对结论：hold 5，weaken 0，drop 0。发现稿引用的行为与磁盘活码一致，行号仍落在同一函数上。drop 无。本方案只描述改法，不附可合入补丁。

生产改动只落在 `terminatorlib/plugins/logger.py`、`terminatorlib/plugins/remote.py`、`terminatorlib/plugins/custom_commands.py`、`terminatorlib/plugins/run_cmd_on_match.py`、`terminatorlib/plugins/auto_theme.py`。

## r11-1 hold

问题类：Logger 每次把取出的终端文本写入文件时丢掉最后一个字符，下一次从光标接着记，丢掉的字符不会再出现。

不变量：

- `write_content` 写入文件的字节等于本次 `get_text_range` / `get_text_range_format` 返回元组的第 0 项，含末尾字符。
- 本次请求的结束行、结束列仍记成下一次起点。起点是「已经整段写入的范围的终点」，不是被删掉一个字符之后的位置。
- 结束列不是 0 时，末字符是光标前的正文，必须留下。结束列是 0 时，末字符是这一行的换行，也必须留下。
- `stop_logger` 在行列有变化时仍调用 `write_content`，因此停止日志与跨屏刷新遵守同一条。

本机 VTE 0.68 的 `get_text_range`：光标在 `(5, 0)` 时范围文本是 `'hello'`，切片后是 `'hell'`；再喂 `'XYZ\r\n!'` 并从该光标续写，两段切片拼起来是 `'hellXYZ\n'`，全文是 `'helloXYZ\n!'`。光标在 `(0, 1)` 时范围文本是 `'ab\n'`。注释里「最后一个字符永远是换行」与这次取出的文本不符。`>= 72` 的 `get_text_range_format` 分支在本机 VTE 上不存在，但同一条 `content[:-1]` 写在两条分支汇合之后。

要动的符号：

- `Logger.write_content`（约 42–54 行）。`content = content[0]` 之后整段 `fd.write`，删掉 `content[:-1]`。
- 约 53–54 行继续把 `col_end` / `row_end` 存进 `self.loggers[terminal]`。
- `Logger.save`（约 56–65 行）与 `Logger.stop_logger`（约 102–109 行）继续调用 `write_content`，调用点不用改。

明确不改：`save` 里「未满一屏不写」的 `get_row_count` 门槛，开始记录时光标位置的初始化，文件选择对话框，`contents-changed` 的连接方式。

本地验证：插件目录下没有 Logger 测试。应新增断言：假终端的 `get_text_range` 返回 `('hello', None)`、终点列非 0 时，文件内容是 `hello`，记下的行和列等于传入的终点；返回 `('ab\n', None)` 且终点列为 0 时，文件内容是 `ab\n`。再断言连续两次 `write_content`，第二次起点用第一次记下的终点，拼接结果含第一次的末字符。`stop_logger` 在行列变化时走同一写入，文件里同样有末字符。

## r11-2 hold

问题类：`docker`/`podman` 的 `exec`/`attach` 命令行被默认 `ArgumentParser` 解析时会 `SystemExit`，定时回调里接不住，整个 Terminator 退出。

不变量：

- 识别容器主机失败时进程继续运行，`GetHost` 返回 `None`。
- 命令参数里的 `-h` / `--help`（包括 `docker exec -it <容器> mysql -h 127.0.0.1` 这种子命令参数）不触发解析器帮助，也不退出。
- 只有 `-l` / `--latest`、没有容器名的 `exec` / `attach`（如 `podman attach -l`、`exec -l -it`）不退出；`GetHost` 返回 `None`。
- 能解析出容器名的命令行仍返回该名字。`_update_watches` 仍每秒调用 `_apply_host_settings`。

要动的符号：

- `ContainerSession._get_host_exec`（约 263–299 行）和 `ContainerSession._get_host_attach`（约 301–334 行）里的两只 `ArgumentParser`。
- 关闭自动帮助（`add_help=False`），使 `-h` 不再走 `HelpAction` → `parser.exit()`。
- 缺容器名时，本机 Python 3.10 的 `parser.error()` 仍会 `sys.exit`；`ArgumentParser(exit_on_error=False)` 只放过 `ArgumentError`，拦不住这条路径。解析调用本身要接住 `SystemExit`，或让容器名变为可选并在缺失时返回 `None`，且 `error` / `exit` 不得结束进程。失败结果是 `None`。
- `ContainerSession.GetHost`（约 197–214 行）的 `except Exception` 接不住 `SystemExit`（`SystemExit` 的基类是 `BaseException`）。不要把「进程还活着」寄托在这个 `except` 上。
- 调用链保持：`Remote.__init__` 的 `GLib.timeout_add`（约 450–454 行）→ `_update_watches`（约 463–477 行）→ `_apply_host_settings`（约 669–678 行）→ `GetHost`。本机 GLib 超时里未捕获的 `SystemExit` 会以该退出码结束进程；`RuntimeError` 则只打印并继续。修解析后这条链不再抛出 `SystemExit`。

明确不改：`_get_host_run` 用 `--name` 下标取名字的路径，SSH 的 `getopt`，`IsType` / `_get_command` 的判定。`-l` 后面还有词时，现有解析会把那个词当成容器名（`exec -l -it bash` 得到容器名 `bash`，并不退出）；这次只消除退出，不重写「latest 表示没有容器名」的语义。

本地验证：插件目录下没有 Remote 测试。应新增断言：用与 `_get_host_exec` 相同的参数表解析 `['-it', 'c', 'mysql', '-h', '127.0.0.1']`，不发生 `SystemExit`，容器名为 `c`；解析 `['-l', '-it']` 与 attach 的 `['-l']`，不发生 `SystemExit`，结果是 `None`；解析 `['-it', 'c', 'sh']` 仍得到 `c`。再断言 `GetHost` 在上述失败输入上返回 `None`，且异常类型不是漏出去的 `SystemExit`。

## r11-3 hold

问题类：记录上一条命令时在主线程无期限等待固定路径 `/tmp/term_cmd`；文件打不开时把 `None` 交给 `Gtk.Entry.set_text`。

不变量：

- `get_last_exe_cmd` 从键位或「Bookmark Last Cmd」进入时，GTK 主线程不在 `time.sleep` 里空转。等待有终点：超时，或私有临时文件里已经有命令文本。
- 重定向目标是当前用户私有目录中不可预测的路径，不再使用 `os.path.join(os.sep, 'tmp', 'term_cmd')`。其它用户或另一个终端不能靠抢这个固定名字注入内容，也不能靠同名符号链接让 shell 的 `>` 截断别的文件。
- 空文件只表示「还没写完」，不是成功。取不到命令时，`name` 与 `command` 是空字符串。`Gtk.Entry.set_text` 与 `TextBuffer.set_text` 收到的是字符串。本机 PyGObject 对这两个 `set_text(None)` 抛 `TypeError`。
- 前台不是会执行这条 `fc` 重定向的 shell 时，等待结束后对话框仍能打开，名字和命令为空。

要动的符号：

- `CustomCommandsMenu.get_last_exe_cmd`（约 113–144 行）。现在 `count` 只在 `/tmp/term_cmd` 已存在时增加，文件永不出现则 `while not (count == 2 or fsz)` 一直成立。把 `fc -n -l -1 -1 > …` 的目标换成私有临时文件；路径插进 shell 命令时保持单个重定向目标（名字本身不含空格或 shell 元字符，或由调用方保证按一个词引用）。用 `GLib` 超时或工作线程等待，到点则停止。`feed_child` 仍在主线程发出。
- 打开失败时现在 `last_cmd` 保持 `None` 并返回。改为返回空字符串。读完后删除的是这次自己创建的文件。
- `get_last_exe_cmd_dialog_vars`（约 146–153 行）继续把同一字符串放进 `name` 和 `command`。`on_new`（约 488–493 行）在键存在且值为 `None` 时，`dict.get` 不会落到默认的 `''`。
- `_create_command_dialog`（约 461–468 行）的 `name.set_text` 与 `command.get_buffer().set_text` 因此收到字符串。
- 调用点保持：`on_keypress` 的 `PluginActAdd`（约 160–167 行）和 `on_last_exe_cmd`（约 475–478 行）。对话框仍在拿到结果之后出现，确认后仍 `_save_config`。

明确不改：书签对话框的字段集合，快捷键 `PluginActAdd` / `PluginActBmk`，`fc -n -l -1 -1` 表示「历史里上一条」这件事，菜单里执行已保存命令的 `_execute`。

本地验证：没有 custom commands 测试。应新增断言：发出的 shell 命令不含 `/tmp/term_cmd`；目标路径落在用户私有目录且每次不同。假时钟或有限次轮询下，文件一直不出现时函数返回 `''`，且没有不可结束的循环。临时文件已是指向其它路径的符号链接时，这次实现不再打开那个固定路径。`get_last_exe_cmd_dialog_vars` 在取不到命令时 `name` 与 `command` 均为 `''`。`on_new` 把该字典交给 `_create_command_dialog` 时，两个文本参数的类型是 `str`。

## r11-4 hold

问题类：配置条目没有 `position` 时，每读完一条就把已累积的无序命令按 `len(cmd_list)` 写回，覆盖已有键或把同一条插入多次；`run_cmd_on_match` 还在这条循环里保存启用插件。

不变量：

- 每条同时含名称与命令（或 regexp 与命令）的配置，在 `cmd_list` 里恰好出现一次。
- 带 `position` 的条目仍用该整数做键，无 position 的条目不覆盖这些键。
- 无 position 的条目在全部 section 读完后，按出现顺序各写入一个当前不存在的非负整数键（取最小空位）。`len(self.cmd_list)` 不能当这个键：键为 0 和 2 时长度为 2，再写入会盖掉 2。
- `RunCmdOnMatchMenu._load_configured_handlers` 只在合并完成后调用一次。没有读入任何有效条目时不调用它，避免多一次 `config.save()`。

要动的符号：

- `CustomCommandsMenu.__init__`（约 65–92 行）。`for cmd in noord_cmds` 现在与 `if "position"` 同级，位于 `for part in sections` 之内。把它移到 section 循环之后，并改用未占用的键。
- `RunCmdOnMatchMenu.__init__`（约 95–119 行）做同样的搬移。`self._load_configured_handlers()` 从 section 循环内挪到合并之后、且 `cmd_list` 非空时。
- `_load_configured_handlers`（约 162–183 行）仍负责按最终 `cmd_list` 登记 `_RunCmdOnMatch_{键}` 并 `config.save()`。`_save_config`（custom commands 约 228–247 行，run_cmd 约 141–159 行）仍按排序后的顺序写 `position`。

明确不改：缺 `name`/`command` 或 `regexp`/`command` 的 section 仍跳过。用户在界面里重排后 `update_cmd_list` 从 0 连续编号的路径。不把这两个插件收成同一份实现。

本地验证：没有这两份插件的测试。应把「sections → cmd_list」收成不打开对话框、不连接键位的函数再测，或在测试里替换 `plugin_get_config` 的返回值。应新增断言：顺序为 position 0、position 2、无 position 时，三条命令都在，键 2 仍是原来的第二条；两条都无 position 时，第一条只出现一次，`cmd_list` 长度为 2。对 `RunCmdOnMatchMenu`，多条 section 加载过程中 `_load_configured_handlers` / `Config.save` 只在最终列表上发生一次；全部 section 都无效时不调用。

## r11-5 hold

问题类：任意终端弹出右键菜单时，所有终端的 profile 被设成当前自动主题；设置框里改明暗 profile 后点取消，终端仍停在预览值上。

不变量：

- `AutoTheme.callback` 只往菜单里追加一项。它不调用 `change_theme` / `apply_theme`，也不调用 `Handy.StyleManager.set_color_scheme`。
- 插件构造并 `load_config` 之后，按已保存的 mode 应用一次主题，替代「靠第一次右键才应用」。Dark / Auto / Light 的判定沿用现在的布尔式：`mode=='Dark'`，或 `mode=='Auto'` 且 `is_dark_theme()`。
- 系统主题名变化时，仅 `mode=='Auto'` 才 `change_theme`（`setup_theme_monitor` 里现有的提前返回保持）。
- 设置对话框可以预览：改 Light/Dark 下拉、或切换 Vte 的 Light/Dark/Auto 单选时，仍可对所有终端 `set_profile`。打开对话框前记下每个终端自己的 `get_profile()`，以及当时的 `AutoTheme.mode` 和 Handy 配色方案。
- 响应不是 `Gtk.ResponseType.OK` 时，每个终端 `set_profile` 回自己的原 profile，`AutoTheme.mode` 与 Handy 方案回到打开前。确认时才 `save_config`。
- `apply_theme` 仍遍历 `plugin.Terminator().terminals`。`terminatorlib.plugin` 引入的就是 `terminatorlib.terminator.Terminator`。每个终端的 `set_profile` 改的是该终端 `Config` 上的 profile 名并 `reconfigure`。

要动的符号：

- `AutoTheme.callback`（约 55–72 行）。保留菜单项与 `do_menu_toggle` 连接。去掉无条件的 `change_theme(mode)`，以及紧随的 `teardown_theme_monitor` / `set_color_scheme` / `setup_theme_monitor`。`__init__`（约 49–52 行）已经 `load_config` 并 `setup_theme_monitor`，一次应用放在这次构造里。
- `AutoTheme.apply_theme` / `change_theme`（约 119–131 行）仍是改 profile 的地方，菜单不再调用它们。
- `MySettingDialog.on_light_combo_change` / `on_dark_combo_change`（约 400–407 行）和 `on_radio_button_toggled`（约 414–429 行，其中 `self.mgr.mode = self.mode_sel` 会在确认前改类属性）继续可以预览，但必须能撤销。
- `MySettingDialog.on_dialog_response`（约 451–460 行）的非 OK 分支现在只清 `change_cb` 并打印。在这里按终端恢复 profile，并恢复 `mode` 与 Handy 方案。`do_menu_toggle`（约 167–182 行）仍只在 `Gtk.ResponseType.OK` 时 `save_config`。
- 终端菜单的调用点 `TerminalPopupMenu` 约 397–403 行保持：每个 `terminal_menu` 插件的 `callback` 仍在菜单构建时执行。

明确不改：profile 里的配色定义，对话框 CSS，`load_config` 用 `terminals[0]` 当缺省 profile 的做法，菜单项目前不 `set_active` 的勾选状态，`terminal.set_profile` 在 profile 名变化时 `_session_mark_dirty` 的行为。恢复就是再 `set_profile` 回原名。

本地验证：没有 AutoTheme 测试。Handy 不可导入时跳过。应新增断言：对两个 profile 名不同的假终端调用 `callback` 后，两者的 profile 与调用前相同，且 `apply_theme` / `set_profile` 未被调用，菜单项已追加。打开对话框前记下两个不同的 profile，触发 Light 下拉或 Vte 单选的预览后再走取消响应，两个终端各自回到原 profile，`AutoTheme.mode` 回到打开前的值。走 OK 响应时，终端保持预览 profile，并且会 `save_config`。
