"""m21: end-to-end session restore round-trip on the real ./terminator.

One setup run builds 2 tabs (tab 1 split), per-terminal cwd, a manual
terminal title, a forced window title, floating (overlay) maximise and
coloured + plain output, then quits via SIGTERM (normal finalize). Each
test copies that saved state to a fresh HOME and restarts once.
Needs an X display (tests/run_tests.sh provides Xvfb).
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DRIVER = os.path.join(HERE, 'e2e', 'roundtrip_driver.py')
MARK = 'RTMARK'

pytestmark = pytest.mark.skipif(not os.environ.get('DISPLAY'),
                                reason='needs an X display')


def _env(root):
    home = os.path.join(root, 'home')
    env = dict(os.environ)
    env.update(HOME=home, XDG_CONFIG_HOME=os.path.join(home, '.config'),
               XDG_CACHE_HOME=os.path.join(home, '.cache'),
               XDG_STATE_HOME=os.path.join(home, '.local', 'state'),
               RT_DIR_A=os.path.join(root, 'a'), RT_DIR_B=os.path.join(root, 'b'),
               RT_ORIG_CWD=root, SHELL='/bin/bash', PS1='$ ')
    return env


def _run(root, phase, extra_env=None):
    env = _env(root)
    env.update(extra_env or {})
    out = os.path.join(root, '%s.json' % phase)
    log = os.path.join(root, '%s.log' % phase)
    with open(log, 'w') as fh:
        rc = subprocess.call([sys.executable, DRIVER, phase, out, '-u', '-d'],
                             env=env, stdout=fh, stderr=subprocess.STDOUT,
                             timeout=120)
    data = json.load(open(out)) if os.path.exists(out) else {'error': 'no output'}
    logtext = open(log, errors='replace').read()
    assert 'error' not in data, (data, logtext[-3000:])
    assert rc == 0, logtext[-3000:]
    return data, logtext


@pytest.fixture(scope='module')
def saved(tmp_path_factory):
    root = str(tmp_path_factory.mktemp('rt-setup'))
    for d in ('home', 'a', 'b'):
        os.makedirs(os.path.join(root, d))
    # Short prompt: with a long wrapped prompt, bash's SIGWINCH redraw (the
    # split/overlay resizes) can overwrite the line above it in VTE, which
    # made the marker line flaky in an early run.
    with open(os.path.join(root, 'home', '.bashrc'), 'w') as fh:
        fh.write("PS1='$ '\n")
    pre, _log = _run(root, 'setup')
    by_cwd = {t['cwd']: t for t in pre['terminals']}
    t1 = by_cwd[os.path.join(root, 'a')]
    t2 = by_cwd[os.path.join(root, 'b')]
    t3 = [t for t in pre['terminals'] if t not in (t1, t2)][0]
    return {'root': root, 'pre': pre, 't1': t1['uuid'], 't2': t2['uuid'],
            't3': t3['uuid']}


def _clone(saved, tmp_path):
    root = str(tmp_path)
    shutil.copytree(os.path.join(saved['root'], 'home'), os.path.join(root, 'home'),
                    symlinks=True)
    for d in ('a', 'b'):
        os.makedirs(os.path.join(root, d))
    # Saved session paths point at the setup root; rewrite to this clone.
    sp = os.path.join(root, 'home', '.local', 'state', 'terminator', 'session.json')
    txt = open(sp).read().replace(saved['root'], root)
    open(sp, 'w').write(txt)
    return root


def _cache(root, uuid):
    return os.path.join(root, 'home', '.cache', 'terminator', 'scrollback',
                        uuid + '.txt')


def _terms(post):
    return {t['uuid']: t for t in post['terminals']}


def test_setup_state_was_built(saved):
    pre = saved['pre']
    assert len(pre['terminals']) == 3
    w = pre['windows'][0]
    assert w['tabs'] == 2 and w['overlay'] and w['overlay_uuid'] == saved['t1']
    assert w['forced_title'] == 'FixedWinTitle'
    texts = {t['uuid']: t['text'] for t in pre['terminals']}
    assert MARK + '_RED_T1' in texts[saved['t1']]
    for u in (saved['t1'], saved['t2'], saved['t3']):
        assert os.path.isfile(_cache(saved['root'], u)), u
    # The saved cache (not just the live VTE) must hold each marker.
    assert MARK + '_RED_T1' in open(_cache(saved['root'], saved['t1'])).read()
    assert MARK + '_PLAIN_T2' in open(_cache(saved['root'], saved['t2'])).read()


def test_full_roundtrip(saved, tmp_path):
    root = _clone(saved, tmp_path)
    post, log = _run(root, 'verify')
    terms = _terms(post)
    assert set(terms) == {saved['t1'], saved['t2'], saved['t3']}
    w = post['windows'][0]
    assert len(post['windows']) == 1 and w['tabs'] == 2
    assert w['overlay'] and w['overlay_uuid'] == saved['t1']
    assert w['forced_title'] == 'FixedWinTitle'
    assert terms[saved['t1']]['cwd'] == os.path.join(root, 'a')
    assert terms[saved['t2']]['cwd'] == os.path.join(root, 'b')
    assert terms[saved['t2']]['title'] == 'MyManualTitle'
    assert not terms[saved['t1']]['title'] and not terms[saved['t3']]['title']
    assert MARK + '_RED_T1' in terms[saved['t1']]['text']
    assert MARK + '_PLAIN_T2' in terms[saved['t2']]['text']
    assert MARK + '_PLAIN_T3' in terms[saved['t3']]['text']
    red = [l for l in terms[saved['t1']]['sgr'].splitlines()
           if l.endswith(MARK + '_RED_T1\x1b[0m') or (MARK + '_RED_T1\x1b') in l]
    assert red and '\x1b[' in red[0].split(MARK)[0], terms[saved['t1']]['sgr'][-500:]
    assert 'Traceback' not in log


def test_restore_robustness_missing_cwd_deleted_and_corrupt_cache(saved, tmp_path):
    root = _clone(saved, tmp_path)
    shutil.rmtree(os.path.join(root, 'b'))                     # t2 cwd gone
    os.unlink(_cache(root, saved['t3']))                        # t3 cache gone
    with open(_cache(root, saved['t1']), 'wb') as fh:           # t1 cache junk
        fh.write(b'\xff\xfe\x00garbage\x1b[999;9999H\x1b]0;evil\x07\x1b[31' * 50)
    post, log = _run(root, 'verify')
    terms = _terms(post)
    assert set(terms) == {saved['t1'], saved['t2'], saved['t3']}
    assert terms[saved['t2']]['cwd'] == os.path.join(root, 'home')
    assert terms[saved['t2']]['title'] == 'MyManualTitle'
    assert MARK + '_PLAIN_T2' in terms[saved['t2']]['text']
    assert MARK not in terms[saved['t3']]['text']
    assert 'garbage' in terms[saved['t1']]['text']
    assert post['windows'][0]['tabs'] == 2
    assert 'Traceback' not in log


def test_restore_with_cache_disabled_between_runs(saved, tmp_path):
    root = _clone(saved, tmp_path)
    cfgdir = os.path.join(root, 'home', '.config', 'terminator')
    os.makedirs(cfgdir, exist_ok=True)
    with open(os.path.join(cfgdir, 'config'), 'w') as fh:
        fh.write('[global_config]\n  scrollback_cache = False\n')
    post, log = _run(root, 'verify')
    terms = _terms(post)
    assert set(terms) == {saved['t1'], saved['t2'], saved['t3']}
    for t in terms.values():
        assert MARK not in t['text']
    assert terms[saved['t2']]['cwd'] == os.path.join(root, 'b')
    assert 'Traceback' not in log
