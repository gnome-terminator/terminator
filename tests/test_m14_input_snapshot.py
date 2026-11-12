"""M14: paste / feed snapshot before input; single contents-changed handler."""
from terminatorlib import terminal as term_mod
from terminatorlib.terminal import Terminal


class _Vte(object):
    def __init__(self):
        self.fed, self.pasted = [], []

    def feed_child(self, b):
        self.fed.append(b)

    def paste_clipboard(self):
        self.pasted.append('c')

    def paste_primary(self):
        self.pasted.append('p')

    def grab_focus(self):
        pass


class _Cache(object):
    calls = []

    def snapshot_before_command(self, t):
        _Cache.calls.append(t)


def _t(monkeypatch, cfg=None):
    t = Terminal.__new__(Terminal)
    t.__dict__['vte'] = _Vte()
    t.__dict__['config'] = dict({'disable_mouse_paste': False,
                                 'scrollback_cache': True}, **(cfg or {}))
    _Cache.calls = []
    monkeypatch.setattr(term_mod, 'ScrollbackCache', _Cache)
    return t


def test_feed_with_newline_snapshots(monkeypatch):
    t = _t(monkeypatch)
    t.feed('ls')
    assert _Cache.calls == []
    t.feed('ls\n')
    t.feed(b'make\r')
    assert t.vte.fed == [b'ls', b'ls\n', b'make\r']
    assert _Cache.calls == [t, t]


def test_paste_snapshots_every_target(monkeypatch):
    a, b = _t(monkeypatch), Terminal.__new__(Terminal)
    b.__dict__['vte'] = _Vte()

    class _T(object):
        def get_target_terms(self, _):
            return [a, b]
    a.__dict__['terminator'] = _T()
    a.paste_clipboard()
    assert _Cache.calls == [a, b]
    assert a.vte.pasted == ['c'] and b.vte.pasted == ['c']


def test_mouse_paste_disabled_does_not_snapshot(monkeypatch):
    t = _t(monkeypatch, {'disable_mouse_paste': True})
    t.paste_clipboard(mouse=True)
    assert _Cache.calls == []


def test_contents_changed_dispatches_both(monkeypatch):
    seen = []
    monkeypatch.setattr(Terminal, '_on_contents_changed_cwd_probe',
                        lambda self, *a: seen.append('cwd'))
    monkeypatch.setattr(Terminal, '_on_scrollback_contents_changed',
                        lambda self, v: seen.append('sb'))
    t = _t(monkeypatch)
    t._on_vte_contents_changed(t.vte)
    t.config['scrollback_cache'] = False
    t._on_vte_contents_changed(t.vte)
    assert seen == ['cwd', 'sb', 'cwd']


def test_single_contents_changed_connect():
    import inspect
    src = inspect.getsource(term_mod.Terminal)
    assert src.count("'contents-changed',") == 2  # connect_signals + reconfigure
    assert '_on_vte_contents_changed' in src
