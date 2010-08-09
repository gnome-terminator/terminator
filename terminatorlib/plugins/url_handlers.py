# Terminator by Chris Jones <cmsj@tenshu.net?
# GPL v2 only
"""url_handlers.py - Default plugins for URL handling"""
import re
import terminatorlib.plugin as plugin

# Every plugin you want Terminator to load *must* be listed in 'AVAILABLE'
AVAILABLE = ['LaunchpadBugURLHandler', 'LaunchpadCodeURLHandler', 'APTURLHandler', 'MavenPluginURLHandler']

class LaunchpadBugURLHandler(plugin.URLHandler):
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

class LaunchpadCodeURLHandler(plugin.URLHandler):
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

class APTURLHandler(plugin.URLHandler):
    """APT URL handler. If there is a URL that looks like an apturl, handle
    it appropriately"""
    capabilities = ['url_handler']
    handler_name = 'apturl'
    match = '\\bapt:.*\\b'

    def callback(self, url):
        """Actually we don't need to do anything for this to work"""
        return(url)

class MavenPluginURLHandler(plugin.URLHandler):
    """Maven plugin handler. If there is the name of a Maven plugin, link
    to its documentation site."""
    
    capabilities = ['url_handler']
    handler_name = 'maven_plugin'
    mavenfilters = {}
    mavenfilters['apache_maven_plugins'] = 'clean|compiler|deploy|failsafe|install|resources|site|surefire|verifier|ear|ejb|jar|rar|war|shade|changelog|changes|checkstyle|clover|doap|docck|javadoc|jxr|linkcheck|pmd|project-info-reports|surefire-report|ant|antrun|archetype|assembly|dependency|enforcer|gpg|help|invoker|jarsigner|one|patch|pdf|plugin|release|reactor|remote-resources|repository|scm|source|stage|toolchains|IDEs|eclipse|idea'
    
    match = '\\b(maven-(%(apache_maven_plugins)s)-plugin)\\b' % mavenfilters

    def callback(self, url):
        return('http://maven.apache.org/plugins/%s' % url)
