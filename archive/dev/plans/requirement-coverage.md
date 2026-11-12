# 需求编号与测试对照

状态：已完成。范围：TX-01 至 TX-09。负责：agent:grok。

覆盖需求：TX-01、TX-02、TX-03、TX-04、TX-05、TX-06、TX-07、TX-08、TX-09。

## 目标与依据

让每条已实现的需求能从编号找到设计、这份计划和测试。行为以 [需求](../../../docs/requirements/terminatorx.md) 和 [架构](../../../docs/design/architecture.md) 为准。测试说明里的 `TX-` 编号只标在已经覆盖该条验收的文件上。

## 步骤与剩余工作

1. 在现有测试文件的说明里写上它实际覆盖的验收编号。已完成。
2. 把启动时是否读取会话的判断收成 `launch_is_plain` 和 `launch_wants_restore`，并由 `terminator` 调用。已完成。`TX-01.2` 由 `tests/test_session.py` 覆盖。
3. 按现行代码改正 `TX-01.3`：单独的 `--working-directory` 不恢复上次会话，但该窗口仍写入会话。已完成。
4. 引用了验收编号的测试用 `tests/run_tests.sh` 跑过。已完成。整库 `verify` 里的 `tests` 命令这次没有跑，见验证一节。

没有未完成的步骤。

## 未决事项与待决取舍

没有。整库测试仍以 `docs/wiki.json` 里的 `tests` 命令为准，不在这里另记一条必跑命令。

## 工作区与集成

改动在当前工作区，尚未提交。涉及 `terminator`、`terminatorlib/session.py`、需求页，以及说明里写了验收编号的测试文件。

## 验证

```
2026-10-30 用 `wiki.py verify` 运行，输入是工作区：HEAD `6108ae1ea4fd`，相对 HEAD 有 87 个文件未提交（含未跟踪文件）；配置 `docs/wiki.json` 的 sha256 前缀为 `837b9cf0aa8e`。

- `check`：`python3 scripts/wiki/wiki.py check --root .`，通过（退出码 0，用时 0.2 秒）。输出第一行：`check: passed (0 errors, 0 warnings)`。
- 未运行：`tests`。
```

人工核对：上面的 `check` 只证明文档结构。引用了验收编号的测试文件另用 `tests/run_tests.sh` 跑过，426 项通过，1 项跳过（`tests/test_scrollback_color.py`）。登记的整库 `tests` 命令这次没有执行。

## 完成与交接

验收编号、设计和测试的对应关系已经写回需求页的「证据：」行，状态为已验证。本计划结束后归档，开发入口只保留指向归档的链接。
