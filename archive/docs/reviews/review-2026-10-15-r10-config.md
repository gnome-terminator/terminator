---
title: "r10 config 发现"
type: audit
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "重命名会丢掉配置档或布局；格子尺寸和插件键写错层；调试类参数与删除 default 会崩溃。"
---

# r10 config 发现

范围内通读 `terminatorlib/config.py`、`configjson.py`、`optionparse.py`、`keybindings.py`。下面 5 条都能沿这些文件里的路径走通。

## r10-1 高

**症状：** 把配置档或布局重命名到已有名字上，原来的那份设置被盖掉；重命名成自己的名字时，该项会从内存里消失。改成 `__internal_json_profile__`、`__internal_json_layout__` 或 `__last_session__` 后，下一次保存不会把它们写进配置文件。

**代码：**

```406:412:terminatorlib/config.py
    def rename_profile(self, profile, newname):
        """Rename a profile"""
        if profile in self.base.profiles:
            self.base.profiles[newname] = self.base.profiles[profile]
            del(self.base.profiles[profile])
            if profile == self.profile:
                self.profile = newname
```

```431:435:terminatorlib/config.py
    def rename_layout(self, layout, newname):
        """Rename a layout"""
        if layout in self.base.layouts:
            self.base.layouts[newname] = self.base.layouts[layout]
            del(self.base.layouts[layout])
```

```943:955:terminatorlib/config.py
        for profile in self.profiles:
            if profile == JSON_PROFILE_NAME:
                continue
            dbg('Processing profile: %s' % profile)
            parser['profiles'][profile] = dict_diff(
                    DEFAULTS['profiles']['default'], self.profiles[profile])

        parser['layouts'] = {}
        for layout in self.layouts:
            if layout == JSON_LAYOUT_NAME:
                continue
            if layout == '__last_session__':
                continue
```

`JSON_PROFILE_NAME` / `JSON_LAYOUT_NAME` 即 `__internal_json_profile__` 与 `__internal_json_layout__`（`configjson.py` 第 7–8 行）。

**为什么是问题：** 目标名已存在时，赋值直接替换该键上的字典，被盖住的配置档或布局没有副本。目标名与原名相同时，先赋给自己再 `del`，键被删掉。保存又跳过上述保留名，内存里还在的内容不会进入文件，重启后丢失。

**方向：** 重命名前拒绝同名、已占用的名字，以及保存时会跳过的保留名。

## r10-2 中

**症状：** 配置档里的 `cell_width` / `cell_height` 读出来始终是全局值，写也写进全局。插件用 `plugin_set` 写入与全局或当前配置档同名的键（例如 `font`）时，改的是全局或配置档，插件自己的树是空的。

**代码：**

```135:136:terminatorlib/config.py
            'cell_width'            : 1.0,
            'cell_height'           : 1.0,
```

```307:308:terminatorlib/config.py
                'cell_height'           : 1.0,
                'cell_width'            : 1.0,
```

```984:991:terminatorlib/config.py
        if key in self.global_config:
            dbg('%s found in globals: %s' %
                    (key, self.global_config[key]))
            return(self.global_config[key])
        elif key in self.profiles[profile]:
            dbg('%s found in profile %s: %s' % (
                    key, profile, self.profiles[profile][key]))
            return(self.profiles[profile][key])
```

```1008:1017:terminatorlib/config.py
        if key in self.global_config:
            self.global_config[key] = value
        elif key in self.profiles[profile]:
            self.profiles[profile][key] = value
        elif key == 'keybindings':
            self.keybindings = value
        elif plugin is not None:
            if plugin not in self.plugins:
                self.plugins[plugin] = {}
            self.plugins[plugin][key] = value
```

`Config.plugin_set`（第 550–552 行）把调用转给 `set_item(..., plugin=pluginname)`，走的是同一段判断。

**为什么是问题：** `cell_width` 和 `cell_height` 同时出现在 `DEFAULTS['global_config']` 和 `DEFAULTS['profiles']['default']`。加载时配置档节里的值会进 `self.profiles`，但查找和赋值都先命中 `global_config`，配置档里的数值到不了界面，改动也落不到该配置档。插件键只要和这两层撞名，就会改掉用户的全局项或当前配置档，并在随后的 `save()` 里写进配置文件。

**方向：** 全局、配置档、插件分通道读写，`cell_width` / `cell_height` 只留在其中一个层。

## r10-3 中

**症状：** 只加 `--debug-classes` 或 `--debug-methods`、不带 `-d`/`--debug` 时，进程在解析命令行时抛 `TypeError` 退出，窗口起不来。

**代码：**

```94:99:terminatorlib/optionparse.py
    parser.add_argument('-d', '--debug', action='count', dest='debug',
            help=_('Enable debugging information (twice for debug server)'))
    parser.add_argument('--debug-classes', action='store', dest='debug_classes',
            help=_('Comma separated list of classes to limit debugging to'))
    parser.add_argument('--debug-methods', action='store', dest='debug_methods',
            help=_('Comma separated list of methods to limit debugging to'))
```

```138:140:terminatorlib/optionparse.py
    if options.debug_classes or options.debug_methods:
        if not options.debug > 0:
            options.debug = 1
```

**为什么是问题：** `action='count'` 在用户没写 `-d` 时得到的是 `None`，不是 `0`。`not options.debug > 0` 会先算 `None > 0`，比较本身就抛 `TypeError`，后面的 `options.debug = 1` 执行不到。

**方向：** 比较之前把缺省的 `debug` 当成 0，再决定是否自动打开调试。

## r10-4 中

**症状：** 在布局之间复制终端字段时，没有 `uuid` 的终端会共用一个槽，目标侧这些终端全被写成源里最后一条的值。源值是空字符串或 `False` 时，目标上的旧值保持不动。

**代码：**

```582:585:terminatorlib/config.py
            cp_item = section.get(item, None)
            uuid    = str(section.get('uuid', None))
            if cp_item:
                items[uuid] = cp_item
```

```594:599:terminatorlib/config.py
            uuid       = str(section.get('uuid', None))
            update_item = items.get(uuid, None)
            if uuid and update_item:
               dbg("update layout item:(%s) with value:(%s)"
                                            % (item, update_item))
               section[item] = update_item
```

**为什么是问题：** 缺 `uuid` 时 `str(None)` 是字符串 `"None"`，后面的 `if uuid` 仍为真，于是所有缺 uuid 的终端挤在同一个键上，后出现的源终端盖住前面的。`if cp_item` 把 `''` 和 `False` 当成“没有可复制的值”，空命令清不掉目标上的旧命令，`False` 也翻不掉目标上的 `True`。

**方向：** 只用真实存在的 uuid 配对，空字符串和 `False` 也要写到目标终端上。

## r10-5 中

**症状：** 删掉名为 `default` 的配置档之后，当前档仍指向 `default`，再读配置档级的键（例如字体）会抛 `KeyError: 'default'`。

**代码：**

```392:400:terminatorlib/config.py
    def del_profile(self, profile):
        """Delete a profile"""
        if profile == self.profile:
            # FIXME: We should solve this problem by updating terminals when we
            # remove a profile
            err('Config::del_profile: Deleting in-use profile %s.' % profile)
            self.set_profile('default')
        if profile in self.base.profiles:
            del(self.base.profiles[profile])
```

```978:991:terminatorlib/config.py
    def get_item(self, key, profile='default', plugin=None, default=None):
        """Look up a configuration item"""
        if profile not in self.profiles:
            # Hitting this generally implies a bug
            profile = 'default'

        if key in self.global_config:
            dbg('%s found in globals: %s' %
                    (key, self.global_config[key]))
            return(self.global_config[key])
        elif key in self.profiles[profile]:
            dbg('%s found in profile %s: %s' % (
                    key, profile, self.profiles[profile][key]))
            return(self.profiles[profile][key])
```

**为什么是问题：** 正在使用 `default` 时，`del_profile` 先 `set_profile('default')`（此时键还在），随后把 `profiles['default']` 删掉，`self.profile` 仍是 `'default'`。`get_item` 发现这个名字不在表里，又把查找名设回 `'default'`，接着对已删除的键做下标。全局键还能返回；字体这类只存在于配置档的键会崩。`set_item` 第 1010 行对同一字典下标，写入同样会崩。

**方向：** 不允许删掉 `default`，或者删除后立刻按内置默认值再建出这个配置档。
