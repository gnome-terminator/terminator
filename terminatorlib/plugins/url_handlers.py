# Terminator by Chris Jones <cmsj@tenshu.net?
# GPL v2 only
"""url_handlers.py - Default plugins for URL handling"""
import re
import plugin

# Every plugin you want Terminator to load *must* be listed in 'available'
available = ['LaunchpadBugURLHandler', 'LaunchpadCodeURLHandler', 'APTURLHandler']

class URLHandler(plugin.Plugin):
    """Base class for URL handlers"""
    capabilities = ['url_handler']
    handler_name = None
    match = None

    def callback(self, url):
        """Callback to transform the enclosed URL"""
        raise NotImplementedError

class LaunchpadBugURLHandler(URLHandler):
    """Launchpad Bug URL handler. If the URL looks like a Launchpad changelog
    closure entry... 'LP: #12345' then it should be transformed into a 
    Launchpad Bug URL"""
    capabilities = ['url_handler']
    handler_name = 'launchpad_bug'
    match = '\\b(lp|LP):?\s?#?[0-9]+(,\s*#?[0-9]+)*\\b'

    def callback(self, url):
        """Look for the number in the supplied string and return it as a URL"""
        for item in re.findall(r'[0-9]+', url):
            url = 'https://bugs.launchpad.net/bugs/%s' % item
            return(url)

class LaunchpadCodeURLHandler(URLHandler):
    """Launchpad Code URL handler. If the URL looks like a Launchpad project or
    branch entry then it should be transformed into a code.launchpad.net URL"""
    capabilities = ['url_handler']
    handler_name = 'launchpad_code'
    lpfilters = {}
    lpfilters['project'] = '[a-z0-9]{1}[a-z0-9\.\-\+]+'
    lpfilters['group'] = '~%s' % lpfilters['project']
    lpfilters['series'] = lpfilters['project']
    lpfilters['branch'] = '[a-zA-Z0-9]{1}[a-zA-Z0-9_+@.-]+'

    match = '\\b((lp|LP):%(project)s(/%(series)s)?|(lp|LP):%(group)s/(%(project)s|\+junk)/%(branch)s)\\b' % lpfilters

    def callback(self, url):
        """Look for the number in the supplied string and return it as a URL"""
        if url.startswith('lp:'):
            url = url[3:]
        return('https://code.launchpad.net/+branch/%s' % url)

class APTURLHandler(URLHandler):
    """APT URL handler. If there is a URL that looks like an apturl, handle
    it appropriately"""
    capabilities = ['url_handler']
    handler_name = 'apturl'
    match = '\\bapt:.*\\b'

    def callback(self, url):
        """Actually we don't need to do anything for this to work"""
        return(url)

