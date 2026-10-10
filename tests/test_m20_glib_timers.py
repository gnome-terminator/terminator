"""m20: no deprecated GObject main-loop helpers; on_tab_switch is one-shot safe."""
import os
import re
import types

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'terminatorlib')
PAT = re.compile(r'GObject\.(idle_add|timeout_add|timeout_add_seconds|source_remove)\s*\(')


def test_no_gobject_mainloop_helpers():
    bad = []
    for dp, _dn, fns in os.walk(ROOT):
        for fn in fns:
            if fn.endswith('.py'):
                p = os.path.join(dp, fn)
                for i, line in enumerate(open(p, encoding='utf-8'), 1):
                    if PAT.search(line):
                        bad.append('%s:%d' % (os.path.relpath(p, ROOT), i))
    assert not bad, bad


def test_activitywatch_imports_glib():
    src = open(os.path.join(ROOT, 'plugins', 'activitywatch.py'), encoding='utf-8').read()
    assert 'from gi.repository import GLib' in src


def test_on_tab_switch_returns_source_remove():
    from terminatorlib.notebook import Notebook
    calls = []
    fake = types.SimpleNamespace(terminator=types.SimpleNamespace(
        find_terminal_by_uuid=lambda urn: calls.append(urn)))
    r = Notebook.on_tab_switch(fake, None, None, 0, {'tabs_last_active_term': None})
    assert r is False
    last = types.SimpleNamespace(urn='x')
    r = Notebook.on_tab_switch(fake, None, None, 0, {'tabs_last_active_term': last})
    assert r is False and calls == ['x']
