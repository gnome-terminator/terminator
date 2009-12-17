import plugin

available = ['LaunchpadURLHandler']

class LaunchpadURLHandler(plugin.Plugin):
    capabilities = ['url_handler']

    def do_test(self):
        return "Launchpad blah"
