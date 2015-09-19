#!/bin/sh
# Stupid workaround for intltools not handling extensionless files
ln -s terminator ../terminator.py
ln -s remotinator ../remotinator.py

# Make translation files
intltool-update -g terminator -o terminator.pot -p

# Cleanup after stupid workaround
rm ../terminator.py
rm ../remotinator.py
