---
title: "r02 prefseditor 方案"
type: plan
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "五条均保留：布局 profile 下标写错、调色板重复连接、缺失布局名中断填表、快捷键搜索滞后、配色色块与方案脱节。"
---

# r02 prefseditor 方案

核对结论：hold 5，weaken 0，drop 0。发现稿引用的行为与磁盘活码一致；个别行号有偏移，下面锚点以活码为准。drop 无。本方案只描述改法，不附可合入补丁。

生产改动只落在 `terminatorlib/prefseditor.py`。`terminatorlib/preferences.glade` 本路不改。

## r02-1 hold

问题类：增删 profile 后布局里的 profile 下拉只追加不清空，点终端时用新下标套旧行，`changed` 把错误名字写回布局并保存。

不变量：

- `layout_profile_chooser` 的条目与 `config.list_profiles()` 排序后一一对应，没有上一轮留下的前缀。
- 点选类型为 Terminal、且已保存 profile 的布局项时，下拉显示的文本等于该项里的 profile，这次点选不把该项改成另一个名字。
- 重建下拉的过程（清空、追加、程序化 `set_active`）不把 `layout[item]['profile']` 写成 `None` 或过渡项。`GtkComboBoxText` 清空当前行时会发 `changed`，而 `LayoutEditor.on_layout_profile_chooser_changed` 在 `layout_item` 已设置时会无条件 `get_active_text()` 并 `save()`。

要动的符号：

- `LayoutEditor.update_profiles`（现于约 2663 行：重建两个下标字典后只 `append_text`）。
- `LayoutEditor.set_layout_item`（约 2740 行：用 `profile_profile_to_ids` 的下标 `set_active`）。
- `LayoutEditor.on_layout_profile_chooser_changed`（约 2750 行）。程序化刷新期间跳过写入，或暂时断开 `changed`；用户改选时才按当前条目文本写入。选中按 profile 名字对齐条目。

`PrefsEditor.on_layout_profile_chooser_changed`（约 2408 行）只转发到 `LayoutEditor`，glade 第 4561 行的 `changed` 接的是这个转发。转发关系保持。调用点在 `addprofile`（约 2100 行，添加成功与否之后都会调用）和 `on_profileremovebutton_clicked`（约 2123 行）。克隆走 `addprofile`，同一条刷新路径覆盖。

明确不改：`add_profile` / `del_profile` 的配置内容，profile 列表树，布局树的结构和命令、工作目录字段，glade 信号名。`on_profile_name_edited` 今天不刷新这个下拉，本项不做重命名同步。布局项缺少 `profile` 或名字为空时仍走现有的 `set_active(0)` 分支。

本地验证：现无测试覆盖 `update_profiles`。`tests/test_m26_prefs_layout.py` 会构造 `PrefsEditor`，但不碰布局 profile 下拉。应新增断言：连续两次 `update_profiles` 后，组合框模型行数等于 profile 数，且文本集合与排序后的 `list_profiles()` 相同；对已保存某个 profile 的终端调用 `set_layout_item` 后，`get_active_text()` 等于该名字，布局配置里的 profile 字符串与调用前相同。

## r02-2 hold

问题类：每换一次 profile，`set_profile_values` 都再 `connect` 一次调色板 `button-press-event`，一次点击按连接次数串行跑 `dialog.run()`。

不变量：每个 `palette_colorpicker_*` 在这个偏好窗口里只有一个 `button-press-event` 处理函数。点一次只进入一次 `edit_palette_button`。

要动的符号：`PrefsEditor.set_profile_values` 里约 921–926 行的循环。点击连接挪到 `PrefsEditor.__init__` 在 `add_from_string` 之后做一次，或在循环里跳过已经接过的色块。`on_profile_selection_changed`（约 2332 行）继续只负责调用 `set_profile_values` 加载颜色。打开窗口时 `select_iter` 会进来一次，之后每次换 profile 再进来，所以不能把 `connect` 留在这条加载路径上。

明确不改：`edit_palette_button` 的取色、确认保存、取消回滚；`on_palette_colorpicker_draw`、`load_palette`、`on_palette_combobox_changed`。glade 里这些色块只有 `draw`（`palette_colorpicker_1` 起，全文件里 `button-press-event` 只有前景/背景两处），保持由代码接点击。

本地验证：现无测试。应新增断言：连续两次 `set_profile_values` 之后，`palette_colorpicker_1` 上 `button-press-event` 的处理函数数量为 1；把 `edit_palette_button` 换成计数桩，再发一次该信号，计数为 1。

## r02-3 hold

问题类：当前布局名不在布局列表里（会话恢复后就是 `__last_session__`）时，`set_values` 在高亮那一行 `KeyError`，快捷键和插件两页不再填充。

不变量：`Terminator.layoutname` 为空、为 `__internal_json_layout__`、为 `__last_session__`，或其它不在 `layoutiters` 的名字时，`set_values` 不抛。布局列表选中 `default`。快捷键模型和插件列表仍被填上。`default` 也不在 `layoutiters` 时不下标，改为不选中或选中第一行。

要动的符号：`PrefsEditor.set_values` 里约 667–672 行。现在只把 `__internal_json_layout__` 排除，然后 `self.layoutiters[layout_to_highlight]`。`__last_session__` 在约 656–657 行从本地列表去掉，因此不在 `layoutiters` 里。`config.list_layouts()` 本身也会滤掉这两个名字，本地 `remove` 是重复过滤；高亮失败来自下标，不是来自少写一次 `remove`。

抛出点在快捷键填充（约 678 行）和插件填充（约 743 行）之前。`PrefsEditor.__init__` 约 321–326 行用 try 包住整个 `set_values`，异常只记日志，窗口仍打开。`Terminator.create_layout` 会把传入的布局名记到 `layoutname`，会话布局名是 `__last_session__`。

明确不改：布局列表继续不展示 `__last_session__` 和 `__internal_json_layout__`。不改 `list_layouts` 的过滤，不改 `create_layout` 对 `layoutname` 的赋值，不改 321–326 行的 try/except。

本地验证：`tests/test_m21_session_roundtrip.py` 会 `create_layout(SESSION_LAYOUT_NAME)` 并注释偏好稍后会高亮它，但不断言偏好页填完。应新增断言：构造 `PrefsEditor` 之前把 `Terminator().layoutname` 设为 `__last_session__`，构造完成后快捷键 liststore 行数大于 0，插件列表已完成填充，`layoutlist` 当前选中为 `default`。测完恢复 Borg 上的 `layoutname`。

## r02-4 hold

问题类：快捷键搜索在按键默认处理之前读 `get_text()`，并且长度不在 `[2, 10)` 时不 `refilter`，输入、退格和粘贴都比框里的字慢一拍，大约 10 个字符后列表不再变。

不变量：过滤串等于 `keybindingsearchentry` 当时的全文。长度为 0、1 以及大于等于 10 时，在文本已经改变之后都 `refilter`。可见行对应该全文。

要动的符号：`PrefsEditor.set_values` 里嵌套的 `on_search`、`on_search_refilter`（约 704–718 行），以及接到 `keybindingsearchentry` 的 `key-press-event` 和 `backspace`。`filter_visible`（约 694–696 行）读的是 `keybind_filter_str`。改为在 `GtkEntry` 的 `changed` 上取 `get_text()` 并总是 `refilter`。去掉 `MAX_SEARCH_LEN` 对刷新的跳过。

`key-press-event` 和 `backspace` 都在默认处理之前发出：字符还没插入，退格也还没删掉。`on_search_refilter` 自己不更新过滤串，只用上一拍留下的字符串再滤一次。glade 里该输入框（约 4930 行）没有信号，连接全在这段代码里。

明确不改：`filter_visible` 的匹配范围（动作名、按键、描述，以及禁用项显示成 `Disabled`）。不改 `on_cellrenderer_accel_edited` / `on_cellrenderer_accel_cleared`。不改 glade 里这个输入框。

本地验证：`tests/test_prefseditor_keybindings.py` 只覆盖快捷键冲突对话框和 accel 编辑。应新增断言：写入 1 个字符后可见集按这 1 个字符过滤；文本长度到 10 以及更长时可见集继续随全文变化；把文本缩短后用的是缩短后的全文；一次 `set_text` 写入多字符后立即按全文过滤。

## r02-5 hold

问题类：内置方案会把前景/背景色块重新设为可点；色块是 `DrawingArea`，换方案时不 `queue_draw`，连续切换仍画着上一套颜色；点色只改配置里的颜色，方案下拉停在内置项上。勾着系统主题色时，方案下标相对 glade 初始值有变化，色块又被放开。

不变量：

- `foreground_colorbutton` 与 `background_colorbutton` 可点击，当且仅当方案是 `custom` 且「使用系统主题颜色」未勾选。
- 方案切换把前景/背景写入配置之后，两个色块都重绘。连续两次换成不同内置方案时，色块显示后一次的颜色。
- 用户通过色块得到的颜色对不上当前内置方案时，下拉停在 `custom`（`colorschemevalues['custom']` 为 12）。切到 `custom` 时不用内置色覆盖刚写入的前景/背景。取消颜色对话框时，颜色和方案下标都回到打开前，并重绘。
- 勾着系统主题色时，方案下标变或不变，两个色块都保持不可点。

要动的符号：

- `PrefsEditor.on_color_scheme_combobox_changed`（约 2450–2464 行）：现在无条件 `set_sensitive(True)`，写入颜色后只 `reconfigure()`，没有 `queue_draw`。已敏感时 `set_sensitive(True)` 不会再触发重绘。
- `PrefsEditor.set_profile_values` 约 891–907 行：先按 `scheme == 'custom'` 设敏感度，再 `set_active`。glade 里 `color_scheme_combobox` 的 `active` 为 11（`deep_teal`，约 2821–2822 行），`changed` 接到上述回调。下标未变时 `changed` 不发出，前半段的敏感度会留下。两处用同一条件：是否 `custom`，以及 `use_theme_colors_checkbutton` 是否勾选。
- `on_foreground_colorbutton_click`、`on_background_colorbutton_click`，以及它们的 `notify::rgba` 回调（约 1422–1470 行）。颜色与当前内置方案不一致时把下拉设为 `custom`。取消路径在恢复颜色之外恢复方案下标。
- 与 `on_use_theme_colors_checkbutton_toggled`（约 2466 行）对齐：勾选时它会关掉方案框和两个色块；方案回调不得再把色块设回可点。加载顺序是约 869 行先 `set_active` 主题色勾选，约 907 行再 `set_active` 方案。

色块的 `draw`（约 1411–1420 行、1442–1450 行）从 `self.config` 读色。重绘靠 `queue_draw`，靠 `reconfigure()` 更新不了这两个 `DrawingArea`。

明确不改：`colourschemes` / `colorschemevalues`（`deep_teal` 仍是 11，`custom` 仍是 12）。不改 glade 的 `active=11`，以及已有的 `changed`、`draw`、`button-press-event`。不改调色板色块（那是 r02-2）。不改 `draw` 函数的铺色方式。不改终端如何跟随系统主题。

本地验证：现无测试覆盖方案下拉与这两个色块。应新增断言：从 `deep_teal` 改到另一内置方案再改到第三个时，两个色块不敏感，且第二次切换后配置颜色等于后一个方案，两个色块都已 `queue_draw`（或测试里跑一次 `draw` 读到后一个方案的颜色）；`use_theme_colors` 为真且方案下标不是 11 时两个色块不敏感；方案已是 `custom`、主题色仍勾着、再次 `set_profile_values` 时色块仍不敏感；未勾主题色且方案为 `custom` 时色块敏感，把前景改成对不上内置方案的颜色后，组合框活动项为 `custom`，配置前景仍是新颜色；颜色对话框取消后，前景、背景和方案下标与打开前一致。
