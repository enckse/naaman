#!/bin/bash
for options in $(cat naaman.conf | grep -v "^#" | cut -d "=" -f 1); do
    cat scripts/naaman.conf.5 | grep -q "^$options$"
    if [ $? -ne 0 ]; then
        echo "missing $options man entry for naaman.conf"
        exit 1
    fi
done
