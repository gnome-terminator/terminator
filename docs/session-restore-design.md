# Terminator 会话恢复与分屏体验改进设计

> 适用代码：`TIIEHenry/terminator` @ `9f2d0b6`（2026-09-07）。文中 `file:line` 均基于该提交。
> 范围：A 布局+工作目录实时保存/恢复；B 滚动缓冲区缓存；C 分屏标题栏（Wave 风格）；D 多布局下单分屏最大化（浮层，Wave 风格）；E 按阅读列宽分档自动字号。**用户决策：本 fork 全部功能默认开启**（D1/D2/D4 已定）。

---

## 1. 背景与现状分析

### 1.1 为什么重开后不恢复

| # | 原因 | 代码位置 |
|---|---|---|
| 1 | 启动时固定加载 `default` 布局：未传 `-l` 时 `options.layout = 'default'`，随后直接 `create_layout` | `terminatorlib/optionparse.py:158-159`；`terminator:131-137` |
| 2 | 内置 `default` 只有 1 窗口 1 终端；用户不手动保存就永远是它 | `terminatorlib/config.py:282-292` |
| 3 | 退出路径不保存：最后一个窗口销毁 → `deregister_window` → `Gtk.main_quit()`，全程无 `describe_layout` / `config.save()` | `terminatorlib/window.py:295-311`；`terminatorlib/terminator.py:130-141` |
| 4 | 配置只在显式操作时写盘（首选项"添加/保存布局"） | `terminatorlib/prefseditor.py:1634-1657`、`1659-1682`；`config.py:462-466` |
| 5 | 会话插件默认未启用：`enabled_plugins` 只有 3 个 URL handler；未启用的插件在加载时被跳过 | `config.py:105-107`；`plugin.py:102-104` |
| 6 | 插件只存不取：`SaveLastSessionLayout.load_session_layout` 注释为 "not used"；`capabilities=['session']` 全仓库无人查询 | `plugins/save_last_session_layout.py:20,31-35` |
| 7 | 插件保存时机不可靠：只靠 `pre-close-term`（`window.py:305-306`）+ 每实例只存一次（`:78-81`）；还把 SIGCHLD 绑到保存（`:59-61`），任意子进程退出都会写配置；注销/关机时 X 连接断开，destroy 不一定走、Python 信号处理在 `Gtk.main()` 中被延迟 → 已知 issue #843（`CHANGELOG.md:50`） |
| 8 | 工作目录只在 `describe_layout(save_cwd=True)` 时记录；首选项的保存按钮不传该参数，只从旧配置拷贝 `directory` | `terminal.py:1961-1962`；`prefseditor.py:1674-1676` |
| 9 | 滚动缓冲区从未作为会话视觉缓存序列化/回读（插件里虽有 `get_text_range*` 用于日志/远程等，但不回填 VTE） | `plugins/logger.py` 等 |
| 10 | DBus 单实例：已有实例时，新进程只通过 DBus 请求主进程按 `default` 再开一个窗口 | `terminator:84-122`；`ipc.py:73-89` |

`CHANGELOG.md:15-20` 中 #1053、#1059–#1063（会话保存/自动保存）仅为"Closed issues"，代码中没有实现。

### 1.2 可复用的现有能力

- `Terminator.describe_layout(save_cwd)`（`terminator.py:638-646`）→ `Container.describe_layout`（`container.py:269-335`，记录窗口 position/size/maximised/fullscreen、paned ratio、notebook labels/active_page/last_active_term、窗口 last_active_window）→ `Terminal.describe_layout`（`terminal.py:1948-1966`，记录 profile/group/title/uuid/可选 directory）。
- `Terminator.create_layout(name)`（`terminator.py:216` 起）按配置中的布局名重建；`Terminal.create_layout`（`terminal.py:1968-1985`）恢复 `command`/`directory`/`uuid`；`spawn_child` 在 `terminal.py:1690-1692` 用 `self.directory` 设置 cwd。
- `layout_done`（`terminator.py:311` 起）在布局完成后统一 `spawn_child`（`:325-327`），因此 **uuid 在 spawn 之前已恢复**，可用于 B 的缓存回填。
- `get_cwd()`（`terminal.py:257-268`）优先 OSC7（`get_current_directory_uri`），失败回退 psutil（`cwd.py:15-20`）。
- `config.py:846-851` 保存布局时已有跳过 `JSON_LAYOUT_NAME`（`__internal_json_layout__`）的先例，`prefseditor.py:455-456` 同样从列表中隐藏它。

### 1.3 现有代码中的隐患（实现时必须处理）

1. **zoom/maximise 状态下 `describe_layout` 会丢失其他分屏**：`Window.zoom` 把被放大的终端直接作为窗口唯一子控件（`window.py:690-719`，`self.remove(old_child)` + `self.add(widget)`），而 `Window.get_children()` 只返回 `self.get_child()`（`window.py:613-617`），`Container.describe_layout` 递归 `get_children()`（`container.py:329-332`）。结果：放大时保存 = 只剩一个终端。
2. **拖动分隔条不会更新 `Paned.ratio`**：`ratio` 只在 Python 侧 `Paned.set_position()`（`paned.py:507-511`）或 `new_size`（`paned.py:477-481`，size-allocate 时）里更新；用户直接拖 GTK handle 只改 GTK 的 position。保存前必须用 `ratio_by_position(get_length(), get_handlesize(), get_position())`（`paned.py:488-493`）重新计算。
3. **布局值类型**：从 ConfigObj 读出的布局值都是字符串，恢复代码按字符串比较，如 `layout['maximised'] == 'True'`（`terminator.py:295-300`）、`layout['last_active_window'] == 'True'`（`window.py:1174`）、`int(...['order'])`（`notebook.py:118-119`）。会话文件若用 JSON 原生布尔值，恢复会静默失效。
4. **最后一个终端退出时**：`deregister_terminal` 在终端数为 0 时销毁所有窗口（`terminator.py:169-180`），此时 `describe_layout` 得到空布局，不能覆盖会话。

---


## 1A. 产品设计

### 1A.1 用户故事（核心场景）

| # | 作为… | 我想… | 以便… | 验收标准 |
|---|---|---|---|---|
| U1 | 每天开关 Terminator 的开发者 | 重开后窗口、tab、分屏、各终端目录和上次一样 | 不用每天重新摆布局、cd | 关闭后重开，结构/目录/窗口位置一致（**含 D5：约 10 秒内关多窗视为一次退出，全部恢复**）；20 个分屏以内 1 秒内可用 |
| U2 | 同上 | 看到上次每个分屏最后的输出 | 想起"刚才做到哪了" | 每个终端顶部显示上次内容 + 明确的"只读记录"分隔线，新提示符在其下 |
| U3 | 注销/关机/崩溃后的用户 | 也能恢复到接近崩溃前的状态 | 不因意外丢布局 | 最多丢失最近约 2 秒的布局变化 |
| U4 | 偶尔想要干净环境的用户 | 一次性"不恢复"启动，或清空会话 | 有逃生口 | `terminator --no-restore`；菜单"新会话"；首选项"清除会话与缓存" |
| U5 | 使用 tmux/vim mouse 的用户 | 在标题栏右键/齿轮打开 Terminator 菜单 | 程序吞掉右键时仍可操作 | 标题栏右键、齿轮按钮弹出与终端右键完全相同的菜单 |
| U6 | 多分屏用户 | 在多分屏布局中把一个分屏浮层最大化看清（其他分屏暗化仍可见），再平滑回去 | 不丢失上下文 | 放大时其他分屏暗化可见；动画约 200ms；Ctrl+Shift+X/按钮/点暗区可还原 |
| U7 | 密集分屏用户 | 小分屏自动小一点字号，大分屏不变 | 每个分屏都至少有一行可读宽度 | 上下两分屏不缩字；只有达不到 60 cell/24 行的分屏降档；档位可见、可关闭 |

### 1A.2 非目标（明确不做，避免期望落差）

- 不恢复正在运行的程序（vim、ssh 连接、服务器进程、shell 内存历史）。在分隔线和首选项说明中写清。
- 不自动重连 ssh / 不自动重跑命令（首版）。远程分屏恢复为本地 shell + 提示"上次此处为 user@host"。
- 不做"多套命名会话"管理（已有"布局"概念承担；可把当前会话"另存为布局"）。

### 1A.3 默认值与待决策项

| 设置 | 默认（本 fork，**用户已确认全部开启**） | 理由 | 决策 |
|---|---|---|---|
| 恢复上次会话 `restore_last_session` | **开** | 用户最核心诉求 | **D1 已定：开** |
| 屏幕内容缓存 `scrollback_cache` | **开**（私人机器：不做敏感提示/排除列表等隐私强制） | 用户明确要；0600/0700 与 TTL 仅作可靠性/磁盘卫生 | **D2 已定：开** |
| 缓存行数 `scrollback_cache_lines` | 2000 | 足够回忆上下文，磁盘可控 | — |
| 标题栏按钮 `titlebar_buttons` | **开** | Wave 风格；现有 `show_titlebar`（默认 True）已显示标题栏 | — |
| 焦点分屏绿框 `pane_accent_color` | **开**（`#3fb950`） | Wave 风格：绿框 = 当前焦点分屏 | **D13 已定** |
| 浮层最大化 `pane_overlay_maximise` | **开** | 用户明确要 | **D3 已定：M3 一次交付浮层+动画** |
| 动画 `pane_animation_expand_ms`/`restore_ms` | 200/160；`reduce_motion=system` 跟随 GNOME"减少动画"；首选项有可见开关 | 尊重无障碍设置 | — |
| 按阅读列宽缩放 `auto_font_scale` | **开**（离散档位 + 滞回 + 徽标/popover/中央提示） | 用户明确要；上下两分屏不缩字，仅窄/矮分屏降档；可锁定单终端字号 | **D4 已定：开** |
| 档位徽标 `auto_font_scale_show_badge` | **开** | 让字号变化"可解释" | — |

### 1A.4 设置界面（首选项）

- 新增顶层页 **"会话"**（位于"布局"与"快捷键"之间，`preferences.glade` 顶层 notebook）：
  - [x] 启动时恢复上次的窗口、标签页和分屏
  - [x] 同时恢复每个终端上次的屏幕内容（仅文字，保存在本机 `~/.cache/terminator`；私人机器不做敏感警告）
    - 每个终端最多保存 [2000] 行
    - 不缓存以下配置方案（profile）的终端：[多选列表]
    - （上一项关闭时本组置灰；关闭缓存会立即删除已缓存内容）
  - 按钮：**清除已保存的会话与屏幕缓存**（二次确认）；**将上次会话另存为布局…**（桥接现有"布局"概念）
  - 只读信息：上次保存时间、会话中的窗口/终端数
- "全局"页 › 外观区：
  - [x] 在终端标题栏显示 设置/最大化/关闭 按钮
  - [x] **最大化此分屏**时使用浮层效果（其他分屏暗化仍可见；不是窗口最大化）；减少动画：(•) 跟随系统 ( ) 始终减少 ( ) 始终播放
  - 焦点分屏边框颜色 [■ #3fb950]；标题栏密度 (•) 标准 ( ) 紧凑
  - [x] 窄/矮分屏自动缩小字号（至少 [60] 列、[24] 行）；**上下两分屏窗口够高则保持 100%**；档位 100%/90%/80%；[x] 显示比例
  - 屏幕缓存依赖「恢复上次会话」（关闭 A 时 B 置灰）
- "布局"页：列表中不显示内部的 `__last_session__`（已有做法），通过"会话"页的"另存为布局"导出。

### 1A.5 控制与逃生口

| 需求 | 设计 |
|---|---|
| 一次性不恢复 | `terminator --no-restore`；指定 `-l/-e/-x/--working-directory` 时本来就不恢复 |
| 强制恢复（即使配置关闭） | `terminator --restore` |
| 清空 | 首选项按钮；`terminator --clear-session`（删除会话文件与缓存后正常启动） |
| 从运行中开始新会话 | 终端右键菜单 › "会话" › "下次启动不恢复"（单次标记） |
| 恢复导致崩溃的死循环 | **崩溃保护**：恢复前写 `restoring` 标记，`layout_done` 后 10s 删除；下次启动发现标记仍在 → 跳过恢复、把会话改名为 `session.json.crashed`，在第一个终端显示一行说明 |
| 单个终端不想被记录内容 | 非需求（私人机器）；可选以后加右键开关 |
| 字号档位不想要 | 首选项开关；右键菜单"锁定此终端字号"（该终端固定 100%，直到解除） |

### 1A.6 反馈与"不意外"原则

- **恢复内容分隔线文案**（前景色 90，gettext）：`──── 以上为上次会话的输出（仅文字快照，进程未恢复）· 10-10 15:00 ────`；目录不存在 / 远程会话可追加说明行。**不**做首次「敏感信息」警告（私人机器覆盖）。
- **字号档位变化**：无动画；`90%` 徽标 + popover（说明上下两分屏够高则 100%，仅窄/矮降档）+ 中央短提示。档位在**首次有效 size-allocate（宽高>0）后**计算；`scaled_zoom` 期间暂停 E。
- **关闭有进程时确认（D17 已定）**：范围内存在**需确认的进程**（`terminal.pid` 自身或任一非 shell 后代，减去 `close_confirm_ignore`）时，弹**单个**模态 `Gtk.MessageDialog`（非 popover）；有进程时 **取代** `ask_before_closing`（合并文案），不叠两个框。无进程时仍走 `ask_before_closing`。
  - **排期**：关窗 / Ctrl+Shift+Q / 关终端 → **M1**；标题栏 ✕ → **M2**。
- **命名一致性**：D 称"单分屏最大化"（菜单/按钮："最大化此分屏"/"还原分屏"，对应现有 "Maximize terminal"，Ctrl+Shift+X）、"Zoom terminal / 缩放终端"（带字号缩放，Ctrl+Shift+Z），与窗口最大化（命令行 `-m/--maximise`）区分；按钮 tooltip 写"最大化此分屏（Ctrl+Shift+X）"。E 在界面上称"自动字号"而非"缩放"，避免与 Zoom 混淆。
- **标题栏**：保留左侧分组（group）图标与名称；新按钮在右侧；profile 关闭 `show_titlebar` 时按钮随之隐藏——右键仍可从终端区域弹菜单，文档说明这一取舍。

### 1A.7 边缘流程

| 场景 | 行为 |
|---|---|
| 多窗口关闭（**D5 已定**） | 约 10 秒内关闭的多个窗口视为一次退出，全部写入会话；超时后按仍打开的窗口保存 |
| 远程 ssh 分屏 | 目录为本地 shell 目录；**M1 不做**远程专用分隔线（CUT）；不自动重连（非目标） |
| 目录已删除/未挂载 | 回到 home，并在分隔线说明 |
| 崩溃/注销 | 防抖保存 + 信号保存；崩溃保护防止死循环 |
| 已有自定义 `default` 布局的老用户（**D6 已定**） | 会话优先；无会话时用 `default`。会话页说明"未恢复会话时使用默认布局" |
| 已有 Terminator 实例时再次启动 | 只开新窗口（不重复恢复），与现状一致 |

### 1A.8 范围与里程碑（范围审查后）

| 里程碑 | 内容 | 估计 | 说明 |
|---|---|---|---|
| **M0** | 合并真机清单 + **含 gi/PyGObject 的测试环境**（`pytest --doctest-modules` 会收进 Vte 模块） | **1 天** | |
| **M1（MVP）** | A（finalize/D5/D17）+ B 纯文本（2.5–3 天）+ 会话页；并行线见下 | **8.5–10.5 天** | U1–U4 |
| **M2** | C 标题栏；C4 `has_multiple_terms` 尽早；C6 在 A7 后 | **2.5–3 天** | 可与 M1 并行 |
| **M3** | D：D1a 占位/swap → D1b Overlay+`get_children()[0]` 审计 → D1c 放大/关闭 → D2 → D3 动画；补 prefs/快捷键 | **8–11 天** | P0 合入门槛 |
| **M2b** | E（E3+E4 同发；E3 pause API 先于 D3） | **1.5–2 天** | 可与 M3 交错 |
| 以后 / 可选 | 隐私增强（已决定不做）；`CACHEDIR.TAG` 可选。颜色、下次不恢复、外接屏归位已做。旧插件导入不做 | — | |

合计约 **22–28 人日**（审查上调）。

**全局 PR 序（可实施性审查）**：M0 → M1 三线并行（A0–A2→**A2b**→A3–A6 / A7 D17 / B1–B4；**A8+B5 同改 glade**；D0 可提前）→ M2（C6 after A7）→ M2b E → M3。串行热点：`preferences.glade`、`window.py on_destroy_event`、`terminal.py close/spawn/connect_signals`。

**成功标准**（Terminator 无遥测，用验收标准代替指标）：U1–U7 验收全部通过；自用两周内"恢复失败/布局错位"0 次、崩溃保护触发 0 次；20 分屏恢复 < 1 秒；关闭/重开无明显卡顿（保存 < 20ms）。

### 1A.9 决策汇总（用户确认：其余均按推荐锁定）

| # | 事项 | 决议 |
|---|---|---|
| D1 | 恢复上次会话默认 | **已定：开** |
| D2 | 屏幕缓存默认 | **已定：开**；私人机器不强制隐私缓解（无首次敏感提示、无命令/profile 排除强制）；0600/TTL 作可靠性 |
| D3 | D 排期 | **已定：M3 一次交付**浮层 + 动画（不拆 M3a/M3b） |
| D4 | E 默认/排期 | **已定：开**；M2b，可与 M3 并行 |
| D5 | 多窗口关闭语义 | **已定：约 10 秒内关闭的多个窗口视为一次退出**，全部写入会话（quit-all 语义） |
| D6 | 已有自定义 `default` 布局 | **已定：会话优先**；无会话时用 `default` |
| D7 | 缓存位置 | **已定：`$XDG_CACHE_HOME/terminator/scrollback`**（`~/.cache/...`） |
| D8 | 排除规则 | **已废弃（私人机器）**：不强制命令/profile/单终端排除；配置键可保留但默认空、UI 不强调 |
| D9 | TTL / 上限 | **已定：7 天；512 KB/终端；20 MB 总量**（仅磁盘卫生，非隐私） |
| D10 | `-l X` 是否成为会话属主 | **已定：否**（仅无参数启动且持锁的主实例写会话） |
| D11 | 只读 home | **已定：restore-only**（可恢复，不保存；静默） |
| D12 | OSC 窗口标题 | **已定：不保存** |
| D13 | 焦点/浮层颜色 | **已定：Wave 绿色 `#3fb950`** |
| D14 | 还原快捷键 | **已定：`Shift+Esc` 开启**（默认 `<Shift>Escape`） |
| D15 | 标题栏双击 | **已定：切换单分屏最大化**；编辑标题改到右键菜单 |
| D16 | 放大期间 `Alt+方向键` | **已定：转移最大化**到目标分屏 |
| D17 | 关闭时进程确认（pid+非 shell 后代−忽略名单） | **已定：开**，模态 `Gtk.MessageDialog` |
| D18 | E 最低档 | **已定：0.8**（tiers `['1.0','0.9','0.8']`） |
| D19 | E 下 `Ctrl+0` | **已定：只重置基础字号**，自动档位保留 |
| D20 | 标题栏密度 | **已定：标准**（24–26px） |
| D21 | 点击蒙层后焦点 | **已定：回到被放大的终端**（刻意异于 Wave「聚焦被点分屏」） |


## 2. 需求与设计

### 新增配置项汇总（`config.py` `DEFAULTS['global_config']`，`config.py:84-125`；同步 `doc/terminator_config.adoc` 与 `prefseditor.py`/`preferences.glade`）

| 名称 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `restore_last_session` | bool | `True`（**已定**，见 1A.3 D1） | 无 `-l` 启动时恢复上次会话 |
| `session_save_delay_ms` | int | `1500` | 布局变动防抖延迟（1000–2000） |
| `session_file` | str | `''` | 空则用 `$XDG_STATE_HOME/terminator/session.json`（私人单机，无 hostname） |
| `close_confirm_ignore` | list(str) | `['gitstatusd','ssh-agent','gpg-agent','dbus-daemon']` | D17：不算「需确认」的进程 basename；仅配置文件 |
| `scrollback_cache` | bool | `True`（**已定**，配首次提示；见 1A.3 D2） | 启用 B |
| `scrollback_cache_exclude_profiles` | list(str) | `[]` | B：可选；非需求 |
| `scrollback_cache_exclude_commands` | list(str) | `[]`（私人机器默认空；可选） | B：可选排除；非需求 |
| `scrollback_cache_ttl_days` | int | `7`（**已定**） | B：缓存保留天数 |
| `scrollback_cache_max_kb` | int | `512` | B：单终端上限 |
| `scrollback_cache_total_mb` | int | `20`（**已定**） | B：总量上限 |
| `scrollback_cache_lines` | int | `2000` | 每终端最多缓存行数 |
| `scrollback_cache_interval_s` | int | `20` | 批量刷写间隔（10–30） |
| `titlebar_buttons` | bool | `True` | C：标题栏显示 齿轮/最大化/关闭 按钮 |
| `pane_overlay_maximise` | bool | `True` | D：单分屏最大化使用浮层模式（兄弟分屏暗化可见）；False 回退旧 reparent/zoom 行为 |
| `pane_animation_expand_ms` | int | `200` | D：放大动画时长 |
| `pane_animation_restore_ms` | int | `160` | D：还原动画时长 |
| `reduce_motion` | str | `'system'` | D：`system`/`on`/`off`；on 时不播放缩放动画 |
| `pane_accent_color` | str | `'#3fb950'`（**已定**） | C/D：焦点分屏边框与浮层描边颜色 |
| `titlebar_density` | str | `'standard'`（**已定**） | C：`compact`/`standard` |
| （快捷键）`restore_maximised` | keybinding | `<Shift>Escape`（**已定**） | D：还原单分屏最大化 |
| `auto_font_scale` | bool | `True`（**已定**，见 1A.3 D4） | E：启用按阅读列宽分档自动缩放 |
| `auto_font_scale_show_badge` | bool | `True` | E：非 100% 时在标题栏显示档位徽标（如 `90%`） |
| `auto_font_scale_tiers` | list(str) | `['1.0','0.9','0.8']`（**已定** floor=0.8） | E：离散档位，降序；最后一档即下限（存为字符串，见下注） |
| `reading_measure_min_cols` | int | `60` | E：舒适阅读列宽下限（单位：终端单元格 cell，CJK 字占 2 cell） |
| `reading_measure_ideal_cols` | int | `0` | E：可选理想列宽（如 66）；>0 时作为升档目标，见 E.1 |
| `auto_font_scale_min_rows` | int | `10` | E：每个终端可用行数下限（0 = 不按高度判断） |
| `auto_font_scale_hysteresis` | float | `0.08` | E：升档滞回比例（8%），只作用于升档 |
| `auto_font_scale_delay_ms` | int | `150` | E：size-allocate 防抖 |

> 注 1：现有 `show_titlebar`（`config.py:244`）是 **profile 级**，`titlebar_*` 设为 global 级，避免与 profile 冲突。
> 注 2：`ConfigBase` 生成 configspec 时对 list 类型执行 `','.join(value)`（`config.py:606-607`），**DEFAULTS 中的列表元素必须是 str**，否则启动即 `TypeError`；读取后在使用处 `float()/int()` 转换并校验。
> 注 3：新增 global 键只需加到 `DEFAULTS['global_config']`，类型由默认值推导（`config.py:600-610`）。

---

### A. 布局 + 工作路径实时保存/恢复

#### A.1 新模块 `terminatorlib/session.py`

```python
class SessionManager(Borg):         # 与 Terminator/Config 同样用 borg 单例
    def mark_dirty(self, reason=''): ...   # 任何变动只调用这个
    def _flush(self):                        # GLib 防抖回调
    def save_now(self, final=False): ...     # 同步写盘；**即便 final 也要求 is_writer()**
    def finalize(self): ...                  # 统一退出：save→B flush/stop→overlay 还原
    def will_persist(self, terminal) -> bool: ...  # 供 B：uuid 是否在「下次会话」中
    def session_uuids(self) -> set | None: ...
    def load(self) -> dict | None
    def install_signal_handlers(self)
    def acquire_lock(self) -> bool           # 多实例保护
    restored_this_run: bool                  # 供 B 回填门闩
```

- 另设兜底定时器：每 60s 调一次 `mark_dirty('periodic')`（内容不变则不写盘），覆盖没有 OSC7 时 cwd 变化不触发事件的情况。
- `mark_dirty`：若 `self._timer` 为空则 `GLib.timeout_add(delay, self._flush)`；已有定时器则不重置（"最多延迟 delay"，避免连续拖动时永远不落盘）。`_flush` 返回 `False` 并清空 `_timer`。
- 在 `Terminator.doing_layout` 为 True 时（`terminator.py:221` 设 True，`layout_done` 设 False）忽略 `mark_dirty`，并在 `layout_done` 末尾主动 `mark_dirty('layout_done')` 一次。
- `save_now`：
  1. `layout = Terminator().describe_layout(save_cwd=True)`；
  2. 若布局中 Terminal 数为 0 → **不写**（保留上一份快照，见 1.3-4）；
  3. 叶子值统一 `str()`（列表元素也 str），与 ConfigObj 读出的类型一致（见 1.3-3）；注意 `uuid`/`last_active_term` 是 `uuid.UUID` 对象、`size` 是 tuple、`maximised` 是 bool，直接 `json.dump` 会失败或类型不符；
  4. 原子写：`fd, tmp = tempfile.mkstemp(dir=目录, suffix='.tmp')` → `os.fchmod(fd, 0o600)` → `json.dump` → `flush` + `os.fsync(fd)` → `os.replace(tmp, path)` → 对目录 `fsync`（见 A.8/B.7）；会话文件名 `session.json`（私人单机，无 hostname）；目录 `os.makedirs(..., mode=0o700, exist_ok=True)`；
  5. 内容未变则跳过写盘：**比较时排除 `saved_at`**（只 hash layout）；`size` 等必须是**逐元素** `str` 列表（如 `["1280","800"]`），禁止 `str(tuple)`（恢复侧 `int(parts[0])`，`terminator.py:288`）。

#### A.2 会话文件格式（`session.json`）

```json
{
  "version": 1,
  "saved_at": "2026-10-10T15:00:00+08:00",
  "terminator_version": "2.1.6+fork.1",
  "layout": {
    "child0":   {"type": "Window", "parent": "", "order": "0",
                 "position": "100:80", "size": ["1280", "800"],
                 "maximised": "False", "fullscreen": "False",
                 "title": "Terminator", "last_active_window": "True"},
    "child1":   {"type": "Notebook", "parent": "child0", "order": "0",
                 "labels": ["", "build"], "active_page": "1",
                 "last_active_term": ["9a1…", "c3d…"]},
    "child2":   {"type": "HPaned", "parent": "child1", "order": "0", "ratio": "0.42"},
    "terminal3":{"type": "Terminal", "parent": "child2", "order": "0",
                 "profile": "default", "uuid": "9a1…",
                 "directory": "/home/margaret/src/terminator"},
    "terminal4":{"type": "Terminal", "parent": "child2", "order": "1",
                 "profile": "default", "uuid": "7be…",
                 "directory": "/tmp"},
    "terminal5":{"type": "Terminal", "parent": "child1", "order": "1",
                 "profile": "default", "uuid": "c3d…",
                 "directory": "/home/margaret", "maximised_pane": "True"}
  }
}
```

`maximised_pane` 为 D 新增的可选键（见 D.6）。`command` 键**不写入**（不自动重跑命令，避免副作用）。

#### A.3 "变动"事件挂钩点（全部只调用 `SessionManager().mark_dirty()`）

| 变动 | 挂钩位置 |
|---|---|
| 分屏 split | `Paned.split_axis`（`paned.py:37`）、`Window.split_axis`（`window.py:629`）、`Notebook.split_axis`（`notebook.py:179`）末尾 |
| 关闭终端/容器变化 | `Paned.remove`（`paned.py:247`）、`Notebook.remove`（`notebook.py:239`）、`Window.remove`（`window.py:607`）；`Terminator.deregister_terminal`（`terminator.py:169`） |
| 新建/关闭/切换/重排 tab | `Notebook.newtab`（`notebook.py:278`）、`closetab`（`notebook.py:375`）；连接 `switch-page`（已有 `notebook.py:38`）；`page-reordered`（`notebook.py:62` 当前被注释，需新连一个仅标脏的 handler） |
| 拖分隔条 / 尺寸分配 | **`Paned.new_size`（`paned.py:477-481`）末尾标脏**（分配时已更新 ratio）；不依赖 `button-release`（GTK3 手势可能吞事件）。防抖在 SessionManager |
| 窗口大小/位置 | `Window.register_callbacks`（`window.py:122-131`）新增 `configure-event`；已有 `window-state-event`（`window.py:128`→`338`）中标脏 |
| cwd 变化 | `Terminal` 连接 VTE `current-directory-uri-changed`（在 `terminal.py:521` 附近与 `window-title-changed` 一起，用 `self.cnxids.new`）；VTE 0.78+ 该信号被 `termprop-changed` 取代，需 `GObject.signal_lookup` 检测后二选一。没有 OSC7 的 shell 不会触发，cwd 只能在其他事件或定时保存时由 psutil 回退取得 |
| 标题/分组/profile 变化 | `Titlebar` `edit-done`（`terminal.py:177`）、`really_create_group`（`terminal.py:681`）、`set_profile` |
| 放大/还原 | `Window.zoom`/`unzoom`（`window.py:690`/`721`）末尾，或 D 的新实现 |

`Paned.describe` 保存前修正 ratio：在 `Container.describe_layout`（`container.py:294-295`）写 `ratio` 之前，若对象是 Paned 且已 realize，则用 `ratio_by_position(self.get_length(), self.get_handlesize(), self.get_position())` 刷新 `self.ratio`。

**zoom 状态下保存（1.3-1）**，两种模式分别处理：
- D 浮层模式（默认）：终端原位置是 `PanePlaceholder`，其 `describe_layout` 委托给被放大终端（D.3），布局树完整，无需特殊处理。
- 旧 reparent 模式（`pane_overlay_maximise=False` 或 `scaled_zoom`）：新增 `Window.describe_layout(count, parent, global_layout, child_order, save_cwd)` 覆盖。若 `self.is_zoomed()`：
  1. 以 `self.zoom_data['old_child']` 作为根递归描述（而不是 `get_children()`）；
  2. 在 `Window.zoom` 中额外记录 `zoom_data['old_index']`（Paned：`old_parent.get_children().index(widget)`，即 child1=0/child2=1；Notebook：已有 `notebook_tabnum`，`window.py:706-708`）；
  3. 描述 `old_parent` 时它只剩一个子控件，需要在 `Container.describe_layout` 中检测"`self is zoom_data['old_parent']`"，在 `old_index` 位置插入 `zoom_data['widget'].describe_layout(...)`，并给它加 `maximised_pane='True'`。
  - 该路径较绕：**仅 legacy zoom / scaled_zoom** 期间 `mark_dirty` 跳过（保留放大前快照）。**浮层放大不跳过**（Placeholder 委托 + `maximised_pane`）；监听 D 的 `pane-maximise-changed` 信号标脏。final/`finalize`：legacy 可先无动画 unzoom；浮层在 **save 之后**再 `overlay_restore(animate=False)`。

#### A.4 退出与信号

- **统一退出入口 `SessionManager.finalize()`**（取代原先分散的 deregister/`save_now` 描述）：`final_saving=True` → `save_now(final=True)`（**要求 `is_writer()`，含 final**）→ `ScrollbackCache.flush_all(final=True, synchronous=True)` → `stop(join_timeout=1s)` → 各窗 `overlay_restore(animate=False)`（若有）→ 调用方再关终端 / `Gtk.main_quit()`。每步独立 try；标记 `_finalize_done` 防重入。`Window.on_destroy_event`（`window.py:295`）**开头**（close 循环前）若为本进程最后一窗则 `finalize()`，否则 `note_window_closing`（D5）；须加 `_session_destroy_handled` 幂等（快捷键路径会同步调用后又被 `destroy` 信号重入，`window.py:221-225`/`311`）。
- **Ctrl+Shift+Q / 关闭窗口 / 关终端（D17，M1）**：
  1. 范围：`scope_terminals`——特判单独 `Terminal`；Window 用 `Terminator().terminals` 中 `get_toplevel()==window` 者，并并入 legacy `zoom_data['old_child']` 子树；`PanePlaceholder` 委托 `.terminal`。
  2. 进程：`terminal.pid` 自身（basename 非 shell）+ 递归后代中非 shell 者 − `close_confirm_ignore`（默认 `gitstatusd`/`ssh-agent`/`gpg-agent`/`dbus-daemon`）。无 pty/`/proc`/`pid is None` → **保守弹确认**。
  3. 有进程：**一个** `Gtk.MessageDialog`，**取代** `ask_before_closing`；取消为默认焦点。
  4. 无进程：现有 `ask_before_closing`。
  5. API：`close_confirm.request_close_terminal(term)`；`TerminalPopupMenu.close_terminal` 委托之；**修** `key_close_term`（`terminal.py:2101`）。标题栏 ✕ → M2。
- **SIGTERM/SIGHUP**：`GLib.unix_signal_add`（或 `GLibUnix.signal_add`）→ `finalize()` → `Gtk.main_quit()` → `SOURCE_REMOVE`。主实例确定后安装。**不要** `signal.signal`，**不要** SIGCHLD。
- **X 连接断开 / 崩溃 / SIGKILL**：无法补存，依靠防抖保存，最多丢失最近 `session_save_delay_ms` 内的变动。
- `SaveLastSessionLayout` 插件：保持兼容但在文档中标注弃用；若与 `restore_last_session` 同时启用，SessionManager 安装 GLib 信号处理后插件的 `signal.signal` 会覆盖或被覆盖——在 `SessionManager.install_signal_handlers` 启动时如检测到该插件启用，打印 warning 建议禁用。

#### A.5 启动恢复

修改 `optionparse.py:158-159`：

```python
if options.layout is None:
    options.layout = 'default'
    options.layout_from_default = True   # 新标记
```

在 `terminator:127-133` 之间（主实例、`reconfigure()` 之后）：

```python
if config['restore_last_session'] and getattr(OPTIONS,'layout_from_default',False) \
   and not OPTIONS.command and not OPTIONS.execute and not OPTIONS.configjson:
    sess = SessionManager()
    if sess.acquire_lock():
        data = sess.load()          # 解析失败/版本不符 → None 并备份为 session.json.bad
        if data:
            config.base.layouts[SESSION_LAYOUT_NAME] = sanitize(data['layout'])
            OPTIONS.layout = SESSION_LAYOUT_NAME   # '__last_session__'
```

- `SESSION_LAYOUT_NAME = '__last_session__'`：在 `config.py:846-851` 的保存循环和 `prefseditor.py:455-456` 的列表过滤里与 `JSON_LAYOUT_NAME` 一起跳过，**绝不写入用户 config**。
- `sanitize`：对每个 Terminal 的 `directory`，`os.path.isdir()` 失败则改为 `os.path.expanduser('~')`；删除 `command`；未知 profile 交由 `Terminal.create_layout`（`terminal.py:1973-1975`）现有逻辑忽略。
- `create_layout` 失败已有兜底 `new_window()`（`terminator:134-136`）。
- 恢复焦点与位置：恢复后聚焦上次的活动窗口/终端（已有 `last_active_window`/`last_active_term`）；若窗口 `position` 不在任何当前显示器范围内（外接屏已拔掉），移回主显示器并按需缩小到可见区域。
- `-x/-e/--working-directory/--new-tab`、`-l X`、`--config-json`：均不恢复（用户显式意图优先）。
- 新增命令行参数（`optionparse.py`，均未与现有短参数冲突；不加短参数）：`--no-restore`、`--restore`、`--clear-session`（见 1A.5）。
- 崩溃保护：恢复前写 `$XDG_STATE_HOME/terminator/restoring` 标记，`layout_done` 后 `GLib.timeout_add_seconds(10, ...)` 删除；**`finalize`/正常退出立即清除**（避免启动后 10s 内退出被误判崩溃）；启动时若标记存在 → 跳过恢复（见 1A.5），并用 `ScrollbackCache.feed_notice` 在首终端提示。`--working-directory` 是否与恢复冲突：冲突时不恢复。

#### A.6 DBus / 多实例

- DBus 已有主实例时，第二次启动走 `ipc.new_window_cmdline`（`terminator:119-122`，`ipc.py:73-89`）→ 只新开 `default` 窗口，**不恢复**（会话已在主实例中存活）。
- `-u/--no-dbus` 多实例：会话文件只能有一个写者（另见 A.8 会话属主规则）。`acquire_lock()` 用 `fcntl.flock(lockfd, LOCK_EX|LOCK_NB)` 锁 `session.lock`；拿不到锁的实例既不恢复也不保存（只打印 dbg）。主实例退出时锁随进程释放。
- 多窗口：一个会话包含所有窗口（`describe_layout` 遍历 `self.windows`）。多窗口关闭（**D5 已定**）：约 10 秒内连续关窗视为一次退出——关窗前把即将关闭的窗口布局记入短时缓冲（合并键用 layout **child 名**，因 Window.uuid 不持久化）；缓冲期内这些终端 `will_persist=True`（B 不删缓存）；10 秒内主实例退出则 finalize 合并写入；**超时**则丢弃缓冲布局，并 `ScrollbackCache.discard_uuids(...)` 删掉仅属于已关窗的缓存。
- 隐藏窗口（`hide_window` 热键）仍在 `self.windows` 中，会被保存；恢复时正常显示。
- **逐个关闭窗口**：Terminator 没有"退出全部"动作，`close_window`（`Ctrl+Shift+Q`，`config.py:164`）只关当前窗口（`window.py:221-225` 直接调用 `on_delete_event`/`on_destroy_event`）。因此多窗口时逐个关闭，最终会话只含最后关闭的窗口——这是"退出时仍打开的窗口"语义下的预期结果，文档中写明。若后续需要"恢复全部窗口"，可新增 `quit_all` 快捷键：先 `save_now(final=True)` 并设 `final_saving=True`（之后的 mark_dirty 全部忽略），再依次销毁窗口。
- `layoutlauncher`/布局菜单打开的额外窗口（`spawn_new_terminator(..., ['-u','-l',name])`，`layoutlauncher.py:101`）是 `-u` 独立进程：拿不到锁 → 不参与会话。**已知局限**，文档说明。

#### A.7 边界与风险

- 性能：`describe_layout` 为纯内存遍历，O(终端数)；`get_cwd()` 走 OSC7 无系统调用，psutil 回退每终端一次 `/proc` 读，防抖下可忽略。
- cwd 准确性依赖 shell 发 OSC7（bash/zsh 需 `vte.sh`）；ssh、tmux 内的目录无法得到（只会是本地 shell 的目录）。
- 敏感信息：会话只含路径和标题；文件 0600。
- 恢复后 uuid 与上次一致，便于 B 关联；同一会话同时恢复两次被锁机制避免。

---


#### A.8 可靠性加固（隐私与可靠性审查）

- **会话属主规则（D10 已定）**：只有"无参数启动且持有锁"的主实例写会话；`-l X`、`-e`、`--working-directory` 等启动即使持锁也**不写**会话；`save_now` **含 final 也必须 `is_writer()`**。另起的 `-u -l` / layoutlauncher 进程不写。
- **会话轮转**：每次退出前的最终保存先把 `session.json` 轮转为 `session.json.prev`、`.prev2`（最多 2 份），恢复失败或崩溃保护触发时可从 `.prev` 恢复；首选项会话页提供"恢复上一份会话"。
- **崩溃保护**：`restoring` 标记（见 A.5、1A.5）。
- **退出路径**：信号处理与 `on_destroy_event` 中保存都包在 `try/finally`，`finally` 中保证 `Gtk.main_quit()`，任何保存异常都不能阻止退出。
- **防抖写失败**：同 B.7 的 `OSError` 处理与退避；会话写失败不影响终端使用。
- **systemd-logind**：若可用，通过 DBus 获取 `delay` 类型的 shutdown/sleep inhibitor（`org.freedesktop.login1.Manager.Inhibit("shutdown:sleep", "Terminator", "保存会话", "delay")`），收到 `PrepareForShutdown(true)` 时保存并释放；不可用时依赖防抖与 SIGTERM。
- **版本**：`version` 不认识（更新的版本写的）→ 不恢复、不覆盖，提示"会话由更新版本创建"；旧版本则按迁移函数升级。
- **`restore_directory`**：保留现有布局编辑器中用户为终端设置的 `directory`；会话恢复时以会话中的 cwd 为准。
- **`list_layouts()`**：在 `ConfigBase.list_layouts`/`Config.list_layouts` 中过滤 `__last_session__`（不只在 prefseditor），使 `--list-layouts`、layoutlauncher、右键"布局"菜单都看不到它。
- **插件迁移**：检测到 `SaveLastSessionLayout`/`SaveUserSessionLayout` 已启用时，在会话页提示"已内置会话恢复，可禁用旧插件"，并提供一次性把 `SaveLastSessionLayout` 布局导入为会话的按钮。

---

### B. 滚动缓冲区缓存（仅作视觉缓存）

#### B.1 定位

只恢复"看起来像上次"的文字，**不恢复任何进程**（vim/ssh/前台任务/shell 内存历史/环境变量/alternate screen 内容都不可恢复）。默认值见 1A.3（推荐开启并在首次恢复时提示，可按 profile 排除、可一键清除）。

#### B.2 存储

- 路径：`$XDG_CACHE_HOME/terminator/scrollback/<uuid>.txt`（缺省 `~/.cache/...`；扁平，无 hostname；**D7 已定**），uuid 取 `str(terminal.uuid)`（`terminal.uuid` 为 `uuid.UUID`，见 `util.py:338-342`；str 后为 36 位小写 hex+连字符，文件名安全；读取时用正则校验，防路径注入）。目录 0700、文件 0600。
- 内容：纯文本，最后 `scrollback_cache_lines` 行。

#### B.3 采集

- `Terminal.__init__` 中（`terminal.py:169` 附近）若开关打开，`self.cnxids.new(self.vte, 'contents-changed', self._mark_scrollback_dirty)`：只置 `self._sb_dirty = True`，不做 I/O。
- `ScrollbackCache`：定时刷写。**主线程读 VTE**，bytes 交**工作线程**写盘（工作线程禁止碰 VTE/GTK）。
  1. 主线程按版本分支取最后 N 行：优先 `get_text_range_format` / `get_text_range`（`hasattr`）；旧 VTE 回退 `write_contents_sync` 到内存流再截断；`scrollback_infinite` 时禁止全量导出堵主线程。
  2. 工作线程原子写（B 不 fsync）；哈希相同则跳过。
- 补写：`Terminal.close()`（`terminal.py:270`，在 `cnxids.remove_widget` 之前 VTE 仍可用）和 A.4 的退出/信号路径调用 `flush(term)`。
- 主动关闭某个终端时：以 `SessionManager.will_persist(terminal)` 为准（uuid 是否落入「下次将恢复的会话」——含 finalize 退出与 D5 缓冲；**不是**单纯看 `final_saving` 时序）。True → 保留；False → 删除；无 uuid → 跳过。末终端 exit 时 finalize 在 `close()` 之前，故会保留。

#### B.4 恢复

- 在 `spawn_child` 开头、`spawn_*` 之前：清洗控制字符后 **必须** `self.vte.feed(...)` 写入显示缓冲。**禁止** `Terminal.feed`（内部 `feed_child`，会送给 shell）。单测断言不调用 `feed_child`。分隔线见 1A.6。
- 回填门闩：`restored_this_run` 且每终端一次 `_scrollback_restored`（`child-exited` 回调里的「respawn」实为退出码，**不可**当布尔门闩；Relaunch 同 uuid 不得重复回填）。
- 回填内容超出 VTE `scrollback_lines` 会被正常截断，无害。

#### B.5 清理与安全（可靠性）

- 启动时清理 `*.tmp`、超 TTL 文件；持锁后再删会话中不存在的 uuid 文件。
- 关闭 B 或「清除」：停写后删除 `scrollback/`。
- 目录 0700、文件 0600、`mkstemp`+`fchmod`+`os.replace`：防止本机其他用户误读（**可靠性/多用户基本卫生**，非隐私产品需求）。
- `euid` ≠ 目录属主（如 `sudo`）：不写会话/缓存（避免提权写坏文件）。
- 回填前去掉 C0/C1 与 ESC/OSC（防止把缓存当终端指令执行——**安全可靠性**）。
- 不保存 OSC 窗口标题（D12）；保存前去掉 Window 节点里的 OSC title（`container.py:300-301`）。

#### B.7 原「隐私加固」——私人机器覆盖（第 15 轮）

**用户确认：私人个人机器，下列隐私缓解不作为需求（可整段推迟/删除实现）：**

| 项 | 状态 |
|---|---|
| 前台命令排除列表（ssh/sudo/gpg/…） | **不做**（配置键可留空默认） |
| ECHO 关闭时跳过采集 | **不做** |
| alternate screen 跳过 | **不做** |
| 脱敏 / redact | **不做** |
| 首次「可能含敏感信息」警告 | **不做** |
| 按 profile / 右键「不缓存此终端」强制 | **不做**（非 MVP） |
| `CACHEDIR.TAG` | **可选**，非必须 |
| TTL / 体积上限 | **保留**，仅磁盘卫生（D9） |
| 0600/0700、OSError 退避、属主检查、控制字符清洗 | **保留**，可靠性 |

依赖：B 仍依赖 A（关闭恢复则不回填）；设置页可一句说明，无需恐吓式文案。

#### B.6 颜色

已实现。VTE 0.72 及以上用 `get_text_range_format` 导出 HTML 再转成 SGR。更早的 VTE 没有这支 API，改读 `get_text_range` 每个单元格的颜色，按 UTF-8 字节对齐后写成 SGR。粗体没有单独字段，不保留。背景与 `get_color_background_for_draw` 相同时省略。

---

### C. 分屏标题栏（Wave 风格）

#### C.1 目标外观

```
[图标][grp] user@host: ~/src                  [90%][⚙][⤢][✕]
```
左：终端图标 + 现有分组图标/标签 + 标题（`termtext`，通常由 shell 的 OSC 0/2 设为 `user@host: cwd`）；右：E 档位徽标（仅非 100% 时）、齿轮（菜单）、最大化/还原、关闭。常驻的 `80x24` 尺寸文字不再显示（仅在调整大小时临时显示约 1 秒；现有 `title_hide_sizetext` 仍可控制）。空间不足时的折叠顺序：尺寸文字 → 分组名 → 档位徽标 → 标题省略号截断；三个按钮始终保留。

#### C.2 改动点

- `terminatorlib/titlebar.py`
  - `__init__`（`titlebar.py:40-96`）：在 `hbox` 中 `bellicon`（`:89` `pack_end`）之后再 `pack_end` 三个 `Gtk.Button`（`relief=Gtk.ReliefStyle.NONE`、`focus_on_click=False`、图标 `emblem-system-symbolic` / `view-fullscreen-symbolic`↔`view-restore-symbolic` / `window-close-symbolic`，`Gtk.IconSize.MENU`），并设 tooltip。按 `titlebar_buttons` 控制 `set_visible`。左侧 `ebox` 前插入 `Gtk.Image.new_from_icon_name('utilities-terminal-symbolic', MENU)`。
  - `TerminalPopupMenu.show(widget, event=None, anchor=None, skip_link_check=False)`（`terminal_popup_menu.py:104`）新增两个参数：`skip_link_check=True` 时跳过 `hyperlink_check_event/match_check_event`（`:116-136`，标题栏/按钮坐标不属于 VTE，会误判 URL）但保留 `event.button/time`；`anchor` 非空时用 `menu.popup_at_widget(anchor, Gdk.Gravity.SOUTH_EAST, Gdk.Gravity.NORTH_EAST, event)` 代替 `popup_at_pointer`（`:405`）。
  - 齿轮：`TerminalPopupMenu(term).show(btn, event, anchor=btn, skip_link_check=True)`——菜单贴着按钮下沿右对齐弹出，键盘激活（Enter/Space）同样可用。
  - 最大化：`maximise`/`unzoom`；单终端置灰。菜单敏感度（`terminal_popup_menu.py:278-279`）与按钮统一用 `Window.has_multiple_terms()`，禁用 `get_toplevel()==get_parent()`。
  - 关闭：`close_terminal()`；标题栏 ✕ 在 **M2** 接 D17（逻辑见 A.4）。与最大化按钮间距 6px，悬停红色。
  - 右键：`button == 3` 时先 `grab_focus()`，再 `show(..., skip_link_check=True)`，**必须 `return True`**。
  - 文档/帮助中写明终端区域内的替代方式：`Shift+右键` 绕过程序的鼠标捕获（VTE 行为）、键盘 `Menu` 键/`Shift+F10` 打开菜单。
  - 可访问性：三个按钮设置 `accessible-name`（"终端菜单"/"最大化此分屏"/"关闭终端"），tooltip 带快捷键（如 "最大化此分屏（Ctrl+Shift+X）"）。
  - 尺寸：按钮点击区域 24×24px（图标 16px），标题栏高 24–26px；`titlebar_density` 默认 **standard**（D20 已定）；另提供 `compact`（20px）。
  - 双击标题栏（**D15 已定**）：切换单分屏最大化。取消 `EditableLabel` 双击编辑；「编辑标题」→ 右键菜单，可选 **F2**。
  - 不新增"始终显示"开关：现有 profile 级 `show_titlebar`（默认 True）已经让单终端也显示标题栏（`titlebar.py:196-204`），再加一个开关会重复且令人困惑（产品审查 P1-6）。
- `terminatorlib/terminal.py`：zoom/unzoom 后调用 `self.titlebar.update_zoom_icon()`；`Window.zoom/unzoom` 结束时对相关终端调用。
- `terminatorlib/config.py`：新增 `titlebar_buttons`、`titlebar_density`、`pane_accent_color`（global）。
- `prefseditor.py`/`preferences.glade`：全局页新增两个复选框。
- 焦点色（**D13 已定**）：获得焦点的分屏用 `pane_accent_color`（`#3fb950`）画 1px 边框；D 浮层同色圆角/阴影/蒙层。
- CSS：按钮最小化 padding（`button.titlebar-btn { padding: 0 2px; min-height: 0; min-width: 0; }`），通过 `Gtk.StyleContext.add_provider_for_screen` 在 `Terminator.reconfigure`（`terminator.py:368`）中加载。

#### C.3 边界

- 标题栏高度变化会让 VTE 减少一行（`title_at_bottom` `terminal.py:187-192` 需同样支持）。
- 分组编辑（`groupentry`）与按钮共存时宽度不足：标题 `EditableLabel` 已在 `Viewport` 中可伸缩，按钮固定宽度。
- 拖拽：标题栏是 DnD 源（`terminal.py:499`），按钮需 `stop` 冒泡（`return True`），避免点击触发拖拽。
- 窗口未放大且只有 1 个终端时，最大化按钮置灰。

---

### D. 多布局下单分屏最大化（浮层，Wave 风格）

#### D.1 现状

`Terminal.maximise()` 发 `maximise` 信号（`terminal.py:1637-1639`），Paned/Notebook 把它连到 `top_window.zoom(widget, False)`（`paned.py:102,115`；`notebook.py:313-314`）。`Window.zoom`（`window.py:690-719`）：从原父容器 `remove` 终端、把窗口原子树 `remove`、把终端 `add` 到窗口；`unzoom`（`window.py:721-745`）反向。问题：瞬切无动画；放大期间布局树脱离窗口（导致 1.3-1）；其他分屏不可见。

#### D.2 目标行为

**术语与边界（用户确认）**：D 指"多布局下单布局/单分屏最大化"——在多分屏布局中，把**一个**分屏以浮层形式铺满当前标签的窗格区域（四周留边距）。左侧标签列表和原生标签条留在浮层外，仍然可以点。其他分屏**保留在原位、暗化但仍可见**于背后。
- **不是**窗口最大化（`-m/--maximise`、窗口管理器最大化，窗口尺寸不变）。
- **不是**现有的 zoom/reparent（`Window.zoom` 会把其他分屏从窗口中移除、不可见，见 D.1）；D 期间布局树完整保留、兄弟分屏不被销毁或移出窗口，仍正常运行和接收输出。
- 只对多分屏布局有效：窗口内只有 1 个终端时按钮置灰、快捷键无效。
- 界面用语："最大化此分屏"/"还原分屏"；首选项与菜单中避免单独使用"最大化"以免与窗口最大化混淆。


- 放大：终端以浮层覆盖当前标签的窗格区域（不含左侧标签列表和原生标签条），四周留 `12px` 边距、圆角 `8px`、`pane_accent_color` 描边（2px，与焦点框同色）+ 阴影；背后窗格保持原样但覆盖一层 `rgba(0,0,0,0.55)` 暗色蒙层。标签栏不暗化，点击仍切到对应标签。
- 动画：放大 `pane_animation_expand_ms`（默认 200ms，ease-out cubic `t' = 1-(1-t)^3`）；还原 `pane_animation_restore_ms`（默认 160ms，ease-in-out）。快照按**等比例**缩放（不拉伸文字），尺寸差部分用背景色填充；动画最后 80ms 快照与真实终端交叉淡入（crossfade）。动画中途再次触发 → 从当前插值位置反向播放。
- 减少动画：首选项提供可见选项"减少动画"（`reduce_motion`，默认跟随系统 `gtk-enable-animations`）；开启时直接切换，仅保留 100ms 蒙层淡入淡出。
- 退出放大：再次点最大化按钮、`toggle_zoom`（`<Shift><Control>x`）、快捷键 `restore_maximised`（**D14 已定**默认 `<Shift>Escape`；可清空；**不用单独 Esc**）、点击蒙层区域。
- 点击蒙层防误触：放大动画结束后 300ms 内忽略；仅响应按下与松开都在蒙层上的左键单击；还原后焦点回到被放大的终端（**D21 已定**）。
- 焦点与输入：放大时**先**把真实终端放到终点位置并 `grab_focus()`，快照覆盖在其上播放动画；动画期间键盘输入直接进入终端，不丢字符。还原同理。
- 放大期间 `Alt+方向键`（**D16 已定**）：**转移最大化**到目标分屏（浮层改挂目标，原分屏回占位）；不先整窗还原。标题栏双击见 C.2（D15）。
- `scaled_zoom`（`Ctrl+Shift+Z`，带字体缩放）保留旧行为，不在本需求范围。

#### D.3 结构（GTK3）与 M3 硬前置（P0）

**D3 仍一次交付浮层+动画**；M3 **内**顺序：① 遍历/关闭安全 → ② Overlay 可用 → ③ 动画。

```
Window
 └─ Gtk.Overlay
     ├─ main：原布局根
     ├─ DimLayer（蒙层）
     └─ PaneFrame → Terminal（浮层）
原位：PanePlaceholder
```

- 覆盖 `add`/`remove`/`get_children`/`get_child`。
- **P0 遍历**：覆盖 `get_terminals` / `get_visible_terminals` / 后代枚举，**必须包含**浮层中的终端。
- **P0 占位**：进入容器 children 簿记；只用包装过的 remove/add（或 pack1/2）；占位 **跳过** `connect_child`；`get_visible_terminals` 不因占位报错（跳过或委托浮层终端）。
- **P0 关闭**：所有 `close-term` / `wrapcloseterm` / `on_destroy_event` / 关窗路径，若在浮层最大化则先还原再关。
- **P0 信号**：reparent 到 PaneFrame 后显式接 `unzoom`/`maximise`/`close-term`（及 Window.add 那组 Terminal 信号）。
- **占位控件**：`PanePlaceholder` 保存放大前截图（**必须** `Gdk.pixbuf_get_from_window` + 坐标换算；**禁止**依赖 `terminal.draw(cr)`，VTE GL 常空白）。子树替换走包装过的 `swap_child` / `remove+add`（**禁止**裸 `Gtk.Paned.pack1/pack2` 绕过簿记）。Placeholder **跳过** `connect_child`；`enumerate_descendants` **委托** `placeholder.terminal`（唯一计数来源）。记录 `(parent, slot)`。常驻 Overlay 会使 `get_parent()` 变成 Overlay——优先「仅放大期插入 Overlay」，并提供 `util.logical_parent()` 审计（见子方案 D / 审查 P0）。
- **描述布局**：`PanePlaceholder.describe_layout(...)` 委托给被放大的终端（加 `maximised_pane='True'`），从而放大状态下会话保存完整（顺带解决 1.3-1）。`PanePlaceholder.get_terminals()`/导航等返回该终端。
- **reparent**：`old_parent` 中用占位控件替换终端 → 把终端放进 `PaneFrame` → `overlay.add_overlay(frame)`。终端在 Overlay 中时，信号连接（split/close/title 等）应由 Window 接管（参考 `Window.add` 中 Terminal 分支，`window.py:572-603`）；放大期间 split/rotate/move-tab/detach 先自动还原再执行（`rotate` 已有先 unzoom 的先例，`window.py:747-752`）。
- **定位**：连接 `Gtk.Overlay` 的 `get-child-position` 信号，返回当前插值矩形 `Gdk.Rectangle`；每帧 `overlay.queue_resize()`（或对 frame `queue_allocate`）。
- **动画驱动**：`frame.add_tick_callback(cb)`，用 `frame_clock.get_frame_time()`（微秒）计算进度，结束时 `return GLib.SOURCE_REMOVE`。蒙层 alpha 同步 0→0.55。`reduce_motion` 生效（`on`，或 `system` 且 `gtk-enable-animations=False`）时直接跳到终点。
- **样式**：`PaneFrame` 加 CSS class `pane-maximised`：`border: 2px solid <pane_accent_color>; border-radius: 8px; padding: 2px;` + `box-shadow`。VTE 自身不会裁剪成圆角，圆角由 frame 的 padding 留白呈现即可（不对 VTE 做 shape mask）。
- **蒙层**：`DimLayer.draw` 中 `cr.set_source_rgba(0,0,0,alpha); cr.paint()`；`overlay.set_overlay_pass_through(dim, False)` 使其吃掉点击，`button-press-event` → 还原。

#### D.4 快照与 VTE

- **P0 快照**：reparent **前** `Gdk.pixbuf_get_from_window(...)`。禁止依赖 `terminal.draw(cr)`（VTE GL 常空白）。失败 → **无动画**直达终态，功能仍可用。
- 真实终端先就位并聚焦；SnapshotArea 等比缩放；末 80ms crossfade；`reduce_motion` 跳过缩放动画。
- 禁止动画中每帧改 VTE 分配。

#### D.5 改动点汇总

| 文件 | 函数 | 改动 |
|---|---|---|
| `window.py` | `__init__`/`register_callbacks`（`:122-131`） | 创建 `self.overlay`，`Gtk.Window.add(self, overlay)`；连 `get-child-position` |
| `window.py` | `add`/`remove`/`get_children`（`:568-617`），新增 `get_child` | 改为操作 overlay 主子控件 |
| `window.py` | `zoom`/`unzoom`（`:690-745`） | `font_scale=False` 且 `pane_overlay_maximise` → 走新 `overlay_maximise/overlay_restore`；`font_scale=True`（scaled_zoom）保留旧逻辑 |
| `window.py` | `is_zoomed`（`:681`） | 浮层模式同样设置 `term_zoomed` 属性，保证菜单（`terminal_popup_menu.py:278`）、`key_toggle_zoom` 等无需改动 |
| 新 `terminatorlib/paneoverlay.py` | `PanePlaceholder`、`PaneFrame`、`DimLayer`、`SnapshotArea`、`Animator` | 新增 |
| `paned.py`/`notebook.py` | 在 old_parent 中替换子控件的辅助函数 | 占位/还原 |
| `terminal.py` / `config.py` | `on_keypress`、`keybindings` | 新快捷键 `restore_maximised`（**已定** Shift+Esc） |
| `terminator.py` | `reconfigure`（`:368`） | 加载 CSS provider |
| `container.py` | `describe_layout`（`:269`） | 支持占位控件委托 |

#### D.6 与会话（A）的交互

- 保存：放大状态下保存完整布局，被放大终端带 `maximised_pane='True'`。
- 恢复：`layout_done` 之后（`terminator.py:311-359`，`present_with_time` 之后）用 `GLib.idle_add` 对带该键的终端调用 `maximise()`，**不播放动画**（直接终态）。
- 每窗口最多一个放大终端；若数据中有多个，只取第一个。

#### D.6.1 放大期间的边界情况

- **被放大的终端退出**（`exit`/`close-term`）：先无动画还原（把占位从原父容器移除，相当于该终端在原位置关闭），再走正常 `closeterm` 逻辑；不要把已销毁的终端放回原位置。
- **背后其他分屏退出**：原 Paned 可能塌缩、占位控件被移到祖父容器。还原时**以占位控件当前的 `get_parent()` 为准**，不要用放大时记录的 `old_parent`。
- **Notebook 中放大后切换 tab**：在 `switch-page`（`notebook.py:38`）中若当前窗口处于浮层放大，先无动画还原再切换。
- **窗口尺寸变化**（最大化窗口、拖窗口边）：浮层矩形按窗口实时计算（`get-child-position` 每次分配重算），不需要动画。
- **detach-tab、拖拽终端、分组广播**：放大期间禁用拖拽/detach；分组广播不受影响（终端仍在 `Terminator().terminals` 中）。
- **动画进行中再次点击**：忽略或反转方向（以当前插值进度为起点反向播放），不得叠加两个 tick callback。

#### D.7 风险

- Overlay/`get_child` 语义；漏改遍历 → 关确认/广播漏终端（P0 必测）。
- 占位簿记错误损坏 Paned；pixbuf 失败则无动画。
- HiDPI `get_scale_factor()`；放大期禁用拖拽/detach。

---

### E. 按分屏大小自动缩放字体（**默认开启**，见 1A.3 D4）

#### E.1 行为（按"舒适阅读列宽"逐终端分档）

**依据（为什么用阅读列宽而不是分屏数量）**

- 排版学的"行长 / measure"：西文正文每行 45–75 字符较舒适，约 66 字符为理想值（Bringhurst《The Elements of Typographic Style》）；中文正文每行约 30–40 字较舒适。
- 终端按**单元格（cell）**计列：ASCII 字符占 1 cell，CJK 全角字符占 2 cell（VTE 的 `get_column_count()` 本身就是 cell 数）。因此阈值直接用 cell 表示即可同时照顾中英文：60 cell ≈ 60 个西文字符 ≈ 30 个汉字，落在两者的舒适区间下沿；80 cell ≈ 40 个汉字为中文舒适区上沿。
- 终端里的代码/日志常按 80 列排版，但"能读"比"不折行"更重要：低于约 60 cell 时，提示符+路径就占去大半行，命令输出频繁折行，阅读效率明显下降；而字号过小同样不可读——所以既要设列宽下限，也要设档位下限（floor）。
- 结论：判断依据是**该终端自己的可用宽度是否达到舒适阅读列宽**，而不是"分了几屏"。上下分屏不缩宽度，就不该缩字；只有密集网格里过窄/过矮的小分屏才降档。

**参数**

- `tiers = auto_font_scale_tiers`（严格降序，首项 1.0；**D18 已定** `['1.0','0.9','0.8']`，floor=0.8）。
- `MIN_C = reading_measure_min_cols`（默认 60 cell）；`IDEAL_C = reading_measure_ideal_cols`（默认 0 = 不用；可设 66）；`MIN_R = auto_font_scale_min_rows`（默认 10，宽度为主，仅极矮窗格按行缩；0 = 不看行数）；`h = auto_font_scale_hysteresis`（默认 0.08）。
- 以中文为主的用户可把 `MIN_C` 调到 64–80（≈ 32–40 个汉字）。

**计算（每个终端独立，与分屏数量无关）**

1. 基础字号下的单元格尺寸：`base_cw = vte.get_char_width() / cur_scale`，`base_ch = vte.get_char_height() / cur_scale`（除以当前 scale，避免缩小后列数变多导致判定振荡）。
2. 可用列/行（基础字号）：`cols0 = floor(avail_w / base_cw)`，`rows0 = floor(avail_h / base_ch)`，`avail_w/h` 取 VTE 自身分配（已扣标题栏、滚动条、padding）。档位 s 下：`cols(s) = floor(cols0 / s)`，`rows(s) = floor(rows0 / s)`。
3. `ok(i) = cols(tiers[i]) >= MIN_C and (MIN_R == 0 or rows(tiers[i]) >= MIN_R)`。
4. **降档**：当前档 `cur` 若 `not ok(cur)` → `cur += 1`，逐档重复，直到 `ok(cur)` 或到 floor（floor 仍不满足就停在 floor）。
5. **升档（带滞回）**：否则若 `cur > 0`，检查上一档：`cols(tiers[cur-1]) >= UP_C` 且 `(MIN_R == 0 or rows(tiers[cur-1]) >= ceil(MIN_R*(1+h)))`，其中 `UP_C = max(ceil(MIN_C*(1+h)), IDEAL_C)`；满足则 `cur -= 1`，逐档重复。即"更大一档仍能满足阅读列宽（并留出余量）才升档"。
6. 一次计算只走一个方向；逐档在内存完成，**最终只在 `cur != self._font_tier` 时调用一次** `vte.set_font_scale(tiers[cur])`。

**示例**（窗口 160 cell × 50 行，基础字号，MIN_C=60、MIN_R=10、h=0.08 → 升档需 ≥65 列/≥11 行，IDEAL_C=0）

| 场景 | 该终端 cols0×rows0 | 逐档判断 | 结果 |
|---|---|---|---|
| 单分屏 | 160×50 | 1.0 满足 | 100% |
| 上下两分屏 | 160×24 | 1.0 满足 | 100% |
| 左右两分屏 | 79×50 | 1.0 满足（79 ≥ 60） | 100% |
| 2×2 网格 | 79×24 | 1.0 满足 | 100% |
| 左右三分屏 | 52×50 | 0.9→57 ✗，0.8→65 ✓ | 80% |
| 3×3 网格 | 52×15 | 0.9→57×16 ✗，0.8→65×18 ✗（行不足） | 停在 floor **80%** |
| 3×3 网格，`MIN_R=0` | 52×— | 0.8→65 ✓ | 80% |
| 某分屏 59 列 | 59×50 | 0.9→65 ✓ | 90% |
| 该分屏拉宽到 62 列（当前 90%） | 62×50 | 升到 1.0 需 62 ≥ 65 ✗ | 保持 90% |
| 再拉宽到 65 列 | 65×50 | 65 ≥ 65 ✓ | 100% |
| 三分屏合并回两分屏（当前 80%） | 79×50 | 0.9 档 87 ≥ 65 ✓ → 1.0 档 79 ≥ 65 ✓ | 100% |

> 上下分屏能否保持 100% 也取决于窗口高度：窗口低于约 50 行时每个分屏不足 24 行会降档；不想按高度降档可设 `MIN_R=0`。

- 同一窗口内不同终端可处于不同档位（大分屏 100%、旁边窄分屏 80%），符合"每终端独立"。
- 配置校验：tiers 严格降序、都在 (0, 1]、首项 1.0；`MIN_C ≥ 1`；`IDEAL_C == 0 或 IDEAL_C ≥ MIN_C`；`MIN_R ≥ 0`；`0 ≤ h < 1`；否则 dbg 警告并禁用 E。

#### E.2 实现方式：`Vte.Terminal.set_font_scale` 而非改 FontDescription

- 现有字号路径：`zoom_in/zoom_out/zoom_font`（`terminal.py:1857-1877`）通过 `set_font(pangodesc)`（`terminal.py:1889-1891`）修改字体并记录 `custom_font_size`；`reconfigure` 在 `custom_font_size` 为空时按配置重设字体（`terminal.py:774`）；`zoom_orig`（`terminal.py:1879-1887`）恢复配置字体。
- E 使用 `vte.set_font_scale(tier)`（VTE 2.91 API 即有，与字体描述正交）：
  - 用户 Ctrl+/−/0（`config.py:131-133`）改的是**基础字号**，自动缩放在其上相乘，二者互不覆盖；
  - `reconfigure` 重设字体不会清掉 scale；
  - 会话/布局只保存基础字号或根本不保存字号（`describe_layout` 当前不记录字体），**绝不保存 scale**；需求说明里明确：若将来要保存字号，存 `custom_font_size`（基础值）。
- 不用改 FontDescription 的原因：会与 `custom_font_size`、`zoom_orig`、`scaled_zoom`（`Window.zoom` 的 `font_scale=True` 分支，`zoom_scale` `terminal.py:1596` 起直接 `set_font`）互相覆盖。

#### E.3 改动点

| 文件 | 函数 | 改动 |
|---|---|---|
| `terminal.py` | `on_vte_size_allocate`（`:1562`） | 防抖 `update_auto_font_scale()`；**宽高>0 的首次分配后**才算档。`scaled_zoom` 期间暂停 E 并 `set_font_scale(1.0)`，结束后重算 |
| `terminal.py` | 新增 `update_auto_font_scale()` | 读 `self.vte.get_allocated_width/height()`、`get_char_width/height()`、`get_font_scale()`，按 E.1 先判断降档、否则判断升档（逐档循环、仅升档带滞回，升档阈值 `UP_C`）；档位不变则返回，否则一次 `set_font_scale` 并记录 `self._font_tier` |
| `terminal.py` | `zoom_font`/`zoom_orig` | 不变（基础字号）；之后调用 `update_auto_font_scale()`。**D19 已定**：`Ctrl+0` 只重置基础字号，**不**取消自动档位、**不**锁定 100% |
| `paned.py` | `split_axis`（`:37`）、`remove`（`:247`）、`on_button_release`（`:160`） | 不在这里决定档位，只在结构变化/拖动结束后让子树终端各自重算一次（拖动过程中只靠 size-allocate 防抖） |
| `window.py` | `zoom`/`unzoom`（`:690`/`:721`）及 D 的浮层 | 进入 `scaled_zoom`（font_scale=True）时暂停 E 并 `set_font_scale(1.0)`，unzoom 后恢复；D 动画期间暂停 E，结束后重算一次 |
| `config.py` | `DEFAULTS['global_config']` | 新增 `auto_font_*` 键（见配置表） |
| `prefseditor.py`/`preferences.glade` | 全局页 | 开关 + `reading_measure_min_cols` + 显示徽标（三项；档位/滞回仅配置文件） |

#### E.4 优缺点与风险

- 优点：分屏后每个 pane 能看到更完整的行（编译输出、日志不折行），切回单屏自动恢复。
- 缺点/风险：
  - **可读性**：小于 ~8pt 难以阅读，**下限 0.8**（D18）；默认不放大（上限 1.0）。
  - **VTE 重排与 SIGWINCH**：字号变化 → 行列数变化 → VTE rewrap + 向 PTY 发窗口大小变化，vim/htop/less 等 TUI 会重绘；必须防抖，拖动分隔条时只在稳定后改一次。
  - **反馈回路**：字号变化不改变容器分配，但开启 `geometry_hinting` 时 `on_vte_size_allocate` 会调用 `deferred_set_rough_geometry_hints`（`terminal.py:1565-1567`），窗口可能按字符网格对齐而改变大小 → 再触发 size-allocate。缓解：离散档位 + 滞回 + 仅档位变化时应用 + 同一终端 500ms 内最多切换一次档位。
  - **用户困惑**：同一窗口中不同 pane 字号不同；标题栏可显示当前档位如 `90%` 提示（复用 `sizetext`，`titlebar.py:215-218`）。
  - **与 D 交互**：浮层放大后终端变大 → scale 回到 1.0，正是期望；动画期间暂停 E，避免每帧改字号。
  - **与 A 交互**：恢复布局时字号由分配推导，天然一致；不需要也不应保存 scale。
  - **与分组广播/多窗口**：无影响。
- **与 B 回填**：缓存文本在 spawn 前 feed，档位变化后 VTE 会按新列数 rewrap，显示正常。

---

---

### 2.F 实现清单（按文件）

| 文件 | 新增/修改 | 需求 |
|---|---|---|
| `terminatorlib/util.py` | 新增 `get_state_dir()` / `get_cache_dir()`（仿 `get_config_dir`） | A、B |
| `terminatorlib/session.py`（新） | `SessionManager`（mark_dirty/save_now/**finalize**/will_persist/session_uuids/load/锁/信号）、`SESSION_LAYOUT_NAME` | A |
| `terminatorlib/scrollback.py`（新） | `ScrollbackCache`（flush_all/stop/discard_uuids/clear_all/feed_notice） | B |
| `terminatorlib/close_confirm.py`（新） | 进程探测、`request_close_terminal`、D17 对话框 | A/D17 |
| `terminatorlib/paneoverlay.py`（新） | `PanePlaceholder`、`PaneFrame`、`DimLayer`、`SnapshotArea`、`Animator` | D |
| `terminator`（入口） | 主实例确定后：`install_signal_handlers()`；恢复判断（A.5） | A |
| `optionparse.py:158-159` | `layout_from_default` 标记 | A |
| `config.py` | DEFAULTS 新键；保存循环跳过 `__last_session__`（`:846-851`） | A–E |
| `prefseditor.py:455-456` 及全局页 | 隐藏 `__last_session__`；新增开关 | A–E |
| `terminator.py` | `layout_done` 末尾 mark_dirty + 恢复放大态；`deregister_terminal` mark_dirty；`reconfigure` 加载 CSS | A、C、D |
| `window.py` | `on_destroy_event` 开头 final save；`configure-event`/`window-state-event` 标脏；Overlay 包装与 `get_child` 覆盖；浮层 zoom/unzoom | A、D |
| `container.py:269-335` | ratio 刷新；占位委托；旧 zoom 模式描述 | A、D |
| `paned.py` / `notebook.py` | 结构变动/拖动结束标脏；占位替换辅助；E 重算触发 | A、D、E |
| `terminal.py` | `current-directory-uri-changed`、`contents-changed` 标脏；`close()` 刷缓存；`spawn_child` 回填；`update_auto_font_scale`；放大图标刷新 | A、B、C、E |
| `titlebar.py` | 图标、三个按钮、右键菜单、E 档位徽标 | C、E |
| `plugins/save_last_session_layout.py` | 不改；SessionManager 检测到其启用时警告 | A |
| `doc/terminator_config.adoc`、`tests/` | 配置文档、单测 | 全部 |

## 3. 测试计划

### 3.1 单元测试（`tests/`，pytest，无需显示器的部分）

- `session.py`：值字符串化、`sanitize`（不存在目录 → home、移除 command）、原子写（模拟写一半异常时旧文件保持不变）、0 终端不覆盖、内容未变不写、锁（两个进程同时 `acquire_lock` 只有一个成功）。
- 会话 JSON 版本不符/损坏 → 返回 None 并改名 `.bad`。
- `ScrollbackCache` 截取最后 N 行、`\n`→`\r\n`、孤立文件清理、文件权限 0600。
- `config.save()` 不写出 `__last_session__`。

### 3.2 集成/手工（Xvfb + `terminator -u -d` 或真实桌面）

| 场景 | 期望 |
|---|---|
| 2 窗口、tab+分屏、各终端 cd 不同目录 → Ctrl+Shift+Q → 重开 | 结构、窗口位置大小、ratio、tab 标签、活动 tab、目录一致 |
| 拖分隔条后 2s 内 `kill -9` | 新 ratio 已保存（防抖已落盘） |
| `kill -TERM`/`kill -HUP` 主进程 | 保存后退出 |
| 注销桌面会话 | 会话最多丢失最近 1.5s 变动 |
| 删除某目录后重开 | 该终端落在 home，无报错 |
| `terminator -l foo` / `-e cmd` / `--working-directory` | 不恢复，会话文件不被启动覆盖 |
| 已有实例时再启动 | 只新开 default 窗口 |
| 两个 `-u` 实例 | 只有第一个读写会话 |
| 最后一个终端里 `exit` | 会话保留上一份非空快照 |
| 放大某分屏（旧模式与浮层模式）时退出 → 重开 | 全部分屏恢复，且该分屏处于放大态 |
| B 开启：`seq 1 5000` 后退出重开 | 显示最后 2000 行 + 灰色分隔线，新提示符在下方 |
| B：关闭单个终端 | 其缓存文件被删除 |
| C：tmux mouse on 时右键标题栏 | 弹出 Terminator 菜单 |
| C：齿轮/最大化/关闭按钮 | 同菜单；关闭有确认；单终端时最大化置灰 |
| D：放大/还原动画 | 约 200ms、无明显卡顿；动画期间 vim 只收到 1 次 SIGWINCH（可用 `trap 'echo WINCH' WINCH` 验证） |
| D：放大中按 split/rotate/拖拽 | 先还原再执行或被禁用，无崩溃 |
| 兼容：启用旧 SaveLastSessionLayout 插件 | 打印警告，功能不冲突 |
| E 开启：单屏 → 上下分屏（窗口 ≥ 50 行） | 两个终端都保持 100% |
| E：左右两分屏（各约 79 列） | 保持 100%（≥ 60 cell） |
| E：输出中文为主的内容 | 列宽按 cell 计算，60 cell ≈ 30 汉字；调到 `MIN_C=80` 后按 40 汉字判断 |
| E：单屏 → 左右三分屏 → 关闭一侧 | 三分屏时约 52 列 → 降到 80%；变回两分屏后满足 ≥ 65 列即逐档回到 100% |
| E：3×3 网格 | 每个终端逐档降级，最多到 floor（80%），不再更小 |
| E：同一窗口一大一小两分屏 | 大的 1.0、小的降档，互不影响 |
| E：拖分隔条使列数在 60 附近反复跨越 | 降到 90% 后需 ≥ 65 列才回到 100%，不来回切换 |
| E：配置非法（档位非降序/阈值长度不符） | 打印警告并禁用 E，不崩溃 |
| E：分屏后 Ctrl+加号 / Ctrl+0 | 基础字号变化，自动缩放在其上重新计算，不互相覆盖 |
| E：拖动分隔条 | 松开后约 150ms 才调整一次字号；vim 不持续闪烁 |
| E + geometry_hinting 开启 | 无窗口尺寸来回抖动 |

### 3.2b 可靠性测试

- 回填使用 `vte.feed`，断言未调用 `feed_child`。
- 目录/文件 0700/0600；属主不符或 `sudo` 时不写坏文件。
- 控制字符/OSC 回填不改变剪贴板或标题。
- 磁盘满 / 只读 home：不崩溃、不挡退出；restore-only。
- `-l foo` 退出不覆盖日常会话；损坏会话不覆盖；`--list-layouts` 无 `__last_session__`。
- TTL 到期文件启动后删除。
- D17：有后代进程时只弹一个对话框；无进程走 `ask_before_closing`。

### 3.3 性能

- 50 个终端时 `save_now` 耗时 < 20ms（`time.perf_counter` 打 dbg）。
- B：10 个终端各 10 万行 scrollback（`scrollback_infinite`）时刷写不阻塞 UI > 50ms；否则改为每次 tick 只刷 1–2 个终端（轮转）。

---

## 4. 实施顺序、工作量与验收

### 4.1 里程碑与任务

| 里程碑 | 任务 | 估计 |
|---|---|---|
| M0 | 真机清单 + gi 测试环境 | 1 天 |
| M1 | A + D17 + finalize/D5/will_persist + 会话页（含 A2b） | 6–7.5 天 |
| M1 | B：`vte.feed`、同步最终 flush、TTL/0600、与 D5 discard_uuids | 2.5–3 天 |
| M2 | C（C4 早合入） | 2.5–3 天 |
| M3 | D 拆 D1a/b/c + 动画 + prefs | 8–11 天 |
| M2b | E（E3+E4 同发） | 1.5–2 天 |
| 以后 | 隐私增强不做；`CACHEDIR.TAG` 可选。颜色、下次不恢复、外接屏归位已做。旧插件导入不做 | — |

### 4.2 M1 暴露的配置项（精简）

首选项界面只暴露：`restore_last_session`、`scrollback_cache`、`scrollback_cache_lines`、`scrollback_cache_exclude_profiles`、"清除"/"恢复上一份会话"/"另存为布局"按钮。其余（`session_save_delay_ms`、`session_file`、`scrollback_cache_interval_s`、`*_max_kb`、`*_total_mb`、`*_ttl_days`、`*_exclude_commands`）只在配置文件中可改，文档化但不进 UI。M2 增加 `titlebar_buttons`、`titlebar_density`、`pane_accent_color`；M2b 增加 `auto_font_scale`、`reading_measure_min_cols`、`auto_font_scale_show_badge`（默认均开）；M3 增加 `pane_overlay_maximise`、`reduce_motion`。

### 4.3 与上游合并的可能性

| 部分 | 可合并性 | 说明 |
|---|---|---|
| A（会话恢复） | 高 | 上游有多个相关 issue（#843、#1053、#1059–#1063）；默认值上游可能要求关闭 |
| B（缓存） | 中 | 隐私顾虑，上游大概率要求默认关闭 |
| C（标题栏按钮/右键） | 高 | 改动小、可配置 |
| D（Overlay 最大化） | 低–中 | Window 结构改动大，需保留 `pane_overlay_maximise=False` 的旧行为 |
| E（自动字号） | 低 | 偏个人偏好 |

建议各里程碑独立 PR，fork 中的默认值（D1/D2/D4 及 C/D 全部开启）与上游 PR 的默认值（关闭）分开处理。

### 4.4 各里程碑验收标准

- **M1**：U1–U4（含 D5）；D17 单对话框；`vte.feed` 单测；0600/TTL/OSError；20 分屏 <1s；崩溃保护。
- **M2**：U5；「最大化此分屏」；`has_multiple_terms`；D15；button==3 返回 True；✕→D17。
- **M3**：U6；P0 遍历/关闭/占位/pixbuf；动画或降级；Alt+方向键转移最大化；Shift+Esc；D21。
- **M2b**：U7；floor 0.8；size-allocate 后算档；scaled_zoom 暂停；Ctrl+0 只重置基础字号。

## 5. 审查记录

> 第 1–12 轮中与「默认关闭 / E 推迟 / D 拆分 / 待确认」冲突的结论 **已废弃**。隐私强制项以 **第 15 轮私人机器覆盖** 为准。


### 第 1 轮：正确性（逐条核对 file:line 与 API）

- 修正行号：`global_config` 范围（`config.py:84-125`）、窗口 maximised 恢复（`terminator.py:295-300`）、`Container.describe_layout` 结束行（`:335`）、`Terminal.create_layout` profile（`:1973-1975`）、`really_create_group`（`terminal.py:681`）、`layout_done` 范围（`:311-359`）、rotate 先还原（`window.py:747-752`）、zoom 记录 tab 号（`window.py:706-708`）。
- 发现 `terminal.uuid` 是 `uuid.UUID` 对象（`util.py:338-342`），不带 `urn:uuid:` 前缀；修正示例 JSON 和缓存文件名说明，并要求 JSON 序列化前 str 化（UUID/tuple/bool 直接 dump 会失败或类型不符）。
- 发现恢复代码按字符串比较（`== 'True'`、`int(order)`），确认会话文件必须把叶子值字符串化。
- 发现 `ConfigBase` 生成 configspec 时对列表执行 `','.join`（`config.py:606-607`），E 的档位/阈值默认值必须是字符串列表，否则启动 TypeError。
- API 核对：`write_contents_sync` 只有 `WriteFlags.DEFAULT`（纯文本）；HTML 导出为 `get_text_range_format`（0.72+，需 hasattr）；`set_font_scale` 与 `set_font` 正交；`current-directory-uri-changed` 在 VTE 0.78+ 被 `termprop-changed` 取代，需探测；GTK3 `Gtk.Overlay` 的 `get-child-position`、`set_overlay_pass_through`（3.18+）、`add_tick_callback`（3.8+）可用；信号用 `GLib.unix_signal_add`（新 PyGObject 为 `GLibUnix.signal_add`，需兼容）。
- 本环境未安装 PyGObject/VTE，API 结论基于公开文档，需在目标机上用 `hasattr` 与版本号实测。

### 第 2 轮：设计缺口与边界

- **zoom 下保存会丢分屏**（`Window.zoom` reparent + `get_children` 只返回当前子控件）：增加两种模式下的处理，首版旧模式在 zoom 期间不更新快照。
- **拖分隔条不更新 `Paned.ratio`**：保存前按当前 position 重算 ratio。
- **最后一个终端 `exit`** 会导致空布局：0 终端不覆盖会话。
- **保存时机**：`on_destroy_event` 先关闭终端再 deregister，final save 必须挪到函数开头；SIGCHLD 不再处理；增加 60s 兜底定时器（无 OSC7 时 cwd 不触发事件）。
- **多窗口语义**：没有"退出全部"动作，逐个关窗只保留最后一个窗口，已写明并给出 `quit_all` 扩展方案。
- **多实例**：`-u`/layoutlauncher 子进程用 `flock` 排他锁，只有持锁实例读写会话；DBus 已有实例时不恢复。
- **D 放大期间**：被放大终端退出、背后分屏塌缩（以占位控件当前父容器为准）、切换 tab、窗口改尺寸、动画中重复点击、detach/拖拽，均补充了处理规则。
- **安全**：会话/缓存 0600、目录 0700；缓存默认关闭；文件名由 uuid 正则校验；关闭单个终端即删除其缓存；启动清理孤立文件。
- **性能**：防抖不重置（最多延迟一个周期）、内容不变不写盘；B 用"最后 N 行"代替全量导出，避免 `scrollback_infinite` 卡顿；D 用快照动画，避免每帧 SIGWINCH；E 用离散档位+滞回，防止与 `geometry_hinting` 形成反馈回路。
- **兼容**：`__last_session__` 与 `__internal_json_layout__` 一样不写入 config、不在首选项中显示；旧 SaveLastSessionLayout 插件保留但启用时警告；`scaled_zoom` 保留旧行为，E 在其期间暂停。

### 第 3 轮：清晰度与可实施性

- 把含糊的"zoom 状态描述"段落改写为分步骤实现说明。
- 增加按文件列出的实现清单（2.F），每个需求都能对应到具体文件和函数。
- E 按要求改为离散档位：明确了选档公式（以基础字号下的列/行数判定）、滞回规则与数值示例、仅档位变化时应用、配置校验规则。
- 配置表补全类型与默认值，并注明 list 必须为字符串列表、global 与 profile 级的区别。
- 测试计划按需求补充可验证的期望（例如用 `trap WINCH` 验证动画期间只收到一次 SIGWINCH，以及滞回不来回切换）。

### 第 4 轮：D（浮层最大化）与 E（分档字号）专项复核

- **E 判定逻辑按要求重写**：去掉"按分屏数量/窗口比例/阈值列表"的做法，改为每个终端只看自己在基础字号下的可用列/行数，对比绝对阈值（默认 80 列 × 24 行）；逐档降级直到满足或到 floor；升档带滞回（只作用于升档）；逐档在内存计算、最终只 `set_font_scale` 一次。配置项相应改为 `auto_font_scale_min_cols`/`auto_font_scale_min_rows`（int），删除列表阈值。（列宽阈值与键名已在第 5 轮更新为 `reading_measure_min_cols`=60，见下。）
- **E 增加数值示例表**，验证"上下两分屏保持 100%、只有密集网格中的小分屏降档、到 floor 停止、滞回防抖"。
- **E 发现的隐患**：上下分屏能否保持 100% 取决于窗口高度（< ~50 行时每个分屏 < 24 行会降档），已在文中注明，并说明 `MIN_R=0` 可只看宽度。
- **E 判定必须用基础字号下的列/行**（除以当前 scale），否则缩小后列数变多会立刻触发升档，形成振荡；已写入公式。
- **D 复核**：确认文档覆盖了浮层结构（Overlay + 占位控件 + 绿色圆角边框 + 暗色蒙层）、ease-out 动画（`add_tick_callback` + `get-child-position`）、快照动画避免 VTE 每帧 reflow/SIGWINCH、退出方式（按钮/`toggle_zoom`/可选 Shift+Esc/点击蒙层）、与会话保存的关系（`maximised_pane` 键、恢复时无动画）、改动点表与风险（`Window.get_child` 语义变化为最高风险）。
- **D × E 交互**：动画期间暂停 E，动画结束后按浮层尺寸重算一次（通常回到 1.0），还原后再按原分屏尺寸重算；`scaled_zoom` 期间 E 暂停并将 scale 置 1.0。已写入 E.3/E.4。
- **D 补充确认**：放大期间被放大终端退出、背后分屏塌缩、切 tab、动画中重复点击的处理规则均在 D.6.1 中。

### 第 5 轮：E 改为"舒适阅读列宽"后的全文一致性复核

- **E 判定依据**改为排版学阅读列宽：西文 45–75 字符（理想约 66）、中文约 30–40 字；终端按 cell 计数，CJK 字占 2 cell，因此默认 `reading_measure_min_cols=60` cell（≈ 60 西文字符 ≈ 30 汉字），并说明中文为主可调到 64–80。
- **配置项统一**：`auto_font_scale_min_cols` 改名为 `reading_measure_min_cols`（默认由 80 改为 60）；新增可选 `reading_measure_ideal_cols`（默认 0；>0 时作为升档目标 `UP_C = max(ceil(MIN_C*(1+h)), IDEAL_C)`）；`auto_font_scale_min_rows`、`auto_font_scale_hysteresis`、`auto_font_scale_tiers` 保留。全文已无旧键名和旧阈值列表。
- **示例与测试同步**：阈值从 80 改为 60 后，左右两分屏（79 列）和 2×2 网格不再降档；改用左右三分屏、3×3 网格、59→62→65 列的边界场景说明降档与滞回；测试计划中的期望值同步更新（≥ 65 列才回 100%）。
- **单位一致**：列数一律按 cell；行数滞回取 `ceil(MIN_R*(1+h))`（24 → 26）；各处百分比/小数表示统一按档位说明。
- **与其他需求一致性**：E.2（`set_font_scale` 与用户 Ctrl+/− 基础字号正交、不保存 scale）、E.3（D 动画期间暂停、`scaled_zoom` 时置 1.0）、E.4（geometry_hinting 反馈回路用档位+滞回+限频缓解）与新判定逻辑无冲突；A 会话不保存 scale，恢复后由尺寸重新推导。
- **全文复查**：配置表、2.F 实现清单、测试计划、工作量表中的 E 内容与新定义一致；D 章节（浮层、动画、快照、会话联动、边界与风险）未受影响。

### 第 6 轮：产品审查

**P0**
- 默认值与用户目标冲突：`restore_last_session`、`scrollback_cache` 原默认关闭，等于用户什么都得不到 → 推荐本 fork 默认开启（D1/D2 待确认），缓存配首次提示、profile 排除、一键清除。
- 缺少逃生口：无法一次性"干净启动"或清空 → 新增 `--no-restore`/`--restore`/`--clear-session`、首选项"清除会话与缓存"、菜单"下次启动不恢复"。
- 恢复导致崩溃会形成死循环 → 新增崩溃保护（restoring 标记 + 自动跳过 + 改名 `.crashed` + 提示）。

**P1**
- 恢复内容分隔线文案不够明确 → 改为"以上为 <时间> 的屏幕记录（只读，程序未恢复）"，并对已删除目录、远程会话追加说明。
- 隐私：缓存可能含敏感输出 → 设置页明确写出存储位置与风险；按 profile 排除；单终端"不缓存此终端内容"。
- 字号自动变化可能令人意外 → 不做字号动画、标题栏 `90%` 徽标 + 解释性 tooltip、右键/popover「锁定此终端字号」、界面称"自动字号"避免与 Zoom 混淆；**E 默认开（D4 已定）**。
- `titlebar_always_show` 与现有 profile 级 `show_titlebar`（默认已对单终端显示）重复 → 已删除该配置项。
- 命名：沿用"最大化终端/缩放终端"现有菜单用语，与窗口最大化 `-m` 区分。
- 多窗口逐个关闭只保留最后一个窗口，可能不符合"全部回来"的期望 → 列为决策 D5。
- 设置分散 → 新增首选项顶层"会话"页，外观相关放"全局"页，提供"将上次会话另存为布局"桥接现有概念。

**P2**
- 远程 ssh 分屏只能恢复本地目录 → 列为非目标，分隔线提示；ssh 重连/命令重跑作为以后的 opt-in。
- 老用户已有自定义 `default` 布局 → 会话优先、无会话时用 default（D6）。
- 动画需尊重系统"减少动画" → 已明确 `gtk-enable-animations=false` 时时长为 0。
- 成功标准：Terminator 无遥测，改为验收标准（U1–U7、两周 0 次恢复失败、20 分屏 < 1s）。

**文档改动**：新增 1A 产品设计（用户故事、非目标、默认值与决策表、设置界面、控制与逃生口、反馈文案、边缘流程、MVP 范围与成功标准）；配置表默认值更新（D1/D2 推荐开启、新增 `scrollback_cache_exclude_profiles`、`auto_font_scale_show_badge`，删除 `titlebar_always_show`）；B 分隔线文案、A.5 新参数与崩溃保护同步。

### 第 7 轮：UX 审查

- 标题栏：关闭按钮与其他按钮留间距、悬停红色、前台进程运行时关闭需确认；按钮点击区域 24×24、标题栏 24–26px，提供紧凑/标准密度；去掉常驻 `80x24`，定义空间不足时的折叠顺序；按钮有可访问名称与带快捷键的 tooltip。
- 菜单：齿轮用 `popup_at_widget` 锚定按钮；标题栏右键先聚焦该分屏，再传真实事件并 `skip_link_check`（避免 URL 误判又保留 button/time）；文档说明 `Shift+右键` 与 `Menu`/`Shift+F10`。
- 单终端判断：`terminal_popup_menu.py:279` 用父控件 == 窗口判断，在 Overlay 结构下会误判 → 新增 `Window.has_multiple_terms()`。
- 焦点色：绿框 = 当前焦点分屏（Wave 语义），浮层在此基础上加圆角/阴影/蒙层，颜色统一为 `pane_accent_color`。
- 放大动画：放大 200ms ease-out / 还原 160ms；快照等比缩放 + 最后 80ms crossfade；中途反向；真实终端先就位并获得焦点，快照盖在上面，动画期间输入不丢；首选项提供可见的"减少动画"选项。
- 还原快捷键统一为可配置的 `restore_maximised`（推荐 Shift+Esc），不再使用单独 Esc；蒙层点击防误触。
- E 反馈：档位徽标 + popover + 档位变化时的中央提示；档位在**首次有效 size-allocate 后**计算（非 spawn 前）。
- 恢复：恢复焦点与活动窗口；窗口位置不在任何显示器上时移回可见区域。
- 分隔线文案统一为 `──── 以上为上次会话的输出（仅文字快照，进程未恢复）· 10-10 15:00 ────`，经 gettext，只用前景色 90。

### 第 8 轮：隐私与可靠性审查

- B 依赖 A；关闭 B 或点击清除会先停止写入再删除目录；增加 TTL、单终端与总量上限、`CACHEDIR.TAG`。
- ~~不采集：排除列表 / ECHO / alt-screen~~ → **第 15 轮已废弃**（私人机器不强制）。
- 文件安全：`mkstemp` + `fchmod 0600` + `os.replace`；目录 0700 且校验属主/非符号链接；启动清理 `*.tmp`（无论是否持锁）；A 写盘 fsync 文件与目录，B 不 fsync；euid 与目录属主不符（sudo）时禁用 A/B。
- 回填前清洗 C0/C1 控制字符与 ESC/OSC 序列，防止缓存内容在回填时执行终端指令；不保存 OSC 窗口标题（发现 `container.py:300-301` 会写入窗口标题，需在保存前删除）。
- 失败处理：所有写盘捕获 `OSError` 并退避，连续失败自动停用 B；保存放在 `try/finally`，保证 `Gtk.main_quit()`；只读 home 静默降级。
- 会话属主规则（只有无参数启动且持锁的实例写会话）、会话轮转 `.prev/.prev2`、崩溃保护、未知版本不覆盖、私人单机不区分主机名；systemd-logind delay inhibitor。
- `__last_session__` 在 `list_layouts()` 层过滤；旧插件迁移提示与导入；新增 3.2b 隐私与可靠性测试清单。

### 第 9 轮：范围与里程碑审查

- 范围改为里程碑：M1（A+B 纯文本，6.5–8 天）、M2（C，约 1.5 天，可与 M1 并行）、M3a（D 无动画，4–5 天）、M3b（D 动画，2–3 天）；E 推迟。合计 M1–M3b 约 15–19 人日（比原估计 11–14 天多，主要来自隐私加固、测试环境与 D 的回归）。
- 增加 M0 测试环境（Xvfb + dbus + VTE 的 CI 与 pytest 夹具）。
- 精简配置：M1 首选项只暴露 4 个设置与 3 个按钮，其余配置仅在配置文件中可改。
- 增加与上游合并可能性评估表，以及每个里程碑的验收标准（4.4）。
- 所有需用户决定的事项按推荐方案写入正文并标"待确认"，汇总在 1A.9（D1–D21）。

### 第 10 轮：用户决策——全部功能默认开启

- 用户明确覆盖此前"保守默认"建议：`restore_last_session`、`scrollback_cache`、`titlebar_buttons`（及 Wave 焦点绿框）、`pane_overlay_maximise`、`auto_font_scale` **全部默认 True**。
- D1/D2/D4 标记为**已定：开**；D3（D 是否拆 M3a/M3b）等其余项仍待确认。
- 隐私缓解全部保留：首次提示、命令/profile 排除、0600/0700、TTL、上限、ECHO/alt-screen 跳过、一键清除、崩溃保护。
- E 不再"推迟且默认关"：改为 M2b（可与 M3 并行），默认开，配徽标/popover/中央提示/单终端锁定。
- 配置表、1A.3、1A.4、1A.8、1A.9、第 4 章里程碑与上游说明已同步。

### 第 11 轮：关闭时前台进程确认（用户决策）

- D17 **已定：开**——关闭标题栏 ✕、关闭窗口、退出时，若范围内仍有需确认的进程（见 A.4：shell pid 自身及非 shell 后代，减去忽略名单），必须弹出模态确认**对话框**（`Gtk.MessageDialog`，非 popover）；覆盖 `close_terminal`、`on_delete_event`、Ctrl+Shift+Q。
- 与现有 `ask_before_closing`（"多个终端时询问"）并存：有进程时一律确认；无进程时仍按原策略。
- 已写入 1A.6、C.2 关闭按钮、1A.9 D17。

### 第 12 轮：D 术语澄清与 D17 对话框形式（用户决策）

- D 明确为"多布局下单分屏最大化"：一个分屏以浮层铺满窗口（留边距），其他分屏原位暗化仍可见；不是窗口最大化，也不是会移除兄弟分屏的 zoom。已更新 D 标题、D.2 术语与边界、U6、命名、配置说明与里程碑表。
- D17 确认形式明确为模态对话框（`Gtk.MessageDialog`，默认焦点在"取消"），不是 popover；已同步 1A.6、C.2、1A.9。

### 第 13 轮：锁定全部剩余决策（用户："其他的按推荐来"）

用户确认其余待确认项全部锁定。点名覆盖（与原表推荐列不一致处以用户点名为准）：

| 决议 | 内容 |
|---|---|
| D3 | M3 **一次交付**浮层+动画（不拆 M3a/M3b） |
| D5 | 多窗口 **~10s quit-all** |
| D6 | 会话优先于 `default` |
| D7 | 缓存 `~/.cache`（`$XDG_CACHE_HOME`） |
| D8 | profile 排除 + 默认排除 ssh/mosh/su/sudo/gpg/pass/kubectl exec/docker exec |
| D9 | TTL 7 天；512 KB/终端；**20 MB** 总量；**不脱敏** |
| D10 | 仅无参数启动持锁实例写会话 |
| D11 | 只读 home = **restore-only**（可恢复、不保存、静默） |
| D12 | 不保存 OSC 窗口标题 |
| D13 | Wave 绿框 `#3fb950` |
| D14 | Shift+Esc 还原单分屏最大化 |
| D15 | 双击标题栏切换最大化；编辑标题改右键 |
| D16 | Alt+方向键 **转移最大化** |
| D18 | E floor **0.8** |
| D19 | Ctrl+0 只重置基础字号 |
| D20 | 标题栏密度标准 |
| D21 | 点蒙层还原后焦点回被放大终端 |

已同步 1A.3/1A.7/1A.8/1A.9、配置表、A/B/C/D/E、第 4 章。决策项不再保留「待确认」。

### 第 14 轮：并行终审（产品 / 工程 / 隐私·MVP）

工程与产品修复已并入正文：D 的 P0 遍历/关闭/占位/信号/pixbuf；B 的 `vte.feed` 与主线程读；C 的 return True / D15 / `has_multiple_terms`；E 的 size-allocate；D17 进程定义与单对话框及 M1/M2 排期；文案「最大化此分屏」；U1↔D5；M0 精简；旧审查结论标废弃。

（隐私·MVP 终审中的排除列表/首次敏感警告等，被第 15 轮用户覆盖撤销为强制项。）

### 第 15 轮：私人机器——撤销隐私强制（用户覆盖）

用户确认私人个人使用：**不做**命令排除、ECHO/alt-screen 跳过、脱敏、首次敏感警告、强制 per-profile/per-terminal 不缓存；`CACHEDIR.TAG` 可选。**保留** 0600/0700、属主检查、OSError 退避、控制字符清洗、TTL/上限（磁盘卫生）。B.7 改为「已覆盖」说明表；M1 工作量略降；排除类配置默认空。

**Go / No-Go**：**有条件 Go**——按 M0（1d）→M1（A 含 A2b+finalize+D17 / B 2.5–3d）→M2→M2b→M3（D1a/b/c）推进；合计 **22–28 人日**。M3 合入门槛含 Overlay/`logical_parent` 与遍历/关闭/占位/快照降级；M1 须含 finalize 序、D5×B `will_persist`/`discard_uuids`、D17 忽略名单与旧 zoom 范围。

### 第 16 轮：子方案并行审查落地（跨模块 / 代码准确性 / 可实施性 + 父级决议）

父级锁定并写入正文 / 子方案：

1. **私人单机**：去掉一切 hostname 分段 → `session.json` / `session.lock` / `restoring`；滚动缓存扁平 `scrollback/<uuid>.txt`。
2. **D17**：计 `terminal.pid` 自身 + 非 shell 后代 − `close_confirm_ignore`；Flatpak/`pid is None` 保守确认。
3. **`SessionManager.finalize()`** 统一退出序；`on_destroy_event` / SIG* 只调它；幂等守卫。
4. **跨模块 API**：`will_persist` / `restored_this_run` / `session_uuids` / `request_close_terminal`；B：`discard_uuids` / `feed_notice` / `clear_all`。
5. **`save_now` 含 final 也要 `is_writer()`**；变更 hash 排除 `saved_at`；`size` 元素级 str 列表。
6. **跳过保存仅 legacy zoom**；浮层可保存；`pane-maximise-changed`；finalize 内 save 后再无动画还原浮层。
7. **文件拆分**：`util` 目录助手 + `session.py` / `scrollback.py` / `close_confirm.py` / `autofont.py` / `paneoverlay.py`。
8. **主文档勘误**：D.3 禁止 `draw(cr)`/裸 pack；删「E 默认关」「spawn 前算档」；D17 不再写「前台进程」；远程 ssh 分隔线 M1 CUT。
9. **里程碑**：**22–28 人日**；M0=1 天（含 gi）；全局 PR 序与 glade/`on_destroy`/`terminal.py` 串行热点见 1A.8。
10. **`docs/impl-m2-titlebar.md`** 标废弃，以 `docs/sub/C-titlebar.md` 为准。

无主功能：崩溃 `feed_notice`→A/B；「下次不恢复」菜单 / 插件导入 / 外接屏归位 → 延后；远程 ssh 注 → CUT。
