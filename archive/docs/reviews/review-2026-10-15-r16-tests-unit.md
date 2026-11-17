---
title: "r16 tests-unit 发现"
type: audit
status: draft
phase: N/A
created: 2026-10-15
updated: 2026-10-15
summary: "5 处单元测试断言会放过会话布局偏离、回滚被截空，以及关闭确认与按键送入的错误。"
---

范围内只读 `tests/test_*.py`。下面 5 条都是测试自身会漏判的问题。

## r16-1

- 严重度：高
- 症状：会话保存后再加载，布局哈希不相等时测试仍然通过，终端 uuid、目录等未另作断言的字段可以悄悄丢掉。

```137:139:tests/test_session.py
    loaded = sm.load()
    assert loaded is not None
    assert layout_change_hash(loaded['layout']) == sm._last_change_hash or True
```

`assert A == B or True` 的结果恒为真，哈希比较没有失败路径。同函数只另外核对了版本、窗口尺寸和标题（第 132–135 行）。布局里的 `uuid` 与 `directory`（第 119–121 行）加载后没有再核对，偏离只能靠这条哈希断言发现。

方向：断言 `layout_change_hash(loaded['layout'])` 等于 `sm._last_change_hash`。

## r16-2

- 严重度：高
- 症状：回滚按字节截断时，结果被截成空串，或只留下最旧的行，测试仍然通过。

```53:56:tests/test_scrollback_text.py
    def test_bytes_cap(self):
        text = ('x' * 200 + '\n') * 20
        out = truncate_lines_and_bytes(text, 100, 1)  # 1KB
        self.assertLessEqual(len(out.encode('utf-8')), 1024)
```

输入约 4KB。唯一断言是编码后不超过 1024 字节，空串满足该不等式。同文件 `test_lines` 要求留下尾部 `'c\nd'`（第 49–51 行），这条字节上限没有要求留下最新的行。

方向：断言截断结果是原文尾部，并且长度落在上限之内。

## r16-3

- 严重度：中
- 症状：只剩 shell 的终端仍弹出关闭确认时，这条测试不会失败。

```18:40:tests/test_close_confirm.py
def test_shell_only_not_confirm():
    class Term(object):
        pid = os.getpid()  # pytest process — usually not a shell basename

    # Force ignore of our own process name by treating it as shell
    ignore = set()
    # Monkeypatch relevant_processes to use known shell pid simulation
    class ShellTerm(object):
        pid = 1  # init — name varies; use mock via monkeypatch

    # Unit-level: empty found when basename in SHELL
    # Simulate by calling with a fake that we control via /proc of self:
    # Mark our pid's basename as shell by temporarily adding it
    myname = cc._proc_basename(os.getpid()) or 'python'
    shells = set(cc.SHELL_BASENAMES)
    shells.add(myname)
    # Inline check of filter logic
    found = []
    bname = myname
    skip = shells | set(cc.DEFAULT_CLOSE_CONFIRM_IGNORE)
    if bname and bname not in skip:
        found.append((os.getpid(), bname))
    assert found == []
```

`Term`、`ShellTerm`、`ignore` 都没有参与断言。函数先把当前进程名放进 `shells`，再判断该名字是否落在这个集合外。`found` 因此一直是空列表。`should_confirm_processes` 没有被调用。

方向：用只含 shell 的终端调用关闭确认，并断言不需要弹窗。

## r16-4

- 严重度：中
- 症状：按字节截断把多字节字符从中间切开，或丢掉末尾的 `y` 时，测试仍然通过。

```31:37:tests/test_scrollback_text.py
    def test_no_split_multibyte(self):
        # '€' is e2 82 ac
        data = b'x' + '€'.encode('utf-8') + b'y'
        out = truncate_utf8_bytes(data, 4)  # would start mid-euro if naive
        # Must be valid utf-8
        out.decode('utf-8')
        self.assertTrue(out.endswith(b'y') or out == b'y' or '€'.encode('utf-8') in out)
```

`data` 是 5 字节 `78 e2 82 ac 79`。保留末尾 4 字节得到 `e2 82 ac 79`，正好是完整的「€」加 `y`，朴素切片本身就是合法 UTF-8。切进欧元中间的是末尾 3 字节 `82 ac 79`。断言又是三选一：结果只含「€」而丢掉 `y`，或原样返回整个缓冲区，都为真。

方向：用会落在欧元中间的字节预算，并断言得到完整的尾部字符序列。

## r16-5

- 严重度：中
- 症状：带回车的输入没有送进终端时，测试仍然通过，用户敲下的命令可以丢失。

```40:46:tests/test_m14_input_snapshot.py
def test_feed_with_newline_snapshots(monkeypatch):
    t = _t(monkeypatch)
    t.feed('ls')
    assert _Cache.calls == []
    t.feed('ls\n')
    t.feed(b'make\r')
    assert _Cache.calls == [t, t] and t.vte.fed[-1] == b'make\r'
```

快照次数只说明两次带换行的 `feed` 都调用了 `snapshot_before_command`。`fed[-1]` 只约束最后一次是 `b'make\r'`。`b'ls'` 与 `b'ls\n'` 没有出现在 `vte.fed` 里时，断言仍然成立。

方向：断言 `vte.fed` 按顺序包含这三次送入的字节。
