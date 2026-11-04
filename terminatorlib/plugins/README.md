# 插件

插件在进程启动后由 `terminatorlib/plugin.py` 按配置里的 `enabled_plugins` 加载。每个插件一个文件，放在本目录。

本 fork 的会话保存不走插件。`save_last_session_layout.py` 和 `save_user_session_layout.py` 是上游留下的布局插件，不负责 `session.json`。会话的读写在 `terminatorlib/session.py`，见 [架构](../../docs/design/architecture.md)。

改插件的启用、卸载和 URL 处理器时，看 `tests/test_plugins_r11.py` 和 `tests/test_r14_plugin_enable.py`。不要在插件里再写一份会话恢复。
