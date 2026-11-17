# Terminator by Chris Jones <cmsj@tenshu.net>
# GPL v2 only
"""Two-layer pane attention.

A bell only sets "look at this pane". The states idle, working, blocked,
done, error and clear are the OSC 7501 names and are written only by a
hook. Display priority is blocked, error, attention, working, done.
blocked and error stay until a later hook update. done and attention
clear when the pane gains keyboard focus or receives a key.
"""

CALLS_PER_SECOND = 8
CALL_WINDOW_S = 1.0
NOTIFY_GAP_S = 8.0
MESSAGE_LIMIT = 160

STATES = ('idle', 'working', 'blocked', 'done', 'error', 'clear')

# Higher wins when a tab aggregates its panes. Attention sits below
# blocked and error, and above working and done.
_RANK = {
    'blocked': 50,
    'error': 40,
    'attention': 30,
    'working': 20,
    'done': 10,
}

GLYPH = {
    'blocked': '!',
    'error': 'x',
    'attention': '*',
    'working': '…',
    'done': '+',
}

_NOTIFY = ('blocked', 'error', 'done', 'attention')
_MARK_CLASSES = (
    'titlebar-agent-blocked',
    'titlebar-agent-error',
    'titlebar-agent-attention',
    'titlebar-agent-working',
    'titlebar-agent-done',
)


def normalise_state(state):
    """Return a known state name, or None."""
    if state is None:
        return None
    text = str(state).strip().lower()
    if text in STATES:
        return text
    return None


def clip_message(message):
    """One short line. Drop control characters."""
    if not message:
        return ''
    kept = []
    for char in str(message):
        if char >= ' ' or char == '\t':
            kept.append(char)
    text = ' '.join(''.join(kept).split())
    if len(text) > MESSAGE_LIMIT:
        return text[:MESSAGE_LIMIT - 1] + '…'
    return text


def display_kind(attention, agent_state):
    """The single mark to draw, or None.

    idle and clear draw nothing. A bell's attention mark is used only
    when it outranks the hook state.
    """
    best = None
    best_rank = 0
    if agent_state in _RANK:
        best = agent_state
        best_rank = _RANK[agent_state]
    if attention and _RANK['attention'] > best_rank:
        best = 'attention'
    return best


def winning(panes):
    """Most urgent mark across panes.

    Each pane is ``(attention, agent_state)`` or
    ``(attention, agent_state, message)``. Returns ``(kind, message)``.
    """
    best = None
    best_rank = 0
    message = ''
    for item in panes or ():
        attention = item[0]
        state = item[1]
        msg = item[2] if len(item) > 2 else ''
        kind = display_kind(attention, state)
        if kind is None:
            continue
        rank = _RANK[kind]
        if rank > best_rank:
            best = kind
            best_rank = rank
            message = msg or ''
    return best, message


def with_glyph(title, kind):
    """Append the mark glyph to a tab or pane title."""
    title = title or ''
    if not kind:
        return title
    glyph = GLYPH[kind]
    if not title:
        return glyph
    # The sidebar ellipsizes the end of the row, so the mark stays visible.
    return '%s %s' % (glyph, title)


def apply_report(attention, agent_state, message, incoming, incoming_message):
    """Apply one hook update. None means the state name is unknown.

    clear drops the semantic state and its message. It does not clear
    a bell mark. idle is stored and draws nothing by itself.
    """
    state = normalise_state(incoming)
    if state is None:
        return None
    if state == 'clear':
        return attention, None, ''
    return attention, state, clip_message(incoming_message)


def seen(attention, agent_state, message):
    """Key or confirmed focus. blocked and error stay."""
    if agent_state in ('blocked', 'error'):
        return attention, agent_state, message
    if agent_state == 'done':
        agent_state = None
        message = ''
    return False, agent_state, message


def bell_marks(enabled, window_focused, pane_focused):
    """A bell leaves a persistent mark only when this pane is not being looked at."""
    if not enabled:
        return False
    return not (window_focused and pane_focused)


def notify_allowed(last_time, last_kind, now, kind, window_focused):
    """Desktop notification only while the window is unfocused.

    The same mark waits NOTIFY_GAP_S. A more urgent mark does not wait,
    so a failed or quieter signal cannot swallow the next one.
    """
    if window_focused or kind not in _NOTIFY:
        return False
    if last_time is None:
        return True
    if _RANK[kind] > _RANK.get(last_kind, 0):
        return True
    return (now - last_time) >= NOTIFY_GAP_S


def user_text(kind, message=''):
    """Short label for a tooltip or a notification summary."""
    from .translation import _
    if kind == 'blocked':
        base = _('Waiting for approval')
    elif kind == 'error':
        base = _('Reported an error')
    elif kind == 'attention':
        base = _('Needs attention')
    elif kind == 'working':
        base = _('Busy')
    elif kind == 'done':
        base = _('Finished')
    else:
        base = ''
    message = message or ''
    if base and message:
        return '%s — %s' % (base, message)
    return base or message


def apply_mark(widget, kind, message=''):
    """Show or hide the glyph on a label widget."""
    style = widget.get_style_context()
    for name in _MARK_CLASSES:
        style.remove_class(name)
    if not kind:
        widget.set_text('')
        widget.set_tooltip_text(None)
        widget.hide()
        return
    widget.set_text(GLYPH[kind])
    style.add_class('titlebar-agent-' + kind)
    widget.set_tooltip_text(user_text(kind, message) or None)
    widget.show()


class CallGate(object):
    """At most CALLS_PER_SECOND accepted calls in CALL_WINDOW_S."""

    def __init__(self, window=CALL_WINDOW_S, limit=CALLS_PER_SECOND):
        self.window = window
        self.limit = limit
        self.hits = []

    def allow(self, now):
        self.hits = [stamp for stamp in self.hits if now - stamp < self.window]
        if len(self.hits) >= self.limit:
            return False
        self.hits.append(now)
        return True
