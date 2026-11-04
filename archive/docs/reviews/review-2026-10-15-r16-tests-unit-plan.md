---
title: "r16 tests-unit 方案"
type: plan
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "四条保留、一条降级：收紧会话回读哈希、回滚字节截断、只含 shell 的关闭确认，以及 feed 送入顺序；多字节截断降级后钉住尾字符。"
---

# r16 tests-unit 方案

核对结论：hold 4，weaken 1，drop 0。发现稿 r16-1 至 r16-5 的引用片段与磁盘行号一致。drop 无。本方案只描述改法，不附可合入补丁。

本路只改下面点名的测试。生产模块不动。`tests/e2e/`、`tests/smoke/`、`tests/fixtures/` 不动。发现稿不动。工作区里未提交的 `terminatorlib/altscreen.py` 与 `tests/test_altscreen.py` 不动。

## r16-1 hold

问题类：`test_atomic_write_and_load` 用恒真表达式比较布局哈希，读回结果偏离时测试仍然通过。

不变量：`save_now(final=True)` 成功后，`load()` 返回的 `layout` 的 `layout_change_hash` 等于当时写入的 `sm._last_change_hash`。该哈希覆盖整份 layout，终端的 `uuid` 与 `directory` 变了或丢了，比较失败。比较对象是保存后的 `_last_change_hash`，也就是 `stringify_leaves` 之后、`final=True` 时再经 `retain_locked_tabs` 的那份。这份夹具没有 Notebook，终端会留下。以当前 `save_now` 与 `load`，这份夹具两边哈希相等，`uuid` 与 `directory` 都在读回的终端节点上。

要动的符号：`tests/test_session.py` 的 `test_atomic_write_and_load`。约第 139 行去掉 `or True`，断言 `layout_change_hash(loaded['layout']) == sm._last_change_hash`。同函数约第 132–135 行对版本、窗口尺寸和标题的检查保留。

明确不改：`terminatorlib/session.py` 的 `layout_change_hash`、`save_now`、`load`、`retain_locked_tabs`。同文件其他测试不动，包括 `test_sanitize_missing_directory`。

本地验证：`pytest tests/test_session.py::test_atomic_write_and_load`。去掉恒真后这条应当通过。读回的 layout 若少了终端 `uuid` 或 `directory`，该断言失败。

## r16-2 hold

问题类：`test_bytes_cap` 只要求编码后不超过 1024 字节，空串和只留最旧行都过。

不变量：行数上限高于输入行数时，字节上限的结果同时满足三点：UTF-8 长度不超过 `max_kb * 1024`（这里是 1024）；结果是输入的后缀；结果含有输入的最后一行。本输入是 `('x' * 200 + '\n') * 20`，约 4KB，最后一行是 200 个 `x`。空串的长度合法，而且 `endswith('')` 为真，所以长度或「是后缀」单独都不够。只留开头若干行则不是后缀。`truncate_lines_and_bytes` 在字节切片之后会再对齐到换行，断言锁对齐之后仍在上限内的最新尾部。

要动的符号：`tests/test_scrollback_text.py` 里 `TestTruncateLinesAndBytes.test_bytes_cap`（约第 53–56 行）。`test_lines`（约第 49–51 行）已经要求行数截断留下 `'c\nd'`，保持不动；本条的 `max_lines=100` 高于这 20 行，只补字节上限。

明确不改：`terminatorlib/scrollback_text.py` 的 `truncate_lines_and_bytes` 与 `truncate_utf8_bytes`。同文件其他测试不动。

本地验证：`pytest tests/test_scrollback_text.py::TestTruncateLinesAndBytes::test_bytes_cap`。结果若是 `''`，或是输入的前缀而不是尾部，断言失败。顺带跑 `TestTruncateLinesAndBytes::test_lines`，行数截断仍留下 `'c\nd'`。

## r16-3 hold

问题类：`test_shell_only_not_confirm` 在本地复制了一段过滤，没有调用关闭确认，空列表是自己构造出来的。

不变量：终端自己的进程名属于 `SHELL_BASENAMES`（例如 `bash`），子进程为空，且 `child_exited` 未置位、`pid` 为正整数时，`relevant_processes_for_terminal` 返回 `[]`。在 `_never_ask()` 为假时，`should_confirm_processes` 对这一份终端返回 `(False, [])`。`ask_before_closing == 'never'` 会在进过滤之前直接返回不确认，所以这条断言要在 `_never_ask` 被固定为假的前提下看过滤结果。

要动的符号：`tests/test_close_confirm.py` 的 `test_shell_only_not_confirm`（约第 18–40 行）。删掉未参与断言的 `Term`、`ShellTerm`、`ignore`，以及就地组装的 `found`。`relevant_processes_for_terminal` 在函数内部 `import psutil`，调用前用假的 `sys.modules['psutil']` 提供 `Process`：`name()` 返回 `bash`，`children(recursive=True)` 返回 `[]`，`NoSuchProcess` 与 `Error` 是异常类，`Process` 本身不抛。再调用 `relevant_processes_for_terminal` 与 `should_confirm_processes`。假进程若走了异常分支，生产代码会返回 `[(None, '<unknown>')]` 并要求确认；桩必须报出一个活的 shell，而不是让这条测试靠异常路径过。

明确不改：`terminatorlib/close_confirm.py` 的 `SHELL_BASENAMES`、`relevant_processes_for_terminal`、`should_confirm_processes`、`_never_ask`。同文件 `test_pid_none_no_prompt`、`test_non_shell_self_counts`、`test_ignore_list_filters_gitstatusd` 不动。

本地验证：`pytest tests/test_close_confirm.py::test_shell_only_not_confirm`。shell 名被当成需要确认的进程时失败。顺带跑 `test_non_shell_self_counts` 与 `test_pid_none_no_prompt`：非 shell 仍要确认，`pid is None` 仍不确认。

## r16-4 weaken

问题类：`test_no_split_multibyte` 的字节预算没有踩进多字节字符内部，三选一又放行丢掉尾字节 `y` 或原样返回整个缓冲区。

反证：严重度从中降为低。`out.decode('utf-8')` 没有 `errors` 参数。输入 `b'x' + '€'.encode('utf-8') + b'y'` 是 5 字节 `78 e2 82 ac 79`。末尾 3 字节 `82 ac 79` 不能按 UTF-8 解码，会抛 `UnicodeDecodeError`，测试失败。因此「从中间切开时测试仍然通过」与这条活码不符。同模块 doctest 还要求 `truncate_utf8_bytes('€'.encode('utf-8'), 2)` 为 `b''`。留下的缺口是：预算 4 的切片起点是欧元的首字节 `e2`，朴素 `data[-4:]` 已经是合法的 `€y`，续字节跳过没有被这条用例执行；断言 `endswith(b'y') or out == b'y' or '€' 的编码 in out` 在「只剩欧元、丢掉 `y`」时为真，在返回全部 5 字节时也为真，并且不检查长度不超过预算。

不变量：预算落在欧元的续字节上时（预算 3，切片为 `82 ac 79`），结果是合法 UTF-8，长度不超过预算，并且等于完整尾部 `b'y'`。放不进剩余预算的欧元整字符丢掉，不留下半个字符，也不把 `y` 丢掉。预算 4 若单独保留，结果应是欧元的 UTF-8 加上 `b'y'`，且长度不超过 4；这一档与朴素尾切片相同，不能单独证明续字节被跳过。

要动的符号：`tests/test_scrollback_text.py` 里 `TestTruncateUtf8.test_no_split_multibyte`（约第 31–37 行）。去掉三选一。`test_ascii`、`test_cjk`、`test_zero` 不动。

明确不改：`truncate_utf8_bytes` 的实现和它的 doctest。

本地验证：`pytest tests/test_scrollback_text.py::TestTruncateUtf8::test_no_split_multibyte`。预算 3 的结果若不是 `b'y'`、若解码失败、或长度大于 3，断言失败。顺带跑 `TestTruncateUtf8::test_cjk`。

## r16-5 hold

问题类：`test_feed_with_newline_snapshots` 只检查快照次数和 `vte.fed` 的最后一项，前两次送入可以缺失。

不变量：`Terminal.feed` 每次都把字节交给 `vte.feed_child`，顺序与调用一致。`str` 经 `encode()` 成为 UTF-8；已经是 `bytes` 的原样送入。三次调用之后 `t.vte.fed` 等于 `[b'ls', b'ls\n', b'make\r']`。不含 `\n` 或 `\r` 的第一次不记快照；后两次各记一次，`_Cache.calls` 等于 `[t, t]`。只看 `fed[-1] == b'make\r'` 时，前两次不在列表里，或中间夹了别的字节，断言仍然成立。

要动的符号：`tests/test_m14_input_snapshot.py` 的 `test_feed_with_newline_snapshots`（约第 40–46 行）。保留第一次 `feed('ls')` 之后 `_Cache.calls == []` 的检查，把末行收成对完整 `t.vte.fed` 的相等断言，同时保留两次快照。

明确不改：`terminatorlib/terminal.py` 的 `Terminal.feed`（约第 2529 行：含 `\r` 或 `\n` 时先 `_snapshot_before_input`，然后 `feed_child`）与 `_snapshot_before_input`。同文件粘贴和 `contents-changed` 的测试不动。

本地验证：`pytest tests/test_m14_input_snapshot.py::test_feed_with_newline_snapshots`。`fed` 缺 `b'ls'` 或 `b'ls\n'`、顺序不同、或最后一项不是 `b'make\r'` 时失败；`ls` 若触发了快照也失败。
