from gi.repository import GObject

from terminatorlib.util import dbg
from terminatorlib.tmux import layout

import string
ATTACH_ERROR_STRINGS = ["can't find session terminator", "no current session", "no sessions"]
ALTERNATE_SCREEN_ENTER_CODES = [ "\\033[?1049h" ]
ALTERNATE_SCREEN_EXIT_CODES  = [ "\\033[?1049l" ]

notifications_mappings = {}


def notification(cls):
    notifications_mappings[cls.marker] = cls
    return cls


class Notification(object):

    marker = 'undefined'
    attributes = []

    def consume(self, line, out):
        pass

    def __str__(self):
        attributes = ['{}="{}"'.format(attribute, getattr(self, attribute, ''))
                      for attribute in self.attributes]
        return '{}[{}]'.format(self.marker, ', '.join(attributes))


@notification
class Result(Notification):

    marker = 'begin'
    attributes = ['begin_timestamp', 'code', 'result', 'end_timestamp',
                  'error']

    def consume(self, line, out):
        timestamp, code, _ = line
        self.begin_timestamp = timestamp
        self.code = code
        result = []
        line = out.readline()[:-1]
        while not (line.startswith('%end') or line.startswith('%error')):
            result.append(line)
            line = out.readline()[:-1]
        self.result = result
        end, timestamp, code, _ = line.split(' ')
        self.end_timestamp = timestamp
        self.error = end == '%error'


@notification
class Exit(Notification):

    marker = 'exit'
    attributes = ['reason']

    def consume(self, line, *args):
        self.reason = line[0] if line else None


@notification
class LayoutChange(Notification):

    marker = 'layout-change'
    attributes = ['window_id', 'window_layout', 'window_visible_layout',
                  'window_flags']

    def consume(self, line, *args):
        # attributes not present default to None
        window_id, window_layout, window_visible_layout, window_flags = line + [None] * (len(self.attributes) - len(line))
        self.window_id = window_id
        self.window_layout = window_layout
        self.window_visible_layout = window_visible_layout
        self.window_flags = window_flags

@notification
class Output(Notification):

    marker = 'output'
    attributes = ['pane_id', 'output']

    def consume(self, line, *args):
        pane_id = line[0]
        output = ' '.join(line[1:])
        self.pane_id = pane_id
        self.output = output

@notification
class SessionChanged(Notification):

    marker = 'session-changed'
    attributes = ['session_id', 'session_name']

    def consume(self, line, *args):
        session_id, session_name = line
        self.session_id = session_id
        self.session_name = session_name


@notification
class SessionRenamed(Notification):

    marker = 'session-renamed'
    attributes = ['session_id', 'session_name']

    def consume(self, line, *args):
        session_id, session_name = line
        self.session_id = session_id
        self.session_name = session_name


@notification
class SessionsChanged(Notification):

    marker = 'sessions-changed'
    attributes = []


@notification
class UnlinkedWindowAdd(Notification):

    marker = 'unlinked-window-add'
    attributes = ['window_id']

    def consume(self, line, *args):
        window_id, = line
        self.window_id = window_id


@notification
class WindowAdd(Notification):

    marker = 'window-add'
    attributes = ['window_id']

    def consume(self, line, *args):
        window_id, = line
        self.window_id = window_id


@notification
class UnlinkedWindowClose(Notification):

    marker = 'unlinked-window-close'
    attributes = ['window_id']

    def consume(self, line, *args):
        window_id, = line
        self.window_id = window_id


@notification
class WindowClose(Notification):

    marker = 'window-close'
    attributes = ['window_id']

    def consume(self, line, *args):
        window_id, = line
        self.window_id = window_id


@notification
class UnlinkedWindowRenamed(Notification):

    marker = 'unlinked-window-renamed'
    attributes = ['window_id', 'window_name']

    def consume(self, line, *args):
        window_id, window_name = line
        self.window_id = window_id
        self.window_name = window_name


@notification
class WindowRenamed(Notification):

    marker = 'window-renamed'
    attributes = ['window_id', 'window_name']

    def consume(self, line, *args):
        window_id, window_name = line
        self.window_id = window_id
        self.window_name = window_name


class NotificationsHandler(object):

    def __init__(self, terminator):
        self.terminator = terminator
        self.layout_parser = layout.LayoutParser()

    def handle(self, notification):
        try:
            handler_method = getattr(self, 'handle_{}'.format(
                    notification.marker.replace('-', '_')))
            handler_method(notification)
        except AttributeError:
            pass

    def handle_begin(self, notification):
        dbg('### {}'.format(notification))
        assert isinstance(notification, Result)
        callback = self.terminator.tmux_control.requests.get()
        if notification.error:
            dbg('Request error: {}'.format(notification))
            if notification.result[0] in ATTACH_ERROR_STRINGS:
                # if we got here it means that attaching to an existing session
                # failed, invalidate the layout so the Terminator initialization
                # can pick up from where we left off
                self.terminator.initial_layout = {}
                self.terminator.tmux_control.reset()
            return
        callback(notification.result)

    def handle_output(self, notification):
        assert isinstance(notification, Output)
        pane_id = notification.pane_id
        output = notification.output
        terminal = self.terminator.pane_id_to_terminal.get(pane_id)
        if not terminal:
            return
        for code in ALTERNATE_SCREEN_ENTER_CODES:
            if code in output:
                self.terminator.tmux_control.alternate_on = True
        for code in ALTERNATE_SCREEN_EXIT_CODES:
            if code in output:
                self.terminator.tmux_control.alternate_on = False
        # NOTE: using neovim, enabling visual-bell and setting t_vb empty results in incorrect
        # escape sequences (C-g) being printed in the neovim window; remove them until we can
        # figure out the root cause
        terminal.vte.feed(output.decode('string_escape').replace("\033g",""))

    def handle_layout_change(self, notification):
        assert isinstance(notification, LayoutChange)
        GObject.idle_add(self.terminator.tmux_control.garbage_collect_panes)

    def handle_window_close(self, notification):
        assert isinstance(notification, WindowClose)
        GObject.idle_add(self.terminator.tmux_control.garbage_collect_panes)

    def pane_id_result(self, result):
        pane_id, marker = result[0].split(' ')
        terminal = self.terminator.find_terminal_by_pane_id(marker)
        terminal.pane_id = pane_id
        self.terminator.pane_id_to_terminal[pane_id] = terminal

    # NOTE: UNUSED; if we ever end up needing this, create the tty property in
    # the Terminal class first
    def pane_tty_result(self, result):
        dbg(result)
        pane_id, pane_tty = result[0].split(' ')
        # self.terminator.pane_id_to_terminal[pane_id].tty = pane_tty

    def garbage_collect_panes_result(self, result):
        pane_id_to_terminal = self.terminator.pane_id_to_terminal
        removed_pane_ids = pane_id_to_terminal.keys()

        for line in result:
            pane_id, pane_pid = line.split(' ')
            try:
                removed_pane_ids.remove(pane_id)
                pane_id_to_terminal[pane_id].pid = pane_pid
            except ValueError:
                dbg("Pane already reaped, keep going.")
                continue

        if removed_pane_ids:
            def callback():
                for pane_id in removed_pane_ids:
                    terminal = pane_id_to_terminal.pop(pane_id, None)
                    if terminal:
                        terminal.close()
                return False
            GObject.idle_add(callback)

    def initial_layout_result(self, result):
        window_layouts = []
        for line in result:
            window_layout = line.strip()
            window_layouts.extend(layout.parse_layout(self.layout_parser.parse(window_layout)[0]))
            # window_layouts.append(layout.parse_layout(window_layout))
        terminator_layout = layout.convert_to_terminator_layout(
                window_layouts)
        import pprint
        dbg(pprint.pformat(terminator_layout))
        self.terminator.initial_layout = terminator_layout

    def initial_output_result_callback(self, pane_id):
        def result_callback(result):
            terminal = self.terminator.pane_id_to_terminal.get(pane_id)
            if not terminal:
                return
            output = '\r\n'.join(l for l in result if l)
            terminal.vte.feed(output.decode('string_escape'))
        return result_callback

    def terminate(self):
        def callback():
            for window in self.terminator.windows:
                window.emit('destroy')
        GObject.idle_add(callback)


def noop(result):
    pass
