---
title: "r08 titlebar 方案"
type: plan
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "四条保留、一条降级：编辑确认会锁住旧标题，查找重开与非 ASCII 长度、重复响铃仍要改；自定义标题重写降为契约问题。"
---

# r08 titlebar 方案

核对结论：hold 4，weaken 1，drop 0。发现稿引用的五处行为与磁盘活码一致，行号仍落在同一函数上。drop 无。本方案只描述改法，不附可合入补丁。

生产改动只落在 `terminatorlib/editablelabel.py`、`terminatorlib/titlebar.py`、`terminatorlib/searchbar.py`。

## r08-1 hold

问题类：标题正在编辑时，尺寸提示消失或终端标题更新，再按 Enter，会把打开编辑时的旧文本锁成自定义标题，之后外壳标题不再显示。

不变量：

- 确认编辑时，只把用户相对「打开编辑那一刻的文本」的改动写成自定义标题。
- 编辑期间 `Titlebar.update`、`update_label_only`、`_clear_sizetext` 仍可刷新将要显示的标签，取消（Escape）后看到的是最新自动标题。
- 用户一个字都没改就按 Enter 时，`_custom` 保持假，标签保留刷新后的自动标题（不含已经消失的 `80x24` 一类尺寸后缀）。
- 用户改过字再确认时，标签等于输入框内容，`_custom` 为真；此后外壳标题更新只改 `_autotext`，不改标签。
- 输入框为空仍取消自定义，并用 `_autotext` 恢复自动标题。

要动的符号：

- `EditableLabel.edit`（约 76–82 行：把当时的标签文本拷进输入框，之后不再更新这份拷贝）。在这里留下一份只用于比较的原文。
- `EditableLabel._on_entry_activated`（约 128–139 行：现在拿输入框和「当前标签」比，`entry != label` 就 `set_custom` 并把旧串写回标签）。改为和打开时的原文比。相同则不置 `_custom`、不用输入框覆盖标签。
- `EditableLabel.set_text`（约 66–70 行）在 `_custom` 为假时继续改标签。编辑期间标题栏仍会调用它：`Titlebar.update`（约 275–276 行）、`set_terminal_title`（约 477–480 行）、`update_terminal_size` / `_clear_sizetext` / `update_label_only`（约 444–475 行），以及 `_collapse_idle_cb`（约 1087–1090 行）。这些调用保持，它们不是比较基准。

明确不改：尺寸只显示约一秒的计时，折叠阈值，分组名编辑（`groupentry_*`），颜色和字体。Escape 仍只收起输入框、不把当前输入写成自定义标题。

本地验证：`tests/test_titlebar_chrome.py` 的 `test_sizetext_only_while_timer_pending` 只断言尺寸出现又消失，不覆盖编辑中的确认。应新增断言：`termtext` 已有外壳标题时打开编辑，不改输入框，调用 `_clear_sizetext` 或 `set_terminal_title` 后再走 `_on_entry_activated`，`is_custom()` 为假，标签等于刷新后的自动标题且不含打开时的尺寸后缀；把输入框改一个字符再确认，`is_custom()` 为真且标签等于该输入；这次确认之后再 `set_terminal_title`，标签仍是用户输入。未改动的那次确认之后再 `set_terminal_title`，标签变为新外壳标题。

## r08-2 weaken

问题类：`set_custom_string` 经 `set_text` 写入时占用自动标题缓存；已是自定义时再次调用不更新标签上的文字。

降级原因（读到的反证）：

- 第一次调用时 `_custom` 仍为假，`set_text` 会把标签写成这条字符串。生产调用只有 `Terminal.create_layout`（`terminatorlib/terminal.py` 约 3267–3268 行，布局新建的终端）和 `ipc.py` 约 208 行（新建分屏）。两处都在尚未自定义的标题栏上调用一次，屏幕上会显示这次的字符串。
- 用户在编辑框里把已有自定义标题改成另一串，走 `EditableLabel._on_entry_activated` 约 136–138 行，直接 `_label.set_text(entry)`，不经过 `set_custom_string`。
- 清空并回车会先把 `_custom` 置假并 `set_text(_autotext)`。`Terminal.on_edit_done`（约 2152–2154 行）接着 `vte.grab_focus()`。`grab-focus` 接到 `on_vte_focus`（约 2109–2111 行），发出 `title-change`，`set_terminal_title` / `update` 在自定义已取消时把 `get_window_title()` 的自动标题画回标签。发现稿所说「下一次普通标题刷新之前，清空并回车也不会回到自动标题」，在这条已接好的 `edit-done` 链上不成立。

函数契约仍然是错的：`set_text` 总会改写 `_autotext`（约 66–70 行），第一次 `set_custom_string` 把恢复用的自动标题换成自定义字符串；`_custom` 已为真时，新字符串只进 `_autotext`，标签保持旧文（`titlebar.py` 约 1189–1192 行）。清空能否回到外壳标题，目前依赖编辑结束时的抢焦点，不依赖这份缓存。

不变量：

- 自定义字符串只出现在标签上。`_autotext` 只保留外壳标题、停用提示和尺寸合成的自动文本。
- 已处于自定义时，再次 `set_custom_string` 后标签文字等于新字符串，`_autotext` 与调用前相同，`is_custom()` 仍为真。
- 第一次 `set_custom_string` 后标签等于该字符串，`is_custom()` 为真，`_autotext` 仍是调用前的自动标题。
- 清空输入框并确认后，标签回到该自动标题，`is_custom()` 为假。此断言直接打在标题栏 / 可编辑标签上，不经过 `Terminal.on_edit_done`。

要动的符号：

- `Titlebar.set_custom_string`。写入自定义文案时不要让这次字符串留在 `_autotext`。已是自定义时仍要改标签文字，然后 `set_custom`。
- `EditableLabel` 需要能改标签而不替换 `_autotext`（新的窄入口，或调用前取出 `_autotext`、写完再放回）。`set_text` 在自定义期间继续把外壳合成标题写入 `_autotext`，供以后清空恢复。

明确不改：`_on_entry_activated` 里用户改过字就直接写标签的分支。不改 `set_text`「自定义时仍更新 `_autotext`」。不改 `notebook.py` 的 `set_custom_label`。不改 `terminal.py` / `ipc.py` 的调用点，不改 `get_custom_string` 的含义（自定义时返回标签文字）。不改 `tests/e2e/roundtrip_driver.py`。

本地验证：现无测试调用 `set_custom_string`。应新增上列三条断言。`tests/test_titlebar_chrome.py` 已能构造 `Titlebar`，可挂在同一夹具上。

## r08-3 hold

问题类：关掉查找再打开时，输入框仍是上次的词，但搜索模式已卸掉，回车、上一条、下一条不会按这个词再搜，高亮也不回来。

不变量：对话框再次出现且输入框非空时，VTE 上的搜索模式对应当前文字和当前选项（大小写、整词、正则、折返）。重开后高亮恢复，回车和上一条、下一条按这个词移动。输入框为空时仍清除模式并禁用导航。模式非法时仍标红并清除高亮。

要动的符号：`Searchbar.start_search`（约 57–67 行：只 `present`、聚焦、`select_region`）。在 `self.vte` 已接上且对话框已建好之后，用输入框当前文字走现有 `_apply`。`end_search`（约 69–80 行）会把 `_last` 置空，因此 `_apply(jump=False)` 里「不是在原词后续写」的分支会跳到一处匹配，重开即完成一次查找。

`next_search` / `prev_search`（约 281–298 行）和 `_on_activate`（约 176–180 行）在文字非空时直接 `search_find_next` / `search_find_previous`。模式由重开时装上，这两处保持纯跳转。`select_region` 不改变文字，也不发出 `changed`，不能靠它触发 `_on_changed`。

明确不改：`end_search` 仍清除高亮并把 `_last` 置空。不改 `build_search_pattern`，不改选项的保存，不改 `_install_pattern` 的编译失败回退（那是 r08-4）。

本地验证：`tests/test_search_pattern.py` 只覆盖 `build_search_pattern`。应新增断言：用假 VTE 先让非空输入走过 `_apply`，再 `end_search`，断言搜索正则被清掉且输入框文字还在；接着 `start_search`，断言再次 `search_set_regex` 或 `search_set_gregex`，且模式由当前文字和选项生成；此后 `next_search` 调用的是已装上模式的 `search_find_next`。输入框为空时重开，导航按钮不敏感，且不留下正则。

## r08-4 hold

问题类：查找词含非 ASCII，且按码点截断后的字节仍是合法 UTF-8 时，PCRE2 按截短后的词编译成功，输入框不标红，终端按更短的模式搜索。

不变量：交给 `Vte.Regex.new_for_search` 的长度是该模式的 UTF-8 字节数，或 `-1`（读到结尾）。用户输入要么整段参与编译，要么整段编译失败后走现有 GLib 回退；失败时输入框标红。不得把截短后仍合法的 UTF-8 当成成功模式。

要动的符号：`Searchbar._install_pattern`（约 233–244 行）。现在是 `Vte.Regex.new_for_search(pattern, len(pattern), flags)`。`len(pattern)` 是码点个数。本机 `Vte.Regex.new_for_search('café[', 5, FLAGS_PCRE2)` 能编译（5 字节正好是 `café`，末尾的 `[` 被切掉）；长度为 6 或 `-1` 时，因未闭合的字符类编译失败。`caféx` 是 5 个码点、6 个字节，前 5 个字节是 `café`。`regex.FLAGS_PCRE2` 在存在 `Vte.REGEX_FLAGS_DEFAULT` 时为真，成功即 `return True`，GLib 回退不会跑。

明确不改：`build_search_pattern`，GLib 回退的标志和 `search_set_gregex`，`_mark_entry`。不改 `terminatorlib/plugins/mousefree_url_handler.py` 里同样的 `len(self.searchtext)`。

本地验证：`tests/test_search_pattern.py` 没有安装路径。应新增断言：`_install_pattern` 对 `caféx` 调用 `new_for_search` 时，长度参数为 `len('caféx'.encode('utf-8'))` 或 `-1`，不是 `len('caféx')`。假的 `new_for_search` 记录参数即可。若用真 VTE，标志用带多行位的 `regex.FLAGS_PCRE2`，否则 `search_set_regex` 会因缺少多行编译标志被 VTE 拒绝。

## r08-5 hold

问题类：一秒内响铃超过一次时，较早的那次超时会在后一次还没满一秒时关掉铃图标；标题栏销毁后，铃的超时回调仍会去隐藏图标。

不变量：铃图标从最后一次 `icon_bell` 起显示约一秒。同一时刻只有一个待执行的隐藏超时。较早的超时不再把后一次的 `show` 抹掉。`_on_destroy` 之后 `icon_bell_hide` 不再执行。

要动的符号：

- `Titlebar.icon_bell`（约 1172–1175 行：每次 `GLib.timeout_add(1000, self.icon_bell_hide)`，不保存返回值，也不取消上一个）。保存这一次的 source id；若上一个还在，先 `GLib.source_remove`。
- `Titlebar.icon_bell_hide`（约 1177–1180 行：无条件 `hide`）。执行时先丢掉已保存的 id，再隐藏，并仍 `return False`。
- `Titlebar._on_destroy`（约 999–1006 行：只拆除 `_sizetext_timer` 和 `_collapse_idle`）。用同样方式拆除铃的 source，并清掉 id。

明确不改：`Terminal.on_bell` 里的紧急提示和可见闪烁，铃图标用哪个名字，超时长度 1000 毫秒，隐藏回调只跑一次。

本地验证：现无 `icon_bell` 测试。应新增断言：连续两次 `icon_bell` 只留下后一个 source id，前一个已被 `source_remove`；只让第一次的到期回调跑时图标仍可见，后一次到期才隐藏；`_on_destroy` 时铃的 source 被移除，销毁之后的隐藏回调不再执行。用记录 `timeout_add` / `source_remove` 的假 `GLib` 即可，不必真等一秒。
