---
title: "r07 scrollback 发现"
type: audit
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "超长行会把彩色缓存写成空文件；导出失败会覆盖旧历史；导出止于光标；以 $/# 结尾的命令可能整段不回放；写入失败后不再重试。"
---

审查范围仅 `terminatorlib/scrollback.py` 与 `terminatorlib/scrollback_text.py`。共 5 条。

## r07-1

- **严重度**：高
- **症状**：彩色缓存里最新一行的 UTF-8 长度达到字节预算（默认 512 KiB）且文本以换行结尾时，整份缓存被写成空文件，这一行之前还放得下的行一并消失。

```142:155:terminatorlib/scrollback_text.py
    lines = text.split('\n')[-max_lines:]
    kept = []
    used = 0
    for line in reversed(lines):
        size = len(line.encode('utf-8')) + (1 if kept else 0)
        if used + size > max_bytes:
            break
        kept.append(line)
        used += size
    if not kept:
        plain = _SGR_ANY_RE.sub('', lines[-1]).encode('utf-8')
        return truncate_utf8_bytes(plain, max_bytes).decode('utf-8', 'replace')
    kept.reverse()
    return '\n'.join(kept)
```

```336:342:terminatorlib/scrollback.py
def render_cache_text(src, is_html, n_lines, max_kb):
    """Convert (if HTML) and truncate to the line/byte budget. Thread-safe
    (pure function); returns the str written to the cache file."""
    text = sbt.html_to_sgr(src) if is_html else (src or '')
    if is_html:
        return sbt.truncate_sgr_lines(text, n_lines, max_kb)
    return sbt.truncate_lines_and_bytes(text, n_lines, max_kb)
```

```783:791:terminatorlib/scrollback.py
            try:
                data = render_cache_text(src, is_html, lines, max_kb).encode(
                    'utf-8')
                if not self._dir:
                    self._ensure_dir()
                with self._io_lock:
                    self._bump(uuid_str)
                    sbt.atomic_write_txt(path, data, mode=0o600)
```

**为什么是问题**：`html_to_sgr` 在源文本以换行结束时，结果也以换行结束，`split('\n')` 的最后一项是空串。循环从最新端走，先收下这个 0 字节的空字段，`kept` 变为非空；紧挨着的正文行还要再加 1 个换行字节。正文长度大于等于 `max_bytes` 时这次比较失败并 `break`，退回截断的分支要求 `kept` 为空，因此不会执行。`'\n'.join([''])` 得到 `''`。默认 `scrollback_cache_color` 为真，刷写走这条路径，同步写和 worker 写都会 `os.replace` 掉原文件。实测 `512 KiB` 的一行加换行，以及它前面还有短行的文本，返回值都是空串；刚好等于预算同样为空，少 1 字节才能留下。函数自己的说明写的是超预算时去掉 SGR 再按字节留下该行尾部。

**方向**：末尾空字段先被收下时，超预算的最新正文行仍要走“去 SGR 后按字节留尾部”的退路，避免整段变成空串再覆盖磁盘文件。

## r07-2

- **严重度**：高
- **症状**：取光标或导出文本失败时，已有缓存被一次成功的空写入替换，这次失败的视图还会记入哈希，内容不变就不再重写。

```314:333:terminatorlib/scrollback.py
    try:
        col, end_row = vte.get_cursor_position()
    except Exception as ex:
        dbg('get_cursor_position failed: %s' % ex)
        return '', False
    try:
        lower = int(vte.get_vadjustment().get_lower())
    except Exception:
        lower = 0
    start_row = max(lower, end_row - max(0, n_lines - 1))
    src, is_html = export_vte_text(vte, start_row, 0, end_row, col,
                                   color=color, raw=True)
    if not src:
        # Fallback: write_contents_sync only when range APIs missing and
        # scrollback is finite (caller must gate infinite).
        caps = _vte_caps()
        if not caps['range_format'] and not caps['range'] and caps['write_sync']:
            src = _export_via_write_contents(vte)
        is_html = False
    return src or '', is_html
```

```269:283:terminatorlib/scrollback.py
    text = ''
    try:
        if caps['range_format']:
            result = vte.get_text_range_format(
                Vte.Format.TEXT, start_row, start_col, end_row, end_col)
            text = result[0] if isinstance(result, (tuple, list)) else result
        elif caps['range']:
            result = vte.get_text_range(
                start_row, start_col, end_row, end_col, None)
            text = result[0] if isinstance(result, (tuple, list)) else result
    except Exception as ex:
        dbg('export_vte_text range failed: %s' % ex)
        text = ''
    text = text or ''
    return (text, False) if raw else text
```

**为什么是问题**：`get_cursor_position` 抛错，或 range 导出抛错，返回值都是 `('', False)`。range API 存在时，空结果不会再走 `write_contents_sync`。`_flush_uuid` 把这个空串哈希后照常 `atomic_write_txt`，成功路径会更新 `_last_hash` 并丢掉 dirty。备用屏幕、排除命令、显示器丢失这几条路径都会留下原文件；导出失败这条路径会把原文件换成空文件。终端其实仍有历史时，下一次崩溃读到的是空缓存。

**方向**：导出失败与“终端确实为空”分开，失败时保留已有缓存文件并保持可重试。

## r07-3

- **严重度**：中
- **症状**：每次快照都停在光标格，光标右侧同一行的文字和光标以下各行不会进入缓存。

```314:325:terminatorlib/scrollback.py
    try:
        col, end_row = vte.get_cursor_position()
    except Exception as ex:
        dbg('get_cursor_position failed: %s' % ex)
        return '', False
    try:
        lower = int(vte.get_vadjustment().get_lower())
    except Exception:
        lower = 0
    start_row = max(lower, end_row - max(0, n_lines - 1))
    src, is_html = export_vte_text(vte, start_row, 0, end_row, col,
                                   color=color, raw=True)
```

**为什么是问题**：`export_vte_text` 的终点列是光标列、终点行是光标行。请求范围只覆盖到光标格，列号更大的单元格和行号更大的行都不在这次导出里。光标停在行中间时（方向键、`\r` 回到行首、右侧提示符画在光标右边），该行后半被截掉后写入缓存，原来的完整行被这次快照替换。光标不在缓冲区最后一行时，下面的屏幕内容整段缺失。

**方向**：导出终点用滚动缓冲的最后一行和该行末列。

## r07-4

- **严重度**：中
- **症状**：整段缓存若只含空提示、空白，以及以 `$` 或 `#` 结尾的命令行（例如 `echo $` 及其输出 `$`，或 `make #`），恢复时整段不回放。

```373:384:terminatorlib/scrollback_text.py
# A shell prompt with nothing typed after it.  A command on the same line
# (user@host:~$ ls) does not match.
_PROMPT_ONLY_RE = re.compile(
    r'^(?:\([^)]*\)\s*)*'
    r'(?:'
    r'[^@\s]+@[^:\s]+:.*[$#]\s*'
    r'|'
    r'[^@\s]+@[^:\s]+\s+\S*[$#%>]\s*'
    r'|'
    r'[$#%>]\s*'
    r')$'
)
```

```401:415:terminatorlib/scrollback_text.py
def scrollback_worth_replaying(text):
    """False when the cache is blank, bare prompts, or only old separators.
    ...
    """
    if not text:
        return False
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return any(not _line_is_prompt_or_separator(line) for line in text.split('\n'))
```

```1136:1140:terminatorlib/scrollback.py
        # A prompt with no command output is not a previous session worth
        # marking.  Old separator lines do not count: they were fed by an
        # earlier restore and then snapshotted back into the cache.
        if not sbt.scrollback_worth_replaying(body):
            return False
```

**为什么是问题**：第一条分支是 `user@host:` 之后 `.*[$#]` 直到行尾。提示符本身以 `$` 或 `#` 结尾，用户接着输入、并且整行仍以 `$` 或 `#` 结尾的命令也会匹配。第三条分支把单独一行 `$`、`#`、`%`、`>` 也当成空提示。`scrollback_worth_replaying` 要有一行不属于这类才回放。`clarence@AILinux:~$ echo $` 加上输出 `$` 再加下一行空提示，返回值是 False；`root@host:~# make #` 加下一行空提示同样是 False。`restore_into` 就此返回，终端上看不到这段已保存的会话。

**方向**：空提示只匹配提示符后面没有命令的行，已输入且以 `$` 或 `#` 结尾的命令要算作可回放内容。

## r07-5

- **严重度**：中
- **症状**：一次写入失败后该终端不再自动重试；连续失败三次后的约 300 秒内，关闭终端也不会做最后一次保存。

```783:808:terminatorlib/scrollback.py
            try:
                data = render_cache_text(src, is_html, lines, max_kb).encode(
                    'utf-8')
                if not self._dir:
                    self._ensure_dir()
                with self._io_lock:
                    self._bump(uuid_str)
                    sbt.atomic_write_txt(path, data, mode=0o600)
                    # m19: sync (on-close) writes count toward runtime GC too
                    self._bytes_since_gc = (self._bytes_since_gc or 0) + len(data)
                self._last_hash[uuid_str] = digest
                self._fail_count = 0
            except OSError as ex:
                self._on_write_failed(ex)
            self._dirty.discard(uuid_str)
        else:
            if self._queue is None:
                return
            # The worker converts/truncates and drops writes superseded by a
            # newer intent (seq) for the same uuid.
            with self._io_lock:
                seq = self._bump(uuid_str)
            self._queue.put(('write', uuid_str, (src, is_html, lines, max_kb),
                             digest, seq))
            self._dirty.discard(uuid_str)
```

```690:695:terminatorlib/scrollback.py
    def flush(self, terminal, sync=False, **kwargs):
        """Read VTE and write (sync=True on main thread, else queue)."""
        if kwargs.get('synchronous'):
            sync = True
        if not self._enabled or self._disabled_by_error:
            return
```

```810:826:terminatorlib/scrollback.py
    def on_terminal_close(self, terminal):
        if not self._enabled:
            return
        uuid_str = _terminal_uuid_str(terminal)
        if not uuid_str:
            return
        ...
        try:
            if _sm_will_persist(terminal):
                self.flush(terminal, sync=True)
            else:
                self.delete_uuid(uuid_str)
```

```1082:1095:terminatorlib/scrollback.py
    def _on_write_failed(self, exc):
        self._fail_count = (self._fail_count or 0) + 1
        err('scrollback write failed (%s): %s' % (self._fail_count, exc))
        if self._fail_count >= 3:
            self._disabled_by_error = True
            if self._timer_id:
                try:
                    GLib.source_remove(self._timer_id)
                except Exception:
                    pass
                self._timer_id = 0
            err('scrollback cache disabled after repeated write failures; '
                'retrying in %ds' % int(REENABLE_COOLDOWN_S))
            self._schedule_reenable()
```

**为什么是问题**：同步写的 `OSError` 处理之后，`_dirty.discard` 仍会执行；异步路径在入队时就清掉 dirty，worker 里写失败只调用 `_on_write_failed`，不会把该 uuid 放回 dirty。间隔刷写只看 dirty 集合，内容若不再变化，这次已经读出的快照不会再写。失败满 3 次后 `_disabled_by_error` 为真，`flush` 和 `mark_dirty` 直接返回，而 `on_terminal_close` 的最后保存正是调用 `flush(..., sync=True)`。冷却 300 秒内关掉的终端，最新滚动历史留在进程里，随进程退出丢失。旧文件还在，但关闭前新产生的输出没有落盘。

**方向**：写入失败保持该终端为脏，冷却期间关闭终端仍要做一次同步保存。
