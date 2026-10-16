---
title: "r14 support 方案"
type: plan
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "四条保留、一条降级：调试服务改用户套接字，PATH、配置键迁移和 Flatpak shell 按活码修，插件 enable 只补提前返回。"
---

# r14 support 方案

核对结论：hold 4，weaken 1，drop 0。发现稿引用的五处行号与磁盘活码一致。drop 无。本方案只描述改法，不附可合入补丁。

## r14-1 hold

问题类：`-d` 两次拉起的调试服务在 `127.0.0.1` 随机端口上提供无认证 Python 解释器，处理器上的 `verify_request` 不会被调用。

不变量：

- 仍只在 `OPTIONS.debug >= 2` 时启动。正常启动不监听。
- 监听端不是 `AF_INET`。套接字是路径名 unix socket，位于 `XDG_RUNTIME_DIR`（未设置时放在仅本用户可进入的目录，目录权限 0700），绑定后权限 0600。其他本地用户 `connect` 被文件系统权限拒绝。
- 同一用户的调试标签仍能连上现有 REPL，读到欢迎行并执行代码。`TerminatorConsole` 的读写和 telnet 字节处理保持。
- 路径带本进程 pid，避免上次崩溃留下的文件挡住下一次绑定。进程正常结束时删除该路径。

要动的符号：

- `spawn`（`terminatorlib/debugserver.py` 167–174 行）。现在是 `socketserver.TCPServer(('127.0.0.1', 0), PythonConsoleServer)`。改为 `UnixStreamServer`。`server_address` 变成套接字路径字符串。
- `PythonConsoleServer.verify_request`（48–49 行）固定 `return True`，而且写在 `BaseRequestHandler` 子类上。标准库 `BaseServer._handle_request_noblock` 调用的是服务器自己的 `verify_request`，在 `process_request` 构造处理器之前。这段方法不会执行。不要把它挪到 `TCPServer` 上假装能核对对端 uid：`AF_INET` 没有 `SO_PEERCRED`。准入靠套接字权限，不要再留一个永远返回真的处理器方法。
- 入口 `terminator` 240–247 行仍调用 `debugserver.spawn`，并把 `server_address` 赋给 `Terminator.debug_address`。地址不再是 `(host, port)`。
- `Terminal.spawn_child` 里 `debugserver is True` 的分支（`terminatorlib/terminal.py` 2361–2366 行）。现在拼 `telnet %s %s`。调试标签的命令改成对该 unix 套接字的双向字节流，命令里带套接字路径，不再假定二元组的主机和端口。

明确不改：`optionparse.py` 94–95 行「两次才开调试服务」的计数，以及 `terminator` 240 行的门槛。不改 `TerminatorConsole`。不改 `setDaemon`。不改 `terminal_popup_menu.py` 309 行「`debug_address is not None` 才显示调试标签」。不在 `127.0.0.1` 上加应用层口令。

本地验证：无现成测试。`tests/test_m4_followups.py` 的 `test_child_exited_handlers_pass_respawn_not_debugserver` 只断言退出回调不再把 `debugserver` 传丢，不覆盖 `spawn`。应新增断言：在临时 `XDG_RUNTIME_DIR` 下 `spawn` 得到的是 `AF_UNIX` 路径，模式 0600，绑定地址不是 `127.0.0.1`；同一用户连上能读到欢迎行里的应用名；`spawn_child` 在 `debugserver is True` 且 `debug_address` 为该路径时，拼出的命令包含该路径且不是 `telnet <ip> <port>`。测完关掉服务器并确认路径已删除。

## r14-2 hold

问题类：`path_lookup` 在 PATH 缺失时让 `KeyError` 漏出，PATH 第一段为空时又把整份 PATH 换成三个固定目录。

不变量：

- `os.environ` 里没有 `PATH`：不抛。只搜索现有回退目录 `/usr/local/bin`、`/usr/bin`、`/bin`，顺序不变。
- `PATH` 已设置（包括空字符串、以冒号开头、中间有空段）：按 `split(':')` 的每一段原样搜索，不整表替换。空段表示当前目录。后面的目录仍搜索。
- 绝对路径，以及 `./` 开头且该文件已存在，仍走现在的短路，不看 PATH。找不到时仍返回 `None`。

要动的符号：`path_lookup`（`terminatorlib/util.py` 130–136 行）。`os.environ['PATH']` 缺失时抛的是 `KeyError`，现在的 `except (ValueError, NameError)` 接不住；`NameError` 在 `os` 已导入时也不会从这里出现。空的第一段不要再 `raise ValueError`。捕获 `KeyError` 才使用回退目录。空段留给下面已有的循环：`os.path.join('', command)` 在 POSIX 上得到相对名，`os.path.isfile` 会看当前目录。

`shell_lookup` 169 行继续调用 `path_lookup`，调用方式不改。`Terminal.spawn_child` 2378、2381 行是调用方，本项不改。

明确不改：三个回退目录及其顺序。`shell_lookup` 的候选 shell 顺序。找不到命令时的 `None`。

本地验证：无现成测试。应新增断言：删掉 `PATH` 后查找不抛 `KeyError`，结果位于那三个回退目录之一（或确实不存在时为 `None`）；`PATH` 为 `:临时目录` 且可执行文件只在该临时目录时，返回该文件，而不是只在三个回退目录里找；`PATH` 为空字符串时，只在当前目录找这个命令名，不因 `/usr/bin` 里有同名文件就返回 `/usr/bin` 下的路径；中间空段（`目录甲::目录乙`）仍能找到只放在目录乙的文件。

## r14-3 hold

问题类：旧配置迁移把全文里的 `line_height` 子串换成 `cell_height`，并对原文件 `seek(0)` 覆盖，没有留下可回退的原文件。

不变量：

- 只把作为配置键的 `line_height` 改成 `cell_height`。值、注释、命令、标题里的同样文字不变。键名必须整令牌相等，更长的标识符不变。
- 行的判定：去掉行首空白后，键是 `line_height`，后面是可选空白和 `=`。同一行等号后面的文字不改。
- 文件里没有这种键行时不写。
- 写入中途失败或进程在替换前中断时，原文件字节仍在。成功后目标路径上是新文本。
- 仍只在 `ConfigBase.load` 里尝试一次（`config_file_updated_to_cell_height`，`terminatorlib/config.py` 655 行、777–779 行）。

要动的符号：`update_config_to_cell_height`（`terminatorlib/util.py` 554–585 行）。574 行的 `str.replace` 扫的是整份文本。576–578 行 `seek(0)`、`write`、`truncate` 打在已打开的原文件上。`line_height` 与 `cell_height` 都是 11 个字符，长度相同并不使这次就地写安全。

改成只替换符合上面规则的键，然后用临时文件、fsync、`os.replace` 换上。做法与 `atomic_write_config`（`terminatorlib/config.py` 603 行）相同：先 `realpath`，临时文件与目标同一目录，沿用目标权限，失败则删掉临时文件。不要把这次迁移改成 `ConfigObj.write` 重排整份文件。`atomic_write_config` 的参数是 parser，本函数继续写已经改好的文本。不要为了迁移改 `atomic_write_config` 的签名；现有 `tests/test_config_atomic_save.py` 保持通过。

明确不改：`ConfigBase.load` 的调用时机和「只试一次」标志。`atomic_write_config` 对符号链接和权限的行为。配置默认值与校验。打开失败时现有的日志后返回。

本地验证：`tests/test_config_atomic_save.py` 只覆盖 `atomic_write_config`，不覆盖这次迁移。应新增断言：同一份文本里有键行 `line_height = 1.0`、注释 `# line_height`、命令或值 `echo line_height`，迁移后只有键变成 `cell_height`，另外两处原文还在；缩进的 profile 键行同样被改；文件里没有键行时内容不写；在 `os.replace` 之前失败时原文件字节不变，目录里不留下临时文件。

## r14-4 weaken

问题类：`PluginRegistry.enable` 在插件已启用时打了不能启用的日志，却仍构造新实例并丢掉旧实例，且不调用 `unload`。

降级依据（活码反证，URL 叠层不成立）：

- `Terminal.match_add`（`terminatorlib/terminal.py` 582–584 行）发现同名匹配已在 `self.matches` 里就返回。`URLHandler.__init__`（`terminatorlib/plugin.py` 176–181 行）再次 `match_add` 不会注册第二条规则。
- `prepare_url`（`terminal.py` 2465–2466 行）用注册表里当前实例的 `handler_name` 对上 `self.matches` 再调 `callback`，不调用被丢掉的旧对象。
- 唯一生产调用点 `PrefsEditor.on_plugin_toggled`（`terminatorlib/prefseditor.py` 2362–2364 行）只在 `self.plugins[plugin]` 为假时 `enable`。该表在 753 行用 `registry.is_enabled` 填。偏好开关走不到「已经启用再 enable」。

因此发现稿说的「同一条 URL 规则注册两次」在活码上不发生。仍要收的是 `enable` 自己的控制流：150–155 行在 `err` 之后没有 `return`，156 行总会 `self.available_plugins[plugin]()` 并覆盖 `self.instances`。`load_plugins(force=True)` 在覆盖前会 `unload`（107–114 行），`enable` 没有这一步。`custom_commands` 和 `mousefree_url_handler` 的 `__init__` 会 `connect`，断开在各自的 `unload`。若有人直接再次 `enable`，这些连接会叠上；偏好开关今天不会。

不变量：插件已在 `instances` 里时，`enable` 打出现有错误日志后返回。实例对象不变，构造函数不再调用，`unload` 不调用。尚未启用时仍构造并放入 `instances`，与现在的第一次启用相同。

要动的符号：`PluginRegistry.enable`（150–156 行）。在已存在分支的 `err` 之后 `return`。

明确不改：不要在 `enable` 里先 `unload` 再新建。重建仍只走 `load_plugins(force=True)`。不改 `disable`、`URLHandler`、`match_add` / `match_remove`、`on_plugin_toggled` 的勾选条件。

本地验证：`plugin.py` 顶部 doctest 只 `enable` 一次。应新增断言：假插件第一次 `enable` 后记下 `instances` 里的对象；第二次 `enable` 后仍是同一对象，构造次数为 1，`unload` 次数为 0。

## r14-5 hold

问题类：Flatpak 里解析用户 shell 时，查询失败或 shell 为空会抛异常或返回空串，到不了后面的 shell 列表。

不变量：

- `getent` 给出非空 shell 时原样返回该字符串。不在沙箱里对这个路径做 `os.path.isfile`。宿主路径在沙箱里经常不可见，`get_flatpak_args` 会在宿主上执行它。
- 查询失败，或 shell 字段为空、只有空白：不抛，不 `return`，落到 161 行已有的 `shells` 列表（口令库 shell，然后 bash、zsh、tcsh、ksh、csh、sh）。
- 列表仍找不到时维持现在的隐式 `None`。`Terminal.spawn_child` 2391–2393 行对 `None` 的提示不改。空串不是成功结果：`shell is None` 挡不住 `''`，今天会继续拿空串去 spawn。
- 非 Flatpak 分支的成功路径和候选顺序不变。

要动的符号：`shell_lookup` 里 `is_flatpak()` 分支（`terminatorlib/util.py` 150–156 行）。`check_output` 在非零退出时抛 `CalledProcessError`；可执行文件不存在时抛 `FileNotFoundError`（`OSError`），不是 `CalledProcessError`。`decode` 失败是 `UnicodeDecodeError`，不足 7 段是 `IndexError`。153 行 `pwd.getpwuid(...)[0]` 在没有口令项时抛 `KeyError`；非 Flatpak 分支在 159 行捕获了，Flatpak 分支没有。这些都进入同一条退回，不要只包发现稿点名的那三种。

非 Flatpak 循环只对 `None` 做 `continue`（164 行）。空串会落到 `path_lookup` 再试下一个，结果上会继续找。Flatpak 分支改为失败或空 shell 时不返回，直接使用这段循环，空串不会被当成最终结果。

明确不改：`is_flatpak`（47 行，看 `/.flatpak-info`）。`get_flatpak_args`。非空宿主 shell 的返回值。`spawn_child` 的 Flatpak 参数拼装（2408–2410 行）。

本地验证：无现成测试。应新增断言（把 `is_flatpak` 打成真，并替换 `subprocess.check_output` 或 `pwd.getpwuid`）：非零退出、`FileNotFoundError`、非法 UTF-8、不足 7 段、shell 字段为空、`getpwuid` 抛 `KeyError` 时 `shell_lookup` 都不抛，并返回列表里能找到的那个 shell；`getent` 返回非空 shell 且该路径在本机 `isfile` 为假时，原样返回这一字符串，不改走列表。
