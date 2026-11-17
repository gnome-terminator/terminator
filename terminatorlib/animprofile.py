# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""animprofile.py - opt-in frame timing probe for the pane maximise
animation (m37).

Off unless TERMINATOR_ANIM_PROFILE=<path> is set: then every expand/restore
appends one JSON line to <path> with the frame-clock paint timestamps from
the moment the toggle was requested until shortly after it finished.
Zero cost when the variable is unset (begin() returns None).
"""

import json
import os
import time

from .util import dbg

ENV = 'TERMINATOR_ANIM_PROFILE'
SETTLE_MS = 400


def enabled():
    return bool(os.environ.get(ENV))


def summarize(t0, frames, done_at=None):
    """Pure: stats from [(before_paint, after_paint), ...] monotonic secs.

    >>> summarize(0.0, [(0.0, 0.01), (0.02, 0.03), (0.5, 0.6)], 0.025)['frames']
    2
    >>> summarize(0.0, [(0.0, 0.01), (0.02, 0.03), (0.5, 0.6)], 0.025)['max_gap_ms']
    20.0
    >>> s = summarize(0.0, [(0.010, 0.012), (0.026, 0.028), (0.060, 0.070)])
    >>> s['frames'], s['first_frame_ms'], s['max_gap_ms'], s['max_paint_ms']
    (3, 12.0, 42.0, 10.0)
    """
    if done_at is not None:
        # Only the animation itself: frames up to done plus the first frame
        # after it (the hand-over to the real widget). Idle gaps after the
        # animation ended are not jank.
        cut = [f for f in frames if f[1] < done_at]
        rest = [f for f in frames if f[1] >= done_at]
        frames = cut + rest[:1]
    out = {'frames': len(frames)}
    if not frames:
        return out
    aps = [f[1] for f in frames]
    gaps = [(b - a) * 1000.0 for a, b in zip(aps, aps[1:])]
    paints = [(f[1] - f[0]) * 1000.0 for f in frames]
    out['first_frame_ms'] = round((aps[0] - t0) * 1000.0, 1)
    out['span_ms'] = round((aps[-1] - t0) * 1000.0, 1)
    out['max_paint_ms'] = round(max(paints), 1)
    out['mean_paint_ms'] = round(sum(paints) / len(paints), 1)
    if gaps:
        s = sorted(gaps)
        out['max_gap_ms'] = round(s[-1], 1)
        out['mean_gap_ms'] = round(sum(s) / len(s), 1)
        out['p95_gap_ms'] = round(s[min(len(s) - 1, int(0.95 * len(s)))], 1)
        out['gaps_over_33ms'] = sum(1 for g in s if g > 33.4)
    if done_at is not None:
        out['done_ms'] = round((done_at - t0) * 1000.0, 1)
        after = [f for f in frames if f[1] >= done_at]
        if after:
            out['done_to_next_frame_ms'] = round(
                (after[0][1] - done_at) * 1000.0, 1)
            out['done_frame_paint_ms'] = round(
                (after[0][1] - after[0][0]) * 1000.0, 1)
    return out


class Probe(object):
    def __init__(self, kind, widget, path):
        self.kind = kind
        self.path = path
        self.t0 = time.monotonic()
        self.frames = []
        self.marks = {}
        self._bp = None
        self._clock = None
        self._ids = []
        self._closed = False
        try:
            self._clock = widget.get_frame_clock()
        except Exception:
            self._clock = None
        if self._clock is not None:
            self._ids = [
                self._clock.connect('before-paint', self._on_bp),
                self._clock.connect('after-paint', self._on_ap),
            ]

    def _on_bp(self, _clock):
        self._bp = time.monotonic()

    def _on_ap(self, _clock):
        now = time.monotonic()
        self.frames.append((self._bp if self._bp is not None else now, now))
        self._bp = None

    def mark(self, name):
        self.marks.setdefault(name, time.monotonic())

    def done(self):
        """Animation finished: keep sampling SETTLE_MS, then write."""
        self.mark('done')
        from gi.repository import GLib
        GLib.timeout_add(SETTLE_MS, self.close)

    def close(self):
        if self._closed:
            return False
        self._closed = True
        for hid in self._ids:
            try:
                self._clock.disconnect(hid)
            except Exception:
                pass
        rec = {'kind': self.kind}
        rec.update(summarize(self.t0, self.frames, self.marks.get('done')))
        rec['raw_ms'] = [(round((b - self.t0) * 1000.0, 1),
                          round((a - self.t0) * 1000.0, 1))
                         for b, a in self.frames]
        rec['marks_ms'] = dict((k, round((v - self.t0) * 1000.0, 1))
                               for k, v in self.marks.items())
        try:
            with open(self.path, 'a') as fh:
                fh.write(json.dumps(rec) + '\n')
        except Exception as ex:
            dbg('animprofile write: %s' % ex)
        return False


def begin(kind, widget):
    path = os.environ.get(ENV)
    if not path:
        return None
    try:
        return Probe(kind, widget, path)
    except Exception as ex:
        dbg('animprofile begin: %s' % ex)
        return None
