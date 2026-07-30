# Terminator - multiple gnome terminals in one window
# Copyright (C) 2006-2010  cmsj@tenshu.net
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 2 only.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA

"""Terminator by Chris Jones <cmsj@tenshu.net>"""

import os as _os
import sys as _sys

# Vendored pure-Python deps live under terminatorlib/_vendor. We append it to
# sys.path (at the END) so a system install always takes precedence when
# present, but the app still runs when the dep is missing -- notably on
# Windows, where MSYS2's mingw python is externally-managed (PEP 668) and
# `pip install configobj` fails out of the box. configobj is BSD-licensed;
# pyte is LGPLv3 and therefore NOT vendored (incompatible with GPLv2-only),
# it must come from pip on the target.
_VENDOR_PATH = _os.path.join(_os.path.dirname(__file__), '_vendor')
if _VENDOR_PATH not in _sys.path:
    _sys.path.append(_VENDOR_PATH)

