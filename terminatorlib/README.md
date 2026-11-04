# terminatorlib

这个包实现窗口、标签、分屏和终端。进程入口是仓库根的 `terminator`，不是本目录里的文件。插件另见 [plugins](plugins/README.md)。

跨模块约定在 [架构](../docs/design/architecture.md)。改会话、浮层或配置键之前先读那一页，再改下面的文件。

| 要改的行为 | 源码 | 测试 |
|---|---|---|
| 启动时是否恢复、写哪些标签 | `session.py`，以及仓库根 `terminator` | `tests/test_session.py` |
| 关闭前询问 | `close_confirm.py` | `tests/` 里名字含 `exit_close` 的文件 |
| 回滚缓存 | `scrollback.py`、`scrollback_text.py` | `tests/test_scrollback_*.py` |
| 浮层最大化 | `paneoverlay.py`；父节点用 `util.logical_parent` | `tests/test_paneoverlay.py` |
| 窗格标题栏 | `titlebar.py` | `tests/test_titlebar_chrome.py` |
| 自动字号 | `autofont.py`，终端在 `terminal.py` 里调用 | `tests/test_scaled_zoom_font.py` |
| 备用屏幕隐藏滚动条 | `altscreen.py`；隐藏期间保留同宽槽，避免 VTE 列数变化 | `tests/test_altscreen.py` |
| 默认值和配置文件 | `config.py`；界面在 `prefseditor.py` | `tests/test_prefs_session_titlebar.py` 等 |
| 标签树、分屏比例 | `notebook.py`、`paned.py`、`window.py` | `tests/test_notebook_split.py`、`tests/test_paned_ratio.py` |
| 终端和 VTE | `terminal.py` | `tests/` 中对应 `test_*.py` |

`util.py` 提供配置目录、状态目录、缓存目录和 `logical_parent`。状态目录是会话文件的默认位置，缓存目录是回滚缓存的位置。

全局默认键不要在本页抄一遍。改默认值时改 `config.py`，并核对首选项和 `doc/terminator_config.adoc`。
