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
    """Maven plugin handler. If the name of a Maven plugin is
    detected, it is turned into a link to its documentation site.
    If a Maven plugin goal is detected, the link points to the
    particular goal page. Only Apache (org.apache.maven.plugins)
    and Codehaus (org.codehaus.mojo) plugins are supported."""

    capabilities = ['url_handler']
    handler_name = 'maven_plugin'

    maven_filters = {}
    maven_filters['apache_maven_plugin_shortname'] = 'clean|compiler|deploy|failsafe|install|resources|site|surefire|verifier|ear|ejb|jar|rar|war|shade|changelog|changes|checkstyle|clover|doap|docck|javadoc|jxr|linkcheck|pmd|project-info-reports|surefire-report|ant|antrun|archetype|assembly|dependency|enforcer|gpg|help|invoker|jarsigner|one|patch|pdf|plugin|release|reactor|remote-resources|repository|scm|source|stage|toolchains|eclipse|idea'
    maven_filters['codehaus_maven_plugin_shortname'] = 'jboss|jboss-packaging|tomcat|was6|antlr|antlr3|aspectj|axistools|castor|commons-attributes|gwt|hibernate3|idlj|javacc|jaxb2|jpox|jspc|openjpa|rmic|sablecc|sqlj|sysdeo-tomcat|xmlbeans|xdoclet|netbeans-freeform|nbm|clirr|cobertura|taglist|scmchangelog|findbugs|fitnesse|selenium|animal-sniffer|appassembler|build-helper|exec|keytool|latex|ounce|rpm|sql|versions|apt|cbuilds|jspc|native|retrotranslator|springws|smc|ideauidesigner|dita|docbook|javancss|jdepend|dashboard|emma|sonar|jruby|dbunit|shitty|batik|buildnumber|ianal|jalopy|jasperreports|l10n|minijar|native2ascii|osxappbundle|properties|solaris|truezip|unix|virtualization|wagon|webstart|xml|argouml|dbupgrade|chronos|ckjm|codenarc|deb|ec2|enchanter|ejbdoclet|graphing|j2me|javascript tools|jardiff|kodo|macker|springbeandoc|mock-repository|nsis|pomtools|setup|simian-report|syslog|visibroker|weblogic|webdoclet|xjc|xsltc'
    maven_filters['apache_maven_plugin_artifact_id'] = 'maven\-(%(apache_maven_plugin_shortname)s)\-plugin' % maven_filters
    maven_filters['codehaus_maven_plugin_artifact_id'] = '(%(codehaus_maven_plugin_shortname)s)\-maven\-plugin' % maven_filters
    maven_filters['maven_plugin_version'] = '[a-zA-Z0-9\.-]+'
    maven_filters['maven_plugin_goal'] = '[a-zA-Z-]+'
    maven_filters['maven_plugin'] = '(%(apache_maven_plugin_artifact_id)s|%(codehaus_maven_plugin_artifact_id)s)(:%(maven_plugin_version)s:%(maven_plugin_goal)s)?' % maven_filters
    maven_filters['maven_plugin_named_groups'] = '(?P<artifact_id>%(apache_maven_plugin_artifact_id)s|%(codehaus_maven_plugin_artifact_id)s)(:%(maven_plugin_version)s:(?P<goal>%(maven_plugin_goal)s))?' % maven_filters

    match = '\\b%(maven_plugin)s\\b' % maven_filters

    def callback(self, url):
        matches = re.match(MavenPluginURLHandler.maven_filters['maven_plugin_named_groups'], url)
        if matches is not None:
            artifactid = matches.group('artifact_id')
            goal = matches.group('goal')
            if artifactid is not None:
                if re.match(MavenPluginURLHandler.maven_filters['apache_maven_plugin_artifact_id'], artifactid):
                    if goal is not None:
                        return 'http://maven.apache.org/plugins/%s/%s-mojo.html' % ( artifactid, goal)
                    else:
                        return 'http://maven.apache.org/plugins/%s' % artifactid
                elif re.match(MavenPluginURLHandler.maven_filters['codehaus_maven_plugin_artifact_id'], artifactid):
                    if goal is not None:
                        return 'http://mojo.codehaus.org/%s/%s-mojo.html' % ( artifactid, goal)
                    else:
                        return 'http://mojo.codehaus.org/%s' % artifactid

        plugin.err("Wrong match '%s' for MavenPluginURLHandler." % url)
        return ''
