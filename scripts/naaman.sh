#!/bin/bash
MANPY="bin/man.py"
cat naaman.py | grep -v "import pyalpm" | grep -v "^from pycman" > $MANPY
python $MANPY $@
