#  Terminator.optionparse - Parse commandline options
#  Copyright (C) 2006-2010  cmsj@tenshu.net
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, version 2 only.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA
"""Terminator.optionparse - Parse commandline options"""

import argparse
import sys
import os

from terminatorlib.terminator import Terminator
from .util import dbg, err
from . import util
from . import config
from . import version
from .translation import _

options = None

class ExecuteCallback(argparse.Action):
    def __call__(self, lparser, namespace, values, option_string=None):
        """Callback for use in parsing execute options"""
        setattr(namespace, self.dest, values)

def parse_options():
    """Parse the command line options"""
    is_x_terminal_emulator = os.path.basename(sys.argv[0]) == 'x-terminal-emulator'

    parser = argparse.ArgumentParser()

    parser.add_argument('-v', '--version', action='store_true', dest='version',
            help=_('Display program version'))
    parser.add_argument('-m', '--maximise', action='store_true', dest='maximise',
            help=_('Maximize the window'))
    parser.add_argument('-M', '--maximize', action='store_true', dest='maximise',
            help=_('Maximize the window'))
    parser.add_argument('-f', '--fullscreen', action='store_true',
            dest='fullscreen', help=_('Make the window fill the screen'))
    parser.add_argument('-b', '--borderless', action='store_true',
            dest='borderless', help=_('Disable window borders'))
    parser.add_argument('-H', '--hidden', action='store_true', dest='hidden',
            help=_('Hide the window at startup'))
    parser.add_argument('-T', '--title', dest='forcedtitle',
                      help=_('Specify a title for the window'))
    parser.add_argument('--geometry', dest='geometry', type=str,
                      help=_('Set the preferred size and position of the window'
                             '(see X man page)'))
    if not is_x_terminal_emulator:
        parser.add_argument('-e', '--command', dest='command',
                help=_('Specify a command to execute inside the terminal'))
    else:
        parser.add_argument('--command', dest='command',
                help=_('Specify a command to execute inside the terminal'))
        parser.add_argument('-e', '--execute2', dest='execute',
                nargs=argparse.REMAINDER, action=ExecuteCallback,
                help=_('Use the rest of the command line as a command to '
                       'execute inside the terminal, and its arguments'))
    parser.add_argument('-g', '--config', dest='config',
                      help=_('Specify a config file'))
    parser.add_argument('-j', '--config-json', dest='configjson',
                      help=_('Specify a partial config json file'))
    parser.add_argument('-x', '--execute', dest='execute',
            nargs=argparse.REMAINDER, action=ExecuteCallback,
            help=_('Use the rest of the command line as a command to execute '
                   'inside the terminal, and its arguments'))
    parser.add_argument('--working-directory', metavar='DIR',
            dest='working_directory', help=_('Set the working directory'))
    parser.add_argument('-i', '--icon', dest='forcedicon', help=_('Set a custom \
icon for the window (by file or name)'))
    parser.add_argument('-r', '--role', dest='role',
            help=_('Set a custom WM_WINDOW_ROLE property on the window'))
    parser.add_argument('-l', '--layout', dest='layout',
            help=_('Launch with the given layout'))
    parser.add_argument('-s', '--select-layout', action='store_true',
            dest='select', help=_('Select a layout from a list'))
    parser.add_argument('-p', '--profile', dest='profile',
            help=_('Use a different profile as the default'))
    parser.add_argument('-u', '--no-dbus', action='store_true', dest='nodbus',
            help=_('Disable DBus'))
    parser.add_argument('-d', '--debug', action='count', dest='debug',
            help=_('Enable debugging information (twice for debug server)'))
    parser.add_argument('--debug-classes', action='store', dest='debug_classes',
            help=_('Comma separated list of classes to limit debugging to'))
    parser.add_argument('--debug-methods', action='store', dest='debug_methods',
            help=_('Comma separated list of methods to limit debugging to'))
    parser.add_argument('--new-tab', action='store_true', dest='new_tab',
            help=_('If Terminator is already running, just open a new tab'))
    parser.add_argument('--unhide', action='store_true', dest='unhide',
            help=_('If Terminator is already running, just unhide all hidden windows'))
    parser.add_argument('--list-profiles', action='store_true', dest='list_profiles',
            help=_('List all profiles'))
    parser.add_argument('--list-layouts', action='store_true', dest='list_layouts',
            help=_('List all layouts'))

    for item in ['--sm-client-id', '--sm-config-prefix', '--screen', '-n',
                 '--no-gconf' ]:
        parser.add_argument(item, dest='dummy', action='store',
                help=argparse.SUPPRESS)

    global options
    options = parser.parse_args()

    if options.version:
        print('%s %s' % (version.APP_NAME, version.APP_VERSION))
        sys.exit(0)

    if options.list_profiles:
        for p in Terminator().config.list_profiles():
            print(p)
        sys.exit(0)
    if options.list_layouts:
        for l in Terminator().config.list_layouts():
            print(l)
        sys.exit(0)

    if options.debug_classes or options.debug_methods:
        if not options.debug > 0:
            options.debug = 1

    if options.debug:
        util.DEBUG = True
        if options.debug > 1:
            util.DEBUGFILES = True
        if options.debug_classes:
            classes = options.debug_classes.split(',')
            for item in classes:
                util.DEBUGCLASSES.append(item.strip())
        if options.debug_methods:
            methods = options.debug_methods.split(',')
            for item in methods:
                util.DEBUGMETHODS.append(item.strip())

    if options.working_directory:
        if os.path.exists(os.path.expanduser(options.working_directory)):
            options.working_directory = os.path.expanduser(options.working_directory)
            os.chdir(options.working_directory)
        else:
            err('OptionParse::parse_options: %s does not exist' %
                    options.working_directory)
            options.working_directory = ''

    if options.layout is None:
        options.layout = 'default'

    configobj = config.Config()
    if options.profile and options.profile not in configobj.list_profiles():
        options.profile = None

    configobj.options_set(options)

    optionslist = {}
    for opt, val in list(options.__dict__.items()):
        if type(val) == type([]):
            val = ' '.join(val)
        if val == True:
            val = 'True'
        optionslist[opt] = val and '%s'%val or ''
    # optionslist = dbus.Dictionary(optionslist, signature='ss')
    if util.DEBUG == True:
        dbg('command line options: %s' % options)

    return(options,optionslist)
