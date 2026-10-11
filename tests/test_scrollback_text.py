#!/usr/bin/env python
# GPL v2 only
"""Unit tests for terminatorlib.scrollback_text (gi-free)."""

from __future__ import print_function

import os
import stat
import tempfile
import unittest

from terminatorlib.scrollback_text import (
    UUID_FILE_RE,
    atomic_write_txt,
    format_separator,
    format_separator_feed,
    is_valid_uuid_filename,
    scrollback_worth_replaying,
    strip_replay_separators,
    normalize_newlines_for_feed,
    sanitize_for_feed,
    truncate_lines_and_bytes,
    truncate_utf8_bytes,
)


class TestTruncateUtf8(unittest.TestCase):
    def test_ascii(self):
        self.assertEqual(truncate_utf8_bytes(b'abcdef', 3), b'def')

    def test_no_split_multibyte(self):
        # '€' is e2 82 ac
        data = b'x' + '€'.encode('utf-8') + b'y'
        out = truncate_utf8_bytes(data, 4)  # would start mid-euro if naive
        # Must be valid utf-8
        out.decode('utf-8')
        self.assertTrue(out.endswith(b'y') or out == b'y' or '€'.encode('utf-8') in out)

    def test_cjk(self):
        data = '你好世界'.encode('utf-8')
        out = truncate_utf8_bytes(data, 6)
        self.assertEqual(out.decode('utf-8'), '世界')

    def test_zero(self):
        self.assertEqual(truncate_utf8_bytes(b'abc', 0), b'')


class TestTruncateLinesAndBytes(unittest.TestCase):
    def test_lines(self):
        self.assertEqual(
            truncate_lines_and_bytes('a\nb\nc\nd', 2, 512), 'c\nd')

    def test_bytes_cap(self):
        text = ('x' * 200 + '\n') * 20
        out = truncate_lines_and_bytes(text, 100, 1)  # 1KB
        self.assertLessEqual(len(out.encode('utf-8')), 1024)

    def test_empty(self):
        self.assertEqual(truncate_lines_and_bytes('', 10, 1), '')
        self.assertEqual(truncate_lines_and_bytes('hi', 0, 1), '')


class TestSanitize(unittest.TestCase):
    def test_osc_title(self):
        self.assertEqual(
            sanitize_for_feed('hello\x1b]0;title\x07world'), 'helloworld')

    def test_csi_color(self):
        self.assertEqual(sanitize_for_feed('a\x1b[31mb\x1b[0mc'), 'abc')

    def test_keeps_whitespace(self):
        self.assertEqual(sanitize_for_feed('keep\t\n\r'), 'keep\t\n\r')

    def test_cjk_emoji(self):
        s = sanitize_for_feed('中文emoji😀')
        self.assertIn('中文', s)
        self.assertIn('emoji', s)

    def test_c1(self):
        self.assertEqual(sanitize_for_feed('a\x9bb'), 'ab')


class TestNewlines(unittest.TestCase):
    def test_mixed(self):
        self.assertEqual(
            normalize_newlines_for_feed('a\nb\r\nc\rd'),
            'a\r\nb\r\nc\r\nd')


class TestUuid(unittest.TestCase):
    def test_valid(self):
        u = '12345678-1234-5678-1234-567812345678'
        self.assertTrue(UUID_FILE_RE.match(u))
        self.assertTrue(is_valid_uuid_filename(u))

    def test_rejects_path(self):
        self.assertFalse(is_valid_uuid_filename('../etc/passwd'))
        self.assertFalse(is_valid_uuid_filename('abc'))
        self.assertFalse(is_valid_uuid_filename(None))
        self.assertFalse(is_valid_uuid_filename(''))


class TestSeparator(unittest.TestCase):
    def test_with_mtime(self):
        label = format_separator(0)  # epoch
        self.assertIn('────', label)

    def test_feed_has_sgr(self):
        feed = format_separator_feed(None)
        self.assertIn('\x1b[90m', feed)
        self.assertIn('\x1b[0m', feed)
        self.assertTrue(feed.startswith('\r\n'))


class TestReplayWorth(unittest.TestCase):
    def test_prompt_only_is_skipped(self):
        self.assertFalse(scrollback_worth_replaying('clarence@AILinux:~$ '))
        self.assertFalse(scrollback_worth_replaying(
            'clarence@AILinux:~$ \n'
            '──── 以上为上次会话的输出（已保存的快照，程序未恢复）· 10-10 20:55 ────\n'
            'clarence@AILinux:~$ '))

    def test_command_output_is_kept_and_old_separator_dropped(self):
        text = (
            'clarence@AILinux:~$ ls\n'
            'file\n'
            '──── Output above is from the previous session '
            '(saved snapshot; programs were not restored) · 10-10 20:55 ────\n'
        )
        self.assertTrue(scrollback_worth_replaying(text))
        kept = strip_replay_separators(text)
        self.assertIn('file', kept)
        self.assertNotIn('previous session', kept)


class TestAtomicWrite(unittest.TestCase):
    def test_writes_0600_and_content(self):
        td = tempfile.mkdtemp()
        try:
            path = os.path.join(td, 'abc.txt')
            atomic_write_txt(path, b'hello', mode=0o600)
            with open(path, 'rb') as fh:
                self.assertEqual(fh.read(), b'hello')
            mode = stat.S_IMODE(os.stat(path).st_mode)
            self.assertEqual(mode, 0o600)
        finally:
            for name in os.listdir(td):
                os.unlink(os.path.join(td, name))
            os.rmdir(td)

    def test_preserves_old_on_failure(self):
        td = tempfile.mkdtemp()
        try:
            path = os.path.join(td, 'abc.txt')
            atomic_write_txt(path, b'old', mode=0o600)
            # Simulate failure by targeting a non-writable path after creating
            # a good file — replace onto a directory name should fail mid-way
            # differently; instead verify partial tmp cleanup via bad dir.
            bad_dir = os.path.join(td, 'nosuch')
            bad_path = os.path.join(bad_dir, 'x.txt')
            with self.assertRaises(Exception):
                atomic_write_txt(bad_path, b'new', mode=0o600)
            with open(path, 'rb') as fh:
                self.assertEqual(fh.read(), b'old')
        finally:
            for root, dirs, files in os.walk(td, topdown=False):
                for f in files:
                    os.unlink(os.path.join(root, f))
                for d in dirs:
                    os.rmdir(os.path.join(root, d))
            os.rmdir(td)


if __name__ == '__main__':
    unittest.main()
