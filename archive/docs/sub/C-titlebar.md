# 子方案 C：Wave 风格分屏标题栏（技术实现路径）

> 总方案：[`../session-restore-design.md`](../session-restore-design.md) §C、§1A.6、决策 D13/D15/D17/D20。  
> 代码基线：`TIIEHenry/terminator` @ `9f2d0b6`。文中 `file:line` 均基于该提交。  
> **里程碑：M2**，估计 **2.5–3 人日**（v2 修订；原 1.5–2 天未计入跨模块接口与徽标）。  
> 只写技术实现路径，不改业务代码。  
> **修订记录**：v2 按三路审查与父级裁决；**v2.1** 按 `docs/reviews/findings-summary.md` 补漏，见 §12。

---

## 0. 范围与验收

### 0.1 做

| ID | 能力 | 对齐 |
|---|---|---|
| C-UI | 左：终端图标 + 现有分组区 + 标题；右：[徽标] 齿轮 / 最大化 / 关闭（命中区 24×24，标准密度） | C.1、D20 |
| C-RMB | 标题栏右键：**经 `Terminal.popup_menu`**（新参数）弹出与 VTE 右键相同的菜单；先聚焦；传真实 event；`skip_link_check=True`；`button==3` **必须 `return True`** | C.2、U5 |
| C-GEAR | 齿轮：同样经 `Terminal.popup_menu(..., anchor=btn)` → `popup_at_widget` | C.2 |
| C-MAX | 最大化按钮：M3 前走旧 `maximise`/`unzoom`；图标由 Window 信号 `pane-maximise-changed` 驱动；敏感度用 `has_multiple_terms`（**当前 tab 可见终端**） | C.2、C.3 |
| C-CLOSE | ✕ → **`close_confirm.request_close_terminal(terminal)`**（A 提供，内含 D17）；间距 6px；悬停红色 | D17 |
| C-D15 | 双击标题栏切换最大化；EditableLabel 不再双击编辑；编辑 → 菜单「编辑标题」+ 现有 `Ctrl+Alt+X`，F2 可选 | D15 |
| C-FOCUS | 焦点分屏 1px `pane_accent_color`（`#3fb950`）；**窗口失焦时清除**；与 D 浮层不出现双框 | D13 |
| C-BADGE | 创建徽标控件 + 统一 API `Titlebar.set_scale_badge(scale, locked)`；E 负责挂 popover | E 接口 |
| C-LOCK | 右键菜单新增「锁定此终端字号」（E 的钩子，E 不在时隐藏） | E 接口 |
| C-COLLAPSE | 窄宽折叠：尺寸文字 → 分组名 → 徽标 → 标题省略；三按钮始终保留 | C.1 |
| C-SIZE | 不再常驻 `80x24`：仅 resize 后约 1s；尊重 `title_hide_sizetext` | C.1 |
| C-A11Y | `accessible-name` + 带快捷键 tooltip | C.2 |
| C-DND | 标题栏仍为 DnD 源；按钮停止冒泡 | C.3 |

### 0.2 不做

| 事项 | 归属 |
|---|---|
| 浮层 / Overlay / 动画 / 占位 | **D（M3）**；M2 走旧 reparent zoom |
| `pane-maximise-changed` / `is_maximised_pane` 的**语义定义** | **D**；C 只消费（M2 先于 M3 时 C 落最小垫片，见 §2.4） |
| 进程探测、D17 对话框 | **A**（`close_confirm.py`） |
| 档位计算、popover 内容、锁定状态机 | **E**（`set_auto_font_locked` 等） |
| `titlebar_always_show` | 已否决 |
| 右键「下次启动不恢复」等会话菜单项 | **不归 C**（findings 未归属；若做由 A 在会话菜单改动里加，或 `terminal_menu` 插件） |

### 0.3 验收

1. tmux `mouse on`：标题栏右键弹出 Terminator 菜单；菜单打开期间 quake/hide-on-lose-focus 窗口不被隐藏（`preventHide` 已设）。
2. 齿轮菜单贴在按钮下沿；Enter/Space 可打开。
3. 当前 tab 可见终端 ≥2 时最大化可用；单终端或「当前 tab 只有一个终端（其他 tab 有终端）」时置灰；放大后图标/tooltip 切为「还原分屏」。
4. ✕：有非 shell 后代进程时只弹**一个**对话框，默认焦点「取消」；无进程时走 `ask_before_closing`。
5. 双击标题 → 切换最大化；菜单「编辑标题」与 `Ctrl+Alt+X` 可编辑。
6. 同一时间最多一个绿框；窗口失焦时绿框消失；浮层放大时只有 D 的 2px 框，没有叠加的 1px 框。
7. 拖标题仍可 DnD；点按钮不会拖出终端。

---

## 1. 现状代码地图

### 1.1 控件树（改前）

```
Terminal (Gtk.VBox)                         terminal.py:150–194
 ├─ Titlebar (Gtk.EventBox)                 titlebar.py:17（title_at_bottom 时在下方，terminal.py:187-192）
 │   └─ HBox                                titlebar.py:85–91
 │       ├─ ebox → grouphbox(groupicon, grouplabel, groupentry)   :50–78, :86
 │       ├─ VSeparator                      :87
 │       ├─ Viewport → EditableLabel        :82–88
 │       └─ bellicon (pack_end)             :89
 ├─ terminalbox (VTE + scrollbar)
 └─ searchbar (pack_end)
```

| 钩子 | 位置 | 现状 |
|---|---|---|
| 构造 | `Titlebar.__init__` `titlebar.py:40-96` | 无按钮 |
| 点击 | `button-press-event` → `on_clicked` `:96, :237-241` | 任意键都 `emit('clicked')`；不处理右键；仓库内**没有任何地方 connect `clicked`** |
| 分组区 | `connect_icon` `:98-100` → `Terminal.on_group_button_press` `terminal.py:1018-1063` | 只处理 button 1，其余 `return False` 冒泡 |
| 可见性 | `get_desired_visibility` `:196-204` | 编辑中/有分组时强制显示，否则读 profile `show_titlebar`（`config.py:244`，默认 True） |
| 尺寸文字 | `update` `:109-113`；`update_terminal_size` `:215-218` | `title_hide_sizetext=False` 时常驻 |

### 1.2 EditableLabel（D15 冲突源）

- `editablelabel.py:91-99`：左键 `_2BUTTON_PRESS` → `edit()`，`return True`。
- 编辑快捷键 `edit_terminal_title` 默认 `<Control><Alt>x`（`config.py:208`）→ `terminal.py:2278-2279`。

### 1.3 弹出菜单（现状，已更正）

- 入口 `Terminal.popup_menu` `terminal.py:1213-1218`：**先设 `window.preventHide = True`**，再 `TerminalPopupMenu(self).show(widget, event)`。标题栏若绕过它直接 new `TerminalPopupMenu`，会漏掉 `preventHide`。
- `TerminalPopupMenu.show` `terminal_popup_menu.py:104-407`：
  - `:116-136` 有 event 时对 **VTE** 做 `hyperlink_check_event`/`match_check_event`：标题栏坐标不属于 VTE，会误判 URL。
  - `:124` 用了 `re.search`，但文件**没有 `import re`**；NameError 被 `except Exception` 吞掉 → 插件 URL tag 匹配一直不生效。顺手修（加 `import re`），单独一个提交。
  - `:405` `popup_at_pointer(None)`。
- **最大化菜单项（更正）**：
  - `:278` `if not terminal.is_zoomed():` 分支 → 显示「_Zoom terminal」(`:281`) 与「Ma_ximize terminal」(`:286`)，两者敏感度都用 `:279` `sensitive = not terminal.get_toplevel() == terminal.get_parent()`，含义是"终端直接挂在 Window 下（整窗只有一个终端、无 tab）时置灰"。
  - `:292-295` `else`（已放大）分支 → 只显示「_Restore all terminals」→ `terminal.unzoom`。
  - 所以 `:279` 的问题**不在放大态**，而在未放大态：① 只有一个终端但处于 Notebook 的某个 tab（父是 Notebook）时**误亮**；② M3 Overlay 后父控件关系变化同样会误判。改为 `has_multiple_terms()`（§2.2）。
- 关闭 `close_terminal` `:87-102`：向上找 `construct_confirm_close` 后 `terminal.close()`。A 将其改为调用 `request_close_terminal`。

### 1.4 DnD

`terminal.py:497-500`：`(self.titlebar, BUTTON1_MASK)` 整条标题栏是 MOVE 拖源；`:506-509` 连接 drag-begin/data-get。

### 1.5 最大化 / 关闭路径

| 动作 | 路径 |
|---|---|
| 最大化 | `Terminal.maximise` `terminal.py:1637-1639` → 信号 → `Window.zoom(widget, False)` `window.py:690-719` |
| 还原 | `Terminal.unzoom` → `Window.unzoom` `window.py:721-745` |
| 切换 | `key_toggle_zoom` `terminal.py:2125-2129`（`<Shift><Control>x`） |
| 关终端 | 菜单 `close_terminal`；快捷键 `key_close_term` `terminal.py:2101` 直接 `close()`（A 修） |

### 1.6 焦点与 CSS

- `Terminal` 发出 `focus-in` → `Terminator.focus_changed`（`terminal.py:136`；`terminator.py:629-632`）。
- VTE `focus-in-event`/`focus-out-event`：`terminal.py:524-525`，处理在 `:1509-1530`；窗口失焦 → `Terminal.on_window_focus_out` `:1532-1534`（由 Window 的 focus-out 处理调用）。
- CSS：`Terminator.reconfigure` `terminator.py:368-494` 汇总 `self.style_providers`，`:490-494` 统一 `add_provider_for_screen`。

---

## 2. 设计：签名与钩子

### 2.1 控件树（改后）

```
Titlebar (EventBox)  class: titlebar-density-{standard|compact}
 └─ HBox
     ├─ termicon (Image 'utilities-terminal-symbolic', MENU)   pack_start 最左（新增）
     ├─ ebox → grouphbox（不变）
     ├─ VSeparator
     ├─ Viewport → EditableLabel(double_click_edit=False)
     │   pack_end 顺序（先 pack 的更靠右）：
     ├─ btn_close   class titlebar-btn titlebar-btn-close     ← 最右
     ├─ btn_max     class titlebar-btn
     ├─ btn_gear    class titlebar-btn
     ├─ scale_badge (Gtk.Button relief=NONE, class titlebar-badge; no_show_all)  ← C 创建，E 挂 popover
     └─ bellicon
```

### 2.2 `Window.has_multiple_terms()`（父级裁决：只计当前 tab 可见终端）

```python
# window.py，紧邻 is_zoomed (:681)
def has_multiple_terms(self):
    """当前可见 tab 内是否有 >1 个终端（不计其他 tab）。"""
    return len(self.get_visible_terminals()) > 1   # window.py:790-814
```

- `get_visible_terminals` 遇到 Notebook 时只取当前页（`window.py:803-805`），正好满足"当前 tab"。
- **与 A 的 `scope_terminals` 区分**：跨模块审查写过 `has_multiple_terms = len(scope_terminals)>1`，那是**关窗/关终端确认**的计数范围（含旧 zoom 的 `old_child` 等）。本方法专供标题栏/菜单「最大化此分屏」敏感度，**只数当前 tab 可见终端**（父级裁决 + code-accuracy P1）。二者不要混用同一实现。
- **旧 zoom 态**：Window 的子控件就是被放大的终端，返回 1 → 按钮敏感度必须是 `window.is_maximised_pane(term) or window.has_multiple_terms()`（放大态仍可点「还原」）。
- **M3 依赖**：Overlay 后 `get_visible_terminals` 必须同时计入占位与浮层终端（D 的 P0 遍历）。C 文档把它列为对 D 的接口要求。
- 菜单 `terminal_popup_menu.py:279` 改为：
  ```python
  window = terminal.get_toplevel()
  sensitive = bool(getattr(window, 'has_multiple_terms', None)) and window.has_multiple_terms()
  ```
  `:281/:286` 两项共用；`:292-295` 放大分支不变。菜单文案 `Ma_ximize terminal` → `Ma_ximize pane`（中文「最大化此分屏」），`Restore all terminals` → `_Restore pane`（「还原分屏」）。

### 2.3 菜单入口：一律经 `Terminal.popup_menu`

```python
# terminal.py:1213 扩展（兼容旧调用）
def popup_menu(self, widget, event=None, anchor=None, skip_link_check=False):
    window = self.get_toplevel()
    window.preventHide = True
    menu = TerminalPopupMenu(self)
    menu.show(widget, event, anchor=anchor, skip_link_check=skip_link_check)

# terminal_popup_menu.py:104
def show(self, widget, event=None, anchor=None, skip_link_check=False):
    # skip_link_check: 跳过 :116-136；仍取 event.button/time（无 event：button=3,time=0）
    # anchor: popup_at_widget(anchor, Gdk.Gravity.SOUTH_EAST,
    #                         Gdk.Gravity.NORTH_EAST, event)
    #         异常时回退 popup_at_pointer(event)
```

| 来源 | 调用 |
|---|---|
| VTE 右键（不变） | `terminal.popup_menu(widget, event)` |
| 标题栏右键 | `terminal.grab_focus()` → `terminal.popup_menu(titlebar, event, skip_link_check=True)` |
| 齿轮 | `terminal.popup_menu(btn, event, anchor=btn, skip_link_check=True)` |

### 2.4 最大化状态：消费 D 的信号

**契约（由 D 定义，C 只消费）**：

```python
# Window
__gsignals__['pane-maximise-changed'] = (RUN_LAST, None, (GObject.TYPE_PYOBJECT, GObject.TYPE_BOOLEAN))
def is_maximised_pane(self, term) -> bool
```

C 的用法：

```python
# Titlebar
def _on_hierarchy_changed(self, widget, prev_toplevel):
    # 终端可能被拖到别的窗口 / detach tab：断开旧窗口，连新窗口
    self._disconnect_window_signal()
    win = self.get_toplevel()
    if hasattr(win, 'is_maximised_pane'):
        self._win_sig = (win, win.connect('pane-maximise-changed', self._on_pane_maximise_changed))
    self.refresh_maximise_state()

def _on_pane_maximise_changed(self, window, terminal, maximised):
    self.refresh_maximise_state()        # 同窗所有标题栏都刷新：敏感度会随之变化

def refresh_maximise_state(self):
    win = self.get_toplevel()
    maxed = hasattr(win, 'is_maximised_pane') and win.is_maximised_pane(self.terminal)
    multi = hasattr(win, 'has_multiple_terms') and win.has_multiple_terms()
    self.btn_max.set_sensitive(maxed or multi)
    # 图标 view-fullscreen-symbolic ↔ view-restore-symbolic；tooltip/accessible-name 同步
```

- 另需在 split / closeterm / 切 tab（`switch-page`）后刷新敏感度：在 `Terminator.focus_changed`（`terminator.py:629`）或 `Terminal.on_vte_focus_in` 末尾调 `refresh_maximise_state()`，成本低、覆盖面广。
- **M2 先于 M3 合入时的垫片**（C 实现，D 后续接管/扩展，签名不变）：在 `Window` 加上述信号；`is_maximised_pane(term) = self.is_zoomed() and self.zoom_data and self.zoom_data['widget'] is term and not self.zoom_data['font_scale']`；在 `Window.zoom` 末尾（`:719`）与 `unzoom` 末尾（`:745`）`emit('pane-maximise-changed', widget, True/False)`。`scaled_zoom`（font_scale=True）不算"最大化此分屏"，但仍要 emit 以便刷新敏感度（参数 False）。
- 不再在 `Window.zoom/unzoom` 里直接调用 titlebar 方法（v1 的 `update_zoom_icon` 直调方案作废）。
- **禁止在按钮 clicked 里乐观切图标**：点击只发 `maximise`/`unzoom`；图标与敏感度**只**在收到 `pane-maximise-changed`（以及 hierarchy / focus 触发的 `refresh_maximise_state`）后更新。否则 D 合入异步动画后会出现「图标已是还原、浮层还在播放大」的短暂错态（cross-module 审查指出的 stale-icon）。D 须在状态真正切换后 emit（无动画：同步 emit；有动画：终态 emit）。

### 2.5 关闭 ✕

```python
from .close_confirm import request_close_terminal   # A 模块提供
def on_close_clicked(self, *_):
    request_close_terminal(self.terminal)            # 内含 D17 单对话框 / ask_before_closing
```

- 禁止直接调用 `terminal.close()`。
- **单一关闭入口（implementability）**：`TerminalPopupMenu.close_terminal`（菜单「Close」）**必须**委托 `request_close_terminal`；标题栏 ✕ 直接调同一函数。C6 验收：菜单 Close 与 ✕ 走同一路径（单测 mock 一次即可）。
- 依赖：A 的 A7 先合入；否则 PR-C6 阻塞（不提供临时旁路，避免出现没有进程确认的 ✕）。

### 2.6 徽标统一 API（C 创建控件，E 挂 popover）

```python
def set_scale_badge(self, scale, locked):
    """scale: float|None；locked: bool。
    - scale is None 或 (scale >= 0.999 and not locked) → 隐藏
    - 否则显示 '90%'；locked 时前置锁图标（'changes-prevent-symbolic'）
    - tooltip：'自动字号 90%（点击查看）' / '字号已锁定'
    - 受 auto_font_scale_show_badge 控制由 E 判断后调用；C 不读 E 的配置
    """

self.scale_badge   # 公开属性：E 用 Gtk.Popover.new(self.scale_badge) 并 connect('clicked')
```

- C 只负责控件、显示/隐藏、文案和折叠顺序；**不**写 popover 内容。
- E 子方案中的 `set_font_scale_badge(scale)` 统一改名为本签名（需 E 文档同步，见 §12）。

### 2.7 右键菜单「锁定此终端字号」（E 钩子）

在 `terminal_popup_menu.py` 的 `_Read only`（`:313`）附近：

```python
if hasattr(terminal, 'set_auto_font_locked') and self.config['auto_font_scale']:
    item = Gtk.CheckMenuItem.new_with_mnemonic(_('_Lock font size for this terminal'))  # 锁定此终端字号
    item.set_active(terminal.get_auto_font_locked())
    item.connect('toggled', lambda x: terminal.set_auto_font_locked(x.get_active()))
    menu.append(item)
```

- E 未合入（无该方法）时不显示；`get_auto_font_locked()` 需 E 提供（E 文档现只有 setter，见 §12）。

### 2.8 EditableLabel

```python
def __init__(self, text="", double_click_edit=True): ...
def _on_click_text(self, widget, event):
    if event.button != 1: return False
    if event.type == Gdk.EventType._2BUTTON_PRESS:
        if not self._double_click_edit:
            self.emit('double-clicked')   # 不依赖冒泡，确定性更高
            return True
        self.edit(); return True
    return False
```

- v2 改为**直接发自定义信号 `double-clicked`**（v1 依赖 `return False` 冒泡，GTK 中 EventBox 子控件的冒泡行为与 `visible_window=False` 有关，不可靠）。Titlebar `self.label.connect('double-clicked', lambda *_: self._toggle_pane_maximise())`；Titlebar 自身的 `_2BUTTON_PRESS`（点在空白处）同样 toggle。
- 「编辑标题」菜单项放在 `Set _Window Title`（`:210-213`）之后 → `terminal.key_edit_terminal_title()`。

### 2.9 焦点绿框

| 时机 | 钩子 | 操作 |
|---|---|---|
| VTE 获焦 | `on_vte_focus_in` `terminal.py:1509` | add `terminator-term-focused`，remove `-unfocused` |
| VTE 失焦 | `on_vte_focus_out` `:1525` | 反之 |
| **窗口失焦** | `on_window_focus_out` `:1532` | 清除 focused（父级裁决：失焦即无绿框） |
| 窗口重新获焦 | 已有 `focus_changed` 路径 → VTE focus-in | 自动恢复 |

class 加在 `Terminal`（VBox）上，边框包住标题栏 + VTE。

---

## 3. 事件处理

```python
def on_button_press(self, widget, event):           # 替换 titlebar.py:96 的 on_clicked
    if event.button == 3 and event.type == Gdk.EventType.BUTTON_PRESS:
        self.terminal.grab_focus()
        self.terminal.popup_menu(self, event, skip_link_check=True)
        return True                                  # 硬性要求
    if event.button == 1 and event.type == Gdk.EventType._2BUTTON_PRESS:
        self._toggle_pane_maximise()
        return True
    if event.button == 1 and event.type == Gdk.EventType.BUTTON_PRESS:
        self.show(); self.label.show()
        self.emit('clicked')                          # 保留兼容
    return False                                      # 单击不吞，留给 DnD 阈值判断

def _toggle_pane_maximise(self):
    win = self.terminal.get_toplevel()
    if hasattr(win, 'is_maximised_pane') and win.is_maximised_pane(self.terminal):
        self.terminal.unzoom()
    elif hasattr(win, 'has_multiple_terms') and win.has_multiple_terms():
        self.terminal.maximise()
```

- 右键落在分组 ebox：`on_group_button_press` 对非 1 键 `return False`（`terminal.py:1063`），冒泡到 Titlebar。真机验证；不冒泡时在 `connect_icon` 外包一层委托。
- 三按钮：`button-press-event` 里处理并 `return True`（齿轮需要 event），另连 `clicked` 作为键盘激活（event=None）；`focus_on_click=False`。
- 编辑标题中（`self.editing()`）时不响应双击 toggle。

---

## 4. 布局细节

- **折叠**：尺寸文字 → 分组名（`grouplabel.hide()` 当分配宽度 < 阈值，在 `size-allocate` 中判断，防抖）→ 徽标 → 标题省略（已有 `ellipsize='end'`）。三按钮永不隐藏。
- **尺寸文字**：`update_terminal_size` 设置 `sizetext` 并安排 1s 后清除（重复 resize 只保留一个定时器）；`title_hide_sizetext=True` 时不显示。
- **a11y / tooltip**

| 控件 | accessible-name | tooltip |
|---|---|---|
| 齿轮 | 终端菜单 | 终端菜单（右键标题栏也可） |
| 最大化 | 最大化此分屏 / 还原分屏 | 最大化此分屏（Ctrl+Shift+X）/ 还原分屏（Ctrl+Shift+X） |
| 关闭 | 关闭终端 | 关闭终端（Ctrl+Shift+W） |
| 徽标 | 自动字号 90% | 由 `set_scale_badge` 设置 |

快捷键文本从 `config['keybindings']` 读取并用 `Gtk.accelerator_get_label` 格式化，用户改键后 tooltip 同步。

---

## 5. CSS（共用 `Terminator.reconfigure` 的同一个 provider）

C 与 D 的样式**并入同一段生成的 CSS 字符串**，在 `terminator.py:440-442` 那个 provider 里追加（不另建 provider，避免优先级叠加互相覆盖）；颜色来自 `pane_accent_color`，读取时校验 `Gdk.RGBA.parse`，非法则回退 `#3fb950` 并 `err()`。

```css
.terminator-terminal-window .terminator-term-focused   { border: 1px solid @ACCENT@; }
.terminator-terminal-window .terminator-term-unfocused { border: 1px solid transparent; }

/* 与 D 浮层框不叠加：浮层已有 2px 同色框 */
.terminator-terminal-window .pane-maximised .terminator-term-focused { border-color: transparent; }

button.titlebar-btn { padding: 0 2px; min-height: 0; min-width: 0; }
button.titlebar-btn-close { margin-left: 6px; }
button.titlebar-btn-close:hover { color: #f85149; }
button.titlebar-badge { padding: 0 4px; min-height: 0; font-size: smaller; }

.titlebar-density-standard { min-height: 24px; }
.titlebar-density-compact  { min-height: 20px; }
.titlebar-density-standard button.titlebar-btn { min-width: 24px; min-height: 24px; }
.titlebar-density-compact  button.titlebar-btn { min-width: 20px; min-height: 20px; }
```

- 透明边框占位，避免焦点切换引起 VTE 重新分配（也避免触发 E 的重算）。
- `.pane-maximised` 由 D 的 `PaneFrame` 提供；M2 阶段该规则无匹配，无副作用。

---

## 6. 配置键（global 级，`config.py` `DEFAULTS['global_config']`）

| 键 | 类型 | 默认 | UI |
|---|---|---|---|
| `titlebar_buttons` | bool | `True` | 全局页复选框 |
| `titlebar_show_icon` | bool | `False` | 窗格页复选框（m36）：标题栏左侧终端图标/分组图标；关闭时分组入口在右键菜单「分组」子菜单、组名点击与分组快捷键，发送端显示「广播：全部/分组」文字 |
| `titlebar_density` | str | `'standard'` | 全局页：标准 / 紧凑；非法值回退 standard |
| `pane_accent_color` | str | `'#3fb950'` | 全局页颜色按钮；C/D 共用 |

- profile `show_titlebar=False`：整条标题栏隐藏，按钮与徽标一起消失；终端区仍可 Shift+右键 / Menu / Shift+F10。
- 同步 `prefseditor.py`、`preferences.glade`、`doc/terminator_config.adoc`。

---

## 7. 文件改动清单

| 文件 | 改动 |
|---|---|
| `titlebar.py` | termicon、三按钮、徽标控件与 `set_scale_badge`；`on_button_press`；`refresh_maximise_state` + hierarchy-changed 连接窗口信号；`apply_chrome_config`；尺寸文字定时；折叠 |
| `editablelabel.py` | `double_click_edit` 参数、`double-clicked` 信号 |
| `terminal.py` | `popup_menu(widget, event, anchor, skip_link_check)`；焦点 class（含窗口失焦）；可选 F2 |
| `terminal_popup_menu.py` | `show` 新参数；`:279` 改 `has_multiple_terms`；文案；「编辑标题」「锁定此终端字号」；`import re` |
| `window.py` | `has_multiple_terms`；（M2 先合入时）`pane-maximise-changed` 信号 + `is_maximised_pane` 垫片 + zoom/unzoom emit |
| `config.py` | 三个键 |
| `terminator.py` | `reconfigure` 的共用 CSS 段 + 各标题栏 `apply_chrome_config()` |
| `prefseditor.py`、`preferences.glade`、`doc/terminator_config.adoc` | UI 与文档 |
| `tests/` | §9 |

不改：`close_confirm.py`（A）、`paneoverlay.py`（D）、E 的状态机。

---

## 8. PR 顺序与估计（合计 2.5–3 人日）

| PR | 内容 | 估 | 依赖 |
|---|---|---|---|
| C0 | 配置三键 + 共用 CSS 段 + 首选项控件；`import re` 修复（独立提交） | 0.3d | — |
| C1 | 标题栏控件：termicon、三按钮、徽标控件 + `set_scale_badge`、密度、a11y/tooltip（读快捷键） | 0.5d | C0 |
| C2 | `Terminal.popup_menu` / `show` 新参数；标题栏右键与齿轮接线；`return True` | 0.3d | C1 |
| C3 | `has_multiple_terms`（可见终端）+ 菜单 `:279` 修正与文案；`pane-maximise-changed` 消费 + 垫片；`refresh_maximise_state` 各刷新点 | 0.5d | C1；D 契约文本 |
| C4 | D15：`double-clicked` 信号、双击 toggle、「编辑标题」菜单项、可选 F2 | 0.3d | C1 |
| C5 | 焦点绿框（含窗口失焦清除、与 `.pane-maximised` 去重） | 0.2d | C0 |
| C6 | ✕ → `request_close_terminal` | 0.1d | **A7 已合入** |
| C7 | 「锁定此终端字号」菜单项（hasattr 守卫） | 0.1d | 可先合；E 合入后生效 |
| C8 | 折叠 + 尺寸文字 1s 定时 | 0.3d | C1 |
| C9 | 单测 + 手工清单 + 文档 | 0.4d | 全部 |

合并顺序：C0 → C1 → C2 → **C3（尽早合入：`has_multiple_terms` 是 D 的依赖；implementability 所称「C4 early」即指此项）** → C4 → C5 → C8 → C7 → C6（等 A7）→ C9。

**文件冲突（implementability）**：`preferences.glade` 被 A8、B5、**C0**、E6、D 共用——C0 与这些 PR **串行合并**，不要并行改 glade。`terminal.py` 的 `popup_menu` / 焦点 class（C2/C5）与 A3/B3/B4/E3 可能撞车，合入前 rebase。

---

## 9. 测试

### 9.1 自动化

| 用例 | 断言 |
|---|---|
| `show(..., skip_link_check=True)` | mock VTE，`hyperlink_check_event`/`match_check_event` 未调用；button/time 取自 event |
| 标题栏右键 | 经 `Terminal.popup_menu`：`window.preventHide is True`；handler 返回 True |
| `has_multiple_terms` | FakeWindow：当前 tab 1 个 + 其他 tab 3 个 → False；当前 tab 2 个 → True |
| 菜单敏感度 | Notebook 中单终端 tab → 「最大化此分屏」不可点（修正前会误亮的回归用例） |
| `pane-maximise-changed` | emit 后同窗所有标题栏 `btn_max` 图标/敏感度刷新；终端移到新窗口后旧窗口信号已断开 |
| EditableLabel | `double_click_edit=False` 时双击发 `double-clicked`，`editing()` 为 False |
| `set_scale_badge` | `(None,False)`/`(1.0,False)` 隐藏；`(0.9,False)` 显示 "90%"；`(1.0,True)` 显示锁图标 |
| 锁定菜单项 | 无 `set_auto_font_locked` 时不出现；有时 toggled 调用之 |
| ✕ / 菜单 Close | 均调用 `request_close_terminal(terminal)` 恰好一次；`close_terminal` 仅委托，未直接 `terminal.close()` |
| 焦点 class | `on_window_focus_out` 后无 `terminator-term-focused` |
| 非法 `pane_accent_color` | 回退默认色，不抛异常 |

### 9.2 手工（真机 VTE）

1. 单终端：最大化置灰；右键/齿轮菜单正常。
2. 两个 tab 各一个终端：最大化置灰（菜单与按钮一致）。
3. 左右分屏：按钮/双击/Ctrl+Shift+X 三路放大还原，图标同步。
4. tmux mouse on：标题栏右键出菜单；quake 模式下菜单打开时窗口不隐藏。
5. 齿轮菜单贴按钮下方（X11 与 Wayland）。
6. 拖标题可 DnD；连点 ✕/齿轮不拖出。
7. 焦点：绿框唯一；切到别的应用后绿框消失，切回恢复。
8. M3 合入后：浮层中只见 2px 框，无 1px 内框。
9. `sleep 3600 &` 后点 ✕ → 一个对话框，默认「取消」。
10. `title_at_bottom=True`、`show_titlebar=False`、`titlebar_buttons=False`、compact 密度各走一遍。
11. 拖分隔条：尺寸文字约 1s 后消失。
12. 窄分屏（约 30 列）：按钮仍在，分组名/徽标先隐藏。

---

## 10. 风险

| 风险 | 级 | 缓解 |
|---|---|---|
| 右键绕过 `popup_menu` 漏 `preventHide` | P0 | 统一入口 + 单测 |
| URL 误判 | P0 | `skip_link_check` |
| 按钮触发 DnD | P0 | 按钮 `return True`；手工测 |
| 双击冲突 | P0 | `double-clicked` 信号，不依赖冒泡 |
| ✕ 无进程确认 | P0 | 只调 `request_close_terminal`；C6 等 A7 |
| 敏感度在 Notebook 单终端误亮 | P1 | 可见终端计数 + 回归用例 |
| 终端换窗口后信号悬挂 | P1 | hierarchy-changed 断开重连 |
| M3 遍历漏浮层导致置灰错误 | P1 | 列为对 D 的接口要求 |
| C/D 双框 | P2 | `.pane-maximised` 去重规则；共用 provider |
| `popup_at_widget` 在 Wayland 异常 | P1 | 回退 `popup_at_pointer` |
| 标题栏变高少一行 VTE | P2 | standard ≤26px；测 `title_at_bottom` |
| symbolic 图标缺失 | P2 | 回退非 symbolic 名 |

本机无 GTK/VTE，P0 项必须在装有 VTE 的机器上验证后合入。

---

## 11. 跨模块接口一览

| 方向 | 接口 | 所有者 |
|---|---|---|
| C → A | `close_confirm.request_close_terminal(terminal)` | A |
| C ← D | `Window` 信号 `pane-maximise-changed(terminal, bool)`、`Window.is_maximised_pane(term)`；Overlay 下 `get_visible_terminals` 含浮层终端；`PaneFrame` CSS class `pane-maximised` | D（M2 先合入时 C 提供签名相同的垫片） |
| C → D | `Window.has_multiple_terms()`（可见终端）；`Terminal` 上 `terminator-term-focused` class | C |
| C → E | `Titlebar.set_scale_badge(scale: float\|None, locked: bool)`、`Titlebar.scale_badge` 控件（E 挂 popover）；菜单项调用 `set_auto_font_locked` / `get_auto_font_locked` | C 提供控件；E 提供方法 |
| 共用 | `pane_accent_color`；`Terminator.reconfigure` 的同一个 CSS provider | C 建，D 追加 |

---

## 12. 修订记录与遗留对齐

### v2（2026-10-10，三路审查 + 父级裁决）

1. ✕ 改为调用 `close_confirm.request_close_terminal(terminal)`（A 所有），删除 v1 的临时 `construct_confirm_close` 旁路。
2. 右键/齿轮统一经 `Terminal.popup_menu(widget, event, anchor, skip_link_check)`，保证 `preventHide`。
3. `has_multiple_terms` 改为当前 tab 可见终端（`get_visible_terminals`），不再 `get_terminals`。
4. 最大化图标/敏感度由 `pane-maximise-changed` + `is_maximised_pane` 驱动；作废 v1 中 zoom/unzoom 直调 `update_zoom_icon`。
5. 徽标 API 统一为 `set_scale_badge(scale, locked)`；C 建控件，E 挂 popover。
6. 右键菜单增加「锁定此终端字号」（E 钩子）。
7. 更正 `terminal_popup_menu.py:278`/`:292-295` 的现状描述（`:279` 的问题在未放大态，非放大态）。
8. 与 D 去双框：`.pane-maximised .terminator-term-focused{border-color:transparent}`；C/D 共用 `reconfigure` 中同一 provider。
9. 窗口失焦清除绿框（不再是"建议"）。
10. EditableLabel 改用 `double-clicked` 信号。
11. 附带：`terminal_popup_menu.py` 缺 `import re`。
12. 估计 1.5–2d → **2.5–3d**；PR 重排为 C0–C9。

### v2.1（2026-10-10，`findings-summary.md` 补漏）

对照权威 findings 清单后补入（父级裁决已覆盖的不重复）：
1. 与 A 的 `scope_terminals` 划界：`Window.has_multiple_terms` 仍只数**当前 tab 可见终端**。
2. 最大化图标禁止点击时乐观更新；只信 `pane-maximise-changed`（避免 D 动画期错态）。
3. 菜单 Close 与 ✕ 统一经 `request_close_terminal`；`close_terminal` 必须委托。
4. C3（`has_multiple_terms`）标为 D 的早期依赖；`preferences.glade` 与 A8/B5/E6/D 串行。
5. 明确「下次启动不恢复」不归 C。
6. 菜单项现状描述（`:278` 未放大分支两项共用错误 sensitive；`:292-295` 放大分支）在 v2 已更正，findings P2「C menu-item description inaccurate」以此为准。

### 需其他子方案同步（本文件不改它们）

| 文件 | 需同步 |
|---|---|
| `E-auto-font-scale.md` | `set_font_scale_badge(scale)` → `set_scale_badge(scale, locked)`；徽标控件由 C 创建，E 只挂 popover；补 `get_auto_font_locked()` |
| `D-overlay-maximize.md` | 正式写出 `pane-maximise-changed(terminal,bool)` 与 `is_maximised_pane(term)`；`has_multiple_terms` 改为可见终端计数（D 文档 :330 仍写 `get_terminals`）；`.pane-maximised` 与焦点框去重 |
| `A-session-and-close-confirm.md` | 确认 `request_close_terminal` 位于 `close_confirm.py` 并由 `TerminalPopupMenu.close_terminal` 委托 |
| 总方案 / 旧稿 | 锁定项不改；F2 仍可选。**`docs/impl-m2-titlebar.md` 作废**（仍写 `confirm_close_terminal`，findings P2）：请在该文件顶部加废弃声明或删除，避免照旧稿实现 |

---

## 13. Go / No-Go

**有条件 Go**：C0–C5、C7、C8 可立即开工；C6 需等 A7；C3 的信号签名以 D 文档为准（M2 先合入时用垫片）。P0 真机项全部通过才合入。
