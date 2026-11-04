# 架构与契约

对应需求：TX-01、TX-02、TX-03、TX-04、TX-05、TX-06、TX-07、TX-08、TX-09。

范围：TerminatorX 进程内的模块关系。状态：当前有效。

构建入口是 `setup.py`，安装两个包：`terminatorlib` 和 `terminatorlib.plugins`。进程入口是仓库根的 `terminator`。各文件的职责和测试见 [模块入口](../../terminatorlib/README.md)。

## 启动

`terminator` 解析参数、取得会话锁、决定是否恢复，然后 `Terminator.create_layout`。布局完成后再拉起各个终端里的 shell。会话设置失败不能阻止窗口打开：创建布局失败时改为开一个新窗口。

是否读取会话由 `launch_is_plain` 和 `launch_wants_restore` 决定。普通启动要同时满足：拿到 `session.lock`、没有指定布局（`layout_from_default`）、没有 `-e` / `-x` / `--working-directory` / `--configjson`。在此之上，`restore_last_session` 为真或带了 `--restore`，且没有 `--no-restore`，也没有消耗掉「下次启动不恢复」标记，才读 `session.json`。`--no-restore` 只跳过这一次读取。

## 布局树

窗口里的结构是 Window、Paned、Notebook、Terminal。描述和重建沿 `Container.describe_layout` / `create_layout` 递归。终端节点记录 profile、分组、标题、uuid，以及在保存工作目录时的 directory。

左侧标签列表是 Notebook 旁边的盒子，不是布局节点。`util.layout_root_widget` 从窗口的 GTK 子控件找回 Notebook。父节点用 `logical_parent`，见 [逻辑父节点](../decisions/logical-parent.md)。

会话写盘前把叶子转成字符串。从配置读回的布局值也是字符串，恢复代码按字符串比较。

## 会话契约

提供方是 `SessionManager`（`terminatorlib/session.py`）。消费方是启动脚本 `terminator`、`Terminator` 的退出路径、首选项里的会话页，以及回滚缓存（按终端 uuid 对上这次恢复出来的终端）。

| 动作 | 条件 | 结果 |
|---|---|---|
| 读会话 | 上一节的普通启动条件 | 把布局放进内部布局名，再 `create_layout` |
| 运行中保存 | 持有锁，且该窗口没有被标成排除 | 防抖写入完整布局 |
| 正常退出保存 | `save_now(final=True)` | 先并上几秒内关掉的窗口，再只留锁定标签 |
| 排除窗口 | `-e`、`-x`、非默认的 `-l`、`--configjson` 打开的窗口 | 这些窗口不进会话；进程仍可以保存后来的普通窗口。单独的 `--working-directory` 不排除窗口 |
| 暂停写入 | 首选项「清除会话」或「下次使用先前的会话」 | 本次运行不再覆盖文件 |

`--no-restore` 只跳过这一次读取，属主进程之后仍写。这和早期设计稿里「指定了 `-e` 就完全不写」不同，以本节为准。

改 `restore_last_session`、`session_file` 或 `session_save_delay_ms` 时，要同时看 `config.py` 的默认值、`prefseditor.py` 的会话页、`terminator` 里的恢复判断，以及 `doc/terminator_config.adoc`。只改其中一个，另外三处会继续用旧行为。

## 回滚缓存

提供方是 `terminatorlib/scrollback.py`（文本提取在 `scrollback_text.py`）。缓存目录是 `~/.cache/terminator/scrollback/`。恢复时按终端 uuid 回填。备用屏幕的内容不写入。空提示符不回放。

会话模块决定哪些 uuid 会留到下次；缓存模块按这个结果保留或丢掉文件。不要在终端里直接删缓存文件。

## 关闭确认

提供方是 `terminatorlib/close_confirm.py`。窗格标题栏、终端菜单和窗口关闭都调用它。判断「有没有需要询问的进程」时，shell 本身不算，`close_confirm_ignore` 里的程序名也不算。

## 窗格外观

| 行为 | 提供方 | 何时起作用 |
|---|---|---|
| 标题栏按钮、焦点描边 | `titlebar.py`，窗口和终端负责显示或藏起整条栏 | 分割后才显示整条栏；`titlebar_buttons` 只控制按钮 |
| 浮层最大化 | `paneoverlay.py` | 快捷键或双击标题栏；Shift+Esc 收回 |
| 三档字号 | `autofont.py`，终端在尺寸变化时调用 | `KEEP_FULL_SIZE_SHARE` 为 0.45；阅读列数默认 60 |
| 备用屏幕藏滚动条 | `altscreen.py`；隐藏期间保留同宽槽，列数不变 | 配置文件键 `scrollbar_hide_in_alt_screen` |
| 窗口标题 | `window.py` 跟随焦点终端 | `window_title_mode` |

字号锁定存在终端上，并随布局保存。浮层展开期间，自动字号不要因为尺寸动画改掉档位。

## 配置

全局默认值在 `config.py` 的 `DEFAULTS`。配置文件（profile）默认值在同文件的 profile 段，滚动条隐藏属于这一段。首选项从这两处读，再写回用户配置。手册 `doc/terminator_config.adoc` 是给用户看的键说明，不另在 `docs/` 维护第三份键表。

## 插件

插件由 `terminatorlib/plugin.py` 加载，代码在 `terminatorlib/plugins/`。旧的 `save_last_session_layout` 不再负责本 fork 的会话。新会话逻辑在 `session.py`，不要把保存再挂回那个插件。

## 已知限制

- Wayland 不保存、不恢复窗口坐标。X11 上落到已断开的屏幕时，窗口回到主显示器。
- 回滚缓存是上次输出的只读记录，不是还在运行的程序。
- 早期设计稿（归档中的 `archive/docs/session-restore-design.md` 和 `archive/docs/sub/`）行号基于 2026-09-07 的 `9f2d0b6`。现行行为以本页和代码为准。
