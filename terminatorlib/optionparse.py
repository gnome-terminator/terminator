#!/usr/bin/python
#    Terminator.optionparse - Parse commandline options
#    Copyright (C) 2006-2010  cmsj@tenshu.net
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

import sys
import os

from optparse import OptionParser, SUPPRESS_HELP
from util import dbg, err
import util
import config
import version
from translation import _

options = None

def execute_cb(option, opt, value, lparser):
    """Callback for use in parsing execute options"""
    assert value is None
    value = []
    while lparser.rargs:
        arg = lparser.rargs[0]
        value.append(arg)
        del(lparser.rargs[0])
    setattr(lparser.values, option.dest, value)

def parse_options():
    """Parse the command line options"""
    usage = "usage: %prog [options]"

    is_x_terminal_emulator = os.path.basename(sys.argv[0]) == 'x-terminal-emulator'

    parser = OptionParser(usage)

    parser.add_option('-v', '--version', action='store_true', dest='version',
            help=_('Display program version'))
    parser.add_option('-m', '--maximise', action='store_true', dest='maximise',
            help=_('Maximise the window'))
    parser.add_option('-f', '--fullscreen', action='store_true',
            dest='fullscreen', help=_('Make the window fill the screen'))
    parser.add_option('-b', '--borderless', action='store_true',
            dest='borderless', help=_('Disable window borders'))
    parser.add_option('-H', '--hidden', action='store_true', dest='hidden',
            help=_('Hide the window at startup'))
    parser.add_option('-T', '--title', dest='forcedtitle', 
                      help=_('Specify a title for the window'))
    parser.add_option('--geometry', dest='geometry', type='string', 
                      help=_('Set the preferred size and position of the window'
                             '(see X man page)'))
    if not is_x_terminal_emulator:
        parser.add_option('-e', '--command', dest='command', 
                help=_('Specify a command to execute inside the terminal'))
    else:
        parser.add_option('--command', dest='command', 
                help=_('Specify a command to execute inside the terminal'))
        parser.add_option('-e', '--execute2', dest='execute', action='callback',
                callback=execute_cb, 
                help=_('Use the rest of the command line as a command to '
                       'execute inside the terminal, and its arguments'))
    parser.add_option('-g', '--config', dest='config', 
                      help=_('Specify a config file'))
    parser.add_option('-x', '--execute', dest='execute', action='callback',
            callback=execute_cb, 
            help=_('Use the rest of the command line as a command to execute '
                   'inside the terminal, and its arguments'))
    parser.add_option('--working-directory', metavar='DIR',
            dest='working_directory', help=_('Set the working directory'))
    parser.add_option('-c', '--classname', dest='classname', help=_('Set a \
custom name (WM_CLASS) property on the window'))
    parser.add_option('-i', '--icon', dest='forcedicon', help=_('Set a custom \
icon for the window (by file or name)'))
    parser.add_option('-r', '--role', dest='role', 
            help=_('Set a custom WM_WINDOW_ROLE property on the window'))
    parser.add_option('-l', '--layout', dest='layout', 
            help=_('Launch with the given layout'))
    parser.add_option('-s', '--select-layout', action='store_true',
            dest='select', help=_('Select a layout from a list'))
    parser.add_option('-p', '--profile', dest='profile', 
            help=_('Use a different profile as the default'))
    parser.add_option('-u', '--no-dbus', action='store_true', dest='nodbus', 
            help=_('Disable DBus'))
    parser.add_option('-d', '--debug', action='count', dest='debug',
            help=_('Enable debugging information (twice for debug server)'))
    parser.add_option('--debug-classes', action='store', dest='debug_classes', 
            help=_('Comma separated list of classes to limit debugging to'))
    parser.add_option('--debug-methods', action='store', dest='debug_methods',
            help=_('Comma separated list of methods to limit debugging to'))
    parser.add_option('--new-tab', action='store_true', dest='new_tab',
            help=_('If Terminator is already running, just open a new tab'))
    for item in ['--sm-client-id', '--sm-config-prefix', '--screen', '-n',
                 '--no-gconf' ]:
        parser.add_option(item, dest='dummy', action='store',
                help=SUPPRESS_HELP)

    global options
    (options, args) = parser.parse_args()
    if len(args) != 0:
        parser.error('Additional unexpected arguments found: %s' % args)

    if options.version:
        print '%s %s' % (version.APP_NAME, version.APP_VERSION)
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
            os.chdir(os.path.expanduser(options.working_directory))
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

    if util.DEBUG == True:
        dbg('OptionParse::parse_options: command line options: %s' % options)

    return(options)
