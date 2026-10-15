# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""autofont.py - pure helpers for stepped auto font scaling (M2b / E).

No GTK/VTE imports: safe for headless unit tests and doctest collection.
"""

from __future__ import print_function

from math import ceil, floor


def parse_tiers(raw):
    """Parse config tiers into a strictly decreasing list starting at 1.0.

    Raises ValueError on illegal input.
    """
    if raw is None:
        raise ValueError('tiers must start with 1.0')
    tiers = [float(x) for x in raw]
    if not tiers or tiers[0] != 1.0:
        raise ValueError('tiers must start with 1.0')
    for a, b in zip(tiers, tiers[1:]):
        if not (0 < b < a <= 1.0):
            raise ValueError('tiers must be strictly decreasing in (0,1]')
    return tiers


def cols_rows_from_base(avail_w, avail_h, base_cw, base_ch):
    """Compute base-scale cols/rows from cached cell size.

    Do not use vte.get_column_count() here — that reflects the current
    font_scale and would feed back into the selector.
    """
    if base_cw <= 0 or base_ch <= 0 or avail_w <= 0 or avail_h <= 0:
        return 0, 0
    return int(floor(avail_w / base_cw)), int(floor(avail_h / base_ch))


def base_cell_from_measured(measured, scale):
    """Cell size at font_scale 1.0, recovered from the live cell.

    Do not call set_font_scale(1.0) to measure this. That resizes the
    grid under a running TUI, which then draws for the wrong column count.

    >>> base_cell_from_measured((10, 20), 1.0)
    (10, 20)
    >>> base_cell_from_measured((8, 16), 0.8)
    (10, 20)
    >>> base_cell_from_measured((9, 18), 0.9)
    (10, 20)
    >>> base_cell_from_measured((8, 19), 0.8)
    (10, 24)
    >>> base_cell_from_measured((0, 16), 0.8) is None
    True
    >>> base_cell_from_measured(None, 1.0) is None
    True
    """
    if measured is None:
        return None
    try:
        mw, mh = float(measured[0]), float(measured[1])
        scale = float(scale)
    except (TypeError, ValueError, IndexError):
        return None
    if mw <= 0 or mh <= 0 or scale <= 0:
        return None
    bw = int(round(mw / scale))
    bh = int(round(mh / scale))
    if bw <= 0 or bh <= 0:
        return None
    return (bw, bh)


def same_content_size(a, b, tol_px=16, tol_frac=0.04):
    """True when two panes are the same size for font-tier purposes.

    >>> same_content_size((400, 800), (400, 800))
    True
    >>> same_content_size((400, 800), (408, 804))
    True
    >>> same_content_size((400, 800), (520, 800))
    False
    >>> same_content_size((0, 800), (400, 800))
    False
    """
    try:
        aw, ah = float(a[0]), float(a[1])
        bw, bh = float(b[0]), float(b[1])
    except (TypeError, ValueError, IndexError):
        return False
    if min(aw, ah, bw, bh) <= 0:
        return False
    tol_w = max(float(tol_px), max(aw, bw) * float(tol_frac))
    tol_h = max(float(tol_px), max(ah, bh) * float(tol_frac))
    return abs(aw - bw) <= tol_w and abs(ah - bh) <= tol_h


def base_cell_stale(base, measured, scale, tol_px=1, tol_frac=0.06):
    """m40: True when the cached base cell (cw, ch at font_scale 1.0) no
    longer matches what VTE measures now at ``scale``.

    VTE re-measures its cell when the font, Xft DPI or text scaling
    factor changes; our own set_font_scale() also changes the cell, so at
    scale != 1.0 a small rounding tolerance is allowed and only a real
    font metric change counts.  At scale 1.0 the comparison is exact.

    >>> base_cell_stale((10, 20), (10, 20), 1.0)
    False
    >>> base_cell_stale((10, 20), (12, 25), 1.0)
    True
    >>> base_cell_stale((10, 20), (8, 16), 0.8)
    False
    >>> base_cell_stale((10, 20), (10, 20), 0.8)
    True
    """
    if base is None or measured is None:
        return False
    try:
        bw, bh = float(base[0]), float(base[1])
        mw, mh = float(measured[0]), float(measured[1])
        scale = float(scale)
    except (TypeError, ValueError, IndexError):
        return False
    if bw <= 0 or bh <= 0 or mw <= 0 or mh <= 0 or scale <= 0:
        return False
    if abs(scale - 1.0) < 1e-6:
        return (mw, mh) != (bw, bh)
    for exp, got in ((bw * scale, mw), (bh * scale, mh)):
        if abs(got - exp) > max(tol_px, exp * tol_frac):
            return True
    return False


def select_font_tier(cols0, rows0, cur_index, tiers,
                     min_cols, min_rows, hysteresis, ideal_cols=0):
    """Pick a tier index. One direction only; returns the new index.

    Downscale when the current tier cannot meet min_cols / min_rows.
    Upscale only when the previous tier still meets the hysteresis
    thresholds (and optional ideal_cols).
    """
    n = len(tiers)
    if n == 0:
        return 0
    cur = max(0, min(int(cur_index), n - 1))

    def cols_at(i):
        t = tiers[i]
        return int(floor(cols0 / t)) if t else 0

    def rows_at(i):
        t = tiers[i]
        return int(floor(rows0 / t)) if t else 0

    def ok(i):
        if cols_at(i) < min_cols:
            return False
        if min_rows > 0 and rows_at(i) < min_rows:
            return False
        return True

    if not ok(cur):
        while cur < n - 1 and not ok(cur):
            cur += 1
        return cur

    up_cols = max(int(ceil(min_cols * (1.0 + hysteresis))),
                  int(ideal_cols or 0))
    up_rows = (int(ceil(min_rows * (1.0 + hysteresis)))
               if min_rows > 0 else 0)
    while cur > 0:
        prev = cur - 1
        if cols_at(prev) < up_cols:
            break
        if up_rows and rows_at(prev) < up_rows:
            break
        cur = prev
    return cur


# m26 (round2-ux P1-3): a pane that takes at least this share of its
# window / tab page area never shrinks.  Any 2-pane split (side by side or
# stacked, ~49% each after the handle) keeps 100%; 2x2 grids and 3+ way
# splits (<=~33% / 25%) still step down by the reading measure.
KEEP_FULL_SIZE_SHARE = 0.45


def keeps_full_size(pane_w, pane_h, page_w, page_h,
                    share=KEEP_FULL_SIZE_SHARE):
    """True when the pane is big enough relative to its page to stay 100%.

    >>> keeps_full_size(329, 438, 658, 438)   # side by side
    True
    >>> keeps_full_size(658, 216, 658, 438)   # stacked
    True
    >>> keeps_full_size(329, 216, 658, 438)   # 2x2
    False
    >>> keeps_full_size(100, 100, 0, 0)       # page unknown
    False
    """
    try:
        pane_w, pane_h = float(pane_w), float(pane_h)
        page_w, page_h = float(page_w), float(page_h)
    except (TypeError, ValueError):
        return False
    if min(pane_w, pane_h, page_w, page_h) <= 0:
        return False
    # Allocation rounding/handles: clamp, a pane can't exceed its page
    ratio = min(1.0, (pane_w * pane_h) / (page_w * page_h))
    return ratio >= float(share)


def tier_label(scale):
    """Human-readable percent label for a scale factor."""
    return '%d%%' % int(round(float(scale) * 100))


def validate_auto_font_config(tiers, min_cols, min_rows, hysteresis,
                              ideal_cols=0):
    """Return (ok: bool, reason: str). ok False means E should disable."""
    try:
        parse_tiers(tiers)
    except (TypeError, ValueError) as ex:
        return False, 'tiers: %s' % ex
    try:
        min_cols = int(min_cols)
        min_rows = int(min_rows)
        ideal_cols = int(ideal_cols or 0)
        hysteresis = float(hysteresis)
    except (TypeError, ValueError) as ex:
        return False, 'numeric: %s' % ex
    if min_cols < 1:
        return False, 'min_cols < 1'
    if ideal_cols != 0 and ideal_cols < min_cols:
        return False, 'ideal_cols < min_cols'
    if min_rows < 0:
        return False, 'min_rows < 0'
    if not (0.0 <= hysteresis < 1.0):
        return False, 'hysteresis out of range'
    return True, ''
