#!/bin/sh
# Make translation files
xgettext -L python -o po/terminator.pot terminator terminatorlib/*.py data/terminator.desktop.in
