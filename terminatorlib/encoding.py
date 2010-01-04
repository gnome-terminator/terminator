#!/usr/bin/python
#    TerminatorEncoding - charset encoding classes
#    Copyright (C) 2006-2010  chantra@debuntu.org
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, version 2 only.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

"""TerminatorEncoding by Emmanuel Bretelle <chantra@debuntu.org>

TerminatorEncoding supplies a list of possible encoding
 values.
This list is taken from gnome-terminal's src/terminal-encoding.c
 and src/encoding.c
"""

from translation import _

#pylint: disable-msg=R0903
class TerminatorEncoding:
    """Class to store encoding details"""

# The commented out entries below are so marked because gnome-terminal has done
#  the same.
    encodings = [
        [True, None, _("Current Locale")],
        [False, "ISO-8859-1", _("Western")],
        [False, "ISO-8859-2", _("Central European")],
        [False, "ISO-8859-3", _("South European") ],
        [False, "ISO-8859-4", _("Baltic") ],
        [False, "ISO-8859-5", _("Cyrillic") ],
        [False, "ISO-8859-6", _("Arabic") ],
        [False, "ISO-8859-7", _("Greek") ],
        [False, "ISO-8859-8", _("Hebrew Visual") ],
        [False, "ISO-8859-8-I", _("Hebrew") ],
        [False, "ISO-8859-9", _("Turkish") ],
        [False, "ISO-8859-10", _("Nordic") ],
        [False, "ISO-8859-13", _("Baltic") ],
        [False, "ISO-8859-14", _("Celtic") ],
        [False, "ISO-8859-15", _("Western") ],
        [False, "ISO-8859-16", _("Romanian") ],
        #    [False, "UTF-7", _("Unicode") ],
        [False, "UTF-8", _("Unicode") ],
        #    [False, "UTF-16", _("Unicode") ],
        #    [False, "UCS-2", _("Unicode") ],
        #    [False, "UCS-4", _("Unicode") ],
        [False, "ARMSCII-8", _("Armenian") ],
        [False, "BIG5", _("Chinese Traditional") ],
        [False, "BIG5-HKSCS", _("Chinese Traditional") ],
        [False, "CP866", _("Cyrillic/Russian") ],
        [False, "EUC-JP", _("Japanese") ],
        [False, "EUC-KR", _("Korean") ],
        [False, "EUC-TW", _("Chinese Traditional") ],
        [False, "GB18030", _("Chinese Simplified") ],
        [False, "GB2312", _("Chinese Simplified") ],
        [False, "GBK", _("Chinese Simplified") ],
        [False, "GEORGIAN-PS", _("Georgian") ],
        [False, "HZ", _("Chinese Simplified") ],
        [False, "IBM850", _("Western") ],
        [False, "IBM852", _("Central European") ],
        [False, "IBM855", _("Cyrillic") ],
        [False, "IBM857", _("Turkish") ],
        [False, "IBM862", _("Hebrew") ],
        [False, "IBM864", _("Arabic") ],
        [False, "ISO-2022-JP", _("Japanese") ],
        [False, "ISO-2022-KR", _("Korean") ],
        [False, "ISO-IR-111", _("Cyrillic") ],
        #    [False, "JOHAB", _("Korean") ],
        [False, "KOI8-R", _("Cyrillic") ],
        [False, "KOI8-U", _("Cyrillic/Ukrainian") ],
        [False, "MAC_ARABIC", _("Arabic") ],
        [False, "MAC_CE", _("Central European") ],
        [False, "MAC_CROATIAN", _("Croatian") ],
        [False, "MAC-CYRILLIC", _("Cyrillic") ],
        [False, "MAC_DEVANAGARI", _("Hindi") ],
        [False, "MAC_FARSI", _("Persian") ],
        [False, "MAC_GREEK", _("Greek") ],
        [False, "MAC_GUJARATI", _("Gujarati") ],
        [False, "MAC_GURMUKHI", _("Gurmukhi") ],
        [False, "MAC_HEBREW", _("Hebrew") ],
        [False, "MAC_ICELANDIC", _("Icelandic") ],
        [False, "MAC_ROMAN", _("Western") ],
        [False, "MAC_ROMANIAN", _("Romanian") ],
        [False, "MAC_TURKISH", _("Turkish") ],
        [False, "MAC_UKRAINIAN", _("Cyrillic/Ukrainian") ],
        [False, "SHIFT-JIS", _("Japanese") ],
        [False, "TCVN", _("Vietnamese") ],
        [False, "TIS-620", _("Thai") ],
        [False, "UHC", _("Korean") ],
        [False, "VISCII", _("Vietnamese") ],
        [False, "WINDOWS-1250", _("Central European") ],
        [False, "WINDOWS-1251", _("Cyrillic") ],
        [False, "WINDOWS-1252", _("Western") ],
        [False, "WINDOWS-1253", _("Greek") ],
        [False, "WINDOWS-1254", _("Turkish") ],
        [False, "WINDOWS-1255", _("Hebrew") ],
        [False, "WINDOWS-1256", _("Arabic") ],
        [False, "WINDOWS-1257", _("Baltic") ],
        [False, "WINDOWS-1258", _("Vietnamese") ]
        ]

    def __init__(self):
        pass

    def get_list():
        """Return a list of supported encodings"""
        return TerminatorEncoding.encodings

    get_list = staticmethod(get_list)

