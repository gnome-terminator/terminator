"""Tests for terminatorlib.tmux.protocol"""

import unittest
from terminatorlib.tmux.protocol import unescape_tmux_output, CommandResult


class TestUnescapeTmuxOutput(unittest.TestCase):
    """Test tmux octal escape reversal."""

    def test_no_escapes(self):
        """Plain ASCII passes through unchanged."""
        data = b'hello world'
        self.assertEqual(unescape_tmux_output(data), b'hello world')

    def test_newline_escape(self):
        """\\012 (octal for newline) is unescaped."""
        data = b'line1\\012line2'
        self.assertEqual(unescape_tmux_output(data), b'line1\nline2')

    def test_backslash_escape(self):
        """\\134 (octal for backslash) is unescaped."""
        data = b'path\\134file'
        self.assertEqual(unescape_tmux_output(data), b'path\\file')

    def test_tab_escape(self):
        """\\011 (octal for tab) is unescaped."""
        data = b'col1\\011col2'
        self.assertEqual(unescape_tmux_output(data), b'col1\tcol2')

    def test_carriage_return_escape(self):
        """\\015 (octal for CR) is unescaped."""
        data = b'line\\015'
        self.assertEqual(unescape_tmux_output(data), b'line\r')

    def test_escape_char(self):
        """\\033 (octal for ESC) is unescaped."""
        data = b'\\033[1m'
        self.assertEqual(unescape_tmux_output(data), b'\x1b[1m')

    def test_mixed_content(self):
        """Mix of escaped and plain content."""
        data = b'\\033[32mhello\\033[0m\\012'
        expected = b'\x1b[32mhello\x1b[0m\n'
        self.assertEqual(unescape_tmux_output(data), expected)

    def test_empty(self):
        self.assertEqual(unescape_tmux_output(b''), b'')

    def test_trailing_backslash(self):
        """Backslash at end without enough digits passes through."""
        data = b'test\\'
        self.assertEqual(unescape_tmux_output(data), b'test\\')

    def test_non_octal_after_backslash(self):
        """Non-octal digits after backslash pass through."""
        data = b'test\\xyz'
        self.assertEqual(unescape_tmux_output(data), b'test\\xyz')

    def test_null_byte(self):
        """\\000 is unescaped to null byte."""
        data = b'a\\000b'
        self.assertEqual(unescape_tmux_output(data), b'a\x00b')


class TestCommandResult(unittest.TestCase):
    def test_defaults(self):
        result = CommandResult()
        self.assertEqual(result.timestamp, '')
        self.assertEqual(result.command_number, '')
        self.assertEqual(result.output_lines, [])
        self.assertFalse(result.is_error)

    def test_with_values(self):
        result = CommandResult(
            timestamp='12345',
            command_number='1',
            output_lines=[b'line1', b'line2'],
            is_error=True,
        )
        self.assertEqual(result.timestamp, '12345')
        self.assertTrue(result.is_error)
        self.assertEqual(len(result.output_lines), 2)


if __name__ == '__main__':
    unittest.main()
