"""m21: deferred tab switch resets its pending flag; activitywatch unwatch guard."""
import types

import pytest


def test_deferred_tab_switch_resets_pending_on_exception():
    from terminatorlib.notebook import Notebook

    def boom(*a):
        raise RuntimeError('x')
    fake = types.SimpleNamespace(pending_on_tab_switch=True,
                                 pending_on_tab_switch_args=(1, 2, 3, None),
                                 on_tab_switch=boom)
    with pytest.raises(RuntimeError):
        Notebook.do_deferred_on_tab_switch(fake)
    assert fake.pending_on_tab_switch is False
    assert fake.pending_on_tab_switch_args is None


def test_deferred_tab_switch_one_shot():
    from terminatorlib.notebook import Notebook
    seen = []
    fake = types.SimpleNamespace(pending_on_tab_switch=True,
                                 pending_on_tab_switch_args=(1, 2, 3, None),
                                 on_tab_switch=lambda *a: seen.append(a))
    assert Notebook.do_deferred_on_tab_switch(fake) is False
    assert seen == [(1, 2, 3, None)] and fake.pending_on_tab_switch is False


def _plugin_mod():
    try:
        from terminatorlib.plugins import activitywatch
    except Exception as ex:  # Notify missing
        pytest.skip('activitywatch unavailable: %s' % ex)
    return activitywatch


class _Vte:
    def __init__(self):
        self.disconnected = []

    def disconnect(self, h):
        self.disconnected.append(h)


class _Term:
    def __init__(self):
        self.vte = _Vte()

    def get_vte(self):
        return self.vte


def test_activitywatch_unwatch_not_watched_is_noop():
    aw = _plugin_mod()
    fake = types.SimpleNamespace(watches={})
    aw.ActivityWatch.unwatch(fake, None, _Term())
    term = _Term()
    fake.watches[term] = 7
    aw.ActivityWatch.unwatch(fake, None, term)
    assert term.vte.disconnected == [7] and fake.watches == {}


def test_inactivitywatch_unwatch_not_watched_is_noop(monkeypatch):
    aw = _plugin_mod()
    removed = []
    monkeypatch.setattr(aw.GLib, 'source_remove', lambda i: removed.append(i))
    fake = types.SimpleNamespace(watches={}, timers={})
    aw.InactivityWatch.unwatch(fake, None, _Term())
    term = _Term()
    fake.watches[term] = 5
    fake.timers[term] = 9
    aw.InactivityWatch.unwatch(fake, None, term)
    assert term.vte.disconnected == [5] and removed == [9]
    assert fake.watches == {} and fake.timers == {}
