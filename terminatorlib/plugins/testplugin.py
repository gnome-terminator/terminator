import plugin

class TestPlugin(plugin.Plugin):
    capabilities = ['test']

    def do_test(self):
        return('TestPluginWin')

