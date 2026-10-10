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

from .version import APP_NAME
from .util import dbg

_ = None

# Source-tree locale support (m35).
#
# When terminator runs straight from a git checkout (``python3 ./terminator``)
# the system catalogue in /usr/share/locale is either missing or comes from an
# older distro package that lacks this fork's strings.  In that case we bind
# the text domain to <repo>/build/locale (build/locale/<lang>/LC_MESSAGES/
# terminator.mo, the layout gettext/libintl look up; setup.py's build/mo is
# flat and therefore not usable as a localedir).  Catalogues for the
# user's languages are (re)compiled there with msgfmt when the .po is newer;
# any failure is silent and we fall back to the system catalogue.
#
# Set TERMINATOR_NO_SOURCE_LOCALE=1 to disable all of this.

SOURCE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALE_DIR = None  # directory bound for APP_NAME, None = system default


def _is_source_tree(root):
    """True for a git/source checkout, False for an installed package"""
    return (os.path.isfile(os.path.join(root, 'setup.py')) and
            os.path.isfile(os.path.join(root, 'po', 'POTFILES.in')) and
            os.path.isdir(os.path.join(root, 'terminatorlib')))


def _wanted_languages(environ=None):
    """Language codes gettext would try, from LANGUAGE/LC_ALL/LC_MESSAGES/LANG.

    'zh_CN.UTF-8' yields ['zh_CN', 'zh'].  'C'/'POSIX' are dropped."""
    environ = os.environ if environ is None else environ
    raw = []
    for var in ('LANGUAGE', 'LC_ALL', 'LC_MESSAGES', 'LANG'):
        val = environ.get(var)
        if val:
            raw = val.split(':')
            break
    langs = []
    for item in raw:
        code = item.split('@')[0].split('.')[0].strip()
        if not code or code in ('C', 'POSIX'):
            continue
        for cand in (code, code.split('_')[0]):
            if cand and cand not in langs:
                langs.append(cand)
    return langs


def _compile_catalogues(root, mo_root, langs):
    """Compile po/<lang>.po -> mo_root/<lang>/LC_MESSAGES/APP_NAME.mo when the
    .po is newer.  Never raises; returns the number of catalogues written."""
    import subprocess
    written = 0
    for lang in langs:
        po = os.path.join(root, 'po', '%s.po' % lang)
        if not os.path.isfile(po):
            continue
        mo_dir = os.path.join(mo_root, lang, 'LC_MESSAGES')
        mo = os.path.join(mo_dir, '%s.mo' % APP_NAME)
        tmp = None
        try:
            if os.path.isfile(mo) and \
                    os.path.getmtime(mo) >= os.path.getmtime(po):
                continue
            os.makedirs(mo_dir, exist_ok=True)
            tmp = '%s.tmp.%d' % (mo, os.getpid())
            rc = subprocess.call(['msgfmt', '-o', tmp, po],
                                 stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,
                                 timeout=30)
            if rc == 0 and os.path.isfile(tmp):
                os.replace(tmp, mo)
                written += 1
            elif os.path.exists(tmp):
                os.unlink(tmp)
        except Exception as ex:  # msgfmt missing, read-only tree, timeout...
            dbg('source locale: could not compile %s: %s' % (po, ex))
            try:
                if tmp and os.path.exists(tmp):
                    os.unlink(tmp)
            except Exception:
                pass
    return written


def source_locale_dir(root=SOURCE_ROOT, environ=None, compile_mo=True):
    """Return <root>/build/locale if running from a source tree and it holds a
    catalogue for one of the user's languages, else None."""
    environ = os.environ if environ is None else environ
    if environ.get('TERMINATOR_NO_SOURCE_LOCALE'):
        return None
    if not _is_source_tree(root):
        return None
    langs = _wanted_languages(environ)
    if not langs:
        return None
    mo_root = os.path.join(root, 'build', 'locale')
    if compile_mo:
        _compile_catalogues(root, mo_root, langs)
    for lang in langs:
        if os.path.isfile(os.path.join(mo_root, lang, 'LC_MESSAGES',
                                       '%s.mo' % APP_NAME)):
            return mo_root
    return None


def _bind(localedir):
    """Bind APP_NAME to localedir for Python gettext and for libintl (the
    C-level binding GtkBuilder's set_translation_domain() goes through)."""
    import gettext
    gettext.bindtextdomain(APP_NAME, localedir)
    try:
        import locale
        locale.bindtextdomain(APP_NAME, localedir)
    except Exception as ex:  # no libintl binding on this platform
        dbg('source locale: locale.bindtextdomain failed: %s' % ex)


# pylint: disable-msg=W0702
try:
    import gettext
    try:
        LOCALE_DIR = source_locale_dir()
        if LOCALE_DIR:
            _bind(LOCALE_DIR)
            dbg('source locale: using %s' % LOCALE_DIR)
    except Exception as ex:
        LOCALE_DIR = None
        dbg('source locale: disabled: %s' % ex)
    gettext.textdomain(APP_NAME)
    _ = gettext.gettext
except:
    dbg("Using fallback _()")

    def dummytrans (text):
        """A _ function for systems without gettext. Effectively a NOOP"""
        return(text)

    _ = dummytrans
