---
title: "r15 tests-e2e 发现"
type: audit
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "5 条：会话或 scrollback 回滚丢失、标题冒烟失败仍可能被判通过。"
---

### r15-1 高

症状：第二次 SIGKILL 即使出了 10 秒恢复窗、原会话没有被隔离到 `.crashed`，第三次启动只要还能拉起一个 shell 就算通过。

```389:406:tests/e2e/scenarios.py
    # crash again while the restore marker is still live (<10s)
    in_window = time.monotonic() - t_relaunch
    app.notes.append('2nd SIGKILL %.1fs after relaunch (%s 10s restore window)'
                     % (in_window, 'inside' if in_window < 10 else 'OUTSIDE'))
    app.kill()
    app.launch()
    check(app.alive(), 'third launch after crash-during-restore died')
    wait_for(lambda: len(app.shells()) >= 1, 10, what='shell on 3rd launch')
    app.signal(signal.SIGTERM)
    app.wait_exit()
    sess = app.session()
    # The crash restore may have brought unlocked tabs back. A normal exit
    # then drops them, so the file can be a clean empty layout.
    check(isinstance(sess, dict) and isinstance(sess.get('layout'), dict),
          'no valid session after 3rd launch')
    app.notes.append('3rd launch restored %d terminal(s) from %s' % (
        len(layout_nodes(app.session(), 'Terminal')),
        sorted(f for f in os.listdir(app.state_dir) if 'session' in f)))
```

为什么是问题：套件自己把这条定义为「第二次崩溃落在 10 秒恢复窗内，会话隔离到 `.crashed`，第三次是全新的单窗格」。`in_window` 只写进 note，超时仍继续；`.crashed` 是否存在、内容是否还是崩溃前的三窗格会话都没有断言。`shells() >= 1` 对一个丢掉原会话的新窗口也成立，随后的 SIGTERM 又允许 session 文件变成空 layout。原会话被删掉、没有隔离副本时，这条仍然 PASS。

```59:59:tests/e2e/README.md
| 9-sigkill-recovery | split+tab+cd, wait for debounced save + 5s scrollback interval flush → SIGKILL (no final save) → relaunch restores layout/cwds; SIGKILL again inside the 10s restore window → 3rd launch still starts (session quarantined to `.crashed`, fresh 1-pane session) |
```

方向：第二次 SIGKILL 必须断言仍在 10 秒窗内，并核对 `.crashed` 保住了崩溃前的会话。

### r15-2 高

症状：s9 声称第一次重开会恢复间隔刷盘的 scrollback，重开之后却不再读这些标记。

```358:361:tests/e2e/scenarios.py
def s9_sigkill_recovery(app):
    """m30: hard crash (SIGKILL, no final save) -> relaunch restores the
    last debounced session + last interval scrollback flush; a second
    SIGKILL inside the restore window must not crash-loop the next start."""
```

```373:388:tests/e2e/scenarios.py
    def _cached():
        sb = '\n'.join(app.scrollback_text().values())
        return all('SB_KILO%s_3' % t in sb for t in 'ABC')
    wait_for(_cached, 15, what='interval scrollback flush (5s)')
    app.kill()   # SIGKILL the whole process group: no final save
    check(terminal_dirs(app.session()) == sorted(dirs.values()),
          'session after SIGKILL: %s' % terminal_dirs(app.session()))

    t_relaunch = time.monotonic()
    app.launch()
    wait_for(lambda: len(app.shells()) == 3, 10, what='3 restored shells')
    wait_for(lambda: app.shell_cwds() == sorted(dirs.values()), 10,
             what='restored cwds (got %s)' % app.shell_cwds())
    types = [n['type'] for n in layout_nodes(app.session())]
    check('Notebook' in types and any(t in types for t in ('HPaned', 'VPaned')),
          'restored layout lost tab/split: %s' % types)
```

为什么是问题：`SB_KILO*_3` 只在 SIGKILL 之前用来证明缓存已经落盘。重开后的断言停在 shell 数量、cwd 和布局类型。新进程没有把这三段历史装回终端、甚至把缓存目录清掉，这条仍然 PASS。

方向：重开进入三个窗格之后，再核对每个窗格的 scrollback 里仍有对应的 `SB_KILO*_3`。

### r15-3 高

症状：s10 用「缓存目录里还能搜到第一次运行写下的标记」代替「重开后的终端恢复了 scrollback」。

```429:438:tests/e2e/scenarios.py
    app.launch()
    wait_for(lambda: app.shell_cwds() == sorted([a, b]), 10,
             what='restored cwds (got %s)' % app.shell_cwds())
    check({'HPaned', 'VPaned'} & {n['type'] for n in layout_nodes(app.session())},
          'split lost after quit/relaunch')
    app.signal(signal.SIGTERM)
    app.wait_exit()
    sb = '\n'.join(app.scrollback_text().values())
    for t in ('QUITA', 'QUITB'):
        check('SB_%s_3' % t in sb, 'scrollback %s lost after quit/relaunch' % t)
```

为什么是问题：`SB_QUITA_3` / `SB_QUITB_3` 在第一次退出前就已经写入同一套 `scrollback/`。同一个 `App` 再次 `launch` 前没有清空或换走这个目录，断言又是对目录内全部文件做子串搜索。重开后的终端没有这段历史、旧文件原样留着，检查仍然通过。

方向：重开前隔离旧缓存，只根据这次恢复出来的终端内容判定 scrollback 是否回来。

### r15-4 中

症状：窗口标题冒烟算出 FAIL 仍以状态码 0 退出；某一阶段标题一直停在错误窗格上，只要该阶段内部不来回跳，也算通过。

```129:135:tests/smoke_window_title.py
    total_sw = 0
    for ph, titles in by.items():
        pf = [str(x).split(' ')[0] for x in titles]
        total_sw += sum(1 for i in range(1, len(pf)) if pf[i] != pf[i-1])
    ok = bool(fwn) and str(win.get_title()).split(' ')[0] == fwn[0] and total_sw == 0
    print('RESULT', 'PASS' if ok else 'FAIL', '(in-phase pane switches=%d)' % total_sw)
    os._exit(0)
```

为什么是问题：`ok` 只比较结束时的焦点和窗口标题，并要求各阶段前缀切换次数为 0。`splits` 的中间阶段若一直显示 `P1`、从未跟着焦点走到 `P2` 或 `P0`，切换次数仍是 0，结束时焦点又回到 `P1`，`ok` 为真。即便 `ok` 为假，`os._exit(0)` 也让调用方看到成功。

方向：每个焦点阶段的标题前缀都要等于该阶段的焦点窗格，并由退出码反映 RESULT。

### r15-5 高

症状：TUI 重启冒烟断言的是重启前复制的 snap；第二次启动有没有把 shell 历史恢复出来，不参与成败。

```33:38:tests/smoke/tui_restore_smoke.sh
mkdir -p ${OUT:-/tmp}/snap; cp -r $XDG_CACHE_HOME/terminator/scrollback ${OUT:-/tmp}/snap/ ; cp $HOME/.local/state/terminator/session.json ${OUT:-/tmp}/snap/
start 2
DISPLAY=:77 ${SHOT:-/workspace/smoke/shot.sh} ${OUT:-/tmp}/3-restored.png
pkill -f "./terminator -u"
grep -rq SHELLHIST_42 ${OUT:-/tmp}/snap/scrollback || { echo "FAIL: shell history not cached"; FAIL=1; }
grep -rq TUIFRAME ${OUT:-/tmp}/snap/scrollback && { echo "FAIL: TUI frame cached"; FAIL=1; }
```

为什么是问题：脚本开头要求「退出时 TUI 还在，重启后恢复的是 shell 历史而不是 TUI 画面」。`cp` 发生在 `start 2` 之前，两条 `grep` 只读这份拷贝；`3-restored.png` 没有被比较。第二次进程没把 `SHELLHIST_42` 装回去、或把 `TUIFRAME` 画出来，这里仍然可以 SMOKE_PASS。脚本没有 `set -e`，`cp` 失败会留下上一次 `OUT/snap/scrollback` 里的旧文件，`grep -rq` 会把旧的 `SHELLHIST_42` 再算一次通过。

方向：在第二次启动之后检查恢复出的终端或这次新写入的缓存，并在拷贝前清空 `OUT/snap`。
