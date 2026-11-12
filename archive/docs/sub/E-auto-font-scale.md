# E · 按阅读列宽分档自动字号 — 技术实现子方案（v2）

> 对应主文档：`docs/session-restore-design.md` §E、配置表、D4/D18/D19、M2b。  
> 代码基准：`TIIEHenry/terminator` @ `9f2d0b6`。  
> 范围：每终端独立、离散档位、默认开启；**不改业务代码，本文件仅为实现路径**。  
> 排期：M2b，**1.5–2 人日**（审查上调；可与 M3 并行，但 E3 须先于 D3，见 §6）。  
> v2：并入三路审查 + 父代理锁定项（双暂停模式、徽标 API、toast 位置、cell 缓存、E3+E4 同发）。

---

## 0. 目标与非目标

### 目标

- 每个终端只看**自己**在**基础字号**下的可用列/行（cell；CJK=2 cell），对比 `reading_measure_min_cols=60`（可选 `reading_measure_ideal_cols`）与 `auto_font_scale_min_rows=10`（以宽度/阅读列为主，行数只兜底极矮窗格；上下两格不缩）。
- 档位固定 `['1.0','0.9','0.8']`，floor=`0.8`（D18）。仅跨档时调用一次 `vte.set_font_scale`。
- 降档逐档；升档带 **8% 滞回**；`size-allocate` 防抖；首次有效分配（宽高>0）后才算。
- **两种暂停**（父代理已定，见 §3.5）：
  - `scaled_zoom`：重置 `set_font_scale(1.0)`；
  - D 浮层动画：**只冻结**（不改 scale）；D 在 swap 同一帧同步算好目标档位并应用。
- `Ctrl+0` 只重置基础字号（D19），自动档位保留。
- 标题栏 `%` 徽标：`Titlebar.set_scale_badge(scale, locked)`（**C 建控件，E 挂 popover**）+ 右键「锁定此终端字号」+ Terminal 内 0.8s toast。
- 会话只存基础字号（现状不存字体）；**绝不保存 scale**。
- 基础 cell 尺寸在 **scale==1** 时实测并缓存，**不用** `char_w/scale` 反推（避免取整误差）。

### 非目标

- 不按「分了几屏」或窗口比例缩放；不连续插值；不放大超过 100%。
- 不改 `FontDescription` / `custom_font_size`（留给 Ctrl+/−/0 与 `scaled_zoom`）。
- 不做跨终端统一档位；锁定状态首版不持久化（仅运行时）。

---

## 1. 现状代码锚点（只读核对）

| 能力 | 位置 | 说明 |
|---|---|---|
| VTE `size-allocate` | `terminal.py:526` → `deferred…:1550` → `on_vte_size_allocate:1562` | 已有 idle 合并；末尾挂钩 E |
| 设字体 | `set_font:1889-1891` | FontDescription |
| Ctrl+/− / 0 | `zoom_font:1865` / `zoom_orig:1879` / `key_zoom_normal:2043` | 基础字号；E 在其后 schedule |
| `reconfigure` 字体 | `terminal.py:774-780` | 不清 VTE `font_scale` |
| cell 缩放 | `terminal.py:784-787` | 与 `font_scale` 正交 |
| `scaled_zoom` | `key_scaled_zoom:2131` → `emit('zoom')`；`paned.py:102` → `Window.zoom` 默认 `font_scale=True`（`:690`）→ `zoom_scale:1596` 用 `set_font` | E 在 **`get_zoom_data` 之前** pause+reset |
| 单分屏最大化 | `paned.py:115` `'maximise': [top_window.zoom, False]` | D 后走 overlay；E 冻结式 |
| 标题栏 | `titlebar.py`；C 预留徽标 | C：`set_scale_badge`；E 挂 Popover |
| 右键菜单 | `terminal_popup_menu.py:313` 附近 | C7 加「锁定此终端字号」（`hasattr` 守卫） |
| 配置 list 须全 str | `config.py:606-607` | tiers 元素为 `'1.0'` 等 |
| Prefs 入口 | `terminal.py:2303` / `:2308` `PrefsEditor(self[, cur_page])` | popover「设置」可 `PrefsEditor(term)` |
| `geometry_hinting` | `config.py:88` 默认 False | 开启时有反馈回路风险 |

**缺口**：全仓库无 `get_font_scale`/`set_font_scale` 调用；VTE 2.91+，需 `hasattr`；缺失则禁用 E。

---

## 2. 算法（纯函数 + 伪代码）

### 2.1 `terminatorlib/autofont.py`（无 GTK）

```python
from math import floor, ceil

def parse_tiers(raw) -> list[float]:
    tiers = [float(x) for x in raw]
    if not tiers or tiers[0] != 1.0:
        raise ValueError('tiers must start with 1.0')
    for a, b in zip(tiers, tiers[1:]):
        if not (0 < b < a <= 1.0):
            raise ValueError('tiers must be strictly decreasing in (0,1]')
    return tiers

def select_font_tier(cols0, rows0, cur_index, tiers,
                     min_cols, min_rows, hysteresis, ideal_cols=0) -> int:
    """一次只走一个方向；返回新下标。"""
    n = len(tiers)
    cur = max(0, min(cur_index, n - 1))

    def cols_at(i): return floor(cols0 / tiers[i]) if tiers[i] else 0
    def rows_at(i): return floor(rows0 / tiers[i]) if tiers[i] else 0
    def ok(i):
        if cols_at(i) < min_cols: return False
        if min_rows > 0 and rows_at(i) < min_rows: return False
        return True

    if not ok(cur):
        while cur < n - 1 and not ok(cur):
            cur += 1
        return cur

    up_cols = max(ceil(min_cols * (1.0 + hysteresis)), ideal_cols or 0)
    up_rows = ceil(min_rows * (1.0 + hysteresis)) if min_rows > 0 else 0
    while cur > 0:
        prev = cur - 1
        if cols_at(prev) < up_cols: break
        if up_rows and rows_at(prev) < up_rows: break
        cur = prev
    return cur

def cols_rows_from_base(avail_w, avail_h, base_cw, base_ch) -> tuple[int, int]:
    """用缓存的 scale=1 cell 尺寸计算。禁止用 get_column_count()。"""
    if base_cw <= 0 or base_ch <= 0 or avail_w <= 0 or avail_h <= 0:
        return 0, 0
    return floor(avail_w / base_cw), floor(avail_h / base_ch)

def tier_label(scale: float) -> str:
    return f'{int(round(scale * 100))}%'
```

### 2.2 基础 cell 缓存（审查 P2 → 已定）

`get_char_width()`/`get_char_height()` 返回**当前 scale 下取整**的像素；`char_w/scale` 会有约 1px 误差，在档位边界可能抖（8% 滞回可吸一部分，但不可靠）。

```
Terminal 状态:
  self._base_cell = None   # (cw, ch) 在 font_scale==1.0 时测得

ensure_base_cell():
  if not hasattr(vte, 'get_font_scale'): return False
  scale = vte.get_font_scale()
  if abs(scale - 1.0) < 1e-6:
    cw, ch = vte.get_char_width(), vte.get_char_height()
    if cw > 0 and ch > 0:
      self._base_cell = (cw, ch)
  # 若当前不是 1.0 且尚无缓存：暂缓算档（等暂停/reset 到 1.0，或
  # 一次性 set_font_scale(1.0) 测完再设回——仅初始化路径，见下）
  return self._base_cell is not None

# 首次需要且当前 scale≠1 时（罕见：恢复后立即有非 1 档）：
probe_base_cell_once():
  old = vte.get_font_scale()
  vte.set_font_scale(1.0)
  # 下一 idle：读 char_* 写入 _base_cell，再 set_font_scale(old) 或直接走 update
```

基础字号变化（`zoom_font` / `zoom_orig` / `reconfigure` 改字体）→ **清空** `_base_cell`，下次在 scale=1 时重测（若当前档≠1，先 `probe_base_cell_once` 或等 freeze/reset）。

### 2.3 终端状态机

```
__init__:
  _font_tier = 0
  _auto_font_locked = False
  _auto_font_mode = 'run'   # 'run' | 'freeze' | 'scaled_zoom'
  _auto_font_timer = None
  _auto_font_last_change_ms = 0
  _auto_font_ever_allocated = False
  _base_cell = None
  _scale_popover = None     # E 创建，锚在 titlebar.scale_badge

on_vte_size_allocate 末尾:
  if not config['auto_font_scale'] or not hasattr(vte,'set_font_scale'): return
  w,h = vte.get_allocated_width(), vte.get_allocated_height()
  if w<=0 or h<=0: return
  _auto_font_ever_allocated = True
  if _auto_font_mode == 'freeze': return          # D 动画：忽略 allocate
  if _auto_font_mode == 'scaled_zoom': return     # 已强制 1.0
  schedule_auto_font_scale()

schedule: 防抖 delay=auto_font_scale_delay_ms(150)；已有 timer 不重置（最多延迟）
_flush -> update_auto_font_scale(); return False

update_auto_font_scale(force=False, avail=None):
  # avail=(w,h) 可选：D 在 swap 前传入目标尺寸，同步算档
  if mode != 'run' and not force: return
  if locked: apply_tier(0, reason='locked'); return
  if not _auto_font_ever_allocated and avail is None: return
  tiers = parse_tiers(...)  # 失败 → dbg 禁用
  if not ensure_base_cell(): return
  w,h = avail or (vte.get_allocated_width(), vte.get_allocated_height())
  cols0, rows0 = cols_rows_from_base(w, h, *_base_cell)
  if cols0<=0 or rows0<=0: return
  new = select_font_tier(cols0, rows0, _font_tier, tiers, ...)
  if new == _font_tier and not force: return
  if not force and monotonic_ms()-_last < 500:
    schedule_auto_font_scale(); return
  apply_tier(new)

apply_tier(index, reason='', toast=True):
  _font_tier = index
  scale = tiers[index]
  vte.set_font_scale(scale)
  _last = monotonic_ms()
  refresh_badge()
  if toast and show_badge and scale < 0.999 and reason not in ('init','d-sync','locked'):
    show_center_toast(tier_label(scale))   # 800ms，Terminal 内

refresh_badge():
  if not config['auto_font_scale_show_badge']:
    titlebar.set_scale_badge(None, False); return
  scale = tiers[_font_tier] if not locked else 1.0
  # C API：scale is None 或 (≈1 且 not locked) → 隐藏；locked 显锁标
  titlebar.set_scale_badge(
      None if (scale >= 0.999 and not locked) else scale,
      locked)
```

---

## 3. API 与挂钩点

### 3.1 Terminal 公开 API（供 C / D）

| 方法 | 签名 | 说明 |
|---|---|---|
| `get_auto_font_locked` | `() -> bool` | C 菜单 `set_active` |
| `set_auto_font_locked` | `(locked: bool)` | 锁 → tier0+scale1.0；解锁 → force 重算 |
| `pause_auto_font_scale` | `(mode='freeze'\|'scaled_zoom')` | 见 §3.5 |
| `resume_auto_font_scale` | `()` | mode→`run`；`update(force=True)` |
| `compute_tier_for_size` | `(w, h) -> float` | **给 D**：按目标像素算应设 scale（不写 VTE）；内部用 `_base_cell`+`select_font_tier` |
| `apply_font_tier_scale` | `(scale: float, toast=False)` | **给 D**：同一帧 `set_font_scale` + 更新 `_font_tier` + badge；不经防抖 |
| `schedule_auto_font_scale` / `update_auto_font_scale` | | 常规路径 |
| `get_auto_font_scale` | `() -> float` | 当前档位 scale |

D 未合入 / E 未合入时：D 侧 `getattr(term, 'pause_auto_font_scale', lambda *a, **k: None)`；C 侧 `hasattr(term, 'set_auto_font_locked')`。

### 3.2 Titlebar 徽标（C 提供，E 消费）

```python
# C-titlebar.md §2.6 — E 必须使用此签名，禁止 set_font_scale_badge
def set_scale_badge(self, scale, locked):
    """scale: float|None；locked: bool。
    None 或 (scale≥0.999 and not locked) → 隐藏；否则 '90%'；locked 加锁图标。"""

self.scale_badge   # E: Gtk.Popover.new(self.scale_badge)；connect clicked
```

E 在 `Titlebar.__init__` 之后 / 首次 badge 刷新时：

```python
if self._scale_popover is None and hasattr(self.titlebar, 'scale_badge'):
    btn = self.titlebar.scale_badge
    pop = Gtk.Popover.new(btn)
    # 内容：说明文案；「锁定此终端字号」CheckButton；
    # 「禁用自动字号」→ config['auto_font_scale']=False; config.save(); 全终端 resume/reset；
    # 「设置…」→ PrefsEditor(self)
    btn.connect('clicked', lambda *a: pop.popup())
    self._scale_popover = pop
```

### 3.3 右键菜单「锁定此终端字号」（C7 落地，E 提供方法）

`terminal_popup_menu.py`（约 `:313` `_Read only` 附近），由 **C** 合入：

```python
if hasattr(terminal, 'set_auto_font_locked') and self.config['auto_font_scale']:
    item = Gtk.CheckMenuItem.new_with_mnemonic(_('_Lock font size for this terminal'))
    item.set_active(terminal.get_auto_font_locked())
    item.connect('toggled', lambda x: terminal.set_auto_font_locked(x.get_active()))
    menu.append(item)
```

E 文档责任：保证 `get_auto_font_locked` / `set_auto_font_locked` 存在且与 badge 同步。

### 3.4 Toast（仅 Terminal 内）

- **禁止**挂到 Window / Overlay（D 会重构顶层 Overlay；M2b 可能先于 M3）。
- 做法：把 `self.terminalbox` 包进 `Gtk.Overlay`（Terminal 私有，不影响 `Terminal` 作为容器子控件的身份——父级仍看到 Terminal VBox）。
  - `create_terminalbox` 之后：`wrap = Gtk.Overlay(); wrap.add(terminalbox); self.terminalbox_overlay = wrap`；pack 用 wrap 替代直接 pack terminalbox；**或**在现有 `self.terminalbox` 外再包一层并更新 `self.terminalbox` 引用为 hbox、另存 `self._term_overlay`。
  - 注意：`close()` 里 `self.terminalbox.remove(self.vte)`（`:309`）仍指向内层 hbox；拖放用 `maker.isinstance(..., 'Terminal')` 向上找，不依赖 hbox 父级，安全。
- Toast：`Gtk.Label`，`halign/valign=CENTER`，CSS 半透明；`GLib.timeout_add(800, hide)`；不接收事件（`set_sensitive(False)` / pass-through）。
- 与 `auto_font_scale_show_badge` 同开同关。

### 3.5 双暂停模式（父代理锁定）

| 模式 | 触发 | 行为 | 恢复 |
|---|---|---|---|
| **`scaled_zoom`** | 进入带字号的 zoom | `pause(mode='scaled_zoom')`：**立即** `set_font_scale(1.0)`；忽略 size-allocate | unzoom 恢复 FontDescription 后 `resume()` → force 重算 |
| **`freeze`** | D 浮层动画 / 瞬时 swap | `pause(mode='freeze')`：**不改**当前 scale；忽略 allocate | D 在 swap **同一帧**调用 `compute_tier_for_size(dst_w,dst_h)` + `apply_font_tier_scale(...)`；动画结束后 `resume()`（通常档已是目标，force 为幂等） |

#### scaled_zoom 挂钩（必须在 `get_zoom_data` 之前）

代码准确性审查 P1：若先 `get_zoom_data()` 再 pause，会把「已含 auto scale 的 char 尺寸」记进 `old_*`，unzoom/`zoom_scale` 失真。

```python
# window.py — 今日 :690；D 合入后此逻辑进 _legacy_zoom 的 font_scale 分支
def zoom(self, widget, font_scale=True):
    ...
    if font_scale:
        # BEFORE get_zoom_data (today :700)
        if hasattr(widget, 'pause_auto_font_scale'):
            widget.pause_auto_font_scale('scaled_zoom')
    self.zoom_data = widget.get_zoom_data()
    ...
```

```python
def unzoom(...):
    ...
    if self.zoom_data['font_scale']:
        widget.vte.set_font(self.zoom_data['old_font'])
        if hasattr(widget, 'resume_auto_font_scale'):
            widget.resume_auto_font_scale()
```

D 拆分后：上述插入点在 **`_legacy_zoom` / `_legacy_unzoom` 的 `font_scale=True` 分支**（跨模块 P2）；overlay 路径不走 reset。

#### D 浮层：冻结 + 同帧设档 + 信号

```python
# E 在 Terminal.connect_signals / hierarchy-changed 时连接窗口信号
win.connect('pane-maximise-changed', self._on_pane_maximise_changed)

def _on_pane_maximise_changed(self, window, terminal, maximised):
    if terminal is not self: return
    # 主要用于 badge/UI；真正的 pause/apply 由 D 在 overlay_* 内显式调用
    self.refresh_badge()
```

D 契约（E 期望 D 遵守；E3 未合入时 D 用 getattr）：

1. `overlay_maximise` 开始动画前：`pause_auto_font_scale('freeze')`。
2. **swap 终端到 PaneFrame 的同一帧**（终端已在 dst 分配或已知 dst 像素）：  
   `scale = term.compute_tier_for_size(dst_w, dst_h)`；`term.apply_font_tier_scale(scale, toast=False)`。  
   → 只触发 **一次** SIGWINCH，与 reparent 合并。
3. 动画 tick **不得**再改 font_scale。
4. 动画结束：`resume_auto_font_scale()`。
5. `overlay_restore`：同样 freeze → swap 回原位同帧按原分屏尺寸 apply → 动画结束 resume。
6. emit `pane-maximise-changed`（C/E 刷新）。

### 3.6 挂钩表（file:function:line）

| 文件 | 位置 | 改动 |
|---|---|---|
| `autofont.py` | **新** | 纯函数 |
| `terminal.py` | `__init__:126` | 状态字段 |
| `terminal.py` | `create_terminalbox:333` / pack `:187-192` | Overlay 包一层供 toast |
| `terminal.py` | `on_vte_size_allocate:1562` 末 | schedule（受 mode 门控） |
| `terminal.py` | `zoom_font:1865` / `zoom_orig:1879` | 清 `_base_cell`；schedule（D19：不锁定） |
| `terminal.py` | `reconfigure` 字体段 `:774` 后 | 清 `_base_cell`；schedule |
| `terminal.py` | 新方法 | pause/resume/lock/get/compute/apply/toast/popover |
| `paned.py` | `split_axis:37`、`remove:247`、`on_button_release:160` | 子树 `schedule_auto_font_scale`（结构变化；拖动中靠 allocate） |
| `window.py` | `zoom:690` **在 `:700 get_zoom_data` 前** | `font_scale=True` → `pause('scaled_zoom')` |
| `window.py` | `unzoom:721` font 恢复后 | `resume` |
| `window.py` | D 后 `_legacy_zoom/_legacy_unzoom` | 同上钩子迁入 |
| D `overlay_*` | swap 帧 | freeze + compute/apply；结束 resume |
| `titlebar.py` | C 的 `set_scale_badge` | E 只调用 + 挂 popover |
| `terminal_popup_menu.py` | C7 | 锁定菜单项 |
| `config.py` | `DEFAULTS` `:84` | §4 键；**注意** `hysteresis` 为 float——`defaults_to_configspec` 的 keymap 无 `float`（仅 int/str/bool/list）。实现时：要么扩展 keymap 加 `'float':'float'`，要么默认用字符串 `'0.08'` 并在读取处 `float()`（**推荐扩 keymap**，与 `cell_width` 等同为 float 的 profile 键一致，见 `config.py:628+` profile 分支） |
| `prefseditor.py` / `preferences.glade` | 全局外观 | 三项：`auto_font_scale`、`reading_measure_min_cols`、`auto_font_scale_show_badge` |
| `doc/terminator_config.adoc` | | 全部 E 键 |

**配置 float 细节**：`global_config` 的 `defaults_to_configspec`（`config.py:594-610`）keymap 只有 int/str/bool；profile 段同样。现有 `cell_width`/`cell_height` 在 **profile** 默认里是 float，profile 循环同样用该 keymap——若 float 未映射，ConfigObj 可能当 str。E 实现时与 `cell_width` 同样处理：读时 `float(config['auto_font_scale_hysteresis'])`，DEFAULTS 可保持 `0.08`；并给 keymap 补 `float`（小修复，E2 做）。

---

## 4. 配置键

| 键 | 类型 | 默认 | UI |
|---|---|---|---|
| `auto_font_scale` | bool | `True` | 开关 |
| `auto_font_scale_show_badge` | bool | `True` | 「显示比例」 |
| `auto_font_scale_tiers` | list(str) | `['1.0','0.9','0.8']` | 仅文件 |
| `reading_measure_min_cols` | int | `60` | 「至少 N 列」 |
| `reading_measure_ideal_cols` | int | `0` | 仅文件 |
| `auto_font_scale_min_rows` | int | `10` | 仅文件 |
| `auto_font_scale_hysteresis` | float | `0.08` | 仅文件 |
| `auto_font_scale_delay_ms` | int | `150` | 仅文件 |

校验失败 → dbg 并视作关闭。tiers 元素必须 str。

---

## 5. 与 A/C/D/字号快捷键

| 场景 | 行为 |
|---|---|
| A 会话 | 不写 scale；恢复后 allocate 推导 |
| A `doing_layout` | allocate=0 跳过；完成后自然算档 |
| B 回填 | 之后 rewrap 可接受 |
| C 徽标位 | C1 预留；E5 挂 popover（E5 **依赖 C1**） |
| C 锁定菜单 | C7 + E 的 get/set |
| D 动画 | freeze，同帧 apply；听 `pane-maximise-changed` |
| `scaled_zoom` | reset 1.0；钩在 get_zoom_data 前 / `_legacy_*` |
| Ctrl+/−/0 | 基础字号；0 **不**锁（D19） |
| 单终端 | 通常 100%，无打扰 |

---

## 6. PR 任务（M2b，1.5–2 人日）

| # | 任务 | 估计 | 依赖 / 约束 |
|---|---|---|---|
| E0 | 真机确认 `set/get_font_scale`；写入合并 M0 清单 | 0.1d | M0 |
| E1 | `autofont.py` + `tests/test_autofont.py` | 0.3d | —（随时） |
| E2 | `config.py` 键 + float keymap + adoc | 0.15d | — |
| **E3+E4** | Terminal 状态机 + pause/resume/lock/get + size-allocate/zoom_font/zoom_orig + **scaled_zoom 钩子（window.zoom 在 get_zoom_data 前）** + paned 触发；预留 D getattr 友好 API（`compute_tier_for_size`/`apply_font_tier_scale`） | **0.6d** | E1+E2；**必须同发**；**须先于 D3**（否则 D getattr 空操作，放大时可能叠档） |
| E5 | Toast（Terminal 内 Overlay）+ 挂 `scale_badge` popover + `refresh_badge`→`set_scale_badge` | 0.35d | E3；**C1**（徽标控件） |
| E6 | 首选项三项 + 手工验收；`preferences.glade` **与 A8/B5/C0 串行** | 0.2d | E2–E5 |

合计约 **1.7 人日**（区间 1.5–2）。

**合入门槛**：E1 全绿；E0 API 存在；E3+E4 同 PR；手工 §7.2；D3 合入前确认 E3 已在主干或 D 已写 getattr 回退。

**全局顺序（实现性审查）**：M0 → M1 → M2(C，C1 尽早) → **M2b(E)** → M3(D3 依赖 E3)。

---

## 7. 测试

### 7.1 单测 `tests/test_autofont.py`（无头；`autofont.py` 不 import gi）

参数化覆盖主文档 §E.1 示例表；另测：`parse_tiers` 非法；`cols_rows_from_base`；ideal_cols=66；min_rows=0；边界 avail/cell=0。

> `pytest.ini` 含 `--doctest-modules`：勿在 `terminal.py` 顶层强制 `import autofont` 失败；E 相关 GTK 测试需 gi 环境（归 M0）。

### 7.2 手工

1. 默认开：单终端无徽标、scale=1。  
2. 上下二分（≥50 行高）→ 100%。  
3. 左右三分 → ~80% + toast；关一侧滞回后回 100%。  
4. 60 列附近拖分隔条 → 不闪烁。  
5. Ctrl+ / Ctrl+0 → 基础字号变，档位不锁。  
6. `scaled_zoom` → 期间 scale=1；`get_zoom_data` 的 old_char 为基础格；还原后自动档恢复。  
7. D 放大（合入后）→ 动画中 scale 不抖；swap 帧一次 SIGWINCH；放大后常 100%；还原回原档。  
8. 徽标 popover 锁定 / 禁用 / 设置；右键「锁定此终端字号」与 popover 状态一致。  
9. `geometry_hinting=True` → 无窗口振荡。  
10. 无 `set_font_scale` → 静默禁用。

---

## 8. 风险

| 风险 | 级 | 缓解 |
|---|---|---|
| `get_column_count` / `char_w/scale` 振荡或误差 | P0 | 只用缓存 `_base_cell`；单测锁死 |
| scaled_zoom 与 auto scale 叠乘 / old_font 污染 | P0 | pause **在** `get_zoom_data` 前；reset 1.0 |
| D 动画每帧改字号 | P0 | freeze；仅 swap 帧 apply |
| E3 晚于 D3 | P1 | 顺序约束或 getattr |
| SIGWINCH 闪烁 | P1 | 防抖 150ms；跨档才 set；拖动中不切 |
| geometry_hinting | P1 | 500ms 限频 + 滞回 |
| Terminal 内 Overlay 影响 close/DnD | P2 | 内层 hbox 引用保持；isinstance Terminal 上寻 |
| ConfigObj float | P1 | keymap 补 float + 读时 float() |
| 锁定不持久 | P3 | 首版可接受 |
| Toast 挡字 | P3 | 中央偏上 0.8s、不接事件 |

---

## 9. 与主文档 / 兄弟模块

| # | 项 | 说明 |
|---|---|---|
| 1 | 徽标 | 主文档曾写复用 sizetext；现 **C `set_scale_badge(scale, locked)` + E popover**（C v2 / 审查 P2） |
| 2 | 首选项 | 以 §4.2 三项为准；主文档 E.3「模式/上下限」过时 |
| 3 | Toast | 主文档未定位；**定在 Terminal 内**（跨模块 P2） |
| 4 | 暂停 | 主文档笼统「暂停」；现拆 **reset vs freeze**（跨模块 P1 + 父代理） |
| 5 | cell 测量 | 主文档 `char/scale`；现 **scale=1 缓存**（代码准确性 P2） |
| 6 | 主文档过时句 | §5 审查记录仍有「E 默认关」「spawn 前算档」（约 L822/L844）——**以 1A.3/1A.9/§E.1 为准**；改主文档非本文件职责，实现勿照过时句 |
| 7 | 工作量 | 主文档 1–1.5d → **1.5–2d** |

**决策无冲突**：D4/D18/D19、阅读列 60、floor 0.8、滞回 8%、默认开 —— 全部遵从。

---

## 10. 验收（U7 / M2b）

- [ ] 上下两分屏够高不缩字；仅窄/矮降档；同窗可不同档  
- [ ] floor 0.8；非法配置不崩  
- [ ] 首次有效 size-allocate 后算档  
- [ ] scaled_zoom：get_zoom_data 前 reset；期间 1.0  
- [ ] D：freeze + swap 帧一次 apply；动画中不变档  
- [ ] Ctrl+0 不锁不关 E  
- [ ] `set_scale_badge` + popover + 右键锁定 + Terminal toast  
- [ ] `get_auto_font_locked` 供菜单  
- [ ] 会话无 scale；纯函数单测覆盖示例表  
- [ ] E3+E4 同发；先于 D3（或 D getattr）

---

*v2 结束。实现以本文件 + 主文档决策表 D* 为最高优先级；接口以 C `set_scale_badge` / D `pane-maximise-changed` 为准。*
