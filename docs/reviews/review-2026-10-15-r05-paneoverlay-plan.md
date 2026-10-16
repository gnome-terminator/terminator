---
title: "r05 paneoverlay 方案"
type: plan
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "还原失败时先把终端挂回窗口树再清状态；表面捕获失败不再拿 VTE 图做飞行动画。"
---

# r05 paneoverlay 方案

保留两条，都在 `terminatorlib/paneoverlay.py`。`animprofile.py` 无保留项。

## 1. 还原换槽失败后终端不在窗口里

问题类：还原时终端已经离开框架，换不回原槽就只打日志，放大状态被清掉，占位符被销毁，终端留在控件树外。

不变量：

- 窗口还活着时，`_finish_restore` 返回前 `terminal.get_parent()` 不为空，且 `terminal.get_toplevel()` 是这个 `window`。
- `self.data = None`、`window` 的 `term_zoomed` 置回假、`placeholder.destroy()` 只发生在终端已经挂进该窗口之后。挂回失败则 `is_active()` 仍为真，占位符不销毁，终端留在窗口仍持有的控件里，同一次放大可以再还原。
- 占位符的父控件就是 overlay 时，仍然 `window.add(terminal)`（占位符已是布局根的那条路径）。
- 窗口正在销毁时同样要把终端放回树里，供 describe/close 使用；这条路径继续不 `grab_focus`、不按槽重算字号、不 `_resume_font`。

要动的符号：

- `OverlayController._finish_restore`。现在 `frame.set_terminal(None)` 先移出终端，`self.data = None` 写在 `_swap` 之前；`parent is None` 或 `_swap` 为假时只 `err(...)`，随后无条件 `placeholder.destroy()`。
- 换回失败时把终端挂进当前布局根（`data['main']`，以 `Gtk.Bin.get_child(overlay)` 为准）。窗口里已经放回这棵布局根时，不要再 `Gtk.Window.add(terminal)` 把根挤掉。
- `terminal._overlay_placeholder = None` 与成功挂回一起做。
- `OverlayController._swap`、`OverlayController.is_active` 的含义不变：失败就是 `_swap` 返回假，或占位符没有父控件。

明确不改：

- `Paned.swap_child`、`Notebook.swap_child` 的成功换槽。
- 放大期间布局根被换掉时改读 overlay 的 Bin 子控件（`main()` 与 `_finish_restore` 里的 `actual_main`）。
- `maximise`、`restore` 的动画与捕获，`maximise_when_ready`，`PanePlaceholder._on_draw`，字体暂停/恢复，`animprofile.py`。

本地验证：

- 已有：`tests/test_m37_smooth_maximise.py::test_restore_lands_on_current_slot`，`tests/test_m38_maximise_followups.py::test_reverse_mid_expand_unhides_terminal`，`tests/test_m23_ui_fixes.py::test_p0_root_replaced_under_overlay_without_guard`，`tests/test_m23_ui_fixes.py::test_p2_destroy_during_animation_cancels_tick`。还原成功后终端仍在该窗口里，占位符引用已清；根被替换后放大状态还在；销毁时动画停掉且 `data` 为空。
- 新增：占位符 `get_parent()` 为 `None`，或父控件没有 `swap_child`，或 `swap_child` 返回 `False` / 抛异常时，活窗口上终端的 `get_parent()` 不为空且 `get_toplevel()` 是该窗口；若这次没能挂回，则 `is_active()` 仍为真且占位符未被销毁。窗口已标记销毁时终端仍被放回树，且未 `grab_focus`。

## 2. 表面捕获失败后不再飞 VTE 图

问题类：表面快照失败后，放大仍可能把未做空白检测的 VTE 图当成飞行动画，并拉到整个终端矩形上。

不变量：

- `zoom_anim` 仅当 `capture_widget_surface(terminal)` 返回非空时为真。这张图覆盖整个 Terminal，飞行起点仍是 `_rect_from_widget(terminal, main)`。
- 表面捕获为 `None` 且本次要动画时，走现有 `fade_only`：`_run_animation(expand=True, reduced=True)`。`SnapshotArea` 不接收 `capture_terminal_pixbuf` 转成的表面。
- Wayland 上若还把 pixbuf 交给 `PanePlaceholder`，先 `pixbuf_to_surface`，再用现有 `surface_looks_blank`；判空白则占位符也不留这张图。非 Wayland 不把纯黑终端判成失败，纯黑 pixbuf 可以只留给占位符，仍然不飞。

要动的符号：

- `OverlayController.maximise` 里 `capture_widget_surface` 返回 `None` 之后，用 `capture_terminal_pixbuf` 和 `pixbuf_to_surface` 填 `snap`、再令 `zoom_anim = snap is not None` 的那一段。
- 空白判断复用 `_is_wayland`、`surface_looks_blank`、`pixbuf_to_surface`，不改这三者的阈值和采样。

明确不改：

- `capture_widget_surface` 在 Wayland 上把空白表面返回 `None`。
- `capture_terminal_pixbuf` 仍只抓 VTE（有 `terminal.vte` 时用它，否则用终端自身）。
- `restore()`：表面失败已经是 reduced 淡出，没有 pixbuf 升级。
- `PanePlaceholder._on_draw` 仍按捕获时的 `(sw, sh)` 画。
- 表面捕获成功时的飞行、`frame_hidden` 和交接。

本地验证：

- 已有：`tests/test_m38_maximise_followups.py::test_blank_wayland_capture_falls_back`，`tests/test_m38_maximise_followups.py::test_blank_snapshot_uses_fade_path`，`tests/test_m37_smooth_maximise.py::test_expand_hides_live_terminal_until_handover`。Wayland 空白表面仍是 `None`；两路捕获都空时 `snapshot` 为空且 `frame_hidden` 为假；表面捕获成功时仍然飞行。
- 新增：Wayland 下 `capture_widget_surface` 为 `None`、`capture_terminal_pixbuf` 返回非空 pixbuf（含纯黑）时，`maximise(animate=True)` 之后 `data['snapshot'] is None` 且 `data['frame_hidden']` 为假；纯黑 pixbuf 不进占位符。非 Wayland 上表面失败时 `snapshot` 仍为 `None`，纯黑 pixbuf 可以留在占位符。表面捕获成功时，飞行起点的宽高仍是整个 Terminal 的分配，而不是 VTE 的分配。
