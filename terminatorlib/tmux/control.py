import threading
import subprocess
import Queue

from pipes import quote
from gi.repository import Gtk, Gdk

from terminatorlib.tmux import notifications
from terminatorlib.util import dbg

ESCAPE_CODE = '\033'
TMUX_BINARY = 'tmux'

def esc(seq):
    return '{}{}'.format(ESCAPE_CODE, seq)


KEY_MAPPINGS = {
    Gdk.KEY_BackSpace: '\b',
    Gdk.KEY_Tab: '\t',
    Gdk.KEY_Insert: esc('[2~'),
    Gdk.KEY_Delete: esc('[3~'),
    Gdk.KEY_Page_Up: esc('[5~'),
    Gdk.KEY_Page_Down: esc('[6~'),
    Gdk.KEY_Home: esc('[1~'),
    Gdk.KEY_End: esc('[4~'),
    Gdk.KEY_Up: esc('[A'),
    Gdk.KEY_Down: esc('[B'),
    Gdk.KEY_Right: esc('[C'),
    Gdk.KEY_Left: esc('[D'),
}
ARROW_KEYS = {
    Gdk.KEY_Up,
    Gdk.KEY_Down,
    Gdk.KEY_Left,
    Gdk.KEY_Right
}
MOUSE_WHEEL = {
    # TODO: make it configurable, e.g. like better-mouse-mode plugin
    Gdk.ScrollDirection.UP: "C-y C-y C-y",
    Gdk.ScrollDirection.DOWN: "C-e C-e C-e",
}

# TODO: implement ssh connection using paramiko
class TmuxControl(object):

    def __init__(self, session_name, notifications_handler):
        self.session_name = session_name
        self.notifications_handler = notifications_handler
        self.tmux = None
        self.output = None
        self.input = None
        self.consumer = None
        self.width = None
        self.height = None
        self.remote = None
        self.alternate_on = False
        self.is_zoomed = False
        self.requests = Queue.Queue()

    def reset(self):
        self.tmux = self.input = self.output = self.width = self.height = None

    def remote_connect(self, command):
        if self.tmux:
            dbg("Already connected.")
            return
        popen_command = "ssh " + self.remote
        self.tmux = subprocess.Popen(popen_command,
                                 stdout=subprocess.PIPE,
                                 stdin=subprocess.PIPE, shell=True)
        self.input  = self.tmux.stdin
        self.output = self.tmux.stdout

        self.run_remote_command(command)

    def run_remote_command(self, popen_command):
        popen_command = map(quote, popen_command)
        command = " ".join(popen_command)
        if not self.input:
            dbg('No tmux connection. [command={}]'.format(command))
        else:
            try:
                self.input.write('exec {}\n'.format(command))
            except IOError:
                dbg("Tmux server has gone away.")
                return

    def run_command(self, command, marker, cwd=None, orientation=None,
                    pane_id=None):
        if self.input:
            if orientation:
                self.split_window(cwd=cwd, orientation=orientation,
                                  pane_id=pane_id, command=command,
                                  marker=marker)
            else:
                self.new_window(cwd=cwd, command=command, marker=marker)
        else:
            self.new_session(cwd=cwd, command=command, marker=marker)

    def split_window(self, cwd, orientation, pane_id,
                     command=None, marker=''):
        orientation = '-h' if orientation == 'horizontal' else '-v'
        tmux_command = 'split-window {} -t {} -P -F "#D {}"'.format(
            orientation, pane_id, marker)
        if cwd:
            tmux_command += ' -c "{}"'.format(cwd)
        if command:
            tmux_command += ' "{}"'.format(command)

        self._run_command(tmux_command,
                          callback=self.notifications_handler.pane_id_result)

    def new_window(self, cwd=None, command=None, marker=''):
        tmux_command = 'new-window -P -F "#D {}"'.format(marker)
        if cwd:
            tmux_command += ' -c "{}"'.format(cwd)
        if command:
            tmux_command += ' "{}"'.format(command)

        self._run_command(tmux_command,
                          callback=self.notifications_handler.pane_id_result)

    def attach_session(self):
        popen_command = [TMUX_BINARY, '-2', '-C', 'attach-session',
                         '-t', self.session_name]
        if self.remote:
            self.remote_connect(popen_command)
        if not self.tmux:
            self.tmux = subprocess.Popen(popen_command,
                                     stdout=subprocess.PIPE,
                                     stdin=subprocess.PIPE)
            self.input = self.tmux.stdin
            self.output = self.tmux.stdout
        self.requests.put(notifications.noop)
        self.start_notifications_consumer()
        self.initial_layout()

    def new_session(self, cwd=None, command=None, marker=''):
        popen_command = [TMUX_BINARY, '-2', '-C', 'new-session', '-s', self.session_name,
                '-P', '-F', '#D {}'.format(marker)]
        if cwd and not self.remote:
            popen_command += ['-c', cwd]
        if command:
            popen_command.append(command)
        if self.remote:
            self.remote_connect(popen_command)
        if not self.tmux:
            self.tmux = subprocess.Popen(popen_command,
                                     stdout=subprocess.PIPE,
                                     stdin=subprocess.PIPE)
            self.input = self.tmux.stdin
            self.output = self.tmux.stdout
        # starting a new session, delete any old requests we may have
        # in the queue (e.g. those added while trying to attach to
        # a nonexistant session)
        with self.requests.mutex:
            self.requests.queue.clear()

        self.requests.put(self.notifications_handler.pane_id_result)
        self.start_notifications_consumer()

    def refresh_client(self, width, height):
        dbg('{}::{}: {}x{}'.format("TmuxControl", "refresh_client", width, height))
        self.width = width
        self.height = height
        self._run_command('refresh-client -C {},{}'.format(width, height))

    def garbage_collect_panes(self):
        self._run_command('list-panes -s -t {} -F "#D {}"'.format(
            self.session_name, '#{pane_pid}'),
            callback=self.notifications_handler.garbage_collect_panes_result)

    def initial_layout(self):
        self._run_command(
            'list-windows -t {} -F "#{{window_layout}}"'
            .format(self.session_name),
            callback=self.notifications_handler.initial_layout_result)

    def initial_output(self, pane_id):
        self._run_command(
            'capture-pane -J -p -t {} -eC -S - -E -'.format(pane_id),
            callback=self.notifications_handler.initial_output_result_callback(
                pane_id))

    def toggle_zoom(self, pane_id, zoom=False):
        self.is_zoomed = not self.is_zoomed
        if not zoom:
            self._run_command('resize-pane -Z -x {} -y {} -t {}'.format(self.width, self.height, pane_id))

    def send_keypress(self, event, pane_id):
        keyval = event.keyval
        state = event.state

        if keyval in KEY_MAPPINGS:
            key = KEY_MAPPINGS[keyval]
            if keyval in ARROW_KEYS and state & Gdk.ModifierType.CONTROL_MASK:
                key = '{}1;5{}'.format(key[:2], key[2:])
        else:
            key = event.string

        if state & Gdk.ModifierType.MOD1_MASK:
            # Hack to have CTRL+SHIFT+Alt PageUp/PageDown/Home/End
            # work without these silly [... escaped characters
            if state & (Gdk.ModifierType.CONTROL_MASK |
                        Gdk.ModifierType.SHIFT_MASK):
                return
            else:
                key = esc(key)

        if key == ';':
            key = '\\;'

        self.send_content(key, pane_id)

    # Handle mouse scrolling events if the alternate_screen is visible
    # otherwise let Terminator handle all the mouse behavior
    def send_mousewheel(self, event, pane_id):
        SMOOTH_SCROLL_UP = event.direction == Gdk.ScrollDirection.SMOOTH and event.delta_y <= 0.
        SMOOTH_SCROLL_DOWN = event.direction == Gdk.ScrollDirection.SMOOTH and event.delta_y > 0.
        if SMOOTH_SCROLL_UP:
            wheel = MOUSE_WHEEL[Gdk.ScrollDirection.UP]
        elif SMOOTH_SCROLL_DOWN:
            wheel = MOUSE_WHEEL[Gdk.ScrollDirection.DOWN]
        else:
            wheel = MOUSE_WHEEL[event.direction]

        if self.alternate_on:
            self._run_command("send-keys -t {} {}".format(pane_id, wheel))
            return True
        return False

    def send_content(self, content, pane_id):
        key_name_lookup = "-l" if ESCAPE_CODE in content else ""
        quote = "'" if "'" not in content else '"'
        self._run_command("send-keys -t {} {} -- {}{}{}".format(
                pane_id, key_name_lookup, quote, content, quote))

    def send_quoted_content(self, content, pane_id):
        key_name_lookup = "-l" if ESCAPE_CODE in content else ""
        self._run_command("send-keys -t {} {} -- {}".format(
                pane_id, key_name_lookup, content))

    def _run_command(self, command, callback=None):
        if not self.input:
            dbg('No tmux connection. [command={}]'.format(command))
        else:
            try:
                self.input.write('{}\n'.format(command))
            except IOError:
                dbg("Tmux server has gone away.")
                return
            callback = callback or notifications.noop
            self.requests.put(callback)

    @staticmethod
    def kill_server():
        command = [TMUX_BINARY, 'kill-session', '-t', 'terminator']
        subprocess.call(command)

    def start_notifications_consumer(self):
        self.consumer = threading.Thread(target=self.consume_notifications)
        self.consumer.daemon = True
        self.consumer.start()

    def consume_notifications(self):
        handler = self.notifications_handler
        while True:
            try:
                if self.tmux.poll() is not None:
                    break
            except AttributeError as e:
                dbg("Tmux control instance was reset.")
                return
            line = self.output.readline()[:-1]
            if not line:
                continue
            line = line[1:].split(' ')
            marker = line[0]
            line = line[1:]
            # skip MOTD, anything that isn't coming from tmux control mode
            try:
                notification = notifications.notifications_mappings[marker]()
            except KeyError:
                dbg("Discarding invalid output from the control terminal.")
                continue
            notification.consume(line, self.output)
            handler.handle(notification)
        handler.terminate()

    def display_pane_tty(self, pane_id):
        tmux_command = 'display -pt "{}" "#D {}"'.format(
            pane_id, "#{pane_tty}")

        self._run_command(tmux_command,
                callback=self.notifications_handler.pane_tty_result)

    def resize_pane(self, pane_id, rows, cols):
        if self.is_zoomed:
            # if the pane is zoomed, there is no need for tmux to
            # change the current layout
            return
        tmux_command = 'resize-pane -t "{}" -x {} -y {}'.format(
            pane_id, cols, rows)

        self._run_command(tmux_command)
