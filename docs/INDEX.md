# 当前知识

| 什么时候读 | 正文 |
|---|---|
| 确认本 fork 要保持的行为 | [需求](requirements/terminatorx.md) |
| 判断默认值、恢复边界和布局遍历 | [产品原则](principles/product.md) |
| 改会话、窗格、配置或关窗确认 | [架构与契约](design/architecture.md) |
| 改某个源码文件之前 | [terminatorlib](../terminatorlib/README.md)、[插件](../terminatorlib/plugins/README.md) |
| 准备修改、验证或交接 | [开发规范](standards/development.md) |
| 普通启动没有恢复、标签丢了、字号变了、关窗没有询问 | [故障维护](guides/maintenance.md) |
| 查为什么默认开启、为什么用逻辑父节点、为什么正常退出只留锁定标签 | [默认开启](decisions/defaults-on.md)、[逻辑父节点](decisions/logical-parent.md)、[锁定标签](decisions/locked-tabs.md) |
| 安装、翻译、发布 | [安装](../INSTALL.md)、[翻译](../TRANSLATION.md)、[发布](../RELEASE.md) |
| 看用户能感知的变化 | [变更日志](../CHANGELOG.md) |

两条阅读路径：

- 改会话恢复：从需求 TX-01 到架构里的会话契约，再到 `terminatorlib/session.py` 和 `tests/test_session.py`。
- 排查「重开不是上次的布局」：从 [故障维护](guides/maintenance.md) 到同一条会话契约。改 `restore_last_session` 时，提供方是 `config.py`，消费方是启动脚本 `terminator`、首选项和手册，不能只改一处。

计划与进度见 [开发入口](../dev/INDEX.md)。历史材料不作为当前规则。归档索引会变长，按文件名搜索，不整篇读。
