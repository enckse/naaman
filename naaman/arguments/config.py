"""
Load the configuration file for argument adjustment.

First we get and parse the args and then we also have a config
e.g. /etc/naaman.conf (system)
We take the config and use it to supplement our args
"""

import os
import naaman.logger as log
import naaman.consts as cst
from xdg import BaseDirectory


def get_default_cache():
    """Get default cache path."""
    cache_dir = BaseDirectory.xdg_cache_home
    return os.path.join(cache_dir, cst.NAME)


def get_default_config():
    """Get default config path."""
    return os.path.join(BaseDirectory.xdg_config_home, cst.CONFIG)


def load_config(args, config_file):
    """Load configuration into arguments."""
    log.debug('loading config file: {}'.format(config_file))
    if not os.path.exists(config_file):
        log.debug("does not exist")
        return args
    with open(config_file, 'r') as f:
        dirs = dir(args)
        for l in f.readlines():
            line = l.strip()
            log.trace(line)
            if line.startswith("#"):
                continue
            if not line or len(line) == 0:
                continue
            if "=" not in line:
                log.warn("unable to read line, not k=v ({})".format(line))
                continue
            parts = line.split("=")
            key = parts[0]
            value = "=".join(parts[1:])
            if value.startswith('"') and value.endswith('"'):
                value = value[1:len(value) - 1]
            log.trace((key, value))
            chars = [x for x in key if (x >= 'A' and x <= 'Z' or x in ["_"])]
            if len(key) != len(chars):
                log.warn("invalid key")
                continue
            if key in ["IGNORE",
                       "PACMAN",
                       "RPC_CACHE",
                       "SKIP_DEPS",
                       "NO_CACHE",
                       "REMOVAL",
                       "SCRIPTS",
                       "VCS_INSTALL_ONLY",
                       "IGNORE_FOR",
                       "MAKEPKG",
                       "NO_VCS",
                       "BUILDS",
                       "NO_SUDO",
                       "FETCH_DIR",
                       "VCS_IGNORE"]:
                val = None
                lowered = key.lower()
                try:
                    if key in ["IGNORE", "MAKEPKG", "REMOVAL", "IGNORE_FOR"]:
                        arr = None
                        if key in dirs:
                            arr = getattr(args, lowered)
                        else:
                            dirs.append(key)
                        if arr is None:
                            arr = []
                        if value is not None:
                            arr.append(value)
                            setattr(args, lowered, arr)
                    elif key in ["NO_VCS",
                                 "NO_SUDO",
                                 "SKIP_DEPS",
                                 "NO_CACHE",
                                 "REORDER_DEPS"]:
                        val == value == "True"
                    elif key in ["VCS_IGNORE", "RPC_CACHE"]:
                        val = int(value)
                    else:
                        val = value
                except Exception as e:
                    log.error("unable to read value")
                    log.error(e)
                if val:
                    log.trace('parsed')
                    log.trace((key, val))
                    setattr(args, lowered, val)
            else:
                log.warn("unknown configuration key")
    return args
