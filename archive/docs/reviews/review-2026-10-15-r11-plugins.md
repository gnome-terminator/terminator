---
title: "r11 plugins 发现"
type: audit
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "插件中有日志丢字符、docker/podman 参数解析退出进程、书签写死 /tmp，以及缺 position 时命令配置被覆盖。"
---

## r11-1

- 严重度：高
- 症状：Logger 每次把终端内容写入文件时都会丢掉该段最后一个字符；输出跨越多屏时，每一段刷新各丢一个字符，点 Stop Logger 收尾同样少最后一个字符。

```49:54:terminatorlib/plugins/logger.py
        content = content[0]
        fd = self.loggers[terminal]["fd"]
        # Don't write the last char which is always '\n'
        fd.write(content[:-1])
        self.loggers[terminal]["col"] = col_end
        self.loggers[terminal]["row"] = row_end
```

- 为什么是问题：`get_text_range` / `get_text_range_format` 返回的是起止单元格之间的文本。光标不在列 0 时，最后一个字符是光标前的正文，不是额外补上的换行；只有结束列刚好为 0 时，末字符才是这一行的换行。`content[:-1]` 删掉它之后，函数又把本次的结束行、结束列记成下次起点，下一次范围从光标处开始，被删掉的字符不会再被写入。`stop_logger` 在行列有变化时调用的也是 `write_content`，所以正常停止日志同样丢字。
- 方向：按取出的文本原样写入，并把下一次起点放在真正已经写入的内容之后。

## r11-2

- 严重度：高
- 症状：某个终端的子进程是带 `-h`/`--help` 的 `docker`/`podman exec`，或是只带 `-l`/`--latest`、没有容器名的 `exec`/`attach` 时，Terminator 进程会直接退出，当前所有终端会话丢失。

```202:214:terminatorlib/plugins/remote.py
        try:
            if cmd == "run":
                return self._get_host_run(proc)
            elif cmd == "exec":
                return self._get_host_exec(proc)
            elif cmd == "attach":
                return self._get_host_attach(proc)
            err("unrecognized sub command?")
        except psutil.NoSuchProcess as e:
            dbg(f"proc has gone away: {e}")
        except Exception as e:
            err(f"caught exception {e}")
        return None
```

```283:297:terminatorlib/plugins/remote.py
        parser = argparse.ArgumentParser()
        parser.add_argument("container")
        parser.add_argument("command", nargs='?')
        parser.add_argument('-d', '--detach', action='store_true')
        parser.add_argument('--detach-keys')
        parser.add_argument('-e', '--env')
        parser.add_argument('--env-file')
        parser.add_argument('-i', '--interactive', action='store_true')
        parser.add_argument('-l', '--latest', action='store_true')
        parser.add_argument('--privileged')
        parser.add_argument('--preserve-fds')
        parser.add_argument('-t', '--tty', action='store_true')
        parser.add_argument('-u', '--user')
        parser.add_argument('-w', '--workdir')
        args, unknown = parser.parse_known_args(fullArgs[startIndex:])
```

```463:477:terminatorlib/plugins/remote.py
    def _update_watches(self, _):
        """
        Watch for new terminals in background
        """
        for terminal in self.terminator.terminals:
            self.remote_proc_watch.Register(terminal.pid)
            ret = self.remote_proc_watch.GetPIDProcInfo(terminal.pid)
            if ret:
                child, remoteType = ret
                if terminal not in self.currRemoteTerminals:
                    self._apply_host_settings(
                        terminal=terminal,
                        proc=child,
                        proc_type=remoteType
                    )
```

- 为什么是问题：`_get_host_exec` 和 `_get_host_attach` 使用默认的 `ArgumentParser`。它自带 `-h`/`--help`，遇到这两个参数会 `sys.exit(0)`；`-l`/`--latest` 又把容器名做成必填位置参数，像 `podman attach -l` 或 `exec -l -it` 这种没有容器名的命令会 `sys.exit(2)`。`SystemExit` 不是 `Exception` 的子类，`GetHost` 里的 `except Exception` 接不住。`_update_watches` 由每秒一次的 `GLib.timeout_add` 调用，一旦识别到这类远程进程就会 `GetHost`。回调里冒出的 `SystemExit` 会结束整个进程。`docker exec -it <容器> mysql -h 127.0.0.1 ...` 这类会一直运行、参数里带 `-h` 的命令会触发退出。
- 方向：解析容器命令行时关闭自动 help 和失败即退出，解析失败只当作没有主机名。

## r11-3

- 严重度：高
- 症状：记录「上一条命令」时，若当前前台不是会执行该重定向的 shell，GTK 主线程永久卡住；`/tmp/term_cmd` 若已是指向其它文件的符号链接，shell 的 `>` 会截断那个文件，读到的内容也可能不是本终端的上一条命令。

```113:128:terminatorlib/plugins/custom_commands.py
    def get_last_exe_cmd(self):
        cur_win  = Terminator().last_focused_term.get_toplevel()

        #TODO: there has to be a better way to get the last command executed
        focus_term = cur_win.get_focussed_terminal()
        tmp_file   = os.path.join(os.sep, 'tmp', 'term_cmd')
        command    = 'fc -n -l -1 -1 > ' + tmp_file + '; #bookmark last cmd\n'
        focus_term.vte.feed_child(str(command).encode("utf-8"))

        fsz     = 0
        count   = 0
        while not (count == 2 or fsz):
            time.sleep(0.1)
            if os.path.exists(tmp_file):
                fsz = os.path.getsize(tmp_file)
                count += 1
```

```146:153:terminatorlib/plugins/custom_commands.py
    def get_last_exe_cmd_dialog_vars(self):
      last_exe_cmd = self.get_last_exe_cmd()

      dialog_vars = { 'enabled'   : True,
                      'name'      : last_exe_cmd,
                      'name_parse': False,
                      'command'   : last_exe_cmd }
      return dialog_vars
```

```462:462:terminatorlib/plugins/custom_commands.py
      name.set_text(name_var)
```

- 为什么是问题：`count` 只在 `/tmp/term_cmd` 已经存在时增加。`feed_child` 只是把 `fc ... > /tmp/term_cmd` 送进当前前台；前台若是正在跑的程序、vim，或根本不会执行这条 `fc` 的 shell，文件不会出现，`count` 和 `fsz` 一直是 0，`while` 条件永远成立，主线程停在 `time.sleep` 里。路径固定在大家都能写的 `/tmp`：该名字若是符号链接，用户 shell 的 `>` 会按链接去截断目标文件；其它用户或另一个终端也可以抢先创建同名文件，于是书签读到外来内容。打开失败时函数返回 `None`，对话框仍把这个值传给 `Gtk.Entry.set_text`，而该参数不接受 `None`。
- 方向：改到用户私有、不可预测的临时文件里异步取上一条命令，取不到就结束等待，不要阻塞主线程。

## r11-4

- 严重度：高
- 症状：Custom Commands 或 Run command on matches 的配置里只要有条目没有 `position`，加载后会盖掉已有命令，或把同一条命令插进列表多次；随后保存会把丢失写回配置。

```77:92:terminatorlib/plugins/custom_commands.py
        if "position" in s:
          self.cmd_list[int(s["position"])] = {'enabled' : enabled,
                                               'name' : name,
                                               'name_parse' : name_parse,
                                               'command' : command
                                              }
        else:
          noord_cmds.append(
                              {'enabled' : enabled,
                                'name' : name,
                                'name_parse' : name_parse,
                                'command' : command
                              }
                            )
        for cmd in noord_cmds:
            self.cmd_list[len(self.cmd_list)] = cmd
```

```104:119:terminatorlib/plugins/run_cmd_on_match.py
        if "position" in s:
          self.cmd_list[int(s["position"])] = {'enabled' : enabled,
                                               'regexp' : regexp,
                                               'command' : command
                                              }
        else:
          noord_cmds.append(
                              {'enabled' : enabled,
                                'regexp' : regexp,
                                'command' : command
                              }
                            )
        for cmd in noord_cmds:
            self.cmd_list[len(self.cmd_list)] = cmd

        self._load_configured_handlers()
```

- 为什么是问题：没有 `position` 的条目会进 `noord_cmds`，但后面的 `for cmd in noord_cmds` 写在 `for part in sections` 里面。每处理完一条配置，都会把目前累计的无序命令再写入 `cmd_list`，键是当时的 `len(self.cmd_list)`。这个长度会撞上已经占用的 `position`。例如先载入 position 为 0 和 2 的两条，再载入一条没有 position 的命令，第二条会被盖掉。两条都没有 position 时，第一条会被插入多次。界面保存时会写上 position，但这段加载代码就是用来接受缺 position 的配置的。`run_cmd_on_match.py` 还在同一层循环里调用 `_load_configured_handlers()`，不完整的列表会经过 `config.save()` 写回启用插件。
- 方向：无 position 的条目等全部 section 读完后，再补进尚未占用的位置，不要覆盖已有键。

## r11-5

- 严重度：中
- 症状：在任意终端打开右键菜单时，所有终端的 profile 都会被改成当前自动主题；在设置里改过明暗配色后点取消，这些 profile 仍保持改过的值。

```55:66:terminatorlib/plugins/auto_theme.py
    def callback(self, menuitems, menu, terminal):
        item = Gtk.CheckMenuItem(_(' -  AutoTheme'))
        # item.set_active(True)
        item.connect("toggled", self.do_menu_toggle, terminal)
        menuitems.append(item)
        # print('AutoTheme __init__..')

        # AutoTheme.load_config()
        ## load mode stat
        mode = AutoTheme.mode=='Dark' or AutoTheme.mode=='Auto' and AutoTheme.is_dark_theme()
        print('load mode:', mode)
        AutoTheme.change_theme(mode)
```

```119:131:terminatorlib/plugins/auto_theme.py
    def apply_theme(name):
        terminator = plugin.Terminator()
        # print('---terminals:', len(ts), ts)
        for term in terminator.terminals:
            # print('term:', term)
            term.set_profile(term.get_vte(), name)

    @staticmethod
    def change_theme(isdark):
        # theme = '_light2' if isdark else '_light_day'
        theme = AutoTheme.dark if isdark else AutoTheme.light
        print('--change_theme:', isdark, theme)
        AutoTheme.apply_theme(theme)
```

```400:407:terminatorlib/plugins/auto_theme.py
    def on_light_combo_change(self, widget):
        theme = widget.get_active_text()
        print('-- light selected:', theme)
        self.mgr.apply_theme(theme)
    def on_dark_combo_change(self, widget):
        theme = widget.get_active_text()
        print('-- dark selected:', theme)
        self.mgr.apply_theme(theme)
```

```451:460:terminatorlib/plugins/auto_theme.py
    def on_dialog_response(self, dialog, response_id):
        # print('== on response:', response_id)
        self.mgr.change_cb = None
        self.light_sel = self.light_combo.get_active_text()
        self.dark_sel  = self.dark_combo.get_active_text()
        if response_id == Gtk.ResponseType.OK:
            pass
        # elif response_id == Gtk.ResponseType.CANCEL:
        else:
            print("-- Cancel/close clicked.")
```

- 为什么是问题：`callback` 是每次弹出终端菜单时都会走的路径，里面无条件调用 `change_theme`。`change_theme` 再对 `terminator.terminals` 里的每一个终端 `set_profile`，右键的那个终端原来用什么 profile 不参与判断。设置对话框里两个下拉框一变就 `apply_theme`；取消分支只清掉回调并打印日志，没有把每个终端设回打开对话框之前的 profile。
- 方向：弹出菜单只负责显示菜单项；主题预览在取消时恢复每个终端原先的 profile。
