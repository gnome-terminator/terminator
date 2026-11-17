# TerminatorX 开发约束

TerminatorX 在一个窗口里放多个终端。命令名仍是 `terminator`。桌面名、关于页和默认窗口标题用 TerminatorX。关于页的开发与问题链接指向 https://github.com/TIIEHenry/TerminatorX 。许可是 GPL v2 only。

- `docs/` 是当前需求、原则和设计。`dev/` 是计划、审查和待处理项。`archive/` 是已结束的过程材料和失效文档，不能直接当作当前规则。2026-09-07 的设计稿和 2026-10-15 的审查在归档里，其中的行号对应当时的提交，不能当作现行代码位置。
- 本 fork 新增的会话恢复、关闭确认、回滚缓存、窗格标题栏、浮层最大化、自动字号、备用屏幕隐藏滚动条、分割后均分，默认都开着。关掉某一项要改配置或首选项，不要在代码里把默认改成关。依据见 [默认开启](docs/decisions/defaults-on.md)。
- 会话恢复布局、工作目录、锁定状态和回滚缓存，不恢复正在运行的程序，也不重连 ssh。正常退出写入的会话只保留锁定的标签；没有标签列表的窗口仍保留。进程被杀死时，磁盘上仍是退出前的完整布局。依据见 [锁定标签](docs/decisions/locked-tabs.md)。
- 走布局父子关系时用 `terminatorlib.util.logical_parent`，不要用 `get_parent()` 把暂时插入的 `Gtk.Overlay`、窗格框或左侧标签列表外壳当成布局节点。浮层只在窗格最大化期间插入。依据见 [逻辑父节点](docs/decisions/logical-parent.md)。
- 会话文件里的布局叶子写成字符串。恢复代码用字符串比较，例如 `'True'`。不要写入 JSON 原生布尔值。
- 关闭终端、标签、窗口或布局，走 `close_confirm.request_close_terminal` 或 `construct_confirm_close_with_processes`，不要另做一套确认对话框。
- 配置默认值以 `terminatorlib/config.py` 为准。改键时同时改首选项和 `doc/terminator_config.adoc`。用户能感知的行为变化写进 `CHANGELOG.md`。
- 测试进程在收集前必须先请求 Gtk 3.0 和 Vte 2.91。仓库根的 `conftest.py` 已经这样做。测试模块不要在这之前自行 `import` Gtk。
- 新建文档路径不得含空格、`#`、`%` 或括号。复制模板后改成具体主题名。状态写在正文第一行，不写进文件名。
- 整页归档用 `python3 scripts/wiki/wiki.py archive <路径> --root .` 预览，再加 `--apply --expect <plan_sha256>` 执行。目标已存在时停止，不覆盖。新建前运行 `check-new`。命中历史时判断是恢复、延续还是新主题。
- 状态行、核对行、需求条目、审查问题和待处理项的写法以 `scripts/wiki/formats.md` 为准。配置和规则名在 `scripts/wiki/reference.md` 里按名称搜索，不整篇读。
- 核对人、作者、负责人和签收人写成 `human:<名字>` 或 `agent:<名字>`。Agent 只能写 `agent:`。知识页核对后写 `核对：agent:<名字>，YYYY-MM-DD。`，会过期的页面同时写复核期限。
- 一次审查放在 `dev/reviews/<开始日期>-<主题>/`。每一路一个文件，每条问题一个小节。复查在核对表里追加一行。核对人不能是作者。能写成已有文件里的一节，就不新建文件。
- AI 工具生成的计划、报告和草稿放进 `dev/`，不能写进 `docs/`。
- 拿不准放哪里的问题和想法，一条一文件写进 `dev/inbox/<类型>/<主题>.md`。处理完写明去向，状态改为「已完成」，再归档。
- 只暂存本次工作相关的文件。不要还原其他人和其他 Agent 的未提交改动。
- 留下占位实现或 `TODO` 时写明原因、影响和清理时机。
- 按改动范围运行 `python3 scripts/wiki/wiki.py verify --root .`。命令只登记在 `docs/wiki.json` 的 `verify` 里。计划里的验证记录用 `verify` 的输出，不手写命令结果。
- 新功能和行为变化在同一次改动中写需求条目。设计写「对应需求：」，计划写「覆盖需求：」，测试在说明文字里写验收编号。能写测试的条目写测试。普通修复引用已有编号，不新建需求。
- 决定或设计变化时，同一次改动里更新仍写着旧结论的需求、设计、模块入口和本文件。推翻已采用的决定要补新的决策记录。
- 开始任务时运行 `python3 scripts/wiki/wiki.py remind --root .`。看到 `[agent]` 提醒就更新对应文档，或在提交信息最后一段写 `Docs-Reviewed: <名称> <理由>`。看到 `[user]` 提醒先向用户确认。不得用 `--no-verify` 跳过钩子。
- 每个 clone 启用一次提交检查：`git config core.hooksPath scripts/wiki/hooks`。
- 日常搜索通过 `.ignore` 排除 `archive/`。`grep -R` 不读 `.ignore`，常规查询加 `--exclude-dir=archive`。
- `archive/INDEX.md` 和归档里的审查目录会持续变长。按主题或文件名搜索，只读命中的文件，不整篇读入。

知识与阅读条件见 [知识入口](docs/INDEX.md)。开发规范见 [开发规范](docs/standards/development.md)。接续已有任务才读 [开发入口](dev/INDEX.md)。
