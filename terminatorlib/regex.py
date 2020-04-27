"""
Utilities for Regexp in VTE
"""

import gi
gi.require_version('Vte', '2.91')  # vte-0.38 (gnome-3.14)
from gi.repository import GLib, Vte

# constants for vte regex matching
# TODO: Please replace with a proper reference to VTE, I found none!
PCRE2_MULTILINE = 0x00000400
FLAGS_GLIB = (GLib.RegexCompileFlags.OPTIMIZE | GLib.RegexCompileFlags.MULTILINE)
if hasattr(Vte, 'REGEX_FLAGS_DEFAULT'):
    FLAGS_PCRE2 = (Vte.REGEX_FLAGS_DEFAULT | PCRE2_MULTILINE)
else:
    FLAGS_PCRE2 = None
