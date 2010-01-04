#!/usr/bin/python
#    Terminator.optionparse - Parse commandline options
#    Copyright (C) 2006-2008  cmsj@tenshu.net
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

    configobj = config.Config()
    parser = OptionParser(usage)

    parser.add_option('-v', '--version', action='store_true', dest='version',
            help='Display program version')
    parser.add_option('-d', '--debug', action='count', dest='debug',
            help='Enable debugging information (twice for debug server)')
    parser.add_option('-m', '--maximise', action='store_true', dest='maximise',
            help='Maximise the window')
    parser.add_option('-f', '--fullscreen', action='store_true',
            dest='fullscreen', help='Make the window fill the screen')
    parser.add_option('-b', '--borderless', action='store_true',
            dest='borderless', help='Disable window borders')
    parser.add_option('-H', '--hidden', action='store_true', dest='hidden',
            help='Hide the window at startup')
    parser.add_option('-T', '--title', dest='forcedtitle', help='Specify a \
title for the window')
    parser.add_option('--geometry', dest='geometry', type='string', help='Set \
the preferred size and position of the window (see X man page)')
    parser.add_option('-e', '--command', dest='command', help='Specify a \
command to execute inside the terminal')
    parser.add_option('-x', '--execute', dest='execute', action='callback',
            callback=execute_cb, help='Use the rest of the command line as a \
command to execute inside the terminal, and its arguments')
    parser.add_option('--working-directory', metavar='DIR',
            dest='working_directory', help='Set the working directory')
    parser.add_option('-r', '--role', dest='role', help='Set a custom \
WM_WINDOW_ROLE property on the window')
    for item in ['--sm-client-id', '--sm-config-prefix', '--screen']:
        parser.add_option(item, dest='dummy', action='store',
                help=SUPPRESS_HELP)

    (options, args) = parser.parse_args()
    if len(args) != 0:
        parser.error('Additional unexpected arguments found: %s' % args)

    if options.version:
        print '%s %s' % (version.APP_NAME, version.APP_VERSION)
        sys.exit(0)
    
    if options.debug:
        util.DEBUG = True

    if options.working_directory:
        if os.path.exists(os.path.expanduser(options.working_directory)):
            os.chdir(os.path.expanduser(options.working_directory))
        else:
            err('OptionParse::parse_options: %s does not exist' %
                    options.working_directory)
            sys.exit(1)

    if options.maximise:
        configobj['maximise'] = True

    # FIXME: Map all the other bits of options to configobj

    if util.DEBUG == True:
        dbg('OptionParse::parse_options: options dump: %s' % options)

    return(options)
