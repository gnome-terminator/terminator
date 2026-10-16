---
title: "r07 scrollback 方案"
type: plan
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "保留三条：彩色超长行勿写成空文件，导出失败勿覆盖缓存，以 $/ # 结尾的命令仍要回放。光标只改终点列；写失败只补重试与非最后窗口的关闭保存。"
---

# r07 scrollback 方案

核对结论：hold 3，weaken 2，drop 0。本方案只写保留项怎么改，不附可合入补丁。生产改动只落在 `terminatorlib/scrollback_text.py` 与 `terminatorlib/scrollback.py`。

活码与发现稿引用一致的部分：`truncate_sgr_lines` 的行预算循环、`read_last_n_lines_raw` / `export_vte_text` 的失败返回、`_PROMPT_ONLY_RE`、`_flush_uuid` 在 `OSError` 之后仍 `_dirty.discard`。下面按磁盘行为写改法。

## r07-1 hold

问题类：彩色缓存文本以换行结尾时，最新一行的 UTF-8 长度达到字节预算会让 `truncate_sgr_lines` 返回空串，随后 `atomic_write_txt` 用空文件换掉原缓存。

`split('\n')` 的末项是空串。循环从最新端走，先把这个 0 字节空字段放进 `kept`，于是 `if not kept` 的去 SGR 退路不再执行。下一条（真正的最新正文）还要再加 1 个换行字节，长度大于等于预算就 `break`。`'\n'.join([''])` 得到 `''`。刚好等于预算同样为空；少 1 字节时正文加上这个换行刚好卡住预算，行能留下。无尾随换行的超长行仍走退路，现有单测覆盖的是这条。`html_to_sgr` 在末尾空行（源文本以换行结束，或 `<br>`）时结果也以换行结束，彩色刷写会把这个空串写盘。默认 `scrollback_cache_color` 为真，默认 `scrollback_cache_max_kb` 为 512。同步写和 worker 写最后都是 `os.replace`。

不变量：

- 最新正文行放不进预算时，结果是去掉 SGR 之后、不超过 `max_kb * 1024` 字节的该行尾部，与现在无尾随换行的退路相同。`max_bytes > 0` 且该行有内容时，结果不得是空串。
- 退路用的是最新一条非空正文，不是 `split` 出来的末尾空字段。
- 正文放得下时，尾随换行可以留着。能整行放下的较旧行仍按现在的从新到旧截断。最新一行放不下时，不改成去保留更旧的短行。

要动的符号：`scrollback_text.truncate_sgr_lines`。`render_cache_text` 在 `is_html` 时已经调用它；函数不再返回这种空串之后，同步写和 worker 写不用另做分支。

明确不改：`truncate_lines_and_bytes`（纯文本预算）、`truncate_utf8_bytes`、`html_to_sgr` 的换行形状、放得下的行仍按 SGR 字节计入预算。

本地验证：`tests/test_scrollback_color.py::test_truncate_sgr_oversized_single_line_is_plain` 与 `test_truncate_sgr_lines_budget_and_whole_lines` 保持通过（前者没有尾随换行）。应新增断言：`max_kb` 为 1 时，短行加一条长度等于 1024 字节的正文再加尾随换行，返回值非空、不含 ESC、编码长度不超过 1024，且不含那条短行；长度 1023 再加尾随换行时，正文还在。`html_to_sgr` 吃进以 `<br>` 结尾、最新一行超预算的 HTML 后，再进 `truncate_sgr_lines`，结果同样非空。

## r07-2 hold

问题类：取光标或范围导出失败时，返回值与「终端确实为空」都是 `('', False)`，`_flush_uuid` 把空串哈希后写盘，成功路径更新 `_last_hash` 并丢掉 dirty。

`get_cursor_position` 抛错直接返回 `('', False)`。`export_vte_text` 的范围调用抛错时把文本收成 `''`，`raw=True` 时同样是 `('', False)`。range API 存在时，空结果不会再走 `_export_via_write_contents`。空字节仍会 `os.replace` 掉原文件。下一次若仍导出空串，哈希相同，主线程直接返回，不会再读终端。备用屏幕在导出前返回并保留 dirty 和原文件；排除命令、排除窗口会丢掉 dirty 但不写；显示器丢失在导出前返回，dirty 和文件都不动。

不变量：

- 导出失败与成功的空终端分开。失败：不调用 `atomic_write_txt`，不改 `_last_hash`，该 uuid 仍留在 `_dirty`，下一次间隔还能再导出。
- 成功读到空串：仍写入空文件并记下这次哈希，避免每个周期重写。
- `n_lines == 0` 仍是成功的空结果，不是失败。
- range API 存在时，失败不得改走 `write_contents_sync`。

要动的符号：

- `export_vte_text`：范围 API 抛错时的返回要能和成功空串区分开。HTML 导出失败后继续尝试纯文本，这条保持。
- `read_last_n_lines_raw`：`get_cursor_position` 抛错按失败处理。
- `_flush_uuid`：只在导出成功时哈希、写盘、更新 `_last_hash`、丢掉 dirty。同步写和入队的异步写都不要把失败空串交出去。

明确不改：`in_alt_screen` 的推迟、`cache_exclusion` / `_terminal_window_excluded` 的跳过、`_sm_display_lost` / `_sm_safe_keep` 的提前返回、无限回滚且没有 range API 时的跳过。

本地验证：现无「导出失败保留文件」的测试。应新增断言：缓存里已有非空内容时，`get_cursor_position` 或 range 导出抛错，文件字节不变，`_last_hash` 不变，uuid 仍在 `_dirty`；下一次导出成功且文本不同时会写入。成功导出空串时写成空文件并记下哈希，再来一次相同空串则不再写。`tests/test_m29_displaylost_cache.py` 里跳过写盘的用例，以及 `tests/test_altscreen_cache.py::test_flush_deferred_while_alt_screen_active`，保持通过。

## r07-3 weaken

问题类：快照终点列是光标列，光标所在行在该列之后的文字会随这次快照盖掉缓存里该行原先的内容。

降级反证：`docs/sub/B-scrollback-cache.md` §1.2 把终点写成光标列，并注明只有「若只要整行」才用 `get_column_count()`。`read_last_n_lines_raw` 与这段一致，不是后来写歪。起点行是 `max(lower, end_row - (n_lines - 1))`，光标以上、仍在行数预算内的滚动历史在请求范围内。备用屏幕整段不导出。光标以下的行被排除，是这条算法把终点行定在光标行的结果；普通 shell 里那些行多半是视口空行，不是光标上方的历史。发现稿要求改成「滚动缓冲的最后一行和该行末列」，后半句过宽。

不变量：

- 终点行仍是 `get_cursor_position` 的行。起点行、`get_vadjustment().get_lower()` 的下界、行数预算不动。
- 终点列改为光标所在行的最后一个单元格，使该行光标右侧的文字进入导出。本机 VTE 0.68 只有 `get_text_range`，没有 `get_text_range_format`；两种能力都用同一组行号列号。末列是闭区间还是开区间，用一行已知文字对上，不要写死 `get_column_count()` 或减一。
- 光标以上的行保持整行进入结果。

要动的符号：`read_last_n_lines_raw` 里交给 `export_vte_text` 的终点列。`export_vte_text` 只按传入范围导出，不必改它的选择逻辑。

明确不改：终点行。不改用 adjustment 的上界或屏幕底行。不改 `in_alt_screen` 的跳过。不改 `read_last_n_lines` 在导出之后再按行截断的行为。

本地验证：现无终点列测试。应新增断言：一行里光标停在中段时，`read_last_n_lines_raw` 的导出包含光标右侧的文字；光标上面的一行原样在；起点行不小于 `get_lower()`。光标已在行尾时，结果与现在用光标列导出一致。

## r07-4 hold

问题类：`_PROMPT_ONLY_RE` 的第一条把「`user@host:` 之后任意内容、且整行以 `$` 或 `#` 结尾」当成空提示，`scrollback_worth_replaying` 在每一行都命中时让 `restore_into` 直接返回。

注释写的是同一行上的命令（`user@host:~$ ls`）不匹配。`clarence@AILinux:~$ echo $` 加输出 `$` 加下一行空提示，返回值是 False。`root@host:~# make #` 加下一行空提示同样是 False。`clarence@AILinux:~$ echo hello #` 加下一行空提示也是 False。中间有一行普通输出（例如 `hello`）时返回 True，所以只有整段都被判成空提示、空白或旧分隔线才会整段不回放。第三条把单独一行 `$`、`#`、`%`、`>` 当成空提示，这是现有单测要的行为；`echo $` 的输出 `$` 与空提示无法从文本上分开，不必改这条。

不变量：

- 提示符后面只有空白的行仍不是可回放内容。`tests/test_scrollback_text.py::TestReplayWorth::test_prompt_only_is_skipped` 的两例保持 False。
- 提示符后面已经有命令的行算可回放内容，即使命令以 `$` 或 `#` 结尾。只要有这样一行，`scrollback_worth_replaying` 为 True。
- 单独一行 `$` / `#` / `%` / `>` 仍是空提示。旧分隔线仍不算可回放内容。

要动的符号：`_PROMPT_ONLY_RE`，以及它的唯一分类入口 `_line_is_prompt_or_separator`。`scrollback_worth_replaying` 的 `any(...)` 可以留下。`restore_into` 里对它的判断可以留下。

明确不改：`_SEPARATOR_LINE_RE`、`strip_replay_separators`、第三条对单独提示符的匹配。不去区分「命令输出刚好是一个 `$`」和「一行只有 `$` 的提示符」。

本地验证：`TestReplayWorth::test_command_output_is_kept_and_old_separator_dropped` 与 `scrollback_worth_replaying` 的 doctest 保持通过。应新增断言：`clarence@AILinux:~$ echo $` 加下一行 `clarence@AILinux:~$ ` 为 True；`root@host:~# make #` 加下一行空提示为 True；`clarence@AILinux:~$ echo hello #` 加下一行空提示为 True。只有空提示和旧分隔线时仍为 False。

## r07-5 weaken

问题类：写入的 `OSError` 之后该终端不再处于脏集合，内容若不再变化，这次已经读出的快照不会再写。连续失败三次后，冷却期内走 `flush` 的关闭保存会被 `_disabled_by_error` 吃掉。

降级反证：

- 未满 3 次时 `mark_dirty` 仍会把 uuid 加回 `_dirty`。再有 `contents-changed` 时，周期刷写还会再试。发现稿「一次写入失败后该终端不再自动重试」只在失败之后内容不再变化时成立。
- `flush_all` 不看 `_disabled_by_error`。最后一扇窗口的 `Window.on_destroy_event` 先 `SessionManager.finalize`，里面 `flush_all(sync=True, final=True)`，此时终端还在。只剩最后一台终端时，`Terminal.close` 也会 `finalize(closing=self)`，同样进 `flush_all`。冷却期内的进程退出、最后一窗关闭，仍会同步写。
- 常规运行中关掉一台、且 `will_persist` 为假的终端，`on_terminal_close` 走 `delete_uuid`，本来就不是最后保存。
- 满 3 次之后 `_try_reenable` 会在 `REENABLE_COOLDOWN_S`（300）秒后清掉熔断，并把当时还活着的终端重新放进 `_dirty`。`tests/test_m33_robustness.py::test_write_failures_schedule_reenable` 锁的是这条。

仍然要改的部分：同步写的 `OSError` 处理之后，`_dirty.discard` 仍会执行，且失败路径不更新 `_last_hash`。异步路径在入队时就清掉 dirty，worker 里 `OSError` 只 `idle_add(_on_write_failed)`，不把该 uuid 放回。非最后一扇窗口走 `note_window_closing` 把 uuid 放进 D5 `_closing_buffer`，`will_persist` 为真，`on_terminal_close` 调用 `flush(sync=True)`。`flush` 在 `_disabled_by_error` 时直接返回，这扇窗口里关闭前的新输出不会进这次同步写。

不变量：

- 一次 `OSError` 之后该 uuid 仍为脏，下次间隔会再导出再写。成功落盘才清脏，并把 `_fail_count` 清零。失败不更新 `_last_hash`。
- 连续失败仍在第三次后停掉周期定时器，并在约 300 秒后按现有 `_try_reenable` 恢复。冷却期内 `mark_dirty` 和 `_on_interval` 继续直接返回。
- 冷却期内，`will_persist` 为真的那次同步关闭仍要执行 `_flush_uuid(..., sync=True)`。`flush_all` 保持现在的放行，不要再加一层熔断判断。

要动的符号：

- `_flush_uuid` 同步分支：`except OSError` 之后的 `_dirty.discard` 不得在失败时执行。
- 异步分支：入队时的 `_dirty.discard` 要改成「写成功才清」，或在 worker 的 `OSError` 路径把该 uuid 放回 `_dirty`。worker 的非 `OSError` 异常今天只打日志，同样已经在入队时清过脏；写没落盘就保持脏，不要只补 `OSError` 一条。
- `on_terminal_close` 在 `will_persist` 为真时的保存。今天它调用 `flush`，而 `flush` 开头拒绝 `_disabled_by_error`。这次关闭保存要绕过这道拒绝。不要把周期定时器在冷却期内重新打开。

明确不改：`REENABLE_COOLDOWN_S`、`_schedule_reenable` / `_try_reenable` 的重新标脏、`flush_all`、`_on_interval` 在熔断时的直接返回、显示器丢失时 `on_terminal_close` 的既不写也不删。

本地验证：`test_write_failures_schedule_reenable` 与 `test_reenable_skipped_when_display_lost` 保持通过。应新增断言：同步 `atomic_write_txt` 抛 `OSError` 后，uuid 仍在 `_dirty`，`_last_hash` 不变，原文件仍在；worker 写失败后该 uuid 回到 `_dirty`。`_disabled_by_error` 为真且 `will_persist` 为真时，`on_terminal_close` 仍调用一次同步 `_flush_uuid`。同一熔断下 `flush_all(sync=True)` 仍会刷。`mark_dirty` 在熔断期间仍是空操作。
