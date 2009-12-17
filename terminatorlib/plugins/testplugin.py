import plugin

# available must contain a list of all the classes that you want exposed
available = ['TestPlugin']

class TestPlugin(plugin.Plugin):
    capabilities = ['test']

    def do_test(self):
        return('TestPluginWin')

