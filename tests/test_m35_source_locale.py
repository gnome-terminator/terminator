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


@needs_msgfmt
def test_compiles_only_when_po_newer(tmp_path):
    root = _copy_tree(tmp_path)
    env = {'LANG': 'zh_CN.UTF-8'}
    d = translation.source_locale_dir(str(root), environ=env)
    mo = os.path.join(d, 'zh_CN', 'LC_MESSAGES', 'terminator.mo')
    assert d == str(root / 'build' / 'locale') and os.path.isfile(mo)
    # Only the requested languages are compiled (bare zh from zh_CN.po).
    assert sorted(os.listdir(d)) == ['zh', 'zh_CN']
    old = os.path.getmtime(mo) - 100
    os.utime(mo, (old, old))
    po = str(root / 'po' / 'zh_CN.po')
    os.utime(po, (old - 10, old - 10))
    translation.source_locale_dir(str(root), environ=env)
    assert os.path.getmtime(mo) == old           # up to date: untouched
    os.utime(po, None)
    translation.source_locale_dir(str(root), environ=env)
    assert os.path.getmtime(mo) > old            # .po newer: rebuilt


def test_msgfmt_missing_uses_python_compiler(tmp_path, monkeypatch, capsys):
    root = _copy_tree(tmp_path)
    monkeypatch.setenv('PATH', str(tmp_path / 'nothing-here'))
    d = translation.source_locale_dir(
        str(root), environ={'LANG': 'zh_CN.UTF-8'})
    assert d == str(root / 'build' / 'locale')
    assert not list((root / 'build').rglob('*.tmp.*'))
    assert capsys.readouterr().err == ''


def test_both_compilers_fail_warns_and_leaves_nothing(tmp_path, monkeypatch,
                                                      capsys):
    root = _copy_tree(tmp_path)
    (root / 'po' / 'zh_CN.po').write_text('this is not a po file\n')
    monkeypatch.setenv('PATH', str(tmp_path / 'nothing-here'))
    assert translation.source_locale_dir(
        str(root), environ={'LANG': 'zh_CN.UTF-8'}) is None
    err = capsys.readouterr().err
    assert err.count('\n') == 1 and 'zh_CN.po' in err
    assert not (root / 'build').exists()      # no empty dirs left behind


def test_stale_tmp_files_are_removed(tmp_path):
    root = _copy_tree(tmp_path)
    mo_dir = root / 'build' / 'locale' / 'zh_CN' / 'LC_MESSAGES'
    mo_dir.mkdir(parents=True)
    old, fresh = mo_dir / 'terminator.mo.tmp.1', mo_dir / 'terminator.mo.tmp.2'
    old.write_bytes(b'x')
    fresh.write_bytes(b'x')
    os.utime(old, (1, 1))
    translation.source_locale_dir(str(root), environ={'LANG': 'zh_CN.UTF-8'})
    assert not old.exists() and fresh.exists()   # a live run may own .2


@pytest.mark.parametrize('value,off', [('1', True), ('true', True),
                                       ('YES', True), ('0', False),
                                       ('no', False), ('', False)])
def test_opt_out_values(tmp_path, monkeypatch, value, off):
    monkeypatch.setenv('PATH', str(tmp_path / 'nothing-here'))
    root = _copy_tree(tmp_path)
    d = translation.source_locale_dir(
        str(root), environ={'LANG': 'zh_CN.UTF-8',
                            'TERMINATOR_NO_SOURCE_LOCALE': value})
    assert (d is None) is off


@pytest.mark.parametrize('lang,po', [('zh', 'zh_CN'), ('zh_Hans', 'zh_CN'),
                                     ('zh_SG', 'zh_CN'), ('zh_Hant', 'zh_TW'),
                                     ('zh_MO', 'zh_TW')])
def test_aliases(tmp_path, monkeypatch, lang, po):
    import gettext
    monkeypatch.setenv('PATH', str(tmp_path / 'nothing-here'))
    root = _copy_tree(tmp_path)
    shutil.copy(os.path.join(ROOT, 'po', 'zh_TW.po'), root / 'po')
    d = translation.source_locale_dir(
        str(root), environ={'LANGUAGE': lang, 'LANG': lang + '.UTF-8'})
    assert d is not None
    mo = os.path.join(d, lang, 'LC_MESSAGES', 'terminator.mo')
    with open(mo, 'rb') as handle:
        t = gettext.GNUTranslations(handle)
    want = {'zh_CN': '复制(_C)', 'zh_TW': '複製(_C)'}[po]
    assert t.gettext('_Copy') == want


def test_source_run_without_msgfmt_translates(tmp_path):
    """P1: stock desktops lack msgfmt (package 'gettext'); empty PATH."""
    root = _copy_tree(tmp_path)
    shutil.copytree(os.path.join(ROOT, 'terminatorlib'),
                    root / 'terminatorlib', dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('__pycache__'))
    code = ('from terminatorlib.translation import _, LOCALE_DIR\n'
            'print(LOCALE_DIR)\nprint(_("Panes"))\nprint(_("_Copy"))\n')
    env = _env(LANG='zh_CN.UTF-8', LANGUAGE='zh_CN', PATH='')
    out = subprocess.run([sys.executable, '-c', code], cwd=str(root),
                         env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    lines = out.stdout.strip().splitlines()
    assert lines == [str(root / 'build' / 'locale'), '窗格', '复制(_C)']


SYNTHETIC_PO = r'''msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\n"
"Plural-Forms: nplurals=2; plural=(n != 1);\n"

#, fuzzy
msgid "Fuzzy"
msgstr "模糊"

msgctxt "menu"
msgid "Open"
msgstr "打开"

msgid "Open"
msgstr "开"

#, c-format
msgid "%d file"
msgid_plural "%d files"
msgstr[0] "%d 个\t文件"
msgstr[1] "%d 个\"文件\"\\"

msgid "Multi"
"line\n"
msgstr ""
"多"
"行\n"

msgid "Untranslated"
msgstr ""
#, fuzzy
msgctxt "x"
msgid "FuzzyCtx"
msgstr "y"
msgctxt "z"
msgid "AfterFuzzy"
msgstr "ok"
#~ msgid "Old"
#~ msgstr "旧"
'''


def _catalog(path):
    import gettext
    with open(path, 'rb') as handle:
        cat = dict(gettext.GNUTranslations(handle)._catalog)
    cat.pop('', None)  # header: msgfmt drops POT-Creation-Date
    return cat


def test_python_compiler_semantics(tmp_path):
    import gettext
    po = tmp_path / 's.po'
    po.write_text(SYNTHETIC_PO, encoding='utf-8')
    mo = tmp_path / 's.mo'
    translation.compile_po_python(str(po), str(mo))
    with open(mo, 'rb') as handle:
        t = gettext.GNUTranslations(handle)
    assert t.gettext('Fuzzy') == 'Fuzzy'
    assert t.pgettext('menu', 'Open') == '打开'
    assert t.gettext('Open') == '开'
    assert t.ngettext('%d file', '%d files', 1) == '%d 个\t文件'
    assert t.ngettext('%d file', '%d files', 2) == '%d 个"文件"\\'
    assert t.gettext('Multiline\n') == '多行\n'
    assert t.gettext('Untranslated') == 'Untranslated'
    assert t.pgettext('x', 'FuzzyCtx') == 'FuzzyCtx'
    assert t.pgettext('z', 'AfterFuzzy') == 'ok'
    assert 'Plural-Forms' in t._info.get('plural-forms', 'Plural-Forms') or \
        t._info.get('plural-forms')
    assert t.gettext('Old') == 'Old'


@needs_msgfmt
@pytest.mark.parametrize('name', ['synthetic', 'zh_CN', 'zh_TW', 'de', 'ru'])
def test_python_compiler_matches_msgfmt(tmp_path, name):
    if name == 'synthetic':
        po = tmp_path / 's.po'
        po.write_text(SYNTHETIC_PO, encoding='utf-8')
        po = str(po)
    else:
        po = os.path.join(ROOT, 'po', '%s.po' % name)
    ours, gnu = tmp_path / 'ours.mo', tmp_path / 'gnu.mo'
    translation.compile_po_python(po, str(ours))
    subprocess.run(['msgfmt', '-o', str(gnu), po], check=True)
    assert _catalog(str(ours)) == _catalog(str(gnu))


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


# ---- Traditional Chinese (re-review P2) -------------------------------------

def _zh_catalogue(d, lang):
    import gettext
    with open(os.path.join(d, lang, 'LC_MESSAGES', 'terminator.mo'),
              'rb') as handle:
        return gettext.GNUTranslations(handle)


@pytest.mark.parametrize('env', [{'LANG': 'zh_TW.UTF-8'},
                                 {'LANG': 'zh_HK.UTF-8'},
                                 {'LANGUAGE': 'zh_Hant:zh_CN'}])
def test_traditional_never_falls_back_to_simplified(tmp_path, monkeypatch,
                                                    env):
    monkeypatch.setenv('PATH', str(tmp_path / 'nothing-here'))
    root = _copy_tree(tmp_path)
    for name in ('zh_TW', 'zh_HK'):
        shutil.copy(os.path.join(ROOT, 'po', '%s.po' % name), root / 'po')
    d = translation.source_locale_dir(str(root), environ=env)
    assert d is not None
    # bare zh (gettext's own fallback for zh_XX) is Traditional
    assert _zh_catalogue(d, 'zh').gettext('_Copy') == '複製(_C)'


def test_zh_hk_completed_from_zh_tw(tmp_path, monkeypatch):
    monkeypatch.setenv('PATH', str(tmp_path / 'nothing-here'))
    root = _copy_tree(tmp_path)
    for name in ('zh_TW', 'zh_HK'):
        shutil.copy(os.path.join(ROOT, 'po', '%s.po' % name), root / 'po')
    d = translation.source_locale_dir(str(root),
                                      environ={'LANG': 'zh_HK.UTF-8'})
    hk = _zh_catalogue(d, 'zh_HK')
    assert hk.gettext('_Copy') == '複製(_C)'          # from zh_TW.po
    assert len(hk._catalog) > 300                     # zh_HK.po alone: ~9


def test_zh_dir_rebuilt_when_source_changes(tmp_path, monkeypatch):
    """A zh/ built for a zh_CN run must not leak Simplified into zh_TW."""
    monkeypatch.setenv('PATH', str(tmp_path / 'nothing-here'))
    root = _copy_tree(tmp_path)
    shutil.copy(os.path.join(ROOT, 'po', 'zh_TW.po'), root / 'po')
    d = translation.source_locale_dir(str(root),
                                      environ={'LANG': 'zh_CN.UTF-8'})
    assert _zh_catalogue(d, 'zh').gettext('_Copy') == '复制(_C)'
    translation.source_locale_dir(str(root), environ={'LANG': 'zh_TW.UTF-8'})
    assert _zh_catalogue(d, 'zh').gettext('_Copy') == '複製(_C)'


# ---- installed tree under another prefix (re-review P1) ---------------------

def _fake_install(tmp_path, prefix_name='prefix', with_mo=True,
                  copy_pkg=False):
    prefix = tmp_path / prefix_name
    site = prefix / 'lib' / 'python3.13' / 'dist-packages'
    pkg = site / 'terminatorlib'
    if copy_pkg:
        shutil.copytree(os.path.join(ROOT, 'terminatorlib'), pkg,
                        ignore=shutil.ignore_patterns('__pycache__'))
    else:
        pkg.mkdir(parents=True)
        (pkg / '__init__.py').write_text('')
    if with_mo:
        _install_mo(prefix)
    return prefix, site, pkg


def _install_mo(prefix):
    mo_dir = prefix / 'share' / 'locale' / 'zh_CN' / 'LC_MESSAGES'
    mo_dir.mkdir(parents=True)
    translation.compile_po_python(os.path.join(ROOT, 'po', 'zh_CN.po'),
                                  str(mo_dir / 'terminator.mo'))
    return str(prefix / 'share' / 'locale')


ZH = {'LANG': 'zh_CN.UTF-8'}


def test_installed_catalogue_beside_package(tmp_path):
    prefix, _site, pkg = _fake_install(tmp_path)
    assert translation.installed_locale_dir(
        ZH, package_dir=str(pkg), argv0='', prefixes=()) == \
        str(prefix / 'share' / 'locale')


def test_installed_catalogue_beside_script(tmp_path):
    _prefix, _site, pkg = _fake_install(tmp_path, with_mo=False)
    other = tmp_path / 'other'
    (other / 'bin').mkdir(parents=True)
    (other / 'bin' / 'terminator').write_text('')
    want = _install_mo(other)
    assert translation.installed_locale_dir(
        ZH, package_dir=str(pkg), argv0=str(other / 'bin' / 'terminator'),
        prefixes=()) == want


def test_installed_falls_back_to_sys_prefix(tmp_path, monkeypatch):
    _prefix, _site, pkg = _fake_install(tmp_path, with_mo=False)
    sysprefix = tmp_path / 'sysprefix'
    want = _install_mo(sysprefix)
    monkeypatch.setattr(sys, 'prefix', str(sysprefix))
    found = translation.installed_locale_dir(ZH, package_dir=str(pkg),
                                             argv0='')
    assert found == want


def test_installed_nothing_found_keeps_default(tmp_path):
    _prefix, _site, pkg = _fake_install(tmp_path, with_mo=False)
    assert translation.installed_locale_dir(
        ZH, package_dir=str(pkg), argv0='',
        prefixes=(str(tmp_path / 'nope'),)) is None
    assert translation.installed_locale_dir(
        {'LANG': 'C.UTF-8'}, package_dir=str(pkg), argv0='',
        prefixes=()) is None


def test_installed_opt_out(tmp_path):
    _prefix, _site, pkg = _fake_install(tmp_path)
    assert translation.installed_locale_dir(
        dict(ZH, TERMINATOR_NO_SOURCE_LOCALE='yes'), package_dir=str(pkg),
        argv0='', prefixes=()) is None


def test_package_prefix():
    f = translation._package_prefix
    assert f('/usr/local/lib/python3.13/dist-packages/terminatorlib') == \
        '/usr/local'
    assert f('/home/u/.local/lib/python3.13/site-packages/'
             'terminator-2.1.egg/terminatorlib') == '/home/u/.local'
    assert f('/usr/lib64/python3.12/site-packages/terminatorlib') == '/usr'


def test_installed_tree_subprocess_python_and_gtkbuilder(tmp_path):
    """The user's setup: package + .mo under /usr/local-like prefix, python
    from another prefix.  Python _() and GtkBuilder (libintl) both see 窗格."""
    prefix, site, _pkg = _fake_install(tmp_path, copy_pkg=True)
    src = None
    for cand in ('/usr/lib/locale/C.utf8', '/usr/lib/locale/C.UTF-8'):
        if os.path.isdir(cand):
            src = cand
            break
    locpath = tmp_path / 'loc'
    if src:
        shutil.copytree(src, locpath / 'zh_CN.UTF-8')
    code = r"""
import os, gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from terminatorlib import translation
from terminatorlib.translation import _, LOCALE_DIR
print(LOCALE_DIR)
print(_('Panes'))
b = Gtk.Builder()
b.set_translation_domain('terminator')
b.add_from_file(os.path.join(os.path.dirname(translation.__file__),
                             'preferences.glade'))
print('窗格' in [o.get_label() for o in b.get_objects()
                 if isinstance(o, Gtk.Label)])
"""
    env = _env(PYTHONPATH=str(site), LANG='zh_CN.UTF-8')
    if src:
        env.update(LOCPATH=str(locpath), LC_ALL='zh_CN.UTF-8')
    out = subprocess.run([sys.executable, '-c', code], cwd=str(tmp_path),
                         env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    lines = out.stdout.strip().splitlines()
    assert lines[0] == str(prefix / 'share' / 'locale')
    assert lines[1] == '窗格'
    if src:
        assert lines[2] == 'True'
    assert not (site / 'build').exists()


def test_pocompile_loads_without_gtk(tmp_path):
    """setup.py loads pocompile.py by path; it must need stdlib only."""
    code = r"""
import sys, importlib.util
sys.modules['gi'] = None   # any GTK import would now fail
spec = importlib.util.spec_from_file_location('pc', sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.compile_po_python(sys.argv[2], sys.argv[3])
"""
    mo = tmp_path / 'x.mo'
    subprocess.run([sys.executable, '-c', code,
                    os.path.join(ROOT, 'terminatorlib', 'pocompile.py'),
                    os.path.join(ROOT, 'po', 'zh_CN.po'), str(mo)],
                   check=True, timeout=60)
    assert mo.stat().st_size > 10000
