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


# Locales with no po/<lang>.po of their own that should use another catalogue.
# The .mo is still written under the requested name (e.g. build/locale/
# zh_Hans/...) because that is the directory gettext/libintl will look in.
LANG_ALIASES = {
    'zh': 'zh_CN', 'zh_Hans': 'zh_CN', 'zh_SG': 'zh_CN',
    'zh_Hant': 'zh_TW', 'zh_MO': 'zh_TW',
}

_TMP_MAX_AGE = 60  # seconds; older terminator.mo.tmp.* files are litter


def _po_for(root, lang):
    """po/<lang>.po, or the aliased catalogue, or None"""
    for name in (lang, LANG_ALIASES.get(lang)):
        if name:
            po = os.path.join(root, 'po', '%s.po' % name)
            if os.path.isfile(po):
                return po
    return None


def _parse_po(data):
    """Parse .po bytes into {msgid_bytes: msgstr_bytes} like GNU msgfmt:
    fuzzy entries (except the header) and untranslated entries are dropped,
    msgctxt is joined with EOT, plural ids/strings with NUL."""
    import ast
    import re
    m = re.search(rb'charset=([A-Za-z0-9_.:-]+)', data)
    encoding = m.group(1).decode('ascii') if m else 'utf-8'
    try:
        text = data.decode(encoding)
    except (LookupError, UnicodeDecodeError):
        encoding = 'utf-8'
        text = data.decode('utf-8')

    messages = {}
    entry = {}
    state = {'fuzzy': False, 'section': None, 'idx': None}

    def flush():
        if 'msgid' in entry:
            msgid = entry['msgid']
            fuzzy = state['fuzzy'] and msgid != ''
            if 'msgid_plural' in entry:
                strs = [entry.get('msgstr', {}).get(i, '')
                        for i in sorted(entry.get('msgstr', {}))]
                key = msgid + '\0' + entry['msgid_plural']
                val = '\0'.join(strs)
                translated = any(strs)
            else:
                key = msgid
                val = entry.get('msgstr', {}).get(None, '')
                translated = bool(val) or msgid == ''
            if 'msgctxt' in entry:
                key = entry['msgctxt'] + '\x04' + key
            if translated and not fuzzy:
                messages[key.encode(encoding)] = val.encode(encoding)
        entry.clear()
        state.update(fuzzy=False, section=None, idx=None)

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith('#'):
            if line.startswith('#~'):
                continue  # obsolete
            if state['section'] == 'msgstr':
                flush()
            if line.startswith('#,') and 'fuzzy' in line:
                state['fuzzy'] = True
            continue
        if not line:
            continue
        keyword = None
        for kw in ('msgctxt', 'msgid_plural', 'msgid', 'msgstr'):
            if line.startswith(kw) and line[len(kw):len(kw) + 1] in ' [':
                keyword = kw
                break
        if keyword:
            rest = line[len(keyword):].strip()
            idx = None
            if keyword == 'msgstr' and rest.startswith('['):
                idx = int(rest[1:rest.index(']')])
                rest = rest[rest.index(']') + 1:].strip()
            if keyword in ('msgctxt', 'msgid') and \
                    state['section'] == 'msgstr':
                flush()  # new entry with no comment lines in between
            state['section'], state['idx'] = keyword, idx
            value = ast.literal_eval(rest)
            if keyword == 'msgstr':
                entry.setdefault('msgstr', {})[idx] = value
            else:
                entry[keyword] = value
        elif line.startswith('"') and state['section']:
            value = ast.literal_eval(line)
            if state['section'] == 'msgstr':
                entry['msgstr'][state['idx']] += value
            else:
                entry[state['section']] += value
        else:
            raise ValueError('unparsable .po line: %r' % raw)
    if state['section'] == 'msgstr':
        flush()
    return messages


def _mo_bytes(messages):
    """GNU .mo (little endian, no hash table) for {id_bytes: str_bytes}"""
    import struct
    keys = sorted(messages)
    ids = strs = b''
    offsets = []
    for k in keys:
        offsets.append((len(ids), len(k), len(strs), len(messages[k])))
        ids += k + b'\0'
        strs += messages[k] + b'\0'
    n = len(keys)
    keystart = 7 * 4 + 16 * n
    valuestart = keystart + len(ids)
    koffsets, voffsets = [], []
    for o1, l1, o2, l2 in offsets:
        koffsets += [l1, o1 + keystart]
        voffsets += [l2, o2 + valuestart]
    out = struct.pack('<Iiiiiii', 0x950412de, 0, n, 7 * 4, 7 * 4 + n * 8,
                      0, 0)
    out += struct.pack('<%di' % len(koffsets), *koffsets)
    out += struct.pack('<%di' % len(voffsets), *voffsets)
    return out + ids + strs


def compile_po_python(po, out):
    """Pure-Python fallback for `msgfmt -o out po`"""
    with open(po, 'rb') as handle:
        data = handle.read()
    with open(out, 'wb') as handle:
        handle.write(_mo_bytes(_parse_po(data)))
    return True


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


def _compile_one(po, mo_dir, mo, mo_root):
    """Compile po into mo via msgfmt, else the Python fallback.  Never
    raises; returns True when mo was (re)written."""
    tmp = '%s.tmp.%d' % (mo, os.getpid())
    try:
        os.makedirs(mo_dir, exist_ok=True)
    except OSError as ex:  # read-only tree
        dbg('source locale: cannot create %s: %s' % (mo_dir, ex))
        return False
    _clean_stale_tmp(mo_dir)
    ok = False
    for compiler in (_msgfmt, compile_po_python):
        try:
            if compiler(po, tmp) and os.path.isfile(tmp) and \
                    os.path.getsize(tmp) > 0:
                os.replace(tmp, mo)
                ok = True
                break
        except Exception as ex:  # msgfmt missing/failed, parse error...
            dbg('source locale: %s failed for %s: %s' %
                (getattr(compiler, '__name__', compiler), po, ex))
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass
    if not ok:
        import sys
        sys.stderr.write('terminator: could not compile %s for the source '
                         'checkout; using system translations\n' % po)
        _remove_empty_dirs(mo_dir, os.path.dirname(mo_root))
    return ok


def _compile_catalogues(root, mo_root, langs):
    """Compile po/<lang>.po (or its alias) ->
    mo_root/<lang>/LC_MESSAGES/APP_NAME.mo when the .po is newer.  Never
    raises; returns the number of catalogues written."""
    written = 0
    seen = set()
    for lang in langs:
        po = _po_for(root, lang)
        if po is None or po in seen:
            continue  # e.g. zh after zh_CN: gettext never gets that far
        seen.add(po)
        mo_dir = os.path.join(mo_root, lang, 'LC_MESSAGES')
        mo = os.path.join(mo_dir, '%s.mo' % APP_NAME)
        try:
            if os.path.isfile(mo) and \
                    os.path.getmtime(mo) >= os.path.getmtime(po):
                continue
        except OSError:
            continue
        if _compile_one(po, mo_dir, mo, mo_root):
            written += 1
    return written


def _opted_out(environ):
    value = environ.get('TERMINATOR_NO_SOURCE_LOCALE', '')
    return value.strip().lower() in ('1', 'true', 'yes')


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
