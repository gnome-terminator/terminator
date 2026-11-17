# Terminator - multiple gnome terminals in one window
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 2 only.
"""Pure-Python .po -> .mo compiler (fallback for GNU msgfmt).

Standard library only, so setup.py can load it without GTK."""


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


def compile_po_python(po, out, base=None):
    """Pure-Python fallback for `msgfmt -o out po`.  With base, entries of
    that .po are used for anything po does not translate (e.g. zh_TW under
    a sparse zh_HK); po's header wins."""
    messages = {}
    for path in ([base] if base else []) + [po]:
        with open(path, 'rb') as handle:
            messages.update(_parse_po(handle.read()))
    with open(out, 'wb') as handle:
        handle.write(_mo_bytes(messages))
    return True
