---
title: "r06 session 方案"
type: plan
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "两条保留、两条降级：轮转后的新会话先于更旧备份回退，上一份替换成功才停写；坏节点的断链后代要摘掉，宽限回调列不出终端时不删回滚。空窗口一条剔除。"
---

# r06 session 方案

核对结论：hold 2（r06-2、r06-4），weaken 2（r06-1、r06-5），drop 1（r06-3）。发现稿 r06-1 至 r06-5 的引用片段与 `terminatorlib/session.py` 磁盘行号一致。本方案只描述改法，不附可合入补丁。

r06-3 剔除，不改 `retain_locked_tabs`。`describe_layout` 写出的 Notebook，父节点是 Window；`Window.get_children` 只交出一个布局子节点。该 Notebook 的标签全部未锁定时，`siblings` 为空，窗口进入 `drop`，页内分割在 `subtree` 里一起去掉。`tests/test_tab_lock.py::test_retain_drops_a_window_whose_tabs_are_all_unlocked` 已锁住这一结果：另一窗口的终端留下，Notebook 不留下。两个 Notebook 互为兄弟，或 Notebook 挂在分割节点下面，当前 `Notebook.__init__` 与 `describe_layout` 不会写出这种树。

本路要改的生产符号都在 `terminatorlib/session.py`。`terminator`、`terminatorlib/terminator.py` 的 `create_layout`、`terminatorlib/prefseditor.py` 不动。发现稿不动。工作区里未提交的 `terminatorlib/altscreen.py` 与 `tests/test_altscreen.py` 不动。

## r06-1 weaken

问题类：恢复宽限里第一次保存把崩溃源转到 `.prev` 之后，随后的崩溃仍把新写成的 `session.json` 和该崩溃源一起隔离，回退因此用上更旧的 `.prev2`。

反证：严重度仍按高处理，改法要收窄。发现稿把「空标记和读失败也不要动 `session.json`」算进同一条，这一半与现有约定相反。`_retarget_marker` 把没有来源行的标记当成崩溃源就是 `session.json`。`tests/test_m26_session_disk_full.py::test_crash_marker_without_source_line_still_works` 要求只有时间戳的标记仍把 `session.json` 改名为 `.crashed`。`tests/test_m27_restore_rotation_guard.py::test_binary_marker_does_not_abort` 要求解码失败时同样隔离 `session.json`，并且启动不中止。`begin_restore` 用 `'w'` 截断标记是现有写法，空文件走的是同一条「没有来源行」分支。

另一处收窄：`tests/test_m31_crash_fallback_restore.py::test_second_crash_does_not_clobber_first_quarantine` 在 fallback 标记还在时，把宽限里写进 `session.json` 的内容隔离成 `.crashed.1`，并且 `load_crash_fallback` 返回空。这条标记的来源行已经是 `.prev`。若凡是来源行指向 `.prev` 就留下 `session.json`，这份在失败恢复期间写下的文件会留在原位，下一轮普通 `load()` 会把它当成完好会话。

不变量：标记来源行是 `session.json.prev` 或 `session.json.prev2`，且其余行里没有 `fallback` 时，只隔离该来源文件。此时磁盘上仍在的 `session.json` 是这次轮转之后写完的新布局，`load_crash_fallback` 要先于 `.prev`、`.prev2` 完整读它（`safe_restore` 保持假，回滚按这份布局重放），并把它标成 fallback，使它再崩溃时走现有的「第二次崩溃开空窗」。来源行是 `-`、空、只有时间戳、无法解码，或带有 `fallback` 时，维持现在的隔离列表 `(session.json, 点名的 .prev/.prev2)`。隔离改名失败而仍留在原地的崩溃源，不能只因为文件还在就被当成这份新布局。软失败路径 `restore_failed` 已经把新文件留下、把旋转后的源标成 `.bad`（`test_restore_failed_follows_rotated_source`）；这里要对齐的是硬崩溃在第一次、且来源已被轮转指到 `.prev`/`.prev2` 的情形。

要动的符号：`SessionManager.check_crash_marker`（约第 1231 行，隔离列表始终包含 `session`）、`SessionManager.load_crash_fallback`（约第 1272 行，候选从 `.prev` 开始，不读仍在的 `session.json`）。用检查崩溃标记时记下的「这次留下了轮转后的 `session.json`」来决定回退顺序，依据是标记内容，而不是「`session.json` 文件还在」。`_retarget_marker` 的改写格式不动。

明确不改：`begin_restore` 的打开方式与来源行、`fallback` 行的写法；`_rotate_session` 的替换顺序；来源行是 `-` 时的隔离（`test_restore_prev2_overwritten_drops_source`）；无标记、无保存的崩溃仍先完整用 `.prev` 再 `.prev2`（`test_crash_falls_back_to_prev_full_restore`、`test_crash_falls_back_to_prev2`）；`.prev` 被隔离后有 `.prev2` 时仍用 `.prev2`（`test_prev_source_crash_skips_quarantined_prev`）；第二次崩溃 `crash_fallback_ok` 为假、`load_crash_fallback` 返回空。

本地验证：改 `tests/test_m27_restore_rotation_guard.py::test_restore_session_json_then_save_then_crash`。该测试现在在 `check_crash_marker` 之后用 `load()` 断言得到 `older`，这正是新文件和 `.prev` 都被搬走之后的结果。改完后应断言：新 `session.json` 仍在且 uuid 为这次 `save_now` 写入的值，`.prev` 不在、`.prev.crashed` 是原来的 `src`，`load_crash_fallback` 读到新布局且 `safe_restore` 为假、`_fallback_restore` 为真。顺带跑 `test_crash_marker_without_source_line_still_works`、`test_binary_marker_does_not_abort`、`test_second_crash_does_not_clobber_first_quarantine`、`test_crash_falls_back_to_prev_full_restore`，这四条的现有断言保持通过。

## r06-2 hold

问题类：「使用上一份会话」在替换 `session.json` 成功之前就停掉本轮保存，写盘失败后点击之后的布局不再落盘。

不变量：`session.json.prev` 的 JSON 能解析、且含有 dict 类型的 `layout` 之后，只有 `_atomic_write_json` 把这份内容换上 `session.json` 成功，才调用 `suspend_writes`。成功之后 `_disabled` 为真，`is_writer()` 为假，滚动缓存按现有 `suspend_writes` 停掉，退出时的 `finalize` / `save_now` 不再覆盖这份上一会话。替换抛错时函数返回假，`_disabled` 仍为假，`is_writer()` 仍为真，滚动缓存保持运行，磁盘上的 `session.json` 仍是点击前的内容。本文件里 `_disabled = True` 只出现在 `suspend_writes`；失败路径不调用它，因此不需要把 `_disabled` 设回假的另一条路径。

要动的符号：`SessionManager.restore_prev_session`（约第 1314–1340 行）。把 `suspend_writes('restore previous session')` 放到 `_atomic_write_json` 成功返回之后。函数文档字符串里 “Always suspends writes first” 改成与这个顺序一致：停写是为了保住已经换上的上一份，替换未完成则本轮继续保存。`suspend_writes` 本身不动。

明确不改：解析失败或没有 `.prev` 时的提前返回（`tests/test_m21_persist_fixes.py::test_restore_prev_session_malformed_does_not_suspend`、`tests/test_session.py::test_restore_prev_session_missing_prev`）；成功路径仍停写（`test_restore_prev_session_suspends_writes`）；偏好设置里「清除会话」自己调用的 `suspend_writes('clear session')`；`_atomic_write_json` 的临时文件、fsync 与 `os.replace`。

本地验证：在 `tests/test_session.py` 或 `tests/test_m21_persist_fixes.py` 增加一条断言。上一份 JSON 合法，把 `_atomic_write_json` 打成抛 `OSError` 后，`restore_prev_session` 返回假，`writes_suspended()` 为假，`is_writer()` 为真，磁盘上的 `session.json` 仍是调用前的内容；随后一次 `save_now` 仍能写成新布局。顺带跑 `test_restore_prev_session_suspends_writes`、`test_restore_prev_session_malformed_does_not_suspend`、`test_restore_prev_session_missing_prev`：成功仍停写，畸形或缺少 `.prev` 仍不停写。

## r06-4 hold

问题类：`sanitize_layout` 删掉坏节点后，`parent` 仍指向该名字的分割和终端留在布局里，调用方会把这棵断链树当成要恢复的会话。

不变量：不是 dict，或 `type` 不是非空字符串的节点，删除之后，`parent` 非空且已不在布局里的节点也删除，并重复直到不再有这样的节点。`parent` 为空的顶层节点留下。删完后 `count_terminals_in_layout` 只数还留在布局里的终端；只剩断链终端时计数为 0，`plain_launch_action` 因此返回 `fresh`。同一次清理要盖住两处删除：开头的字典过滤（非 dict、`type` 不是字符串），以及后面循环里对空 `type` 的 `del`。

要动的符号：`sanitize_layout`（约第 241–287 行）。在现有删除都做完之后，按 `retain_locked_tabs` 末尾（约第 194–207 行）的方式多轮摘掉父节点已不在布局中的项。`SessionManager.sanitize_layout` 只是转调，不必另写一套。

明确不改：缺目录改写、去掉 `command`、窗口标题与 `title_forced`；`stringify_leaves`；`retain_locked_tabs` 自身；`terminatorlib/terminator.py` 里 `create_layout` 的层次组装循环。`tests/test_m21_persist_fixes.py::test_sanitize_drops_malformed_nodes` 里没有 `parent` 的终端 `d` 仍留下，非 dict 与 `type` 为整数的节点仍删除。

本地验证：在 `tests/test_m21_persist_fixes.py` 增加断言。一个 `type` 不是字符串的 Window，下面挂 Paned，再挂 Terminal，且 `parent` 沿这条链指上去；`sanitize_layout` 之后这三个键都不在。另一扇 `type` 为 `Window` 的好窗口及其终端仍在。`type` 为空字符串的节点同样带走 `parent` 指向它的后代。顺带跑 `test_sanitize_drops_malformed_nodes` 与 `tests/test_session.py::test_sanitize_missing_directory`：原有畸形节点仍删除，缺目录仍改成家目录。

## r06-5 weaken

问题类：关闭窗口的宽限一到，若列不出仍注册的终端，缓冲里的 uuid 会整批交给 `discard_uuids`。

反证：严重度从中降为低。缓冲里的 uuid 来自 `Window.on_destroy_event` 和 `Container._session_before_last_close` 里对正在关掉的那一扇窗的 `note_window_closing`。回调由 GLib 在约 10 秒后的主循环里运行，这些终端届时已经 `close` 并注销。其他窗口里仍开着的终端不在这份集合里，差集被跳过也不会删到它们的回滚。`note_display_lost` 会先把 `_closing_buffer` 清空，显示断开之后这次回调看到的是空缓冲。留下的缺口只在列举本身抛错：`discard -= still` 没有执行，`discard` 仍是缓冲全集，紧接着的 `discard_uuids` 会删掉其中尚未注销、却已经记在缓冲里的 uuid。

不变量：成功拿到当前 `Terminator().terminals` 的 uuid 集合之后，才删除缓冲 uuid 与该集合的差。列举或遍历抛错时，不调用 `discard_uuids`。回调末尾仍可把 `_closing_buffer` 置空，避免同一份缓冲再次超时。列举成功且某个缓冲 uuid 仍在终端列表里时，该 uuid 留在滚动缓存中。

要动的符号：`SessionManager._buffer_timeout_cb`（约第 1415–1431 行）。`except` 分支改为跳过 `discard_uuids`。`note_window_closing`、`will_persist`、`ScrollbackCache.discard_uuids` 的实现不动。

明确不改：列举成功时的差集；宽限内 `will_persist` 对缓冲 uuid 返回真从而保留缓存；`finalize` 合并缓冲；`note_display_lost` 清空缓冲；`QUIT_ALL_WINDOW_GRACE_S`。

本地验证：目前没有覆盖这条 `except` 的测试。在会话测试里增加断言：缓冲里放有 uuid，把 `Terminator` 或 `terminals` 的读取打成抛异常，超时回调不调用 `discard_uuids`，`_closing_buffer` 被清空。再补一条成功路径：缓冲 uuid 仍出现在终端列表里时，传给 `discard_uuids` 的集合不含该 uuid；已经不在列表里的 uuid 仍被删除。
