---
title: "r05 paneoverlay 发现"
type: audit
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "恢复换槽失败会丢掉终端；Wayland 回退、会话放大等待、占位绘制和动画期字号也有用户可见错误。"
---

# r05 paneoverlay 发现

范围：`terminatorlib/paneoverlay.py`、`terminatorlib/animprofile.py`。以下 5 条。

## r05-1

- 严重度：高
- 症状：还原时若占位符已经不在可换回的父控件里，被放大的终端从窗口里消失，这次放大状态也不能再试一次。

```1672:1727:terminatorlib/paneoverlay.py
        frame.set_terminal(None)
        for extra in (frame, data.get('dim'), data.get('snapshot')):
            if extra is not None and extra.get_parent() is overlay:
                overlay.remove(extra)
        ...
        self.data = None
        window.set_property('term_zoomed', False)

        if root_terminal:
            terminal._overlay_placeholder = None
            window.add(terminal)
        else:
            if main is not None:
                Gtk.Window.add(window, main)
            parent = placeholder.get_parent()
            terminal._overlay_placeholder = None
            if parent is None or not self._swap(parent, placeholder,
                                                 terminal):
                err('overlay restore: placeholder slot lost; terminal %s '
                    'not re-parented' % terminal)
        terminal.show_all()
        placeholder.destroy()
```

`frame.set_terminal(None)` 已经把终端移出框架。随后只有 `root_terminal`（占位符的父控件就是 overlay）会 `window.add(terminal)`。另一条路径在 `parent is None` 或 `swap_child` 失败时只打日志，不把终端挂回窗口，接着 `placeholder.destroy()` 拆掉原槽，并且 `self.data` 已经是 `None`，`is_active()` 为假，不能再走还原。放大过程中布局根被替换是本文件自己写明要处理的情况（P0-1）；父控件不是 overlay、也不再提供 `swap_child` 时，这个窗格会离开控件树，按窗口子树保存布局时也不会再走到它。

方向：换回失败时把终端挂回当前窗口或布局根，未挂回之前不要销毁占位符，也不要先把控制器状态清掉。

## r05-2

- 严重度：中
- 症状：表面快照失败时，放大仍可能播放一块黑图，或把只有 VTE 区域的图拉成含标题栏的整块终端。

```237:243:terminatorlib/paneoverlay.py
        # m38: outside a draw cycle Wayland may hand back a stale/empty
        # backing store; a blank capture would flash black, so report
        # failure and let the caller take the fallback/fade path.
        if _is_wayland(widget) and surface_looks_blank(surf, w, h):
            dbg('capture_widget_surface: blank snapshot on Wayland')
            return None
```

```1225:1242:terminatorlib/paneoverlay.py
        snap = capture_widget_surface(terminal) if animate else None
        pixbuf = None
        if animate and snap is None:
            pixbuf = capture_terminal_pixbuf(terminal)
            if pixbuf is not None:
                vte = getattr(terminal, 'vte', None) or terminal
                snap = pixbuf_to_surface(pixbuf, vte,
                                         vte.get_allocated_width())
        zoom_anim = bool(animate) and snap is not None
        fade_only = bool(animate) and not zoom_anim
        ...
        src_rect = _rect_from_widget(terminal, main)
```

```321:324:terminatorlib/paneoverlay.py
    def capture_terminal_pixbuf(terminal):
        """Snapshot a terminal's VTE region. Never call terminal.draw(cr)."""
        try:
            widget = getattr(terminal, 'vte', None) or terminal
```

`capture_widget_surface` 在 Wayland 上判定空白后返回 `None`，注释要求调用方改走淡入。调用方随即用 `capture_terminal_pixbuf`（`pixbuf_get_from_window` / `_capture_scaled`）再抓一次，且不再做 `surface_looks_blank`。这次只要返回非空 pixbuf，`zoom_anim` 就为真，空白图会当成飞行动画播出去。该 pixbuf 只覆盖 VTE，逻辑宽度也取 VTE 的分配宽度，飞行矩形却用整个 Terminal 的 `src_rect`（含标题栏），画面被拉高。

方向：表面捕获已判失败时走淡入；若仍使用 pixbuf，先做同样的空白检测，并按它实际覆盖的控件矩形来飞。

## r05-3

- 严重度：中
- 症状：会话里标记为放大的窗格会静默不再放大。

```1383:1410:terminatorlib/paneoverlay.py
        def _attempt():
            if state['done']:
                return False
            if getattr(window, 'isDestroyed', False) or \
                    terminal.get_toplevel() is not window:
                _finish()
                return False
            alloc = window.get_allocation()
            if not window.get_mapped() or alloc.width <= 1 or \
                    alloc.height <= 1:
                return False  # wait for size-allocate
            _finish()
            ...
        def _on_alloc(_w, _a):
            if not state['done']:
                GLib.idle_add(_attempt)

        state['hid'] = window.connect('size-allocate', _on_alloc)
        GLib.idle_add(_attempt)
```

`_finish()` 会拆掉 `size-allocate`。终端尚未挂进该窗口时，`get_toplevel()` 不是这个 window（未挂父控件时就是它自己），第一次 idle 就永久结束，之后就算挂进窗口并完成分配也不会再试。另一支：窗口已有尺寸但还没 map 时，idle 返回 `False`，这次等待被 GLib 拿掉；注释写的是等下一次 `size-allocate`，函数却没有在 map 上重新排队。只 map、不再分配时，放大不会发生。

方向：还没挂进窗口、还没 map、或尺寸尚未可用时保持等待，map 与分配都要能再次触发尝试。

## r05-4

- 严重度：中
- 症状：放大期间原槽位尺寸一变，槽里留下的残影仍是截图当时的宽高，不铺满新槽，缩小后则被裁切。

```573:590:terminatorlib/paneoverlay.py
    def _on_draw(self, widget, cr):
        """Paint cached pixbuf or solid background. NEVER terminal.draw(cr)."""
        alloc = widget.get_allocation()
        if not _window_is_rgba(widget):
            cr.set_source_rgb(0.08, 0.08, 0.08)
            cr.rectangle(0, 0, alloc.width, alloc.height)
            cr.fill()
        ...
        if self._snap is not None:
            try:
                _surf, sw, sh = self._snap
                paint_snapshot(cr, self._snap, (0, 0, sw, sh), 0.35)
```

底色按当前分配铺满，快照却画在捕获时的 `(sw, sh)` 上。`sw, sh` 来自放大开始时的表面或 pixbuf，绘制路径没有再用占位符此刻的宽高。窗口或分割条在放大期间改变槽位后，遮罩边缘和未被最大化框完全挡住的部分会看到错位残影；非透明窗口上其余区域是一块 `0.08` 灰底。

方向：占位符绘制矩形改用当前分配宽高。

## r05-5

- 严重度：低
- 症状：放大动画过程中窗口尺寸变了，到达后自动字号仍按动画开始时的终点矩形。

```1250:1315:terminatorlib/paneoverlay.py
        self._pause_font(terminal)
        ...
        self._apply_tier_for_rect(terminal, dst_rect, FRAME_CHROME_PX)
```

```1074:1079:terminatorlib/paneoverlay.py
        data['dst_rect'] = (float(left), float(top),
                            max(1.0, width - left - right),
                            max(1.0, height - top - bottom))
        rtl = self._widget_rtl(data.get('frame') or data.get('overlay'))
        self._set_margins(data.get('frame'),
                          *margins_from_physical(rtl, left, right, top, bottom))
```

```1634:1635:terminatorlib/paneoverlay.py
        terminal = data['terminal']
        self._resume_font(terminal)
```

字号只在放大开始时按当时的 `dst_rect` 设一次，然后 `_pause_font` 一直冻到到达。动画期间 `_apply_chrome_geometry` 会随 overlay 分配改写 `dst_rect` 和框架边距，从而改变终端的实际像素尺寸，但不会再调用 `_apply_tier_for_rect`。`_arrive_maximised` 只 `_resume_font`，没有按最终分配再算一档。动画配置可以长于默认的 200ms，看门狗也要等 0.6 秒无帧才结束，这段时间里改变窗口大小后，自动字号会停在旧终点上。

方向：终点矩形变化后重新套用字号，或在到达时按最终分配再算一次。
