"""
Custom pass-thru arguments.

Some options in naaman (mainly script-based) need to support
more 'variable' args and/or custom options
"""

CUSTOM_ARGS = "Custom options"
CUSTOM_REMOVAL = "removal"
CUSTOM_MAKEPKG = "makepkg"
DEFAULT_OPTS = {}
DEFAULT_OPTS[CUSTOM_REMOVAL] = []
DEFAULT_OPTS[CUSTOM_MAKEPKG] = ["-sri"]
