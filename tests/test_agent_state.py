"""Pane attention rules. TX-11."""

from terminatorlib.agentstate import (
    CallGate,
    apply_report,
    bell_marks,
    clip_message,
    display_kind,
    notify_allowed,
    seen,
    winning,
    with_glyph,
)


def test_bell_is_off_unless_the_profile_asks_for_a_mark():
    """TX-11.1 A bell does not leave a mark while attention_on_bell is false."""
    assert bell_marks(False, False, False) is False
    assert bell_marks(False, True, False) is False


def test_bell_marks_only_a_pane_the_user_is_not_looking_at():
    """TX-11.2 The focused pane of a focused window is already visible."""
    assert bell_marks(True, True, True) is False
    assert bell_marks(True, True, False) is True
    assert bell_marks(True, False, True) is True
    assert bell_marks(True, False, False) is True


def test_hook_states_use_the_osc_7501_names_and_leave_the_bell_mark():
    """TX-11.3 clear drops the semantic state only. Unknown names are refused."""
    assert apply_report(True, 'blocked', 'wait', 'clear', 'gone') == (
        True, None, '')
    assert apply_report(False, None, '', 'idle', 'resting') == (
        False, 'idle', 'resting')
    assert apply_report(False, None, '', 'blocked', ' needs approval ') == (
        False, 'blocked', 'needs approval')
    assert apply_report(False, 'working', 'run', 'done', 'ok') == (
        False, 'done', 'ok')
    assert apply_report(False, None, '', 'nope', '') is None
    assert clip_message('a\x00b\nc') == 'abc'
    assert clip_message('a  b\tc') == 'a b c'
    assert len(clip_message('x' * 500)) == 160


def test_one_pane_accepts_eight_updates_in_a_second():
    """TX-11.3 The ninth update inside one second is rejected."""
    gate = CallGate()
    for _count in range(8):
        assert gate.allow(0.1)
    assert gate.allow(0.2) is False
    assert gate.allow(1.1) is True


def test_a_tab_shows_the_most_urgent_pane():
    """TX-11.4 blocked, error, attention, working, then done."""
    assert display_kind(False, None) is None
    assert display_kind(False, 'idle') is None
    assert display_kind(True, None) == 'attention'
    assert display_kind(True, 'working') == 'attention'
    assert display_kind(False, 'working') == 'working'
    assert display_kind(True, 'blocked') == 'blocked'
    assert winning([
        (False, 'working', ''),
        (True, None, ''),
    ]) == ('attention', '')
    assert winning([
        (True, None, 'look'),
        (False, 'error', 'failed'),
    ]) == ('error', 'failed')
    assert winning([
        (False, 'done', 'a'),
        (False, 'working', 'b'),
    ]) == ('working', 'b')
    assert winning([]) == (None, '')
    assert with_glyph('src', 'blocked') == '! src'
    assert with_glyph('', 'done') == '+'
    assert with_glyph('src', None) == 'src'


def test_focus_clears_done_and_attention_but_not_a_block():
    """TX-11.5 blocked and error stay. done and a bare attention mark clear."""
    assert seen(True, None, '') == (False, None, '')
    assert seen(True, 'done', 'finished') == (False, None, '')
    assert seen(True, 'working', 'run') == (False, 'working', 'run')
    assert seen(True, 'blocked', 'approve') == (True, 'blocked', 'approve')
    assert seen(False, 'error', 'boom') == (False, 'error', 'boom')


def test_notify_only_while_the_window_is_unfocused_and_a_louder_mark_is_not_dropped():
    """TX-11.2 Same mark waits 8 seconds. A more urgent mark does not."""
    assert notify_allowed(None, None, 0, 'done', True) is False
    assert notify_allowed(None, None, 0, 'working', False) is False
    assert notify_allowed(None, None, 0, 'attention', False) is True
    assert notify_allowed(0, 'attention', 7, 'attention', False) is False
    assert notify_allowed(0, 'attention', 8, 'attention', False) is True
    assert notify_allowed(0, 'attention', 1, 'blocked', False) is True
    assert notify_allowed(0, 'blocked', 1, 'done', False) is False
