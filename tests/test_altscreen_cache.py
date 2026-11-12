"""M9: scrollback cache must not snapshot the alternate screen (vim/htop)."""

from __future__ import print_function

import pytest

from terminatorlib.altscreen import AltScreenDetector


def _reset_borg(name):
    from terminatorlib.borg import Borg
    Borg._Borg__shared_state.pop(name, None)


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    _reset_borg('ScrollbackCache')
    import terminatorlib.scrollback as sb
    c = sb.ScrollbackCache()
    cfg = {'scrollback_cache_lines': 100, 'scrollback_cache_max_kb': 64}
    monkeypatch.setattr(c, '_cfg', lambda k, d=None: cfg.get(k, d))
    c._config = {'scrollback_infinite': False}
    c._dir = str(tmp_path / 'sb')
    import os
    os.makedirs(c._dir)
    monkeypatch.setattr(c, 'path_for',
                        lambda u: os.path.join(c._dir, u + '.txt'))
    screen = {'text': 'history line\n$ vim'}
    monkeypatch.setattr(sb, 'read_last_n_lines_raw',
                        lambda vte, n, **kw: (screen['text'], False))
    yield c, screen
    _reset_borg('ScrollbackCache')


class _Alt(object):
    def __init__(self):
        self.detector = AltScreenDetector()


class _Term(object):
    vte = object()

    def __init__(self):
        self.altscreen = _Alt()


def _read(c, u):
    with open(c.path_for(u)) as fh:
        return fh.read()


def test_flush_deferred_while_alt_screen_active(cache):
    c, screen = cache
    t = _Term()
    c._flush_uuid(t, 'u1', sync=True)
    assert _read(c, 'u1') == 'history line\n$ vim'

    t.altscreen.detector.active = True
    screen['text'] = '~\n~\n"file" 3L'
    c._flush_uuid(t, 'u1', sync=True)
    assert _read(c, 'u1') == 'history line\n$ vim'   # untouched
    assert 'u1' in c._dirty                           # retried later

    t.altscreen.detector.active = False
    screen['text'] = 'history line\n$ vim\n$ '
    c._flush_uuid(t, 'u1', sync=True)
    assert _read(c, 'u1') == 'history line\n$ vim\n$ '
    assert 'u1' not in c._dirty


def test_in_alt_screen_tolerates_missing_detector():
    from terminatorlib.scrollback import in_alt_screen

    class Bare(object):
        pass
    assert in_alt_screen(Bare()) is False
    b = Bare()
    b.altscreen = None
    assert in_alt_screen(b) is False


def test_flush_deferred_for_tui_in_fresh_terminal(cache):
    """No history yet (active stays False) but a collapsed+busy episode
    is running: still don't snapshot the TUI screen."""
    c, screen = cache
    t = _Term()
    c._flush_uuid(t, 'u3', sync=True)
    det = t.altscreen.detector
    det.update(collapsed=True, busy=True, raw=True, cursor_beyond=False)
    assert det.active is False and det.episode_start is not None
    screen['text'] = 'VIM SCREEN'
    c._flush_uuid(t, 'u3', sync=True)
    assert _read(c, 'u3') == 'history line\n$ vim'
    det.update(collapsed=False, busy=False)
    c._flush_uuid(t, 'u3', sync=True)
    assert _read(c, 'u3') == 'VIM SCREEN'
