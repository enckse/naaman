"""
Common/core argument parsing.

These are the root-level options for argument parsing for naaman
"""
import argparse
import naaman.consts as cst


def build(config_file, cache_dir):
    """Get common arg parser settings."""
    parser = argparse.ArgumentParser()
    parser.add_argument('-S', '--sync',
                        help="""synchronize packages (install/update). a sync
operation will attempt to install and/or update packages. -S by itself will
attempt to install a list of target packages.""",
                        action="store_true")
    parser.add_argument('-R', '--remove',
                        help="""remove a package. this will call pacman on any
AUR based packages and remove them (if installed).""",
                        action="store_true")
    parser.add_argument('-Q', '--query',
                        help="""query package database. this option is used to
find out what AUR packages are currently installed on the system.""",
                        action="store_true")
    parser.add_argument('-u', '--upgrades',
                        help="""perform an upgrade of installed packages on the
the system. this will attempt to upgrade ALL AUR installed packages. a list of
target packages may also be passed.""",
                        action="store_true")
    parser.add_argument('-s', '--search',
                        help="""search for packages in the AUR. the AUR rpc
endpoints will be called to attempt to find a package with a name or
description matching the input string (change fields using --rpc-field).""",
                        action="store_true")
    parser.add_argument('-c', '--clean',
                        help="""clean the cache. this will clean the naaman
cache area of any cache files. this can be used to invalidate/remove old cache
information for deprecated packages or to reset duration caching options.""",
                        action="store_true")
    parser.add_argument('-d', '--deps',
                        help="""naaman will attempt to build a dependency chain
for the seperately  for each package specified. upon completion naaman will
attempt to install (after confirmation) the determined dependency chain.""",
                        action="store_true")
    parser.add_argument('--version',
                        help="display version information about naaman",
                        action='version',
                        version="{} ({})".format(cst.NAME, cst.__version__))
    parser.add_argument('--no-sudo',
                        help="""disable calling sudo. by default when naaman
has to call pacman directly (e.g. -R), it will call with sudo if required.
passing this option will prevent naaman from using sudo.""",
                        action='store_true')
    parser.add_argument('--verbose',
                        help="""verbose output. this setting will change the
output formatting and enable DEBUG level output. use this to begin to debug
naaman and to see more detail.""",
                        action='store_true')
    parser.add_argument('--trace',
                        help="""trace debug logging. this option is useful to
dump extensive naaman logging information for indepth troubleshooting or
debugging purposes.""",
                        action='store_true')
    parser.add_argument('--pacman',
                        help="""pacman config. when creating the pacman handle
naaman passes a configuration file to pacman for initialization via pyalpm.
this is NOT passed when calling pacman directly (e.g. -R).""",
                        default='/etc/pacman.conf')
    parser.add_argument('--config',
                        help="""naaman config. specify the (optional) naaman
configuration file to use. please use man naaman.conf for available options.
naaman will read configs in the order of (all optional): /etc, XDG_CONFIG_HOME
, and then --config""",
                        default=config_file)
    parser.add_argument('--no-confirm',
                        help="""naaman will not ask for confirmation. when
performing install, update, and remove operations naaman will ask for the user
to confirm the operation. to disable these prompts pass this option. this
option will not suppress makepkg or pacman prompts (use REMOVAL or MAKEPKG in
the naaman.conf)""",
                        action="store_true")
    parser.add_argument('-q', '--quiet',
                        help="""quiet various parts of naaman to display less.
certain operations will display more AUR package information that will be quiet
(displaying minimal package information) if this option is provided.""",
                        action="store_true")
    parser.add_argument('--cache-dir',
                        help="""cache dir for naaman. naaman stores caching and
logging information to this location. naaman will (attempt) to create this
directory if it does not exist.""",
                        default=cache_dir)
    parser.add_argument('--no-config',
                        help="""do not load the config file. to prevent naaman
from loading the configuration file when running specify this option. this can
allow running a specify instance of naaman without certain config options being
loaded.""",
                        action="store_true")
    parser.add_argument('--builds',
                        help="""the location where naaman will perform builds.
if not set this will be in XDG_CACHE_HOME. specifying this option will move
where makepkg operations are performed in the system.""",
                        default=cache_dir,
                        type=str)
    return parser
