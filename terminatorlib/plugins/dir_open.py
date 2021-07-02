from gi.repository import Gtk

from terminatorlib.config import Config
from terminatorlib.terminal import Terminal
from terminatorlib.translation import _
import terminatorlib.plugin as plugin

AVAILABLE = ['CurrDirOpen']


class CurrDirOpen(plugin.MenuItem):
    capabilities = ['terminal_menu']
    config = None

    def __init__(self):
        self.cwd = ""
        self.terminal = None

    def _on_menu_item_add_tag_activate(self, menu_item_add_tag):
        self.terminal.open_url("file://" + self.cwd)

    def callback(self, menuitems, menu, terminal):
        self.cwd = terminal.get_cwd()
        self.terminal = terminal

        menuitem = Gtk.ImageMenuItem(_('Open current directory'))
        image = Gtk.Image()
        image.set_from_icon_name('folder', Gtk.IconSize.MENU)
        menuitem.set_image(image)
        menuitem.set_always_show_image(True)
        menuitem.connect("activate", self._on_menu_item_add_tag_activate)

        menuitems.append(menuitem)
