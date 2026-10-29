# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""zoomguard.py - one place for "leave zoom before describe/close" (m26)

Two kinds of zoom exist on a Window:

* legacy zoom (reparent / scaled zoom): the zoomed terminal replaces the
  window child and every other pane is *detached* from the window.  Any
  describe_layout(), close or structural change must unzoom first or the
  hidden panes are lost / stay registered.
* overlay maximise (module D): the tree stays intact, one terminal floats
  in a temporary Gtk.Overlay.  ``term_zoomed`` is also True while it is up.

Call sites differ in which of the two they must leave (e.g. a session save
keeps the overlay so ``maximised_pane`` is recorded, but must leave a legacy
zoom), so ``leave_zoom`` takes explicit ``legacy`` / ``overlay`` flags.
All helpers duck-type the window so tests can use fakes.
"""

from .util import dbg


def is_overlay_maximised(window, quiet=True):
    """True while window shows the overlay-maximise chrome."""
    try:
        is_ov = getattr(window, 'is_overlay_maximised', None)
        return bool(callable(is_ov) and is_ov())
    except Exception as ex:
        if not quiet:
            raise
        dbg('zoomguard.is_overlay_maximised: %s' % ex)
        return False


def is_legacy_zoomed(window, quiet=True):
    """True for a legacy (reparent/scaled) zoom, i.e. zoomed but not via
    the overlay."""
    try:
        is_z = getattr(window, 'is_zoomed', None)
        if not callable(is_z) or not is_z():
            return False
    except Exception as ex:
        if not quiet:
            raise
        dbg('zoomguard.is_legacy_zoomed: %s' % ex)
        return False
    return not is_overlay_maximised(window, quiet=quiet)


def leave_zoom(window, legacy=True, overlay=True, animate=False,
               reason='', quiet=True):
    """Leave the requested zoom kind(s) on window.

    overlay=True: snap-restore an overlay maximise (animate defaults False,
    as every close/save path wants).  legacy=True: undo a legacy zoom.
    Only one can be active at a time.  Returns True if something was undone.
    quiet=True logs and swallows exceptions (close/save paths must go on);
    quiet=False re-raises (interactive paths that never guarded before).
    """
    if window is None:
        return False
    try:
        # m26 review: predicate errors follow ``quiet`` too, so a broken
        # overlay state on an interactive path is not misread as "legacy
        # zoom" (which would call unzoom() -> animated restore instead).
        if overlay and is_overlay_maximised(window, quiet=quiet):
            window.overlay_restore(animate=animate)
            return True
        if legacy and is_legacy_zoomed(window, quiet=quiet):
            window.unzoom()
            return True
    except Exception as ex:
        if not quiet:
            raise
        dbg('leave_zoom(%s): %s' % (reason or '?', ex))
    return False


def leave_legacy_zoom_all(windows, reason=''):
    """Undo legacy zoom on every window (overlay left as-is). Returns the
    number of windows unzoomed."""
    count = 0
    for window in list(windows or ()):
        if leave_zoom(window, legacy=True, overlay=False, reason=reason):
            count += 1
    return count


def leave_overlay_all(windows, reason=''):
    """Snap-restore every overlay-maximised window. Returns count."""
    count = 0
    for window in list(windows or ()):
        if leave_zoom(window, legacy=False, overlay=True, reason=reason):
            count += 1
    return count


def any_legacy_zoom(windows):
    return any(is_legacy_zoomed(w) for w in list(windows or ()))
