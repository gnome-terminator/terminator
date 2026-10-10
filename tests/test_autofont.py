# Terminator - autofont pure-function unit tests (no GTK)
"""Tests for terminatorlib.autofont (M2b / E)."""

from __future__ import print_function

import os
import sys

import pytest

sys.path.insert(0, os.path.realpath(os.path.join(os.path.dirname(__file__), "..")))

from terminatorlib.autofont import (
    cols_rows_from_base,
    keeps_full_size,
    parse_tiers,
    select_font_tier,
    tier_label,
    validate_auto_font_config,
)

TIERS = [1.0, 0.9, 0.8]
MIN_C = 60
MIN_R = 8
H = 0.08


def _pick(cols0, rows0, cur=0, min_rows=MIN_R, ideal=0):
    return select_font_tier(cols0, rows0, cur, TIERS, MIN_C, min_rows, H, ideal)


# --- parse_tiers ---

def test_parse_tiers_ok():
    assert parse_tiers(['1.0', '0.9', '0.8']) == [1.0, 0.9, 0.8]
    assert parse_tiers([1.0, 0.85]) == [1.0, 0.85]


@pytest.mark.parametrize('raw', [
    [],
    ['0.9', '0.8'],
    ['1.0', '1.0'],
    ['1.0', '1.1'],
    ['1.0', '0.5', '0.6'],
    ['1.0', '0.0'],
    ['1.0', '-0.1'],
])
def test_parse_tiers_illegal(raw):
    with pytest.raises(ValueError):
        parse_tiers(raw)


# --- cols_rows_from_base ---

def test_cols_rows_from_base():
    assert cols_rows_from_base(800, 600, 10, 20) == (80, 30)
    assert cols_rows_from_base(0, 600, 10, 20) == (0, 0)
    assert cols_rows_from_base(800, 600, 0, 20) == (0, 0)
    assert cols_rows_from_base(-1, 600, 10, 20) == (0, 0)


# --- example table (m26 defaults: MIN_C=60 MIN_R=8 h=0.08) ---
# UP needs >= 65 cols / >= 9 rows. Width (reading measure) is primary; rows
# only matter for tiny panes. (Any 2-pane split is additionally pinned to
# 100% by keeps_full_size(), see below.)

@pytest.mark.parametrize('cols0,rows0,cur,expected', [
    (160, 50, 0, 0),   # single pane → 100%
    (160, 24, 0, 0),   # vertical split → 100%
    (79, 50, 0, 0),    # horizontal split → 100%
    (79, 24, 0, 0),    # 2x2 on a wide window → 100%
    (52, 50, 0, 2),    # 3-way horizontal → 80%
    (40, 15, 0, 2),    # 3x3 grid, cols fail → 80% (floor)
    (163, 17, 0, 0),   # 2 panes stacked on 1000x700 → stays 100%
    (163, 8, 0, 0),    # 8 rows is still enough
    (163, 7, 0, 2),    # very short pane (<8 rows even at 0.9) → 80%
    (59, 50, 0, 1),    # 59 cols → 90%
    (62, 50, 1, 1),    # 62 cols while at 90%: hysteresis blocks up → 90%
    (65, 50, 1, 0),    # 65 cols → 100%
    (79, 50, 2, 0),    # merge back from 80% → step up to 100%
])
def test_select_examples(cols0, rows0, cur, expected):
    assert _pick(cols0, rows0, cur) == expected


def test_defaults_match_config():
    from terminatorlib.config import DEFAULTS
    g = DEFAULTS['global_config']
    assert g['reading_measure_min_cols'] == MIN_C
    assert g['auto_font_scale_min_rows'] == MIN_R


@pytest.mark.parametrize('pane,page,keep', [
    ((329, 438), (658, 438), True),    # default window, side by side
    ((658, 216), (658, 438), True),    # default window, stacked
    ((288, 390), (578, 390), True),    # Monospace 9 window, side by side
    ((449, 654), (898, 654), True),    # Noto Sans Mono 14 window
    ((329, 216), (658, 438), False),   # 2x2
    ((219, 438), (658, 438), False),   # 3 side by side
    ((658, 146), (658, 438), False),   # 3 stacked
    ((658, 438), (658, 438), True),    # single pane
    ((800, 500), (658, 438), True),    # rounding: clamped
    ((100, 100), (0, 0), False),       # page unknown
])
def test_keeps_full_size(pane, page, keep):
    assert keeps_full_size(pane[0], pane[1], page[0], page[1]) is keep


def test_select_min_rows_zero():
    # 3x3 with MIN_R=0: floor still needed for cols, but rows ignored
    assert _pick(40, 5, 0, min_rows=0) == 2


def test_select_ideal_cols():
    # With ideal=66, up from 90% needs cols_at(0) >= 66
    assert select_font_tier(65, 50, 1, TIERS, MIN_C, MIN_R, H, ideal_cols=66) == 1
    assert select_font_tier(66, 50, 1, TIERS, MIN_C, MIN_R, H, ideal_cols=66) == 0


def test_tier_label():
    assert tier_label(1.0) == '100%'
    assert tier_label(0.9) == '90%'
    assert tier_label(0.8) == '80%'


def test_validate_ok():
    ok, reason = validate_auto_font_config(
        ['1.0', '0.9', '0.8'], 60, 24, 0.08, 0)
    assert ok and reason == ''


def test_validate_bad():
    ok, reason = validate_auto_font_config(['0.9'], 60, 24, 0.08, 0)
    assert not ok
    ok, reason = validate_auto_font_config(
        ['1.0', '0.9'], 0, 24, 0.08, 0)
    assert not ok
