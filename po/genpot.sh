#!/bin/sh
# Stupid workaround for intltools not handling extensionless files
ln -s terminator ../terminator.py
ln -s remotinator ../remotinator.py

# Make translation files
xgettext --default-domain=terminator --files-from=POTFILES.in --from-code=UTF-8 \
	--directory=..

# Cleanup after stupid workaround
rm ../terminator.py
rm ../remotinator.py
