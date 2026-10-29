"""m25: per-terminal font size + auto-font lock survive session round trip."""
import pytest
from gi.repository import Pango

from tests.test_m21_session_roundtrip import (  # noqa: F401
    env, _make_window, _restore, _close_all, _pump)


def _by_uuid(terms):
    return {str(t.uuid): t for t in terms}


def test_font_size_and_lock_round_trip(env):
    tmp, sm = env
    (tmp / 'a').mkdir()
    (tmp / 'b').mkdir()
    w = _make_window([str(tmp / 'a'), str(tmp / 'b')])
    t1, t2 = w.get_terminals()
    base = t1.vte.get_font().get_size()
    t1.zoom_in()
    t1.zoom_in()
    _pump()
    want = t1.custom_font_size
    assert want == base + 2 * Pango.SCALE
    t2.set_auto_font_locked(True)
    u1, u2 = str(t1.uuid), str(t2.uuid)
    assert sm.save_now(final=True)
    _close_all([w])

    rw, = _restore(sm)
    terms = _by_uuid(rw.get_terminals())
    r1, r2 = terms[u1], terms[u2]
    assert r1.custom_font_size == want
    assert r1.vte.get_font().get_size() == want
    assert not r1.get_auto_font_locked()
    assert r2.custom_font_size is None
    assert r2.get_auto_font_locked()


def test_describe_layout_omits_unset_font_state(env):
    tmp, sm = env
    w = _make_window([str(tmp)])
    t, = w.get_terminals()
    out = {}
    t.describe_layout(0, 'w', out, 0)
    node = out['terminal0']
    assert 'font_size' not in node and 'auto_font_locked' not in node
    t.zoom_in()
    t.set_auto_font_locked(True)
    out = {}
    t.describe_layout(0, 'w', out, 0)
    node = out['terminal0']
    assert node['font_size'] == str(t.custom_font_size)
    assert node['auto_font_locked'] == 'True'
    _close_all([w])


@pytest.mark.parametrize('layout', [
    {},                                   # legacy session: no keys
    {'font_size': 'garbage'},
    {'font_size': '0'},
    {'font_size': str(10 ** 9)},
    {'auto_font_locked': 'False'},
    {'font_size': ''},
])
def test_create_layout_backward_compat_and_invalid(env, layout):
    tmp, sm = env
    w = _make_window([str(tmp)])
    t, = w.get_terminals()
    before = t.vte.get_font().get_size()
    t.create_layout(dict(layout))
    assert t.custom_font_size is None
    assert not t.get_auto_font_locked()
    assert t.vte.get_font().get_size() == before
    _close_all([w])


def test_reconfigure_keeps_custom_font_size(env):
    tmp, sm = env
    w = _make_window([str(tmp)])
    t, = w.get_terminals()
    t.zoom_in()
    want = t.custom_font_size
    t.reconfigure()
    _pump()
    assert t.custom_font_size == want
    assert t.vte.get_font().get_size() == want
    _close_all([w])


def test_zoom_orig_drops_font_size_from_layout(env):
    tmp, sm = env
    w = _make_window([str(tmp)])
    t, = w.get_terminals()
    t.zoom_in()
    out = {}
    t.describe_layout(0, 'w', out, 0)
    assert 'font_size' in out['terminal0']
    t.zoom_orig()
    assert t.custom_font_size is None
    out = {}
    t.describe_layout(0, 'w', out, 0)
    assert 'font_size' not in out['terminal0']
    _close_all([w])
