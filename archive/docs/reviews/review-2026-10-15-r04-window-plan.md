---
title: "r04 window 方案"
type: plan
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "保留分组名与翻译对齐，并把模糊 hint 收成只看本窗口正在用的 profile；关终端、覆盖层分屏、几何提示三处不改。"
---

# r04 window 方案

核对范围是 `terminatorlib/window.py` 的活码。发现稿里的五段引用与磁盘行号一致。下面只给仍要改的项写改法。

## 核对

- r04-1 drop。`Window.closeterm` 里 `leave_zoom(..., legacy=False)` 确实不会恢复 legacy zoom。紧接着的 `Container.closeterm`（`container.py` 约 181–190 行）在 `term_zoomed` 仍为真时用默认参数再调 `leave_zoom`，`legacy=True`，会走到 `Window.unzoom` → `_legacy_unzoom`，先把 `zoom_data['old_child']` 装回窗口，再 `widget.close()`。`close()` 发出 `close-term` 时，窗口侧信号已在 `remove` 里拆掉，原父控件在 `add` 里接上自己的 `wrapcloseterm`，只会拆掉这一个终端。恢复之后 `get_child()` 不是空的，`hoover()` 不会 `emit('destroy')`。发现稿说的「销毁流程把其余窗格逐个关掉」这条链走不通。
- r04-2 drop。`OverlayController.maximise`（`paneoverlay.py` 1312 行）会 `set_property('term_zoomed', True)`。覆盖层打开时 `is_zoomed()` 为真。`split_axis`、`tab_new`、`rotate`、`tab_change`、`move_tab`、`detach_tab_to_new_window` 都先 `leave_zoom`。默认 `overlay=True`，`overlay_restore(animate=False)` 同步走 `_finish_restore`，终端回到原父控件之后才分屏或改标签。不会在 `is_zoomed()` 为假时用 `Window.remove` / `Window.add` 把新 paned 记成布局根。
- r04-3 drop。`set_rough_geometry_hints` 循环里调用的是终端对象的 `get_allocation`。`Terminal.get_allocation`（`terminal.py` 3340–3347 行）用 `translate_coordinates(self.get_toplevel(), 0, 0)` 改写 `x`、`y`。水平分割后，右侧终端相对窗口的 `x` 不是 0，不会和左侧一起进入 `row_sum`。发现稿说的「paned 每个子控件原点都是 (0, 0)，左右两边双计」不成立。
- r04-4 hold。见下。
- r04-5 weaken。全 profile 扫描成立；「KDE 不会按整窗模糊」不成立。见下。

## r04-4 分组名与切换

问题类：非英语界面下，全部分组和标签分组再次触发不会取消，窗口分组的名字一直是英文。

不变量：

- 创建组名与再次切换时的比较，使用同一次 gettext 的结果。
- 带占位符的组名先翻译格式串，再把数字填进去。gettext 看到的 msgid 是 `Window group %s`、`Tab %d`、`All`。
- 英语下组名仍是 `All`、`Tab N`、`Window group N`，再次触发仍会取消。
- 标签组的数字可以在译文字面的前面或后面。只有形状与翻译后的 `Tab %d` 一致的组名才算标签组。

要动的符号：

- `Window.group_all_toggle`：与 `_('All')` 比较，再决定 `ungroup_all` 还是 `group_all`。
- `Window.group_tab_toggle`：用 `_('Tab %d')` 的翻译结果当模板，匹配数字两侧的文字。去掉 `widget.group[:4] == 'Tab '`。
- `Window.group_win`：`_('Window group %s') % (len(self.terminator.groups) + 1)`。

不改：

- `group_all`、`group_tab` 的组名生成（这两处已经是先 gettext 再使用）。
- `ungroup_all`、`ungroup_tab`、`ungroup_win`、`set_groups`、`Terminator.create_group`。
- `group_win_toggle`。它按「当前有没有任何组」切换，不看组名。
- `po/`。`zh_CN.po` 里已有 `All` → `全部`、`Tab %d` → `标签 %d`、`Window group %s` → `窗口组 %s`。

验证：现有测试没有覆盖这三条。`tests/test_m23_ui_fixes.py` 里那条「源码不含 group-all-toggle 键」保持不动。新增断言：

- 把 `terminatorlib.window._` 换成返回 `全部` 的替身。`widget.group == '全部'` 时 `group_all_toggle` 走取消，不再 `create_group`。`widget.group == 'All'` 时不走取消。
- `_('Tab %d')` 返回 `标签 %d` 时，组名 `标签 2` 会取消，组名 `Tab 2` 不会。`_('Tab %d')` 返回 `%d 号标签` 时，组名 `3 号标签` 会取消，组名 `全部` 不会。
- `group_win` 调用 gettext 时 msgid 是 `Window group %s`，交给 `create_group` 的是插值后的译文。

## r04-5 模糊 hint

问题类：窗口的 KDE 模糊 hint 由配置里任意 profile 决定，并且写入时用 4 字节缓冲区配 format 32 的 1 个元素。

降级依据：整窗模糊这件事，当前这种 1 个 CARDINAL 的属性在 KWin 里会被当成整窗。Plasma 5.27 的 `BlurEffect::updateBlurRegion` 在属性已设置但长度不是 4 个 `uint32_t` 的倍数时留下空 region，`blurRegion()` 写明空 region 表示整窗模糊。当前 KWin master 的同一函数把 cardinal 个数为 0 或 1 直接当成整窗模糊。小端上这 4 个 0 字节送出的 CARD32 是 0。因此「合成器不会按整窗模糊」不作为改法的验收。

仍要改的两点：

- `on_window_realize` 遍历 `self.config.base.profiles` 的全部值。别的 profile 同时开了 `background_blur` 且 `background_type` 为 `transparent` 或 `image` 时，这个窗口也会 `set_blur_behind(True)`，与本窗口终端的 profile 无关。
- `set_blur_behind` 在 enable 时用 `(ctypes.c_ubyte * 4)` 和 `nelements=1`、format 32。format 32 按 `long` 读，64 位上每个元素 8 字节，缓冲区只有 4 字节。

不变量：

- 只有本窗口 `get_terminals()` 里某个终端的 profile 同时满足 `background_blur` 为真、且 `background_type` 属于 `transparent` 或 `image`，才设置 hint。纯色 profile 不设。配置里没有任何终端在用的 profile 不参与。
- 窗口上还没有终端时不设 hint。
- 整窗模糊写成空属性：format 32、元素个数 0。不要再传 4 字节数组和元素个数 1。若改成矩形，则用 4 的倍数个 `long`，长度与元素个数一致。
- 配置重载后各窗口仍按自己的终端重算。不能先合成一个全局布尔再写到每个窗口上。

要动的符号或文件：

- `Window.on_window_realize`：判断收成窗口上的一个方法（名字由实现自定），realize 时调用。profile 字典仍用 `config.base.profiles`，键来自本窗口终端的 `get_profile()`。
- `Window.set_blur_behind`：enable 分支改成空属性，或完整的 `long` 矩形。非 X11、窗口尚未 realize 时仍直接返回。
- `Terminator.reconfigure`（`terminator.py` 约 907–915 行）有同一段「任一 profile 则为真，再写到每个窗口」。realize 的修正会在重配置时被这句盖掉，所以这里改成对每个窗口调用上面的窗口方法。除此之外不改 `reconfigure`。
- 终端切换 profile 只走 `Terminal.set_profile` → `Terminal.reconfigure`，不会调用 `set_blur_behind`。同一不变量要求：这个终端 reconfigure 结束时，让它所属窗口重算一次 hint。不要改 profile 切换的其它行为。

不改：

- `prefseditor.py` 的 `background_blur` 开关，以及 `config.py` 里该键的默认值 `False`。
- `background_type` 为 `solid` 时不模糊这一条件。
- `_set_theme_variant_x11` 和 `_GTK_THEME_VARIANT`。
- Wayland 路径（`display_manager() != 'X11'` 时保持返回）。
- 缩放、分屏、几何提示、分组。

验证：仓库里没有 `set_blur_behind` 或 `background_blur` 的测试。新增断言，不需要真的 X 服务器：

- 配置里有两个 profile。本窗口终端只用纯色、未开模糊的那个。另一个开了模糊且背景为 `transparent`。窗口方法的结果为假，不调用启用分支。
- 本窗口终端的 profile 开了模糊且背景为 `transparent` 或 `image` 时结果为真。开了模糊但背景为 `solid` 时为假。
- 窗口没有终端时结果为假。
- enable 时 `XChangeProperty` 的元素个数是 0，或者是 4 的倍数且缓冲区按 `long` 元素分配。元素个数不是 1，缓冲区也不是 4 个 `c_ubyte`。
- `Terminator.reconfigure` 对每个窗口分别取上述结果，不再用一个全局 `should_blur` 写完全部窗口。
