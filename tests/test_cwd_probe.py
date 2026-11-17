"""M7: /proc cwd probe marks session dirty when OSC7 is unavailable."""
from terminatorlib import terminal as term_mod
from terminatorlib.terminal import Terminal


def _t(monkeypatch, cwds):
    t = Terminal.__new__(Terminal)
    t.__dict__['pid'] = 4242
    seq = iter(cwds)
    monkeypatch.setattr(term_mod, 'get_pid_cwd', lambda pid: next(seq))
    marks = []
    monkeypatch.setattr(Terminal, '_session_mark_dirty',
                        lambda self, reason='cwd': marks.append(reason))
    return t, marks


def test_first_probe_only_records(monkeypatch):
    t, marks = _t(monkeypatch, ['/a'])
    assert t.cwd_probe_check() is False and marks == []


def test_change_marks_dirty_once(monkeypatch):
    t, marks = _t(monkeypatch, ['/a', '/a', '/b', '/b'])
    results = [t.cwd_probe_check() for _ in range(4)]
    assert results == [False, False, True, False]
    assert marks == ['cwd-probe']


def test_dead_pid_is_ignored(monkeypatch):
    t, marks = _t(monkeypatch, [None])
    assert t.cwd_probe_check() is False and marks == []
    t.__dict__['pid'] = None
    assert t.cwd_probe_check() is False


def test_probe_is_throttled(monkeypatch):
    t, _ = _t(monkeypatch, [])
    added = []
    monkeypatch.setattr(term_mod.GLib, 'timeout_add',
                        lambda ms, cb: added.append(ms) or 99)
    t._on_contents_changed_cwd_probe()
    t._on_contents_changed_cwd_probe()
    assert added == [Terminal.CWD_PROBE_DELAY_MS]
