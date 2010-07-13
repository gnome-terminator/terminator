import terminatorlib.plugin as plugin

# AVAILABLE must contain a list of all the classes that you want exposed
AVAILABLE = ['TestPlugin']

class TestPlugin(plugin.Plugin):
    capabilities = ['test']

    def do_test(self):
        return('TestPluginWin')

