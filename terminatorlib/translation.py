# Terminator - multiple gnome terminals in one window
# Copyright (C) 2006-2010  cmsj@tenshu.net
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 2 only.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

"""Terminator by Chris Jones <cmsj@tenshu.net>"""

import os
import sys

from .version import APP_NAME
from .util import dbg
from .pocompile import compile_po_python  # noqa: F401  (re-exported)

_ = None

# Locale lookup (m35).
#
# Source checkout (``python3 ./terminator``): the system catalogue is missing
# or from an older distro package without this fork's strings, so we compile
# po/<lang>.po for the user's languages into <repo>/build/locale/<lang>/
# LC_MESSAGES/terminator.mo (the localedir layout; setup.py's build/mo is
# flat) when the .po is newer, with msgfmt or the pure-Python fallback, and
# bind the domain there.
#
# Installed tree: ``setup.py install --prefix /usr/local`` puts catalogues
# in /usr/local/share/locale, but Python gettext and libintl only look in
# sys.base_prefix/share/locale (/usr/share/locale).  We look for
# <prefix>/share/locale/<lang>/LC_MESSAGES/terminator.mo next to the
# package, next to the script, then sys.prefix, sys.base_prefix,
# /usr/local, /usr, and bind the first hit.
#
# Both bindings cover Python gettext and libintl (GtkBuilder).
# TERMINATOR_NO_SOURCE_LOCALE=1|true|yes disables all of this.

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCALE_DIR = None  # directory bound for APP_NAME, None = system default

# Locales without a po/<lang>.po of their own.  The .mo is written under the
# requested name, because that is the directory gettext/libintl look in.
LANG_ALIASES = {
    'zh_Hans': 'zh_CN', 'zh_SG': 'zh_CN',
    'zh_Hant': 'zh_TW', 'zh_MO': 'zh_TW',
}
# Sparse catalogues completed from a fuller one of the same script.
BASE_CATALOGUE = {'zh_HK': 'zh_TW'}
TRADITIONAL_ZH = ('zh_TW', 'zh_HK', 'zh_MO', 'zh_Hant')

_TMP_MAX_AGE = 60  # seconds; older terminator.mo.tmp.* files are litter


def _is_source_tree(root):
    """True for a git/source checkout, False for an installed package"""
    return (os.path.isfile(os.path.join(root, 'setup.py')) and
            os.path.isfile(os.path.join(root, 'po', 'POTFILES.in')) and
            os.path.isdir(os.path.join(root, 'terminatorlib')))


def _codes(environ):
    """Locale codes from LANGUAGE/LC_ALL/LC_MESSAGES/LANG (first set wins,
    like Python gettext), encoding/modifier stripped, C/POSIX dropped."""
    raw = []
    for var in ('LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG'):
        val = environ.get(var)
        if val:
            raw = val.split(':')
            break
    codes = []
    for item in raw:
        code = item.split('@')[0].split('.')[0].strip()
        if code and code not in ('C', 'POSIX') and code not in codes:
            codes.append(code)
    return codes


def _wanted_languages(environ=None):
    """Language codes gettext would try: 'zh_CN.UTF-8' -> ['zh_CN', 'zh']."""
    environ = os.environ if environ is None else environ
    langs = []
    for code in _codes(environ):
        for cand in (code, code.split('_')[0]):
            if cand and cand not in langs:
                langs.append(cand)
    return langs


def _traditional(environ):
    """True when the first Chinese locale asked for is Traditional"""
    for code in _codes(environ):
        if code == 'zh' or code.startswith('zh_'):
            return code in TRADITIONAL_ZH
    return False


def _sources_for(root, lang, traditional=False):
    """.po files to compile for lang, base first, or [] if none."""
    def po(name):
        path = os.path.join(root, 'po', '%s.po' % name)
        return path if os.path.isfile(path) else None

    own = po(lang)
    if own:
        base = po(BASE_CATALOGUE[lang]) if lang in BASE_CATALOGUE else None
        return [base, own] if base else [own]
    if lang == 'zh':
        target = 'zh_TW' if traditional else 'zh_CN'
    else:
        target = LANG_ALIASES.get(lang)
    if target:
        return _sources_for(root, target, traditional)
    return []


def _msgfmt(po, out):
    """Run GNU msgfmt; True on success.  Raises if it cannot be started."""
    import subprocess
    rc = subprocess.call(['msgfmt', '-o', out, po],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, timeout=30)
    return rc == 0 and os.path.isfile(out)


def _clean_stale_tmp(mo_dir):
    import time
    try:
        names = os.listdir(mo_dir)
    except OSError:
        return
    now = time.time()
    for name in names:
        if name.startswith('%s.mo.tmp.' % APP_NAME):
            path = os.path.join(mo_dir, name)
            try:
                if now - os.path.getmtime(path) > _TMP_MAX_AGE:
                    os.unlink(path)
            except OSError:
                pass


def _remove_empty_dirs(path, stop):
    """Remove path and its parents while empty, never above stop"""
    stop = os.path.abspath(stop)
    path = os.path.abspath(path)
    while path.startswith(stop + os.sep) or path == stop:
        try:
            os.rmdir(path)
        except OSError:
            return
        if path == stop:
            return
        path = os.path.dirname(path)


def _stamp(sources):
    return '\n'.join(os.path.basename(p) for p in sources) + '\n'


def _is_current(mo, sources):
    """mo exists, is newer than every source, and was built from them"""
    try:
        mtime = os.path.getmtime(mo)
        if any(os.path.getmtime(p) > mtime for p in sources):
            return False
        with open(mo + '.src', 'r') as handle:
            return handle.read() == _stamp(sources)
    except OSError:
        return False


def _compile_one(sources, mo_dir, mo, mo_root):
    """Compile sources (base first) into mo via msgfmt (single file) or the
    Python compiler.  Never raises; returns True when mo was (re)written."""
    tmp = '%s.tmp.%d' % (mo, os.getpid())
    try:
        os.makedirs(mo_dir, exist_ok=True)
    except OSError as ex:  # read-only tree
        dbg('source locale: cannot create %s: %s' % (mo_dir, ex))
        return False
    _clean_stale_tmp(mo_dir)
    po, base = sources[-1], (sources[0] if len(sources) > 1 else None)
    compilers = [] if base else [lambda: _msgfmt(po, tmp)]
    compilers.append(lambda: compile_po_python(po, tmp, base=base))
    ok = False
    for compiler in compilers:
        try:
            if compiler() and os.path.isfile(tmp) and \
                    os.path.getsize(tmp) > 0:
                os.replace(tmp, mo)
                ok = True
                break
        except Exception as ex:  # msgfmt missing/failed, parse error...
            dbg('source locale: compiling %s failed: %s' % (po, ex))
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass
    if ok:
        try:
            with open(mo + '.src', 'w') as handle:
                handle.write(_stamp(sources))
        except OSError:
            pass
    else:
        sys.stderr.write('terminator: could not compile %s for the source '
                         'checkout; using system translations\n' % po)
        _remove_empty_dirs(mo_dir, os.path.dirname(mo_root))
    return ok


def _compile_catalogues(root, mo_root, langs, traditional=False):
    """Compile the catalogue for each wanted language that has one (own .po,
    alias or base) into mo_root/<lang>/LC_MESSAGES/APP_NAME.mo when stale.
    Never raises; returns the number of catalogues written."""
    written = 0
    failed = set()
    for lang in langs:
        sources = _sources_for(root, lang, traditional)
        if not sources or tuple(sources) in failed:
            continue  # nothing to build, or already failed (warn once)
        mo_dir = os.path.join(mo_root, lang, 'LC_MESSAGES')
        mo = os.path.join(mo_dir, '%s.mo' % APP_NAME)
        if _is_current(mo, sources):
            continue
        if _compile_one(sources, mo_dir, mo, mo_root):
            written += 1
        else:
            failed.add(tuple(sources))
    return written


def _opted_out(environ):
    value = environ.get('TERMINATOR_NO_SOURCE_LOCALE', '')
    return value.strip().lower() in ('1', 'true', 'yes')


def _has_catalogue(localedir, langs):
    return any(os.path.isfile(os.path.join(localedir, lang, 'LC_MESSAGES',
                                           '%s.mo' % APP_NAME))
               for lang in langs)


def source_locale_dir(root=SOURCE_ROOT, environ=None, compile_mo=True):
    """Return <root>/build/locale if running from a source tree and it holds a
    catalogue for one of the user's languages, else None."""
    environ = os.environ if environ is None else environ
    if _opted_out(environ):
        return None
    if not _is_source_tree(root):
        return None
    langs = _wanted_languages(environ)
    if not langs:
        return None
    mo_root = os.path.join(root, 'build', 'locale')
    if compile_mo:
        _compile_catalogues(root, mo_root, langs, _traditional(environ))
    return mo_root if _has_catalogue(mo_root, langs) else None


def _package_prefix(package_dir):
    """Install prefix for a package at <prefix>/lib*/pythonX.Y/
    (site|dist)-packages[/x.egg]/terminatorlib: the parent of the nearest
    lib* ancestor.  None when there is no such ancestor."""
    path = os.path.abspath(package_dir)
    while True:
        parent = os.path.dirname(path)
        if parent == path:
            return None
        if os.path.basename(path).startswith('lib'):
            return parent
        path = parent


def _script_prefix(argv0):
    """<prefix> for a script at <prefix>/bin/terminator, else None"""
    if not argv0 or argv0.startswith('-'):
        return None
    bindir = os.path.dirname(os.path.realpath(argv0))
    if os.path.basename(bindir) == 'bin':
        return os.path.dirname(bindir)
    return None


def installed_locale_dir(environ=None, package_dir=PACKAGE_DIR, argv0=None,
                         prefixes=None):
    """<prefix>/share/locale holding terminator.mo for one of the user's
    languages, searched next to the package, next to the script, then in
    sys.prefix, sys.base_prefix, /usr/local, /usr.  None if not found."""
    environ = os.environ if environ is None else environ
    if _opted_out(environ):
        return None
    langs = _wanted_languages(environ)
    if not langs:
        return None
    if argv0 is None:
        argv0 = sys.argv[0] if sys.argv else ''
    if prefixes is None:
        prefixes = (sys.prefix, getattr(sys, 'base_prefix', sys.prefix),
                    '/usr/local', '/usr')
    candidates = [_package_prefix(package_dir), _script_prefix(argv0)]
    candidates.extend(prefixes)
    seen = set()
    for prefix in candidates:
        if not prefix:
            continue
        localedir = os.path.join(os.path.abspath(prefix), 'share', 'locale')
        if localedir in seen:
            continue
        seen.add(localedir)
        if _has_catalogue(localedir, langs):
            return localedir
    return None


def find_locale_dir(environ=None):
    """build/locale for a source tree, else an installed share/locale"""
    if _is_source_tree(SOURCE_ROOT):
        return source_locale_dir(environ=environ)
    return installed_locale_dir(environ=environ)


def _bind(localedir):
    """Bind APP_NAME to localedir for Python gettext and for libintl (the
    C-level binding GtkBuilder's set_translation_domain() goes through)."""
    import gettext
    gettext.bindtextdomain(APP_NAME, localedir)
    try:
        import locale
        locale.bindtextdomain(APP_NAME, localedir)
    except Exception as ex:  # no libintl binding on this platform
        dbg('locale: locale.bindtextdomain failed: %s' % ex)


# pylint: disable-msg=W0702
try:
    import gettext
    try:
        LOCALE_DIR = find_locale_dir()
        if LOCALE_DIR:
            _bind(LOCALE_DIR)
            dbg('locale: using %s' % LOCALE_DIR)
    except Exception as ex:
        LOCALE_DIR = None
        dbg('locale: lookup disabled: %s' % ex)
    gettext.textdomain(APP_NAME)
    _ = gettext.gettext
except:
    dbg("Using fallback _()")

    def dummytrans (text):
        """A _ function for systems without gettext. Effectively a NOOP"""
        return(text)

    _ = dummytrans
