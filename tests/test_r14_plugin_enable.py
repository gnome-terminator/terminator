"""r14-4: a second enable() must not construct another plugin instance."""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Vte', '2.91')

from terminatorlib.plugin import PluginRegistry

_NAME = '__r14_fake__'


class _Fake(object):
    inits = 0
    unloads = 0

    def __init__(self):
        _Fake.inits += 1

    def unload(self):
        _Fake.unloads += 1


def test_enable_twice_keeps_the_same_instance():
    _Fake.inits = 0
    _Fake.unloads = 0
    registry = PluginRegistry()
    registry.available_plugins[_NAME] = _Fake
    try:
        registry.enable(_NAME)
        first = registry.instances[_NAME]
        registry.enable(_NAME)
        assert registry.instances[_NAME] is first
        assert _Fake.inits == 1
        assert _Fake.unloads == 0
    finally:
        registry.instances.pop(_NAME, None)
        registry.available_plugins.pop(_NAME, None)
