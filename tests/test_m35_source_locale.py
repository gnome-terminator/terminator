"""m35: running from a source checkout picks up po/<lang>.po translations.

The system /usr/share/locale/*/terminator.mo is missing or from an old distro
package, so translation.py binds the domain to <repo>/build/locale (compiled
on demand from po/) for both Python gettext and libintl (GtkBuilder)."""
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from terminatorlib import translation  # noqa: E402

needs_msgfmt = pytest.mark.skipif(shutil.which('msgfmt') is None,
                                  reason='msgfmt (gettext) not installed')

# One fork string per feature area; all must be translated in zh_CN.
FORK_STRINGS = (
    'Panes',                                     # prefs Panes tab
    'Close terminals with running processes?',   # close confirm
    'Terminal menu',                             # titlebar
    '<b>Scrollback cache</b>',                   # scrollback prefs
    'Version: %s',                               # about page
)


def _env(**extra):
    env = {k: v for k, v in os.environ.items()
           if k not in ('LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG',
                        'TERMINATOR_NO_SOURCE_LOCALE')}
    env.update(extra)
    return env


def _run(code, **extra):
    out = subprocess.run([sys.executable, '-c', code], cwd=ROOT,
                         env=_env(**extra), capture_output=True, text=True,
                         timeout=60)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip().splitlines()


def _copy_tree(tmp_path):
    """Minimal fake source tree with its own build dir."""
    root = tmp_path / 'src'
    (root / 'po').mkdir(parents=True)
    (root / 'terminatorlib').mkdir()
    (root / 'setup.py').write_text('')
    (root / 'po' / 'POTFILES.in').write_text('')
    shutil.copy(os.path.join(ROOT, 'po', 'zh_CN.po'), root / 'po')
    return root


def test_wanted_languages():
    f = translation._wanted_languages
    assert f({'LANG': 'zh_CN.UTF-8'}) == ['zh_CN', 'zh']
    assert f({'LANGUAGE': 'zh_CN:en', 'LANG': 'C'}) == ['zh_CN', 'zh', 'en']
    assert f({'LC_ALL': 'de_DE.UTF-8@euro', 'LANG': 'fr_FR'}) == ['de_DE', 'de']
    assert f({'LANG': 'C.UTF-8'}) == []
    assert f({}) == []


def test_installed_tree_keeps_system_catalogue(tmp_path):
    (tmp_path / 'terminatorlib').mkdir()
    assert translation.source_locale_dir(
        str(tmp_path), environ={'LANG': 'zh_CN.UTF-8'}) is None


def test_opt_out_env(tmp_path):
    root = _copy_tree(tmp_path)
    assert translation.source_locale_dir(
        str(root), environ={'LANG': 'zh_CN.UTF-8',
                            'TERMINATOR_NO_SOURCE_LOCALE': '1'}) is None


@needs_msgfmt
def test_compiles_only_when_po_newer(tmp_path):
    root = _copy_tree(tmp_path)
    env = {'LANG': 'zh_CN.UTF-8'}
    d = translation.source_locale_dir(str(root), environ=env)
    mo = os.path.join(d, 'zh_CN', 'LC_MESSAGES', 'terminator.mo')
    assert d == str(root / 'build' / 'locale') and os.path.isfile(mo)
    # Only the requested language is compiled.
    assert os.listdir(d) == ['zh_CN']
    old = os.path.getmtime(mo) - 100
    os.utime(mo, (old, old))
    po = str(root / 'po' / 'zh_CN.po')
    os.utime(po, (old - 10, old - 10))
    translation.source_locale_dir(str(root), environ=env)
    assert os.path.getmtime(mo) == old           # up to date: untouched
    os.utime(po, None)
    translation.source_locale_dir(str(root), environ=env)
    assert os.path.getmtime(mo) > old            # .po newer: rebuilt


def test_msgfmt_missing_is_silent(tmp_path, monkeypatch):
    root = _copy_tree(tmp_path)
    monkeypatch.setenv('PATH', str(tmp_path / 'nothing-here'))
    assert translation.source_locale_dir(
        str(root), environ={'LANG': 'zh_CN.UTF-8'}) is None
    assert not list((root / 'build').rglob('*.tmp.*')) \
        if (root / 'build').exists() else True


def test_no_catalogue_for_language_keeps_system(tmp_path):
    root = _copy_tree(tmp_path)
    assert translation.source_locale_dir(
        str(root), environ={'LANG': 'xx_YY.UTF-8'}) is None


@needs_msgfmt
def test_zh_cn_source_run_translates_fork_strings():
    code = ('from terminatorlib.translation import _, LOCALE_DIR\n'
            'print(LOCALE_DIR)\n'
            'for s in %r: print(repr(_(s)))\n' % (FORK_STRINGS,))
    lines = _run(code, LANG='zh_CN.UTF-8', LANGUAGE='zh_CN')
    assert lines[0] == os.path.join(ROOT, 'build', 'locale')
    got = [eval(x) for x in lines[1:]]  # noqa: S307 - our own repr output
    assert got[0] == '窗格'
    for src, dst in zip(FORK_STRINGS, got):
        assert dst != src, 'untranslated in zh_CN: %r' % src


@needs_msgfmt
def test_gtkbuilder_prefs_panes_tab_translated(tmp_path):
    """C-level binding: the real preferences.glade 'Panes' tab label is
    translated by GtkBuilder.  The box may have no zh_CN locale, so clone
    C.utf8 under that name via LOCPATH (gettext keys on the locale name)."""
    src = None
    for cand in ('/usr/lib/locale/C.utf8', '/usr/lib/locale/C.UTF-8'):
        if os.path.isdir(cand):
            src = cand
            break
    if src is None:
        pytest.skip('no C.utf8 locale directory to clone')
    locpath = tmp_path / 'loc'
    shutil.copytree(src, locpath / 'zh_CN.UTF-8')
    code = r'''
import os, gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from terminatorlib.translation import LOCALE_DIR
b = Gtk.Builder()
b.set_translation_domain('terminator')
b.add_from_file(os.path.join('terminatorlib', 'preferences.glade'))
labels = [o.get_label() for o in b.get_objects() if isinstance(o, Gtk.Label)]
print(LOCALE_DIR is not None, '窗格' in labels, 'Panes' in labels)
'''
    out = _run(code, LOCPATH=str(locpath), LC_ALL='zh_CN.UTF-8')
    assert out[-1] == 'True True False'
    # Opt-out: no source catalogue, and the box has no system one.
    out = _run(code, LOCPATH=str(locpath), LC_ALL='zh_CN.UTF-8',
               TERMINATOR_NO_SOURCE_LOCALE='1')
    assert out[-1].split()[0] == 'False'


@pytest.mark.skipif(not all(shutil.which(t) for t in
                            ('xgettext', 'msgmerge', 'msgattrib')),
                    reason='gettext tools not installed')
def test_every_core_string_has_zh_cn_translation(tmp_path):
    """Extract all _() strings (core, not third-party plugins) and all
    translatable Glade strings; zh_CN.po must translate every one."""
    py = sorted(os.path.join('terminatorlib', f)
                for f in os.listdir(os.path.join(ROOT, 'terminatorlib'))
                if f.endswith('.py')) + ['terminator', 'remotinator']
    glade = [os.path.join('terminatorlib', f) for f in
             ('preferences.glade', 'layoutlauncher.glade')]
    pot_py, pot_ui = tmp_path / 'py.pot', tmp_path / 'ui.pot'
    subprocess.run(['xgettext', '--from-code=UTF-8', '-L', 'Python', '-k_',
                    '-o', str(pot_py)] + py, cwd=ROOT, check=True,
                   capture_output=True)
    subprocess.run(['xgettext', '--from-code=UTF-8', '-L', 'Glade',
                    '-o', str(pot_ui)] + glade, cwd=ROOT, check=True,
                   capture_output=True)
    pot = tmp_path / 'all.pot'
    subprocess.run(['msgcat', '-o', str(pot), str(pot_py), str(pot_ui)],
                   check=True, capture_output=True)
    merged = tmp_path / 'zh.po'
    subprocess.run(['msgmerge', '-q', '--no-fuzzy-matching', '-o',
                    str(merged), os.path.join(ROOT, 'po', 'zh_CN.po'),
                    str(pot)], check=True, capture_output=True)
    for flag in ('--untranslated', '--only-fuzzy'):
        out = subprocess.run(['msgattrib', flag, '--no-obsolete',
                              str(merged)], check=True, capture_output=True,
                             text=True).stdout
        # Entries carry '#:' source refs; the header entry has none.
        # (Counting '#:' also catches wrapped 'msgid ""' multi-line ids.)
        refs = [l for l in out.splitlines() if l.startswith('#:')]
        assert not refs, '%s zh_CN entries:\n%s' % (flag, out)
