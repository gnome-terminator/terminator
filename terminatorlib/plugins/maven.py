# Copyright (c) 2010 Julien Nicoulaud <julien.nicoulaud@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 2 only.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor
# , Boston, MA  02110-1301  USA
import re
import terminatorlib.plugin as plugin

AVAILABLE = [ 'MavenPluginURLHandler' ]

class MavenPluginURLHandler(plugin.URLHandler):
    """Maven plugin handler. If there is the name of a Maven plugin, link
    to its documentation site."""

    capabilities = ['url_handler']
    handler_name = 'maven_plugin'
    mavenfilters = {}
    mavenfilters['apache_maven_plugins'] = 'clean|compiler|deploy|failsafe|install|resources|site|surefire|verifier|ear|ejb|jar|rar|war|shade|changelog|changes|checkstyle|clover|doap|docck|javadoc|jxr|linkcheck|pmd|project-info-reports|surefire-report|ant|antrun|archetype|assembly|dependency|enforcer|gpg|help|invoker|jarsigner|one|patch|pdf|plugin|release|reactor|remote-resources|repository|scm|source|stage|toolchains|eclipse|idea'
    mavenfilters['codehaus_maven_plugins'] = 'jboss|jboss-packaging|tomcat|was6|antlr|antlr3|aspectj|axistools|castor|commons-attributes|gwt|hibernate3|idlj|javacc|jaxb2|jpox|jspc|openjpa|rmic|sablecc|sqlj|sysdeo-tomcat|xmlbeans|xdoclet|netbeans-freeform|nbm|clirr|cobertura|taglist|scmchangelog|findbugs|fitnesse|selenium|animal-sniffer|appassembler|build-helper|exec|keytool|latex|ounce|rpm|sql|versions|apt|cbuilds|jspc|native|retrotranslator|springws|smc|ideauidesigner|dita|docbook|javancss|jdepend|dashboard|emma|sonar|jruby|dbunit|shitty|batik|buildnumber|ianal|jalopy|jasperreports|l10n|minijar|native2ascii|osxappbundle|properties|solaris|truezip|unix|virtualization|wagon|webstart|xml|argouml|dbupgrade|chronos|ckjm|codenarc|deb|ec2|enchanter|ejbdoclet|graphing|j2me|javascript tools|jardiff|kodo|macker|springbeandoc|mock-repository|nsis|pomtools|setup|simian-report|syslog|visibroker|weblogic|webdoclet|xjc|xsltc'
    mavenfilters['apache_maven_plugin_name'] = 'maven\-(%s)\-plugin' % mavenfilters['apache_maven_plugins']
    mavenfilters['codehaus_maven_plugin_name'] = '(%s)\-maven\-plugin' % mavenfilters['codehaus_maven_plugins']

    match = '\\b(%(apache_maven_plugin_name)s|%(codehaus_maven_plugin_name)s)\\b' % mavenfilters

    def callback(self, url):
        if re.match(self.mavenfilters["apache_maven_plugin_name"],url):
            return('http://maven.apache.org/plugins/%s' % url)
        if re.match(self.mavenfilters["codehaus_maven_plugin_name"],url):
            return('http://mojo.codehaus.org/%s' % url)
