"""Custom pass-thru arguments."""

CUSTOM_ARGS = "Custom options"
CUSTOM_REMOVAL = "removal"
CUSTOM_SCRIPTS = "scripts"
CUSTOM_MAKEPKG = "makepkg"
DEFAULT_OPTS = {}
DEFAULT_OPTS[CUSTOM_REMOVAL] = []
DEFAULT_OPTS[CUSTOM_MAKEPKG] = ["-sri"]
DEFAULT_OPTS[CUSTOM_SCRIPTS] = "/usr/share/naaman/"
