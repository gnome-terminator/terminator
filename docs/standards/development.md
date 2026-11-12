# 开发规范

范围：本仓库的修改、验证和文档。状态：当前有效。

## 修改与验证

修改前先确定目标需求或维护现象、适用的原则和决策、要改的文件、怎样验证。小修复沿用现有提交说明。行为变化要改 [需求](../requirements/terminatorx.md)；跨模块约定变化要改 [架构](../design/architecture.md)。

从本目录直接运行：

```bash
python3 terminator --help
```

依赖和安装见 [INSTALL.md](../../INSTALL.md)。手册在 `doc/`。翻译见 [TRANSLATION.md](../../TRANSLATION.md)。

长期沿用的本地路径和命令：

| 目的 | 入口或路径 |
|---|---|
| 从源码构建 | `python3 setup.py build` |
| 直接启动 | `python3 terminator`；参数和一次性启动方式先看 `python3 terminator --help` |
| 安装 | `python3 setup.py install --single-version-externally-managed --record=install-files.txt` |
| 用户配置 | `~/.config/terminator/config`，或 `$XDG_CONFIG_HOME/terminator/config` |
| 会话状态 | `~/.local/state/terminator/session.json`，或 `$XDG_STATE_HOME/terminator/session.json` |
| 回滚缓存 | `~/.cache/terminator/scrollback/`，或 `$XDG_CACHE_HOME/terminator/scrollback/` |
| 聚焦测试 | `tests/run_tests.sh tests/test_<topic>.py -q` |
| 统一检查 | `python3 scripts/wiki/wiki.py verify --root .` |

每轮开始先运行 `python3 scripts/wiki/wiki.py remind --root .`，再读 [知识入口](../INDEX.md)、对应模块入口和需求条目。启用一次提交检查：

```bash
git config core.hooksPath scripts/wiki/hooks
```

只暂存本轮相关路径，保留其他工作区改动。源码或启动脚本改动要跑 `verify` 中的测试，用户可感知的行为写入 `CHANGELOG.md`，长期约定写在 `docs/` 对应入口，不只留在会话里。

验证命令只登记在 `docs/wiki.json` 的 `verify` 里。统一入口：

```bash
python3 scripts/wiki/wiki.py verify --root .
```

| 改动范围 | 通过条件 |
|---|---|
| `terminatorlib/` 或启动脚本 `terminator` | `verify` 里的 `tests` 退出码为 0 |
| 只改文档 | `verify` 里的 `check` 退出码为 0 |
| 会话、浮层、字号、关闭确认的契约 | 上述测试，并对照架构里的对应小节 |

`tests` 执行 `tests/run_tests.sh`。它使用仓库根的 `.venv-test`（带系统 site-packages，以便导入 PyGObject），需要本机的 Gtk 3、VTE 2.91 和 Xvfb。缺显示时脚本会自己起 Xvfb。收集测试前由根目录 `conftest.py` 请求 Gtk 3.0，测试文件不要提前导入 Gtk 4。

端到端套件不在这条 `verify` 里。它需要窗口管理器，并且默认不随单元测试收集。运行方式见 [tests/e2e/README.md](../../tests/e2e/README.md)。

文档检查工具在 `scripts/wiki/`，随仓库一起提交。升级时整目录替换，再对照 `scripts/wiki/reference.md` 看配置字段有没有变。

测试说明里的 `TX-` 编号表示该文件覆盖了对应验收条目。改行为时改测试并保留编号。没有对应测试的条目不要只在说明里补编号。

文档结构用：

```bash
python3 scripts/wiki/wiki.py check --root .
python3 scripts/wiki/wiki.py doctor --root .
```

每个 clone 启用一次 Git 钩子：

```bash
git config core.hooksPath scripts/wiki/hooks
```

钩子在提交时运行 `check --staged` 和 `remind --staged`。不要用 `--no-verify` 跳过。

已知失败要写明哪条测试、怎么复现、什么条件下可以删掉这条记录。暂时不处理的放进 `dev/inbox/` 或对应计划。

## 协作

只暂存本次相关的文件。不要为了工作区干净去还原别人的改动。

用户能感知的行为变化写入 `CHANGELOG.md` 的未发布段落。开发步骤和内部挪动不写进变更日志。

## 文档

当前知识原位改。过程记录放 `dev/`。整篇失效或已经做完的计划、审查，用 `archive` 命令归档，不要手移文件后再改链接。

归档目录和历史审查按文件名检索。`archive/docs/` 里的设计稿描述的是 2026-09-07 的方案，不是现行行号。

验证记录用 `verify` 的输出。输出里的哈希只代表当时被登记的文件。
