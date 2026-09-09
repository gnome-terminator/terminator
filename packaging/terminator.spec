# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the Windows build of Terminator.
#
# Build:   pyinstaller packaging/terminator.spec
# Output:  dist/terminator/terminator.exe  (one-folder) + a dist/terminator.zip
#
# This spec bundles:
#   * the terminatorlib package (incl. the Windows ConPTY backend + pyte);
#   * the Glade UI, theme CSS and icon data;
#   * the hidden imports PyInstaller cannot infer (pyte, the win32 pipe
#     modules, the backend widgets).
#
# GTK3 runtime: PyInstaller's PyGObject hook bundles the gi typelibs, but the
# GTK3 shared libraries (DLLs) must be discoverable. The recommended setup is
# to install the MSYS2 GTK3 runtime and add its bin/ to PATH before running
# pyinstaller, or to ship the GTK3 runtime installer alongside. The
# `gtk_bundle` datas entry below pulls in any DLLs found in the GTK bin on
# the build machine when GTK_BIN is set.
#
# (Spec is written for one-folder mode so the GTK DLL layout stays intact;
# switch to onefile only after validating that GTK loads correctly.)

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Data: Glade UI, theme CSS, icons.
datas = [
    ('terminatorlib/preferences.glade', 'terminatorlib'),
    ('terminatorlib/layoutlauncher.glade', 'terminatorlib'),
]
datas += collect_data_files('terminatorlib', include_py_files=False)

# Pull the GTK DLLs in if the builder pointed us at a GTK bin directory.
gtk_bin = os.environ.get('GTK_BIN')
if gtk_bin and os.path.isdir(gtk_bin):
    dlls = [os.path.join(gtk_bin, f) for f in os.listdir(gtk_bin)
            if f.lower().endswith('.dll')]
    datas += [(d, 'gtk') for d in dlls]

hiddenimports = []
# Windows IPC + ConPTY backend deps that PyInstaller won't see statically.
hiddenimports += collect_submodules('pyte')
hiddenimports += [
    'win32pipe', 'win32file', 'win32api', 'pywintypes',
    'terminatorlib.backends.conpty.pty',
    'terminatorlib.backends.conpty.screen',
    'terminatorlib.backends.conpty_backend',
    'terminatorlib.backends.vte_backend',
    'terminatorlib.platform',
    'terminatorlib.ipc_win32',
]

a = Analysis(
    ['terminator'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtimehooks=[],
    excludes=['terminatorlib.ipc'],  # DBus IPC is Linux-only; skip on Windows
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='terminator',
    debug=False,
    strip=False,
    upx=True,
    console=True,   # keep a console for diagnostics during bring-up
    icon='data/icons/hicolor/48x48/apps/terminator.png',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='terminator',
)
