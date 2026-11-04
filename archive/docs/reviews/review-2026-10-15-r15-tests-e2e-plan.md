---
title: "r15 tests-e2e 方案"
type: plan
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "三条保留、一条降级：收紧恢复窗与 .crashed，重开后按窗格核对 scrollback，窗口标题冒烟退出码，以及 TUI 重启后的缓存。"
---

# r15 tests-e2e 方案

核对结论：hold 3（r15-2、r15-4、r15-5），weaken 1（r15-1），drop 1（r15-3）。发现稿引用的 `tests/e2e/scenarios.py`、`tests/e2e/README.md`、`tests/smoke_window_title.py`、`tests/smoke/tui_restore_smoke.sh` 片段与磁盘行号一致。

r15-3 drop。`s10_quit_relaunch` 在重开后再发 SIGTERM，`wait_exit` 之后才读 `scrollback_text()`。活码里 SIGTERM 进入 `SessionManager.finalize`：`flush_all(sync=True, final=True)` 用当前 VTE 覆盖仍会保留的终端缓存；新进程的 `_last_hash` 为空，不会把杀进程前的旧文件当成未变化而跳过。这次场景是左右分屏，两个终端会留下并被重写。恢复没把 `SB_QUITA_3` / `SB_QUITB_3` 送进 VTE 时，覆盖后的文件里没有这些标记，现有断言会失败。不改 `s10_quit_relaunch`。

本方案只描述改法，不附可合入补丁。本路只改下面点名的测试与 `tests/e2e/README.md` 里对应的场景说明。生产模块不动。`tests/fixtures/` 不动。发现稿不动。工作区里未提交的 `terminatorlib/altscreen.py` 与 `tests/test_altscreen.py` 不动。

## r15-1 weaken

问题类：`s9_sigkill_recovery` 第二次 SIGKILL 出了恢复窗、或崩溃前的会话没有留在 `*.crashed` 时，第三次启动只要还有一个 shell 并留下一份带 `layout` 的 session 文件，场景仍然通过。

反证：严重度保持为高，预期结果按活码收缩。`RESTORING_CLEAR_DELAY_S` 是 10，清除由 `layout_done` 里的 `schedule_clear_restoring` 开始，晚于 `t_relaunch`（它在 `launch()` 之前）。`launch()` 还要等窗口并再睡 1 秒。用 `t_relaunch` 起算的 `in_window < 10` 会把仍处在标记有效期内的击杀判出窗外。README 第 59 行写的「第三次是全新的单窗格」与 `load_crash_fallback` 不符：标记还在时，第三次启动会隔离 `session.json` 以及标记第二行指向的 `.prev` / `.prev2`，再按 `.prev`、`.prev2`、然后 `*.crashed` 的顺序回退；没有 `.prev` 时用隔离文件做 safe restore（布局与 cwd，不回放 scrollback）。`s9_sigkill_recovery` 末尾注释已经写明，这次回退可能把未锁定的标签带回来，随后的正常退出可以留下空 layout。`s12_crash_marker` 覆盖的是事先放好的过期标记，不覆盖这次双 SIGKILL。

不变量：第二次 `kill()` 时，`state_dir/restoring` 仍在。这次击杀前，标记第二行点名的那份会话文件（第二行就是 `session.json` 时就是当前 `session.json`）字节被记下来，其中三个终端目录仍是 `k9_A`、`k9_B`、`k9_C`。第三次 `launch()` 之后、最终 SIGTERM 之前，进程仍活着，且上述字节出现在某个 `*.crashed`（含 `session.json.crashed` 或 `session.json.prev.crashed`）里。进程死在第三次启动上仍然失败。最终 SIGTERM 之后 session 仍是带 `layout` 的 dict，这一条只说明进程能退出。

要动的符号：`tests/e2e/scenarios.py` 的 `s9_sigkill_recovery`（约第 389–406 行）。`in_window` 可以继续写进 `app.notes`。通过条件改为击杀前 `restoring` 存在。击杀紧跟在现有的三个 shell、cwd、布局类型断言之后，前面不再加等待。`shells() >= 1` 改为进程仍活着且隔离文件字节匹配，去掉「单窗格」这一层。同步 `s9_sigkill_recovery` 的文档字符串，以及 `tests/e2e/README.md` 第 59 行：写明窗内第二次崩溃把标记点名的会话隔离为 `*.crashed`，第三次启动走 `load_crash_fallback`。scrollback 重放改由下一条的新场景负责，从这一行的验收里拿掉。

明确不改：`terminatorlib/session.py` 的 `check_crash_marker`、`_quarantine_crashed`、`load_crash_fallback`、`begin_restore`、`schedule_clear_restoring`。`tests/e2e/scenarios_guards.py` 的 `s12_crash_marker`。`tests/e2e/harness.py`。

本地验证：`tests/e2e/run_e2e.sh -k 9-sigkill-recovery`。击杀前删掉 `restoring`，或在第三次启动前删掉应被隔离的会话文件，场景失败。顺带跑 `tests/e2e/run_e2e.sh -k 12-crash-marker`，预置标记仍把种子会话留成字节相同的 `.crashed`，且当次 cwd 是家目录。

## r15-2 hold

问题类：`s9_sigkill_recovery` 只在第一次 SIGKILL 之前用全部缓存文件的拼接确认 `SB_KILO*_3` 已落盘；重开后不再核对这三个窗格是否把这段历史装回终端。

不变量：第一次重开进入三个窗格、cwd 与分屏/标签布局都回来之后，每个 Terminal 节点自己的缓存被这次进程重写，内容同时含有该窗格的 `SB_KILOA_3` / `SB_KILOB_3` / `SB_KILOC_3`（按该节点的 `directory` 对应标签）和分隔行正文 `Output above is from the previous session`。e2e 的 `LANG` 是 `C.UTF-8`，分隔行走英文 msgid。这条分隔行由 `restore_into` 的 `vte.feed` 送入，杀进程前的缓存里没有它。配置里的间隔是 5 秒，`_on_interval` 只刷 `_dirty`；`vte.feed` 与新 shell 的输出都会经 `contents-changed` 调用 `mark_dirty`，新进程的 `_last_hash` 为空，间隔到点会把 VTE 写回 `scrollback/<uuid>.txt`。立刻重读杀进程前的缓存文件，文件还在，不能当作已经装回终端。

这条等待会吃掉恢复标记的 10 秒，所以不放进 `s9_sigkill_recovery`。新场景做到第一次重开的按窗格断言为止，不再第二次 SIGKILL。

要动的符号：`tests/e2e/scenarios.py` 新增场景函数，并在 `SCENARIOS` 里登记为 `9b-sigkill-scrollback`。准备步骤与 `s9_sigkill_recovery` 相同：`scrollback_cache_interval_s = 5`，三个目录，竖直分屏加标签，`_cd` 的标签为 `KILOA`、`KILOB`、`KILOC`，等间隔落盘后 SIGKILL，再 `launch`。重开后的 shell 数、cwd、布局类型断言与 s9 现有三段相同。然后 `wait_for`（超时 15 秒，与现有 `_cached` 一致）直到三个 uuid 文件各自满足上面的不变量。uuid 取自重开后 `session()` 里 Terminal 节点的 `uuid`，文件名是 `scrollback/<uuid>.txt`。`tests/e2e/README.md` 的场景表加上这一行。

明确不改：`terminatorlib/scrollback.py` 的 `restore_into`、`_flush_uuid`、`_on_interval`。`s10_quit_relaunch`。`tests/e2e/harness.py` 的 `scrollback_text`。

本地验证：`tests/e2e/run_e2e.sh -k 9b-sigkill-scrollback`。重开后若某个窗格的缓存没有对应的 `SB_KILO*_3`，或三个标记只出现在同一个文件里，或文件里没有上述分隔行，场景失败。

## r15-4 hold

问题类：`tests/smoke_window_title.py` 在某个焦点阶段的标题前缀一直停在别的窗格上时，只要该阶段内部没有来回跳，结束时焦点又回到当前标题，结果仍是 PASS；并且无论 PASS 还是 FAIL，进程都以状态码 0 退出。

不变量：阶段名里带有明确窗格编号的采样（`focus-P*`、`btn-P*`、`ovl-max-P*`、`ovl-btn-P*`、`ovl-transfer-P*`、`zoom-P*`）中，该阶段记到的每一个窗口标题前缀都等于这个编号。`init-loops`、`newtab`、`newtab-loops`、`unzoom`、`ovl-restore`、`tab0`、`tab1` 同时涉及多个窗格或一次布局切换，不要求单一前缀。`close-P1` 在窗格关闭时标题会离开 P1，只要求关闭前记到的前缀是 P1。结束时 `win.get_focus()` 所在终端的编号仍等于 `win.get_title()` 的前缀。`RESULT` 为 PASS 时进程状态码为 0，为 FAIL 时状态码为 1。`os._exit` 可以保留，用来跳过 Gtk 收尾；状态码跟着上述结果走。

要动的符号：`tests/smoke_window_title.py` 的 `main` 末段（约第 129–135 行）。约第 123–127 行已经按阶段打印前缀，通过条件要把上面的阶段规则算进去。约第 123 行的 `bad = 0` 目前没有参与结果，通过条件改完后要么用它累计失败阶段，要么删掉这个未使用的计数。

明确不改：`tests/e2e/scenarios.py` 的 `s6_window_title`。`terminatorlib` 里设置窗口标题的实现。

本地验证：这个脚本不进 pytest。在有显示的环境里对 `SCENARIO=splits|overlay|zoom|tabs|close` 各跑一次 `PYTHONPATH=. python tests/smoke_window_title.py`。`splits` 里 `focus-P2` 的标题若全程保持 `P1`，打印 `RESULT FAIL` 且状态码为 1。五个场景在标题跟着焦点走时状态码为 0。

## r15-5 hold

问题类：`tui_restore_smoke.sh` 在第二次启动之前把缓存复制到 `OUT/snap`，随后的 `grep` 只读这份副本；第二次进程有没有把 `SHELLHIST_42` 装回终端，不参与成败。`OUT/snap` 也不会先清空。

不变量：退出确认之后、`start 2` 之前，本次运行的 scrollback 副本含有 `SHELLHIST_42`，且不含 `TUIFRAME`。复制前 `OUT/snap` 是空的；`cp` 失败则 `FAIL=1`。`start 2` 之后、再次 `pkill` 之前，对已恢复的窗口送一次回车，让 `snapshot_before_command` 把当前 VTE 写回缓存。写回的活缓存（`XDG_CACHE_HOME/terminator/scrollback`，不是 `OUT/snap`）mtime 晚于第二次进程启动，内容含有 `SHELLHIST_42`，且不含 `TUIFRAME`。脚本开头的 `set -x` 与按条累加 `FAIL` 的写法保留；单独检查这次 `cp` 的状态。`3-restored.png` 继续作为现场截图，不作为成败依据。

要动的符号：`tests/smoke/tui_restore_smoke.sh` 约第 33–38 行。`rm -rf` 的对象是 `${OUT:-/tmp}/snap`。活缓存断言放在第 36 行 `pkill` 之前。第 32 行现有的诊断 `grep` 仍只打印，不代替上述失败条件。

明确不改：`tests/smoke/fake_tui.py`。`tests/e2e/scenarios.py` 的 `s7_altscreen`。生产侧的 `restore_into`。

本地验证：用全新的 `OUT` 跑 `tests/smoke/tui_restore_smoke.sh`，结束时打印 `SMOKE_PASS` 且状态码为 0。预先在该 `OUT/snap/scrollback` 放一份只含 `SHELLHIST_42` 的旧文件，并让本次 `cp` 的源目录缺失：脚本不得打印 `SMOKE_PASS`。第二次启动后的活缓存若没有 `SHELLHIST_42`，或 mtime 仍早于这次启动，状态码为 1。
