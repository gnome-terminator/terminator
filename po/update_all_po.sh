#!/bin/sh
# Update translation files
for po_file in `ls *.po`; do
  msgmerge -N -U ${po_file} terminator.pot
done
