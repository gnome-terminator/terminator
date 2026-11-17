# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""clipboard_image.py - paste a clipboard image as a file path.

VTE 0.68 (Ubuntu 22.04) only asks the clipboard for text, so pasting a
screenshot or "Copy image" leaves the terminal silent: there is no text
target to request.  When the clipboard has image targets but no text,
save the pixbuf as a PNG under ``~/.cache/terminator/pasted-images/``
and paste the shell-quoted path instead.  Files are private to the user
and pruned after a week or 100 pastes.
"""

from __future__ import print_function

import os
import shlex
import tempfile
import time

from .util import dbg, get_cache_dir

DIRNAME = 'pasted-images'
PREFIX = 'image-'
SUFFIX = '.png'
MAX_AGE_SECONDS = 7 * 24 * 60 * 60
MAX_FILES = 100


def image_dir():
    """Directory that holds pasted clipboard images."""
    return os.path.join(get_cache_dir(), DIRNAME)


def quote_path(path):
    """Quote one path for a POSIX shell."""
    return shlex.quote(path)


def paste_text(paths):
    """Text to feed for a list of paths.

    The trailing space matches drag-and-drop and GNOME Terminal's
    "Paste as Filenames", so the next argument can be typed directly.
    """
    return ' '.join(quote_path(path) for path in paths) + ' '


def new_path(directory=None, now=None):
    """Create an empty, private PNG path and return it."""
    directory = directory or image_dir()
    os.makedirs(directory, mode=0o700, exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S', time.localtime(now))
    fd, path = tempfile.mkstemp(prefix=PREFIX + stamp + '-', suffix=SUFFIX,
                                dir=directory)
    os.close(fd)
    os.chmod(path, 0o600)
    return path


def save_pixbuf(pixbuf, directory=None, now=None):
    """Write ``pixbuf`` as a PNG and return the path.

    The file is removed again if encoding fails, so a failed paste does
    not leave an empty image behind.
    """
    path = new_path(directory, now)
    try:
        if not pixbuf.savev(path, 'png', [], []):
            raise IOError('could not encode the clipboard image as PNG')
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    return path


def prune(directory=None, now=None, max_age=MAX_AGE_SECONDS,
          max_files=MAX_FILES):
    """Best-effort removal of old pasted images.

    Only files this module creates are touched.  Errors are ignored: a
    cache that cannot be pruned must not break pasting.
    """
    directory = directory or image_dir()
    now = time.time() if now is None else now
    try:
        entries = [os.path.join(directory, name)
                   for name in os.listdir(directory)
                   if name.startswith(PREFIX) and name.endswith(SUFFIX)]
    except OSError:
        return 0

    kept = []
    removed = 0
    for path in entries:
        try:
            mtime = os.stat(path).st_mtime
            if now - mtime > max_age:
                os.unlink(path)
                removed += 1
                continue
        except OSError:
            continue
        kept.append((mtime, path))

    if len(kept) > max_files:
        kept.sort()
        for _mtime, path in kept[:len(kept) - max_files]:
            try:
                os.unlink(path)
                removed += 1
            except OSError:
                pass

    if removed:
        dbg('pruned %d pasted image(s) from %s' % (removed, directory))
    return removed
