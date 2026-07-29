# Building Terminator for Windows

This documents the native Windows build (M4). The Windows port uses the
ConPTY + pyte backend (see `terminatorlib/backends/`); it does **not** use
libvte or DBus.

## Prerequisites

* Windows 10 1809 or newer (ConPTY requirement).
* Python 3.10 (x64).
* A GTK3 runtime with Python introspection (PyGObject). The supported route
  is [MSYS2](https://www.msys2.org/): install
  `mingw-w64-x86_64-gtk3`, `mingw-w64-x86_64-python3-gobject`,
  `mingw-w64-x86_64-cairo`, then run the build from an MSYS2 shell so the
  GTK DLLs are on `PATH`. Alternatively install a standalone GTK3 runtime
  and set `GTK_BIN` to its `bin` directory.
* Python deps: `pip install pycairo pygobject configobj psutil pyte pywin32 pytest`.

## Install (editable, for development)

```
python setup.py --without-gettext install
```

`--without-gettext` skips the Linux-only `msgfmt` / `intltool-merge` build
steps (`.desktop` and AppStream files are not needed on Windows).

## Package with PyInstaller

```
set GTK_BIN=C:\msys64\mingw64\bin
pyinstaller packaging\terminator.spec
```

The spec bundles `terminatorlib`, the Windows backend, pyte, the win32 pipe
modules, and the Glade/theme/icon data; if `GTK_BIN` is set it also collects
the GTK DLLs. Output is `dist\terminator\terminator.exe`.

## Run

```
dist\terminator\terminator.exe
```

It launches PowerShell (`pwsh` / `powershell`) by default; set
`use_custom_command` in the config to run `cmd.exe` or `wsl.exe` instead.

## What works / what is tracked

* Working: spawning cmd/powershell/wsl, rendering (full per-cell/per-run
  colour -- true-colour, palette, reverse, bold/italic/underline/strike),
  scrollback, resize, colours/fonts, cursor shapes (block/underline/beam)
  with cursor colours and blink, URL matching + open, single-instance,
  split/tab/broadcast (shared layout container logic), dark titlebar (DWM).
* Tracked gaps: SIXEL graphics, OSC-8 hyperlink hover metadata, CJK IME
  composition, double-width/CJK glyph alignment in the per-run renderer.
