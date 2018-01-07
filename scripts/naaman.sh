#!/bin/bash
MANPY="bin/man.py"
cat naaman.py | grep -v "import pyalpm" > $MANPY
python $MANPY $@
