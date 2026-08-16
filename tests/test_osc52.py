"""Tests for OSC 52 clipboard support (parsing layer)."""

import base64
import os
import sys

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

from terminatorlib.osc52 import (  # noqa: E402
    OSC52_MAX_DECODED_BYTES,
    OSC52_MAX_ENCODED_BYTES,
    Osc52Filter,
    clipboards_for_selection,
    decode_payload,
)


def sequence(text, selection=b"c", terminator=b"\x07"):
    """Build an OSC 52 copy sequence for *text*."""
    payload = base64.b64encode(text.encode("utf-8"))
    return b"\x1b]52;" + selection + b";" + payload + terminator


class Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, selections, text):
        self.calls.append((list(selections), text))


def test_bel_terminator_is_stripped():
    rec = Recorder()
    filt = Osc52Filter(rec)
    assert filt.feed(b"before" + sequence("hello") + b"after") == b"beforeafter"
    assert rec.calls == [(["CLIPBOARD"], b"hello")]


def test_st_terminator_is_stripped():
    rec = Recorder()
    filt = Osc52Filter(rec)
    assert filt.feed(sequence("hello", terminator=b"\x1b\\")) == b""
    assert rec.calls == [(["CLIPBOARD"], b"hello")]


def test_selection_names_are_mapped():
    rec = Recorder()
    filt = Osc52Filter(rec)
    filt.feed(sequence("to primary", selection=b"s"))
    filt.feed(sequence("to both", selection=b"cp"))
    assert [c[0] for c in rec.calls] == [["PRIMARY"], ["CLIPBOARD", "PRIMARY"]]


def test_empty_selection_means_clipboard():
    rec = Recorder()
    filt = Osc52Filter(rec)
    filt.feed(sequence("default"))
    assert rec.calls == [(["CLIPBOARD"], b"default")]


def test_query_is_not_answered():
    """A `!` payload must be consumed without any clipboard write."""
    rec = Recorder()
    filt = Osc52Filter(rec)
    assert filt.feed(b"\x1b]52;c;!\x07") == b""
    assert rec.calls == []


def test_invalid_base64_is_passed_through():
    rec = Recorder()
    filt = Osc52Filter(rec)
    assert filt.feed(b"\x1b]52;c;****\x07") == b"\x1b]52;c;****\x07"
    assert rec.calls == []


def test_plain_escape_sequences_are_untouched():
    filt = Osc52Filter(Recorder())
    assert filt.feed(b"\x1b[1;31mbold\x1b[0m") == b"\x1b[1;31mbold\x1b[0m"
    assert filt.feed(b"\x1b]0;title\x07") == b"\x1b]0;title\x07"


def test_sequence_split_across_chunks():
    rec = Recorder()
    filt = Osc52Filter(rec)
    data = sequence("split across reads")
    cut = len(data) // 2
    assert filt.feed(data[:cut]) + filt.feed(data[cut:]) == b""
    assert rec.calls == [(["CLIPBOARD"], b"split across reads")]


def test_head_split_across_chunks():
    rec = Recorder()
    filt = Osc52Filter(rec)
    assert filt.feed(b"abc\x1b]5") == b"abc"
    assert filt.feed(b"2;c;aGVsbG8=\x07") == b""
    assert rec.calls == [(["CLIPBOARD"], b"hello")]


def test_st_terminator_split_across_chunks():
    rec = Recorder()
    filt = Osc52Filter(rec)
    data = sequence("hi", terminator=b"\x1b\\")
    assert filt.feed(data[:-1]) == b""
    assert filt.feed(data[-1:]) == b""
    assert rec.calls == [(["CLIPBOARD"], b"hi")]


def test_byte_at_a_time():
    rec = Recorder()
    filt = Osc52Filter(rec)
    data = b"xx" + sequence("tiny", terminator=b"\x1b\\") + b"yy"
    assert b"".join(filt.feed(bytes([b])) for b in data) == b"xxyy"
    assert rec.calls == [(["CLIPBOARD"], b"tiny")]


def test_two_sequences_in_one_chunk():
    rec = Recorder()
    filt = Osc52Filter(rec)
    assert filt.feed(sequence("one") + sequence("two", selection=b"p")) == b""
    assert rec.calls == [
        (["CLIPBOARD"], b"one"),
        (["PRIMARY"], b"two"),
    ]


def test_oversized_payload_is_not_buffered():
    filt = Osc52Filter(Recorder())
    big = b"\x1b]52;c;" + b"A" * (OSC52_MAX_ENCODED_BYTES + 1024) + b"\x07TAIL"
    assert filt.feed(big) == b"TAIL"


def test_payload_at_the_limit_is_accepted():
    rec = Recorder()
    filt = Osc52Filter(rec)
    payload = base64.b64encode(b"x" * OSC52_MAX_DECODED_BYTES)
    assert filt.feed(b"\x1b]52;c;" + payload + b"\x07") == b""
    assert rec.calls == [(["CLIPBOARD"], b"x" * OSC52_MAX_DECODED_BYTES)]


def test_clipboards_for_selection_dedupes():
    assert clipboards_for_selection("cc") == ["CLIPBOARD"]
    assert clipboards_for_selection("cs") == ["CLIPBOARD", "PRIMARY"]
    assert clipboards_for_selection("") == ["CLIPBOARD"]
    assert clipboards_for_selection("0") == ["CLIPBOARD"]


def test_decode_payload_refuses_bad_input():
    assert decode_payload(b"aGVsbG8=") == b"hello"
    assert decode_payload(b"!") is None
    assert decode_payload(b"") is None
    assert decode_payload(b"!!!!") is None
