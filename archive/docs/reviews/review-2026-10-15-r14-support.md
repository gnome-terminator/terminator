---
title: "r14 support 发现"
type: audit
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "支持层有调试端口越权、PATH 查找错误、配置迁移误改写、插件重复启用和 Flatpak 取 shell 无回退。"
---

## r14-1

- 严重度：高
- 症状：调试服务在本机所有用户都可连的 TCP 端口上提供无认证 Python 解释器，其他本地用户连上后能在 Terminator 进程里执行代码。

```48:49:terminatorlib/debugserver.py
  def verify_request(self, request, client_address):
    return True
```

```167:174:terminatorlib/debugserver.py
def spawn(env):
  PythonConsoleServer.env = env
  tcpserver = socketserver.TCPServer(('127.0.0.1', 0), PythonConsoleServer)
  dbg("debugserver: listening on %s" % str(tcpserver.server_address))
  debugserver = threading.Thread(target=tcpserver.serve_forever, name="DebugServer")
  debugserver.setDaemon(True)
  debugserver.start()
  return(debugserver, tcpserver)
```

`verify_request` 写在 `BaseRequestHandler` 子类上，而 `TCPServer` 只调用服务器自己的 `verify_request`，这段校验不会执行。即便被调用，它也固定返回 `True`。服务绑定 `127.0.0.1` 的随机端口，不核对对端 uid。同一台机器上的其他本地用户扫到端口即可获得该用户 Terminator 进程的完整 Python 执行能力。

方向：在 `TCPServer` 上按对端 uid 拒绝非本用户连接，或改用权限受控的 unix socket。

## r14-2

- 严重度：中
- 症状：需要沿 PATH 找可执行文件时，PATH 未设置会直接抛 `KeyError`；PATH 以冒号开头时，用户自己的目录被丢掉，可能启动错误的 shell 或找不到命令。

```130:136:terminatorlib/util.py
    try:
        paths = os.environ['PATH'].split(':')
        if len(paths[0]) == 0: 
            raise(ValueError)
    except (ValueError, NameError):
        dbg('path_lookup: PATH not set in environment, using fallbacks')
        paths = ['/usr/local/bin', '/usr/bin', '/bin']
```

`os.environ['PATH']` 在变量缺失时抛出的是 `KeyError`，这里却只捕获 `ValueError` 和 `NameError`，日志里写的「PATH 未设置就用回退目录」不会发生。第一段为空（`PATH` 为 `:/usr/bin:...` 或空字符串）时又把整份 PATH 换成三个固定目录，`/usr/local` 之后和家目录下的路径都不再搜索。`shell_lookup` 在口令库里的 shell 不是已存在文件时会调用 `path_lookup`（同文件约 169 行），因此会表现为终端起不来，或退回到 `/usr/bin` 里的另一个 shell。

方向：捕获 `KeyError`，只在 PATH 整体缺失时使用回退目录，空的路径段按当前目录处理并保留其余目录。

## r14-3

- 严重度：中
- 症状：旧配置迁移会把文件中所有 `line_height` 子串改成 `cell_height`，命令、标题或注释里的同样文字被改写，且就地覆盖、没有原文件可回退。

```565:578:terminatorlib/util.py
            if not 'line_height' in config_text:
                #
                # It is either a new config, or it is already using the
                # new ‘cell_height’ property instead the old ‘line_height’.
                #
                dbg('No ‘line_height’ found in ‘%s’.' % filename)
                file.close()
                return

            updated_config_text = config_text.replace('line_height', 'cell_height')

            file.seek(0)
            file.write(updated_config_text)
            file.truncate()
```

替换作用在整份文本上，不区分键、值和注释。用户命令或标题里如果包含这串字符，迁移后内容就变了。写入是对原文件 `seek(0)` 后直接覆盖，中途失败时配置文件本身被写坏。

方向：只替换配置键名，先写入临时文件再替换原文件。

## r14-4

- 严重度：中
- 症状：对已经启用的插件再调用 enable，日志说不能启用，但旧实例不被卸载，新实例仍会挂上，URL 匹配等副作用叠一层。

```150:155:terminatorlib/plugin.py
    def enable(self, plugin):
        """Enable a plugin"""
        if plugin in self.instances:
            err("Cannot enable plugin %s, already enabled" % plugin)
        dbg("Enabling %s" % plugin)
        self.instances[plugin] = self.available_plugins[plugin]()
```

`err` 之后没有 `return`。新对象赋给 `self.instances` 时，旧对象的 `unload` 不会被调用。`URLHandler.__init__` 会给当前每个终端 `match_add`（同文件 176–181 行），而移除匹配只发生在 `unload`（192–199 行）。结果是同一条 URL 规则注册两次，旧插件对象被丢掉但终端上的匹配还在。`load_plugins(force=True)` 在重建前会先 `unload`，enable 这条路径没有同样的步骤。

方向：已经在 `instances` 里就直接返回；确定要重建时先 `unload` 再换上新实例。

## r14-5

- 严重度：中
- 症状：Flatpak 里解析用户 shell 时，`getent` 失败、输出编码不对或字段不足会把异常抛出；shell 字段为空也直接返回，不再尝试 bash/sh。

```150:156:terminatorlib/util.py
    if is_flatpak():
        getent = subprocess.check_output([
            'flatpak-spawn', '--host', 'getent', 'passwd',
            pwd.getpwuid(os.getuid())[0]
        ]).decode(encoding='UTF-8').rstrip('\n')
        shell = getent.split(':')[6]
        return shell
```

`check_output` 在 `flatpak-spawn` 或 `getent` 非零退出时抛 `CalledProcessError`，UTF-8 解码失败或行内不足 7 段时分别抛 `UnicodeDecodeError` 和 `IndexError`。这段没有捕获，后面的 `usershell, bash, zsh, ...` 回退列表不会执行。成功但 shell 字段为空时同样直接 `return`，调用方拿到空字符串。非 Flatpak 分支会跳过空值并继续找一个存在的 shell。

方向：查询失败或 shell 为空时退回后面的 shell 列表，不要把异常直接抛给启动终端的调用方。
