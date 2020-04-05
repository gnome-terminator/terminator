#!/bin/bash

for file in *.py; do
  line=$(pylint $file 2>&1 | grep "^Your code has been rated")
  rating=$(echo $line | cut -f 7 -d ' ')
  previous=$(echo $line | cut -f 10 -d ' ')

  if [ "$rating" != "10.00/10" ]; then
    echo "$file rated $rating (previously $previous)"
  fi
done
