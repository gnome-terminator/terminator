#!/bin/bash

for file in *.py; do
  echo -n "$file: "
  pylint $file 2>&1 | grep "^Your code has been rated"
done
