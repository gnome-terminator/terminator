---
title: "r06 session 发现"
type: audit
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "崩溃标记会隔离新会话并退回更旧备份；恢复上一份失败后本轮不再保存；干净退出会留下空窗口。"
---

## r06-1

**严重度：** 高

**症状：** 恢复后的宽限里只要已经自动保存过，随后的崩溃会把刚写好的 `session.json` 和正在恢复的那一份一起改名为 `.crashed`。下次启动先完整打开更旧的 `.prev2`，最新布局和它的回滚缓冲不会被用上。标记文件是空的，或读取失败时，当前完好的 `session.json` 同样会被隔离。

**代码：**

```984:988:terminatorlib/session.py
        A save during restore (marker present) rotates session.json -> .prev
        -> .prev2; without this a crash would quarantine the wrong file and
        leave the real source to be restored again (crash loop). moves maps
        a suffix of path ('' = session.json itself) to its new suffix, or
        None if that file was overwritten.
```

```1004:1008:terminatorlib/session.py
        target = moves[suffix]
        new_lines = [lines[0] if lines else _now_iso()]
        # '-' = source overwritten; must not read as a legacy (no-source)
        # marker on the next rotation.
        new_lines.append(base + target if target is not None else '-')
```

```1163:1172:terminatorlib/session.py
            with open(path, 'w', encoding='utf-8') as fh:
                fh.write(_now_iso())
                fh.write('\n')
                # m26 post-review: remember which file is being restored so
                # a hard crash quarantines it (a rotated .prev would
                # otherwise be retried, crash-looping every other launch).
                src = getattr(self, '_loaded_from', None)
                if src or self._fallback_restore:
                    fh.write(os.path.basename(src or ''))
                    fh.write('\n')
```

```1221:1238:terminatorlib/session.py
            if len(lines) > 1:
                name = os.path.basename(lines[1].strip())
                base = os.path.basename(session)
                if name in (base + '.prev', base + '.prev2'):
                    src = os.path.join(os.path.dirname(session), name)
            was_fallback = FALLBACK_MARKER_FLAG in [l.strip() for l in lines[2:]]
        except (OSError, ValueError) as ex:
            # ValueError: undecodable marker (UnicodeDecodeError) must not
            # abort startup (m27).
            dbg('SessionManager crash marker read: %s' % ex)
        for victim in (session, src):
            if victim and os.path.isfile(victim):
                dest = self._quarantine_crashed(victim)
                if dest:
                    self._crashed_sources.append(dest)
        self.clear_restoring_now()
        self._crash_skipped = True
        self.crash_fallback_ok = not was_fallback
```

```1272:1288:terminatorlib/session.py
        for candidate in (path + '.prev', path + '.prev2'):
            data = self._load_file(candidate)
            if data is not None:
                self._loaded_from = candidate
                self._fallback_restore = True
                err('SessionManager: previous restore crashed, falling back '
                    'to %s' % os.path.basename(candidate))
                return data
        # newest quarantine first (a stale older *.crashed may exist and
        # push this run's copy to *.crashed.N).
        crashed = list(getattr(self, '_crashed_sources', None) or [])
        for candidate in crashed:
            data = self._load_file(candidate)
            if data is not None:
                self._loaded_from = candidate
                self._fallback_restore = True
                self.safe_restore = True
```

**为什么是问题：** 恢复标记会留到大约 10 秒。这期间的第一次保存会把正在恢复的 `session.json` 转到 `.prev`，把新布局写回 `session.json`，并把标记改指向 `.prev`。`check_crash_marker` 的隔离列表始终包含当前 `session.json`，标记里的 `.prev` / `.prev2` 只是再加一个目标。两份都被挪走之后，`.prev` 已经不在，`load_crash_fallback` 就完整采用更旧的 `.prev2`。更新的 `.crashed` 排在后面，而且会打开 `safe_restore`，回滚缓冲不重放。标记只要存在就进入这段逻辑：`begin_restore` 用 `'w'` 打开，文件会先被截断；截断后立刻崩溃会留下空标记。空内容和读取异常都不会设置 `src`，循环仍然隔离当时的 `session.json`。

**方向：** 只隔离标记点名的那一个文件，并让轮转后新写的 `session.json` 先于 `.prev2` 参与回退；空标记和读失败不要动当前会话文件。

## r06-2

**严重度：** 高

**症状：** 「使用上一份会话」在写盘失败时返回失败，但本进程之后不再写 `session.json`，回滚缓冲也会停。点击之后的布局和输出在退出时留不下来。

**代码：**

```657:659:terminatorlib/session.py
    def is_writer(self):
        return bool(self._owns_session and self._lock_fd is not None and
                    not self._disabled)
```

```669:687:terminatorlib/session.py
    def suspend_writes(self, reason=''):
        """Stop writing session.json (and scrollback) for the rest of this run.

        Used by the preferences "clear" / "use previous session" actions so
        that the running instance does not overwrite the result at exit.
        """
        dbg('SessionManager.suspend_writes: %s' % reason)
        self._disabled = True
        if self._timer is not None:
            try:
                from gi.repository import GLib
                GLib.source_remove(self._timer)
            except Exception:
                pass
            self._timer = None
        try:
            from .scrollback import ScrollbackCache
            ScrollbackCache().stop(join_timeout=1.0)
```

```1333:1340:terminatorlib/session.py
        # Only suspend once we know the copy can succeed
        self.suspend_writes('restore previous session')
        try:
            self._atomic_write_json(path, data)
            return True
        except Exception as ex:
            err('SessionManager.restore_prev_session: %s' % ex)
            return False
```

**为什么是问题：** 注释要求确认复制能成功再暂停。当前顺序是 JSON 解析通过后、`os.replace` 之前就把 `_disabled` 设为 True。临时文件写入或替换仍会因磁盘满、权限或 I/O 错误失败。本文件没有把 `_disabled` 设回 False 的路径，`is_writer` 在本轮剩余时间里一直为假，`finalize` 和 `save_now` 都不再写。`suspend_writes` 同时停掉 scrollback。替换是原子的，失败时磁盘上的 `session.json` 仍是点击前的内容，上一份并没有换上，点击之后的新状态也不会再落盘。

**方向：** 等 `session.json` 替换成功后再暂停写入；替换失败时保持本轮可以继续保存。

## r06-3

**严重度：** 中

**症状：** 干净退出时，一个窗口里的标签都未锁定、但会话里还有别的终端，这份布局会带着已经没有任何终端的窗口（以及中间的空分割节点）一起恢复，用户会看到多出来的空窗口。

**代码：**

```119:120:terminatorlib/session.py
    A window whose tabs were all
    dropped is removed, and so is anything that hung under a dropped page.
```

```157:168:terminatorlib/session.py
        if not kept:
            drop.add(nb_name)
            drop.update(subtree(nb_name))
            parent = node.get('parent')
            parent_node = layout.get(parent)
            if (isinstance(parent_node, dict) and
                    parent_node.get('type') == 'Window'):
                siblings = [name for name, _child in kids(parent)
                            if name != nb_name]
                if not siblings:
                    drop.add(parent)
            continue
```

```194:208:terminatorlib/session.py
    for name in drop:
        layout.pop(name, None)
    changed = True
    while changed:
        changed = False
        for name, node in list(layout.items()):
            if not isinstance(node, dict):
                layout.pop(name, None)
                changed = True
                continue
            parent = node.get('parent') or ''
            if parent and parent not in layout:
                layout.pop(name, None)
                changed = True
    return layout
```

```236:238:terminatorlib/session.py
    if count_terminals_in_layout(kept) == 0:
        return 'fresh', None
    return 'session', kept
```

**为什么是问题：** 函数约定标签被删光的窗口要去掉。实现只在 notebook 的直接父节点类型是 `Window`、并且 `kids()` 里还有别的名字时才保留窗口；已经放进 `drop` 的兄弟仍然算「还有兄弟」，两个都会被删光的 notebook 谁也不会带走窗口。父节点是分割节点时，窗口根本不会进入 `drop`。收尾只删除父节点已经不在布局里的项，没有子节点的 `Window` 和分割容器会留下。`layout_after_exit_policy` 会再跑一次同样的函数，仍然删不掉这些空壳。会话里只要还有别的终端，`plain_launch_action` 就返回 `session` 和这份布局，空窗口会一起被建出来。

**方向：** 窗口下已经没有留下的终端时，把该窗口和中间的空分割节点一并删掉；已经决定丢弃的兄弟不要再算作窗口还在。

## r06-4

**严重度：** 中

**症状：** 会话里有一个坏节点（不是 dict，或 `type` 不是字符串）时，这个节点会被删掉，挂在它下面的终端和分割仍留在布局里，`parent` 指向已经不存在的名字。恢复会拿到一棵窗口链已经断掉的树。

**代码：**

```244:246:terminatorlib/session.py
    Malformed nodes (non-dict, or without a string ``type``) are dropped so
    Terminator.create_layout cannot crash on them.
    missing_dirs (if a list) is appended with paths that were rewritten.
```

```259:270:terminatorlib/session.py
    # Validate before stringify_leaves (it would turn type 3 into '3')
    layout = {k: v for k, v in layout.items()
              if isinstance(v, dict) and isinstance(v.get('type'), str)}
    layout = stringify_leaves(deepcopy(layout)) if layout else {}
    home = os.path.expanduser('~')
    for name in list(layout.keys()):
        node = layout[name]
        if not isinstance(node, dict) or not isinstance(node.get('type'), str) \
                or not node.get('type'):
            dbg('sanitize_layout: dropping malformed node %r' % (name,))
            del layout[name]
            continue
```

**为什么是问题：** 布局是扁平字典，子节点各自占一个键。过滤只看节点自己的 `type`，删掉坏的 `Window` 或分割节点后，后代的 `parent` 仍是那个名字。后面的循环同样只 `del` 当前坏节点。`retain_locked_tabs` 里有「父节点不在布局中就摘掉」的清理，这里没有。这些终端仍会被 `count_terminals_in_layout` 算进布局，调用方会把断了父链的树当作要恢复的会话。

**方向：** 丢掉坏节点时，把 `parent` 已经不在布局里的后代一起丢掉。

## r06-5

**严重度：** 中

**症状：** 关闭窗口后的宽限一到，如果当时列不出仍打开的终端，缓冲里记录过的回滚缓存会被整批删除，其中包含还开着的终端，这些终端的回滚内容会丢。

**代码：**

```1415:1429:terminatorlib/session.py
        discard = set(buf.get('uuids') or set())
        # Keep uuids still open
        try:
            from .terminator import Terminator
            still = set()
            for term in Terminator().terminals:
                if getattr(term, 'uuid', None) is not None:
                    still.add(str(term.uuid))
            discard -= still
        except Exception:
            pass
        if discard:
            try:
                from .scrollback import ScrollbackCache
                ScrollbackCache().discard_uuids(discard)
```

**为什么是问题：** 缓冲里的 uuid 可能仍属于没有关掉的终端，所以要先从当前终端列表里减掉。`Terminator()` 或遍历在拆卸过程中抛错时，`discard -= still` 不会执行，`discard` 保持为缓冲里的全部 uuid。紧接着的 `discard_uuids` 会删除这些回滚文件。异常路径把「减掉仍打开的终端」这一步跳过了，仍在使用的终端会失去回滚缓存。

**方向：** 列不出仍打开的终端时保留这些 uuid 的回滚缓存，不要按缓冲全集删除。
