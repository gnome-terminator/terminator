"""M14: after reconfigure, 'contents-changed' has exactly one live handler."""
import pytest

gi = pytest.importorskip('gi')


def test_reconfigure_keeps_single_contents_changed_handler(monkeypatch):
    from terminatorlib.terminal import Terminal
    calls = []
    monkeypatch.setattr(Terminal, '_on_vte_contents_changed',
                        lambda self, *a: calls.append(1))
    t = Terminal()
    try:
        for _ in range(3):
            t.reconfigure()
        assert list(t.cnxids.cnxids[t.vte]).count('contents-changed') == 1
        t.vte.emit('contents-changed')
        assert calls == [1]
        t.config['scrollback_cache'] = not t.config['scrollback_cache']
        t.reconfigure()
        calls[:] = []
        t.vte.emit('contents-changed')
        assert calls == [1]
    finally:
        t.config['scrollback_cache'] = True
        try:
            t.close()
        except Exception:
            pass
