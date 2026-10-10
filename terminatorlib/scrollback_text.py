# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""scrollback_text.py - gi-free helpers for scrollback cache.

Kept free of gi/Gtk/Vte/util so pytest --doctest-modules and unit tests
can import this module without PyGObject.
"""

from __future__ import print_function

import os
import re
import tempfile
from datetime import datetime

UUID_FILE_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
)

# C0 controls except TAB/LF/CR; also DEL; C1 0x80-0x9f
_C0_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
# ESC sequences: OSC (] ... BEL or ST), CSI ([ ...), other ESC + intermediate/final
_ESC_RE = re.compile(
    r'\x1b'
    r'(?:'
    r'\][^\x07\x1b]*(?:\x07|\x1b\\)?'  # OSC
    r'|'
    r'\[[0-?]*[ -/]*[@-~]'              # CSI
    r'|'
    r'[P^_][^\x1b]*(?:\x1b\\)?'         # DCS/PM/APC rough
    r'|'
    r'.'                                 # other single-byte ESC seq
    r')'
)
_C1_RE = re.compile(r'[\x80-\x9f]')

SEPARATOR_TEMPLATE = (
    '──── 以上为上次会话的输出（仅文字快照，进程未恢复）· {time} ────'
)


def is_valid_uuid_filename(name):
    """Return True if name is a canonical UUID string (no path separators)."""
    if not name or not isinstance(name, str):
        return False
    if '/' in name or '\\' in name or name in ('.', '..'):
        return False
    return bool(UUID_FILE_RE.match(name))


def truncate_utf8_bytes(data, max_bytes):
    """Keep a trailing slice of data of at most max_bytes without splitting UTF-8.

    >>> truncate_utf8_bytes(b'abc', 2)
    b'bc'
    >>> truncate_utf8_bytes('你好世界'.encode('utf-8'), 6) == '世界'.encode('utf-8')
    True
    >>> truncate_utf8_bytes('€'.encode('utf-8'), 2)  # euro is 3 bytes
    b''
    """
    if max_bytes <= 0:
        return b''
    if not isinstance(data, (bytes, bytearray)):
        data = bytes(data)
    if len(data) <= max_bytes:
        return bytes(data)
    chunk = data[-max_bytes:]
    # Skip leading continuation bytes (10xxxxxx) so we start on a codepoint
    i = 0
    while i < len(chunk) and (chunk[i] & 0xc0) == 0x80:
        i += 1
    return bytes(chunk[i:])


def truncate_lines_and_bytes(text, max_lines, max_kb):
    """Take the last max_lines, then trim to max_kb UTF-8 bytes on a line boundary.

    >>> truncate_lines_and_bytes('a\\nb\\nc\\nd', 2, 512)
    'c\\nd'
    >>> out = truncate_lines_and_bytes('x' * 100 + '\\n' + 'y' * 100, 10, 1)
    >>> len(out.encode('utf-8')) <= 1024
    True
    """
    if text is None:
        return ''
    if not isinstance(text, str):
        text = text.decode('utf-8', 'replace')
    max_lines = max(0, int(max_lines))
    max_bytes = max(0, int(max_kb) * 1024)
    if max_lines == 0 or max_bytes == 0:
        return ''
    lines = text.split('\n')
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    text = '\n'.join(lines)
    encoded = text.encode('utf-8')
    if len(encoded) <= max_bytes:
        return text
    truncated = truncate_utf8_bytes(encoded, max_bytes)
    # Prefer starting at a newline so we keep whole lines when possible
    nl = truncated.find(b'\n')
    if nl != -1 and nl + 1 < len(truncated):
        truncated = truncated[nl + 1:]
    return truncated.decode('utf-8', 'replace')


def sanitize_for_feed(text):
    """Strip C0/C1/ESC sequences; keep tab/newline/carriage-return.

    >>> sanitize_for_feed('hello\\x1b]0;title\\x07world')
    'helloworld'
    >>> sanitize_for_feed('a\\x1b[31mb\\x1b[0mc')
    'abc'
    >>> sanitize_for_feed('keep\\t\\n\\r')
    'keep\\t\\n\\r'
    >>> '中文' in sanitize_for_feed('中文emoji😀')
    True
    """
    if not text:
        return ''
    if not isinstance(text, str):
        text = text.decode('utf-8', 'replace')
    text = _ESC_RE.sub('', text)
    text = _C0_RE.sub('', text)
    text = _C1_RE.sub('', text)
    return text


def normalize_newlines_for_feed(text):
    """Normalize all newline styles to CRLF for VTE display feed.

    >>> normalize_newlines_for_feed('a\\nb\\r\\nc\\rd')
    'a\\r\\nb\\r\\nc\\r\\nd'
    """
    if not text:
        return ''
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return text.replace('\n', '\r\n')


def format_separator(mtime, translate=None):
    """Build the grey separator line label (caller wraps SGR).

    mtime is a unix timestamp or None. translate is gettext ``_`` or None.
    """
    _ = translate if translate is not None else (lambda s: s)
    if mtime:
        try:
            ts = datetime.fromtimestamp(float(mtime)).strftime('%m-%d %H:%M')
        except (ValueError, OSError, OverflowError, TypeError):
            ts = ''
    else:
        ts = ''
    return _(SEPARATOR_TEMPLATE).format(time=ts)


def format_separator_feed(mtime, translate=None):
    """Separator ready for vte.feed: CRLF + SGR 90 + label + reset + CRLF."""
    label = format_separator(mtime, translate=translate)
    return '\r\n\x1b[90m' + label + '\x1b[0m\r\n'


def atomic_write_txt(path, data, mode=0o600):
    """Write data via mkstemp + replace. No fsync (session module owns fsync).

    data may be str (encoded UTF-8) or bytes.
    """
    if isinstance(data, str):
        data = data.encode('utf-8')
    dirpath = os.path.dirname(path) or '.'
    fd = None
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=dirpath, prefix='.', suffix='.tmp')
        try:
            os.fchmod(fd, mode)
        except OSError:
            pass
        os.write(fd, data)
        # intentionally no fsync — B cache is best-effort
    except Exception:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
            fd = None
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
        raise
    else:
        os.close(fd)
        fd = None
        os.replace(tmp, path)
        tmp = None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
