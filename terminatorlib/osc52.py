# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""osc52.py - bounded, copy-only OSC 52 clipboard support.

VTE has no handler for OSC 52 (xterm's "set selection" escape sequence) and
upstream has decided not to add one, on the grounds that it lets a remote
host overwrite the local clipboard (GNOME/vte#2495).  Terminator still has
users who want to interoperate with remote tools that speak OSC 52: vim and
tmux with ``set-clipboard on``, ssh sessions, soft-serve, and so on.

This module implements the *parsing* half of opt-in OSC 52 support: an
incremental filter that removes copy sequences from the byte stream flowing
from the child into VTE and decodes them.  The GTK half -- where those bytes
come from and where the clipboard gets written -- lives in
:mod:`terminatorlib.osc52relay`, so that this module stays GTK-free and unit
testable.

Grammar handled (xterm ctlseqs, "OSC 52 ; Pc ; Pd")::

    OSC 52 ; Pc ; Pd ST
    OSC 52 ; Pc ; Pd BEL

* ``Pc`` is a string of selection names; we act on ``c`` (clipboard), ``p``
  and ``s`` (primary selection) and ignore the rest.
* ``Pd`` is base64 text, or ``!`` meaning "query", which we never answer --
  answering would leak the local clipboard to the remote side.

Safety properties, which are the reason this is a separate module:

* copy only, never paste or query;
* payloads are bounded by ``OSC52_MAX_ENCODED_BYTES``/``OSC52_MAX_DECODED_BYTES``
  so a hostile remote cannot make us buffer without limit;
* the filter never reorders, duplicates or drops bytes other than the
  sequences it consumes, so terminal output is unchanged when the feature is
  disabled or a sequence is refused.
"""

import base64
import binascii
import re

__all__ = [
    'OSC52_MAX_ENCODED_BYTES',
    'OSC52_MAX_DECODED_BYTES',
    'Osc52Filter',
    'clipboards_for_selection',
    'decode_payload',
]

#: Largest base64 payload we are willing to buffer while waiting for a
#: terminator.  xterm applies a comparable cap for the same reason.
OSC52_MAX_ENCODED_BYTES = 100 * 1024
#: Largest decoded text we will place on a clipboard.
OSC52_MAX_DECODED_BYTES = 100 * 1024

#: Selection parameter letters understood by the filter.
_SELECTIONS = b'cps01234567'
#: Selection parameter letters we act on, mapped to GDK selection names.
_SELECTION_MAP = {
    'c': 'CLIPBOARD',
    'p': 'PRIMARY',
    's': 'PRIMARY',
}
#: ``\\x1b]52;`` -- the fixed part of a sequence head.
_HEAD_PREFIX = b'\x1b]52;'
#: A complete sequence, terminated by BEL or ST.
_COMPLETE = re.compile(
    rb'\x1b\]52;([cps01234567]{0,4});([!A-Za-z0-9+/=]*)'
    rb'(?:\x07|\x1b\\)')
#: Payload characters: base64, plus the query marker ``!``.
_PAYLOAD_RE = re.compile(rb'[!A-Za-z0-9+/=]*\Z')
#: Longest possible head: prefix, at most four selection letters, semicolon.
_MAX_HEAD = len(_HEAD_PREFIX) + 4 + 1


def clipboards_for_selection(param):
    """Map an OSC 52 selection parameter to GDK selection names.

    An empty parameter selects the clipboard, as in xterm.

    >>> clipboards_for_selection('c')
    ['CLIPBOARD']
    >>> clipboards_for_selection('s')
    ['PRIMARY']
    >>> clipboards_for_selection('cp')
    ['CLIPBOARD', 'PRIMARY']
    >>> clipboards_for_selection('')
    ['CLIPBOARD']
    >>> clipboards_for_selection(b'cp')
    ['CLIPBOARD', 'PRIMARY']
    """
    if isinstance(param, bytes):
        param = param.decode('ascii', 'replace')
    atoms = []
    for char in param or 'c':
        atom = _SELECTION_MAP.get(char)
        if atom is not None and atom not in atoms:
            atoms.append(atom)
    return atoms or ['CLIPBOARD']


def decode_payload(payload):
    """Decode a base64 OSC 52 payload.

    Returns ``None`` for anything we refuse to put on a clipboard: the
    query marker ``!``, malformed base64, or text larger than
    ``OSC52_MAX_DECODED_BYTES``.

    >>> decode_payload(b'aGVsbG8=')
    b'hello'
    >>> decode_payload(b'!') is None
    True
    >>> decode_payload(b'') is None
    True
    """
    if not payload or payload == b'!':
        return None
    try:
        text = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(text) > OSC52_MAX_DECODED_BYTES:
        return None
    return text


def _is_head_prefix(candidate):
    """Could *candidate* still grow into a complete head?"""
    if not candidate.startswith(b'\x1b'):
        return False
    if len(candidate) > _MAX_HEAD:
        return False
    if len(candidate) <= len(_HEAD_PREFIX):
        # Still inside the fixed ``\\x1b]52;`` part.
        return _HEAD_PREFIX.startswith(candidate)
    params = candidate[len(_HEAD_PREFIX):]
    seen = 0
    for char in params:
        if char in _SELECTIONS:
            seen += 1
        elif char == 0x3b:  # ';'
            return True
        else:
            return False
    # Selection letters with no semicolon yet.
    return seen <= 4


def _plausible_prefix(data):
    """Is *data* a strict prefix of some well-formed OSC 52 copy sequence?

    True for a partial head (``\\x1b]``, ``\\x1b]52``, ...) or for a complete
    head followed by zero or more payload characters with no terminator yet.
    """
    if not data.startswith(b'\x1b'):
        return False
    if len(data) <= len(_HEAD_PREFIX):
        return _HEAD_PREFIX.startswith(data)
    if not data.startswith(_HEAD_PREFIX):
        return False
    params, sep, payload = data[len(_HEAD_PREFIX):].partition(b';')
    if not all(c in _SELECTIONS for c in params) or len(params) > 4:
        return False
    if not sep:
        return True
    if payload.endswith(b'\x1b'):
        # Could be the first half of an ST (``\\x1b\\\\``) terminator.
        payload = payload[:-1]
    return _PAYLOAD_RE.match(payload) is not None


def _split_holdback(rest):
    """Split *rest* into ``(emit, hold)``.

    *hold* is the longest suffix that could still grow into a sequence
    completed by a later :meth:`Osc52Filter.feed` call; *emit* is everything
    before it and is safe to hand to VTE now.

    A candidate stops being plausible the moment a byte appears that cannot
    belong to it -- at which point the bytes so far are emitted and scanning
    restarts at the next ESC, so ordinary terminal output is never swallowed
    and no candidate can outlive the escape sequence that follows it.
    """
    pos = rest.find(b'\x1b')
    while pos != -1:
        if _plausible_prefix(rest[pos:]):
            return rest[:pos], rest[pos:]
        pos = rest.find(b'\x1b', pos + 1)
    return rest, b''


class Osc52Filter:
    """Incremental filter removing OSC 52 copy sequences from a byte stream.

    ``callback`` is called as ``callback(selections, text)`` for every
    accepted sequence, where *selections* is a list of GDK selection names
    and *text* is decoded bytes.  The filter holds no GTK objects, so it can
    be unit tested without a display.
    """

    def __init__(self, callback):
        self.buffer = b''
        self.callback = callback

    def feed(self, data):
        """Strip OSC 52 sequences from *data* and return the remaining bytes.

        Sequences split across calls are buffered until they complete; a
        candidate that outgrows ``OSC52_MAX_ENCODED_BYTES`` is flushed
        verbatim so the terminal sees exactly what it would have seen with
        this feature turned off.

        >>> captured = []
        >>> filt = Osc52Filter(lambda sel, txt: captured.append((sel, txt)))
        >>> filt.feed(b'before\\x1b]52;c;aGVsbG8=\\x07after')
        b'beforeafter'
        >>> captured
        [(['CLIPBOARD'], b'hello')]
        """
        pending = self.buffer + data
        self.buffer = b''

        out = bytearray()
        pos = 0
        for match in _COMPLETE.finditer(pending):
            if match.start() > pos:
                out += pending[pos:match.start()]
            pos = match.end()
            text = decode_payload(match.group(2))
            if text is not None:
                self.callback(clipboards_for_selection(match.group(1)), text)

        rest = pending[pos:]
        if not rest:
            return bytes(out)

        # An ESC sitting in the middle of *rest* may be the ST of a sequence
        # completed by a later call (``...payload\\x1b`` + ``\\\\``), so the
        # regex scan above has to run again on data that includes it.  Loop
        # until no new complete sequence appears.
        while rest:
            emit, hold = _split_holdback(rest)
            if not hold:
                out += emit
                break
            if len(hold) > OSC52_MAX_ENCODED_BYTES:
                # Too big to ever be accepted: give up on this candidate and
                # rescan from the next ESC in case a bounded one follows it.
                out += emit + hold[:1]
                rest = hold[1:]
                continue
            out += emit
            self.buffer = hold
            break
        return bytes(out)
