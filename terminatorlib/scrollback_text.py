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
from html.parser import HTMLParser
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

def N_(message):
    """Mark a string for translation without translating it here."""
    return message


# English msgid (translated at use via format_separator(translate=_)).
# The cache may keep colours (scrollback_cache_color), so it is not a
# "text only" snapshot; running programs are never restored.
SEPARATOR_TEMPLATE = N_(
    '──── Output above is from the previous session '
    '(saved snapshot; programs were not restored) · {time} ────'
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


_SGR_RE = re.compile(r'\x1b\[[0-9;]*m\Z')
_SGR_ANY_RE = re.compile(r'\x1b\[[0-9;]*m')


def truncate_sgr_lines(text, max_lines, max_kb):
    r"""Truncate coloured cache text (output of html_to_sgr) safely.

    SGR bytes count against max_kb (it is a disk budget), so colour costs
    some history; we keep the newest *whole* lines that fit. Lines from
    html_to_sgr are self-contained, so dropping whole lines never splits an
    escape or leaks a style. A single newest line larger than the budget is
    stripped of SGR and byte-truncated as plain text.

    >>> truncate_sgr_lines('\x1b[31ma\x1b[0m\n\x1b[32mb\x1b[0m', 1, 1)
    '\x1b[32mb\x1b[0m'
    >>> out = truncate_sgr_lines('\x1b[31m' + 'x' * 3000 + '\x1b[0m', 5, 1)
    >>> '\x1b' in out, len(out) <= 1024
    (False, True)
    """
    if not text:
        return ''
    max_lines = max(0, int(max_lines))
    max_bytes = max(0, int(max_kb) * 1024)
    if max_lines == 0 or max_bytes == 0:
        return ''
    lines = text.split('\n')[-max_lines:]
    kept = []
    used = 0
    for line in reversed(lines):
        size = len(line.encode('utf-8')) + (1 if kept else 0)
        if used + size > max_bytes:
            break
        kept.append(line)
        used += size
    if not kept:
        plain = _SGR_ANY_RE.sub('', lines[-1]).encode('utf-8')
        return truncate_utf8_bytes(plain, max_bytes).decode('utf-8', 'replace')
    kept.reverse()
    return '\n'.join(kept)


def sanitize_for_feed(text, keep_sgr=False):
    """Strip C0/C1/ESC sequences; keep tab/newline/carriage-return.

    keep_sgr=True keeps plain SGR colour/attribute sequences (ESC [ digits ; m)
    and still strips everything else (OSC, cursor moves, DCS...).

    >>> sanitize_for_feed('a\\x1b[1;31mb\\x1b[0m\\x1b[2Jc', keep_sgr=True)
    'a\\x1b[1;31mb\\x1b[0mc'

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
    if keep_sgr:
        parts = []
        for chunk in re.split(r'(\x1b\[[0-9;]*m)', text):
            if _SGR_RE.match(chunk):
                parts.append('\x00SGR' + chunk[2:-1] + '\x00')
            else:
                parts.append(_ESC_RE.sub('', chunk))
        text = ''.join(parts)
        text = _C0_RE.sub(lambda m: m.group(0) if m.group(0) == '\x00' else '',
                          text)
        text = _C1_RE.sub('', text)
        return re.sub(r'\x00SGR([0-9;]*)\x00', '\x1b[\\1m',
                      text).replace('\x00', '')
    text = _ESC_RE.sub('', text)
    text = _C0_RE.sub('', text)
    text = _C1_RE.sub('', text)
    return text


def _hex_rgb(value):
    v = (value or '').strip().lstrip('#')
    if len(v) == 3:
        v = ''.join(c * 2 for c in v)
    if len(v) != 6:
        return None
    try:
        return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


class _VteHtmlToSgr(HTMLParser):
    """Convert VTE's Format.HTML export into text with SGR sequences."""

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.stack = []      # list of (tag, {attr: value})
        self.lines = [[]]

    def _state(self):
        st = {}
        for _tag, attrs in self.stack:
            st.update(attrs)
        return st

    def _sgr(self):
        st = self._state()
        codes = []
        if st.get('bold'):
            codes.append('1')
        if st.get('italic'):
            codes.append('3')
        if st.get('underline'):
            codes.append('4')
        if st.get('strike'):
            codes.append('9')
        if st.get('fg'):
            codes.append('38;2;%d;%d;%d' % st['fg'])
        if st.get('bg'):
            codes.append('48;2;%d;%d;%d' % st['bg'])
        return ('\x1b[' + ';'.join(codes) + 'm') if codes else ''

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        st = {}
        if tag == 'b':
            st['bold'] = True
        elif tag == 'i':
            st['italic'] = True
        elif tag == 'u':
            st['underline'] = True
        elif tag in ('s', 'strike', 'del'):
            st['strike'] = True
        elif tag == 'font':
            rgb = _hex_rgb(a.get('color'))
            if rgb:
                st['fg'] = rgb
        elif tag == 'br':
            self.lines.append([])
            return
        style = a.get('style') or ''
        for decl in style.split(';'):
            if ':' not in decl:
                continue
            k, v = [x.strip().lower() for x in decl.split(':', 1)]
            if k == 'background-color':
                rgb = _hex_rgb(v)
                if rgb:
                    st['bg'] = rgb
            elif k == 'color':
                rgb = _hex_rgb(v)
                if rgb:
                    st['fg'] = rgb
            elif k == 'font-weight' and v == 'bold':
                st['bold'] = True
            elif k == 'font-style' and v == 'italic':
                st['italic'] = True
        self.stack.append((tag, st))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        pieces = data.split('\n')
        for i, piece in enumerate(pieces):
            if i:
                self.lines.append([])
            if piece:
                self.lines[-1].append((self._sgr(), piece))

    def result(self):
        out = []
        for segs in self.lines:
            buf = []
            cur = ''
            for sgr, txt in segs:
                if sgr != cur:
                    if cur:
                        buf.append('\x1b[0m')
                    buf.append(sgr)
                    cur = sgr
                buf.append(txt)
            if cur:
                buf.append('\x1b[0m')
            out.append(''.join(buf))
        return '\n'.join(out)


def html_to_sgr(html):
    r"""Convert VTE Format.HTML export to text + truecolor SGR.

    Every styled line is self-contained (style reopened at line start and
    reset at line end) so line-based truncation never leaks colour.

    >>> html_to_sgr('<pre>a <font color="#C00000"><b>r</b></font> &lt;\n'
    ...             'x</pre>')
    'a \x1b[1;38;2;192;0;0mr\x1b[0m <\nx'
    >>> html_to_sgr('<pre><span style="background-color:#0000C0">'
    ...             'b\nc</span></pre>')
    '\x1b[48;2;0;0;192mb\x1b[0m\n\x1b[48;2;0;0;192mc\x1b[0m'
    >>> html_to_sgr('<pre>plain</pre>')
    'plain'
    """
    if not html:
        return ''
    p = _VteHtmlToSgr()
    p.feed(html)
    p.close()
    return p.result()


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


# A previous restore's separator, once it has been snapshotted back into
# the cache.  Matched in both the English msgid and the zh_CN translation.
_SEPARATOR_LINE_RE = re.compile(
    r'─{2,}.*(?:Output above is from the previous session|以上为上次会话的输出)'
)
# A shell prompt with nothing typed after it.  A command on the same line
# (user@host:~$ ls) does not match.
_PROMPT_ONLY_RE = re.compile(
    r'^(?:\([^)]*\)\s*)*'
    r'(?:'
    r'[^@\s]+@[^:\s]+:.*[$#]\s*'
    r'|'
    r'[^@\s]+@[^:\s]+\s+\S*[$#%>]\s*'
    r'|'
    r'[$#%>]\s*'
    r')$'
)


def _plain_line(line):
    """Drop SGR colour sequences and surrounding space for classification."""
    return _SGR_ANY_RE.sub('', line).strip()


def _line_is_prompt_or_separator(line):
    plain = _plain_line(line)
    if not plain:
        return True
    if _SEPARATOR_LINE_RE.search(plain):
        return True
    return bool(_PROMPT_ONLY_RE.match(plain))


def scrollback_worth_replaying(text):
    """False when the cache is blank, bare prompts, or only old separators.

    A prompt with a command, or any other line, is worth replaying.
    >>> scrollback_worth_replaying('clarence@AILinux:~$ ')
    False
    >>> scrollback_worth_replaying('clarence@AILinux:~$ \\n──── 以上为上次会话的输出（已保存的快照，程序未恢复）· 10-10 20:55 ────')
    False
    >>> scrollback_worth_replaying('clarence@AILinux:~$ ls\\nfile\\n')
    True
    """
    if not text:
        return False
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return any(not _line_is_prompt_or_separator(line) for line in text.split('\n'))


def strip_replay_separators(text):
    """Drop previously fed separator lines so they are not replayed again."""
    if not text:
        return ''
    newline = '\r\n' if '\r\n' in text and '\n' not in text.replace('\r\n', '') else '\n'
    # Classify on logical lines; keep the caller's newline style.
    logical = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    kept = [line for line in logical
            if not _SEPARATOR_LINE_RE.search(_plain_line(line))]
    return newline.join(kept)


def atomic_write_txt(path, data, mode=0o600):
    """Write data via mkstemp + full write + fsync + replace.

    Short writes (ENOSPC, EINTR) are looped/raised so a truncated temp file
    can never replace a good cache.  data may be str (UTF-8) or bytes.
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
        view = memoryview(data)
        written = 0
        while written < len(view):
            n = os.write(fd, view[written:])
            if n <= 0:
                raise OSError('short write to %s' % tmp)
            written += n
        os.fsync(fd)
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
