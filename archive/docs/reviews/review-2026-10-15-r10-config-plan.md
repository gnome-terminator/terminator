---
title: "r10 config 方案"
type: plan
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "三条按原级改，两条降级后仍改；没有丢弃项。"
---

# r10 config 方案

对照 `docs/reviews/review-2026-10-15-r10-config.md` 与磁盘活码。五条引用的行号和对应行为都还在。判定：hold 3（r10-1、r10-2、r10-3），weaken 2（r10-4、r10-5），drop 0。

本方案不改 `terminatorlib/keybindings.py`（发现稿未引用它）。不改 `terminatorlib/util.py` 的 `update_config_to_cell_height`。不改 `terminatorlib/configjson.py` 里 `ConfigJson.extend_config` 直接写入内部档名、内部布局名的做法。

现有 `tests/` 没有 `rename_profile`、`copy_layout_item`、`debug_classes`、`del_profile` 的用例。验证落在新文件 `tests/test_config_r10.py`，用 `tests/run_tests.sh tests/test_config_r10.py -q` 跑。全量套件带 `--doctest-modules`，`terminatorlib/config.py` 文首示例必须仍通过：删除的是非 `default` 档，插件走的是 `plugin_set_config` 整棵树。

碰到 `Config` / `ConfigBase` 的用例要先清 Borg 共享状态里的 `ConfigBase`，并把 `ConfigBase.load` 换成空操作或指到临时配置，避免读到本机配置目录，也避免 `save()` 写回去。断言直接看 `profiles`、`layouts`、`plugins`、`global_config`。

## r10-1 hold

**问题类：** 重命名配置档或布局时，目标已存在会被盖掉，目标与源同名会把该项删掉，改成保存时跳过的保留名则下次保存写不进文件。

**不变量：**

- 目标是另一个已存在的名字时，两个名字下的字典都保持原样。
- 目标与源相同名时，该键还在，值仍是原来的字典。
- 目标是保存会跳过的保留名时，不改名。配置档保留名是 `JSON_PROFILE_NAME`（`__internal_json_profile__`）。布局保留名与 `Config.list_layouts`、`ConfigBase.save` 已有的那一组相同：`JSON_LAYOUT_NAME`（`__internal_json_layout__`）和 `__last_session__`。
- 源名字不存在时不造出目标。
- 成功改名之后，源键消失，目标键是原来的那份字典；若被改名的是当前档 `Config.profile`，当前档改成新名字。

**要动的符号或文件：**

- `Config.rename_profile`、`Config.rename_layout`：上面几种拒绝情况返回 `False` 且不改字典；同名成功视为无操作并返回 `True`；真正改名返回 `True`。保留名用 `configjson` 里已有常量，布局的 `__last_session__` 用 `save` 里已有的那个字面量，避免另起一套字符串。函数内再导入 `configjson` 即可，与 `save` 相同，避免和 `configjson` 顶层导入 `Config` 缠在一起。
- `prefseditor.on_profile_name_edited`、`prefseditor.on_layout_name_edited`：返回 `False` 时不要改树模型，也不要 `save()`。返回 `True` 时保持现在的模型更新和保存。这两处今天不看返回值；`rename_*` 现在隐式返回 `None`，调用方必须和返回值一起改，否则成功的改名也会被当成失败。

**本项不动：** `add_profile` / `add_layout` 已有的「重名返回 False」、`list_layouts` 的过滤、`save` 里跳过保留名的循环、`ConfigJson.extend_config` 对内部名的直接赋值、会话代码对 `__last_session__` 的写入。偏好设置里「源名是 `default` 或新旧名字相同就返回」的判断留在界面上；同名由 `rename_*` 再挡一层。源名 `default` 的拒绝放在 r10-5。

**本地验证：** 新用例。目标已存在时两个配置档（以及两个布局）的内容都还在；同名调用后键还在；目标为 `__internal_json_profile__`、`__internal_json_layout__`、`__last_session__` 时原键还在且新键不出现。成功改名后旧键没有、新键是原字典，当前档名字跟着变。界面回调用假的 `rename_*` 返回 `False` 时，模型文本和保存都不发生。

## r10-2 hold

**问题类：** `cell_width` / `cell_height` 同时在全局默认和配置档默认里，查找和赋值先命中全局；`plugin_set` 走到同一段判断，键名一旦和全局或当前配置档撞车，就改用户配置，插件树仍是空的。

**不变量：**

- 运行时 `cell_width` 和 `cell_height` 只存在于 `global_config`。`Config.__getitem__` / `__setitem__` 继续先看全局，因此偏好设置全局页和 `terminal.py` 里的 `set_cell_width_scale` / `set_cell_height_scale` 仍读写全局。
- 配置档默认值、以及 `defaults_to_configspec` 为配置档生成的规格，不再声明这两个键。`ConfigBase.save` 用 `dict_diff` 只输出默认值里有的键，去掉之后，下一次保存不会再把它们写进配置档节。已经写在配置档节里的旧值今天到不了界面，本项不把它们合并进全局，也不改成按配置档生效。
- `plugin` 参数不是 `None` 时，`get_item` / `set_item` 只读写 `self.plugins[plugin]`。缺键时沿用现在的默认值与 `KeyError`（默认值为假时仍会落到 `KeyError`，与文首 doctest 的真值默认一致）。不再先改全局或当前配置档。
- 未带 `plugin` 的查找顺序保持：全局，然后当前配置档，然后 `keybindings`。

**要动的符号或文件：**

- `DEFAULTS['profiles']['default']`：去掉 `cell_width`、`cell_height`。`DEFAULTS['global_config']` 保留这两键。
- `ConfigBase.get_item`、`ConfigBase.set_item`：`plugin` 不是 `None` 时走插件树并返回。`Config.plugin_get` / `Config.plugin_set` 已转入这两个函数，不必另写一套存储。
- `ConfigBase.load`：配置档节 `update` 进来之后，从每个配置档字典里删掉这两个键，避免同一次运行里的内存副本还占着名字。

**本项不动：** `Config.plugin_get_config`、`plugin_set_config`、`ConfigBase.get_plugin`、`set_plugin`（整棵树）。`plugins/custom_commands.py` 与 `plugins/run_cmd_on_match.py` 仍用命令名或正则当键。全局页的 `on_cellheight_value_changed`、`on_cellwidth_value_changed`。`terminal.py` 对这两个键的读取。

**本地验证：** 新用例。`plugin_set(插件, 'font', 字典)` 之后，`profiles['default']['font']` 仍是原来的字体字符串，`global_config` 不变，该字典出现在 `plugins[插件]['font']`；`plugin_get` 读回这个字典。`plugin_set_config` 写入的整棵树仍能被 `plugin_get` 读到（保住文首 doctest 那条路径）。配置档字典里手工放上不同的 `cell_width` 后，`get_item('cell_width')` 仍是全局值；走一遍保存用的 `dict_diff` 时，配置档输出里没有 `cell_width` / `cell_height`。

## r10-3 hold

**问题类：** 只加 `--debug-classes` 或 `--debug-methods`、不带 `-d` 时，`action='count'` 得到的 `debug` 是 `None`，`None > 0` 抛 `TypeError`，进程在打开窗口前退出。

**不变量：**

- 带了类过滤或方法过滤，且 `debug` 为 `None` 或 `0` 时，把 `debug` 设为 `1`，不抛异常。
- 已经是 `1` 或更大（例如 `-dd`）时保持原次数，过滤列表照旧追加。
- 两个过滤都没给时，`debug` 保持 `None`，后面的 `if options.debug` 仍为假，不打开调试。
- 空字符串的过滤参数仍视为没给（现有 `or` 判断）。

**要动的符号或文件：**

- `optionparse.parse_options` 里 `debug_classes` / `debug_methods` 那段比较。收成同文件里的纯函数，例如给定 `(debug, debug_classes, debug_methods)` 返回应用后的 `debug`。`parse_options` 把返回值写回 `options.debug`，然后再做现有的 `util.DEBUG`、`DEBUGCLASSES`、`DEBUGMETHODS`。这样测试不必跑 `parse_options` 后半段的 `chdir`、`Config()` 和进程级调试开关。

**本项不动：** `-d` / `--debug` 的 `action='count'` 定义、调试服务器「大于 1」的门槛、类名和方法名的逗号拆分。

**本地验证：** 新用例直接调该纯函数。`(None, 'Config', None)` 和 `(None, None, 'load')` 得到 `1`；`(2, 'Config', None)` 得到 `2`；`(1, None, None)` 得到 `1`；`(None, None, None)` 和 `(None, '', '')` 得到 `None`。不调用 `parse_options` 全函数。

## r10-4 weaken

**问题类：** `copy_layout_item` 把缺失的 uuid 收成字符串 `"None"`，这些终端共用一个槽，目标被写成源里最后一条为真的值。

**反证（因此降级）：**

- `session.strip_live_ids` 会去掉节点上的 `uuid`。`prefseditor.on_layoutaddbutton_clicked` 在 `add_layout` 之前调用它；`on_layoutrefreshbutton_clicked` 在三次 `copy_layout_item`（`directory`、`command`、`profile`）之前对目标再调用一次。刷新时两边通常都没有 uuid，`"None"` 是这条路径的常态。
- 刷新目标来自 `Terminator.describe_layout()`，默认 `save_cwd=False`。`Terminal.describe_layout` 不写 `command`，这个默认下也不写 `directory`。唯一调用方复制的三个字段都是字符串，`False` 不是它们的取值。空字符串在这条路径上并不是「清不掉目标里已有的命令」：新描述出来的目标没有命令。把每个终端都写成同一条命令的，是共用槽里最后一条为真的源值。
- 降级后的改法只禁止缺失 uuid 合成同一个键。按真实 uuid 配对之后，现有刷新不会再涂抹命令，也不会再把各终端原来的命令抄过去。这是接受的结果。活动终端的 uuid 继续不写进保存的布局，`strip_live_ids` 的用途是避免滚动回退缓存文件被共用。

**不变量：**

- 缺键、`None` 或空字符串的 uuid 不参与配对，该终端的字段保持调用前的值。
- 两边都有非空 uuid 且字符串形式相同，源节里该键存在时，把值写到目标，包括 `''` 和 `False`。判断标准是键是否存在，不是值是否为真。
- 两个终端的真实 uuid 相同仍共用一个槽。本项不另造身份。

**要动的符号或文件：**

- `Config.copy_layout_item`。不要 `str(None)`。只有非空 uuid 才作为键。源侧用键存在性收集，目标侧用「这个 uuid 是否收集到了」写回，这样 `''` 和 `False` 写得进去。

**本项不动：** `strip_live_ids`、`describe_layout`、`on_layoutrefreshbutton_clicked` 的调用顺序和它传入的三个字段名、`add_layout` 前的剥离、`replace_layout`。

**本地验证：** 新用例。两个没有 uuid 的源终端命令分别是 `a` 和 `b`，目标终端原命令保持不变，不会都变成 `b`。两个 uuid 相同且非空的终端，源的 `command` 为 `''`、目标原来是 `old` 时，目标变成 `''`；源的某个布尔字段为 `False`、目标原来是 `True` 时，目标变成 `False`。不要求布局刷新按钮仍能按终端保留命令。

## r10-5 weaken

**问题类：** `del_profile('default')` 会在当前档仍叫 `default` 的情况下删掉 `profiles['default']`，随后按配置档取键（例如字体）在 `get_item` / `set_item` 里 `KeyError`。

**反证（因此降级）：** 偏好设置走不到这条路径。`prefseditor.on_profileremovebutton_clicked` 在档名是 `default` 时直接返回，不调用 `del_profile`。`on_profile_selection_changed` 把 `profileremovebutton` 设为不敏感。生产代码里调用 `del_profile` 的只有这一处；`config.py` 文首 doctest 删的是别的档名。函数本身仍会崩：正在使用 `default` 时先 `set_profile('default')`（此时键还在，不会按缺失重建），再删掉该键，`self.profile` 仍是 `'default'`。`get_item` 发现档名不在表里又把查找名设回 `'default'`，然后对已删除的键做下标。全局键在这之前就返回了；只存在于配置档的键会崩。`set_item` 对 `self.profiles[profile]` 做 `in` 判断时同样抛 `KeyError`。降为只堵 API，不改界面。

**不变量：**

- `del_profile('default')` 返回后，`profiles['default']` 仍是调用前的那份字典（含用户改过的字体等），`Config.profile` 不变，命令行 `options.profile` 也不被清掉。
- `rename_profile('default', 其他名字)` 返回 `False`，`default` 键还在。否则改名同样会删掉这个键。与 r10-1 的返回值约定一致。
- 删除其他正在使用的档时，仍先 `set_profile('default')` 再删除那个档，并在命令行档名就是被删档时把它清成 `None`（`del_profile` 后半段现有逻辑）。
- `get_item` / `set_item` 在即将使用 `'default'` 而该键不存在时，先放进一份 `DEFAULTS['profiles']['default']` 的副本再下标。这只兜住键已经没了的情况，恢复的是内置默认，不是被删掉的那份自定义；正常路径靠上面的拒绝，不会走到这里。

**要动的符号或文件：**

- `Config.del_profile`：档名是 `default` 时立刻返回，不打「正在删除使用中的档」的日志，不调用 `set_profile`，不删键，也不改 `options.profile`。
- `Config.rename_profile`：源名是 `default` 时返回 `False`（与 r10-1 的拒绝返回值同一处实现）。
- `ConfigBase.get_item`、`ConfigBase.set_item`：使用 `'default'` 前保证该键存在。

**本项不动：** 偏好设置里对 `default` 的提前返回和移除按钮敏感度。`set_profile` 在档名不存在时复制内置默认的行为。删除非 `default` 档的日志和命令行档名清理。

**本地验证：** 新用例。先改 `default` 的 `font`，再 `del_profile('default')`，`font` 仍是改过的值，`get_item('font', 'default')` 不抛异常。`rename_profile('default', 'other')` 为 `False`，键仍叫 `default`。当前档是别的名字时 `del_profile` 那个名字，该键消失，当前档变为 `default`，`get_item('font')` 仍成功。把 `profiles` 里的 `default` 临时拿掉再 `get_item('font', 'default')`，得到内置默认字体且不抛 `KeyError`。
