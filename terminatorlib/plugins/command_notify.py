"""
This plugin will launch a notification when a long running command finishes
and terminal is not active.

It uses VTE's special sequence which is sent when shell prints the prompt. It
depends on https://github.com/GNOME/vte/blob/vte-0-58/src/vte.sh (which has to
be added to /etc/profile.d) and you need to ensure `__vte_prompt_command` is
executed on `PROMPT_COMMAND` in Bash or in `precmd_functions` in Zsh.

Code is written in Hy and generated to Python3.
"""
import terminatorlib.plugin as plugin
from terminatorlib.terminator import Terminator
import gi
gi.require_version('Notify', '0.7')
from gi.repository import GObject, GLib, Notify
VERSION = '0.1.0'
AVAILABLE = ['LongCommandNotify']


class LongCommandNotify(plugin.Plugin):
    capabilities = ['command_watch']
    watched = set()

    def __init__(self):
        self.update_watched()
        Notify.init('Terminator')
        return None

    def update_watched(self):
        """Updates the list of watched terminals"""
        new_watched = set()
        for term in Terminator().terminals:
            new_watched.add(term)
            if not term in self.watched:
                vte = term.get_vte()
                term.connect('focus-out', self.update_watched_delayed, None)
                vte.connect('focus-out-event', self.
                    update_watched_delayed, None)
                notify = vte.connect(
                    'notification-received', self.notification_received, term)
            else:
                notify = None
        self.watched = new_watched

    def update_watched_delayed(self):

        def add_watch(self):
            self.update_watched()
            return False
        GObject.idle_add(add_watch, self)
        return True

    def notification_received(self, vte, summary, body, _terminator_term):
        Notify.Notification.new(summary, body, 'terminator').show(
            ) if not vte.has_focus() else None
        return None

