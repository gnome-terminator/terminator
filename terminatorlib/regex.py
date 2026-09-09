"""
Utilities for Regexp in VTE
"""

import gi
from gi.repository import GLib
from . import platform
# libvte is Linux/BSD only; on Windows the ConPTY backend does not use Vte
# regex, so the typelib must not be required. Vte is None on Windows and
# FLAGS_PCRE2 becomes None, which makes callers fall back to GLib.Regex.
if not platform.IS_WINDOWS:
    gi.require_version('Vte', '2.91')  # vte-0.38 (gnome-3.14)
    from gi.repository import Vte
else:
    Vte = None

# constants for vte regex matching are documented in the pcre2 api:
#   https://www.pcre.org/current/doc/html/pcre2api.html
# the corresponding bits are defined here:
#   https://vcs.pcre.org/pcre2/code/trunk/src/pcre2.h.in?view=markup
PCRE2_MULTILINE = 0x00000400
PCRE2_CASELESS = 0x00000008

GLIB_CASELESS = GLib.RegexCompileFlags.CASELESS

FLAGS_GLIB = (GLib.RegexCompileFlags.OPTIMIZE | GLib.RegexCompileFlags.MULTILINE)
if hasattr(Vte, 'REGEX_FLAGS_DEFAULT'):
    FLAGS_PCRE2 = (Vte.REGEX_FLAGS_DEFAULT | PCRE2_MULTILINE)
else:
    FLAGS_PCRE2 = None
