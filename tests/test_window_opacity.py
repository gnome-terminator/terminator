from types import SimpleNamespace
from xml.etree import ElementTree

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Vte", "2.91")
from gi.repository import Gdk, Vte

from terminatorlib.config import DEFAULTS
from terminatorlib.terminal import Terminal
from terminatorlib.terminator import Terminator


class FakeConfig(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.save_count = 0

    def save(self):
        self.save_count += 1


class FakeWindow:
    def __init__(self):
        self.opacities = []

    def set_opacity(self, opacity):
        self.opacities.append(opacity)


class FakeVte:
    def __init__(self):
        self.opacities = []

    def set_opacity(self, opacity):
        self.opacities.append(opacity)


def make_terminator(first=30, second=100, mode=1, text=100):
    terminator = Terminator.__new__(Terminator)
    terminator.config = FakeConfig(
        window_opacity=first,
        window_opacity_alt=second,
        text_opacity=text,
    )
    terminator.windows = [FakeWindow(), FakeWindow()]
    terminator.terminals = [SimpleNamespace(vte=FakeVte()),
                            SimpleNamespace(vte=FakeVte())]
    terminator.window_opacity_mode = mode
    return terminator


def test_default_opacity_modes_are_thirty_and_one_hundred_percent():
    global_config = DEFAULTS["global_config"]
    assert global_config["window_opacity"] == 30
    assert global_config["window_opacity_alt"] == 100
    assert global_config["text_opacity"] == 100


def test_toggle_cycles_between_both_opacity_modes_for_all_windows():
    terminator = make_terminator()

    terminator.toggle_all_window_opacity()
    assert terminator.window_opacity_mode == 0
    assert [window.opacities[-1] for window in terminator.windows] == [0.3, 0.3]

    terminator.toggle_all_window_opacity()
    assert terminator.window_opacity_mode == 1
    assert [window.opacities[-1] for window in terminator.windows] == [1.0, 1.0]
    assert terminator.get_window_opacity() == 1.0


def test_adjust_updates_only_current_mode_saves_and_clamps():
    terminator = make_terminator(first=30, second=95, mode=1)

    assert terminator.adjust_window_opacity(5) is True
    assert terminator.config["window_opacity"] == 30
    assert terminator.config["window_opacity_alt"] == 100
    assert terminator.config.save_count == 1
    assert [window.opacities[-1] for window in terminator.windows] == [1.0, 1.0]

    assert terminator.adjust_window_opacity(5) is False
    assert terminator.config.save_count == 1

    terminator.window_opacity_mode = 0
    terminator.config["window_opacity"] = 10
    assert terminator.adjust_window_opacity(-5) is False
    assert terminator.config.save_count == 1


def test_adjust_text_opacity_updates_all_terminals_saves_and_clamps():
    terminator = make_terminator(text=95)

    assert terminator.adjust_text_opacity(5) is True
    assert terminator.config["text_opacity"] == 100
    assert terminator.config.save_count == 1
    assert [terminal.vte.opacities[-1]
            for terminal in terminator.terminals] == [1.0, 1.0]

    assert terminator.adjust_text_opacity(5) is False
    assert terminator.config.save_count == 1

    terminator.config["text_opacity"] = 10
    assert terminator.adjust_text_opacity(-5) is False
    assert terminator.config.save_count == 1


def test_alt_mousewheel_adjusts_by_five_percent():
    adjustments = []
    fake_terminal = SimpleNamespace(
        terminator=SimpleNamespace(
            adjust_window_opacity=lambda delta: adjustments.append(delta)
        )
    )

    up = SimpleNamespace(
        direction=Gdk.ScrollDirection.UP,
        delta_y=0,
        state=Gdk.ModifierType.MOD1_MASK,
    )
    down = SimpleNamespace(
        direction=Gdk.ScrollDirection.SMOOTH,
        delta_y=1,
        state=Gdk.ModifierType.MOD1_MASK,
    )

    assert Terminal.on_mousewheel(fake_terminal, None, up) is True
    assert Terminal.on_mousewheel(fake_terminal, None, down) is True
    assert adjustments == [5, -5]


def test_control_alt_mousewheel_adjusts_text_not_window_opacity():
    window_adjustments = []
    text_adjustments = []
    fake_terminal = SimpleNamespace(
        config={"disable_mousewheel_zoom": True},
        terminator=SimpleNamespace(
            adjust_window_opacity=lambda delta: window_adjustments.append(delta),
            adjust_text_opacity=lambda delta: text_adjustments.append(delta),
        ),
    )
    event = SimpleNamespace(
        direction=Gdk.ScrollDirection.UP,
        delta_y=0,
        state=(Gdk.ModifierType.MOD1_MASK |
               Gdk.ModifierType.CONTROL_MASK),
    )

    assert Terminal.on_mousewheel(fake_terminal, None, event) is True
    assert window_adjustments == []
    assert text_adjustments == [5]


def test_terminal_content_layer_keeps_vte_as_sizing_child():
    fake_terminal = SimpleNamespace(
        vte=Vte.Terminal(),
        background_draw=lambda _widget, _context: False,
    )

    terminalbox = Terminal.create_terminalbox(fake_terminal)

    assert fake_terminal.vte.get_parent() is fake_terminal.terminalcontent
    assert fake_terminal.terminalcontent.get_parent() is terminalbox
    assert terminalbox.get_children()[0] is fake_terminal.terminalcontent
    assert terminalbox.get_preferred_width()[1] >= \
        fake_terminal.vte.get_preferred_width()[1]


def test_opacity_controls_are_in_appearance_not_behavior_grid():
    root = ElementTree.parse("terminatorlib/preferences.glade").getroot()
    behavior = root.find(".//object[@id='grid1']")
    appearance = root.find(".//object[@id='grid3']")
    opacity_ids = {
        "window_opacity_label",
        "window_opacity_spinbutton",
        "window_opacity_alt_label",
        "window_opacity_alt_spinbutton",
        "text_opacity_label",
        "text_opacity_spinbutton",
    }

    behavior_ids = {node.get("id") for node in behavior.iter("object")}
    appearance_ids = {node.get("id") for node in appearance.iter("object")}
    assert opacity_ids.isdisjoint(behavior_ids)
    assert opacity_ids <= appearance_ids
