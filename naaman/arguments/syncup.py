"""Sync/update/upgrade options."""

SYNC_UP_OPTIONS = "Sync/Update options"


def sync_up_options(parser):
    """Sync/update options."""
    group = parser.add_argument_group(SYNC_UP_OPTIONS)
    group.add_argument("--ignore-for",
                       metavar='N',
                       type=str,
                       nargs='+',
                       help="""ignore packages for periods of time (hours).
specifying this options allows for ignoring certain packages over time.
this is specified as <package>=<hours>, where <package> will only check
for updates every <hours> period.""")
    group.add_argument('--vcs-ignore',
                       type=int,
                       default=720,
                       help="""time betweeen vcs update checks (hours).
specifying this option will result in vcs-based AUR packages to only be
updated (they will always update) every <hour> threshold.
default is 720 (30 days)""")
    group.add_argument('--no-vcs',
                       help="""perform all sync operations but
skip updating any vcs packages. this will allow for performing various
sync operations without always having vcs packages updating.""",
                       action='store_true')
    group.add_argument('-y', '--refresh',
                       help="""refresh non-vcs packages if there are updates
in the AUR for the package. packages with detected updates in the AUR will be
refreshed (assumes -U).""",
                       action='count')
    group.add_argument('-yy', '--force-refresh',
                       help="""similar to -y but will force refresh over any
--ignore, --ignore-for, --vcs-ignore and disable any rpc caching. Use this
option to override the mentioned flags and force update or installing a
package set.""",
                       action='store_true')
    group.add_argument("--ignore",
                       help="""ignore packages by name. packages ignored will
be skipped during upgrades unless forced (-yy). utilize this to keep packages
back and/or prevent upgrading packages""",
                       metavar='N',
                       type=str,
                       nargs='+')
    group.add_argument("--no-cache",
                       help="""skip caching package files. by default naaman
will take the resulting makepkg output packages and place them in the pacman
cache directory. setting this will disable this operation.""",
                       action="store_true")
    group.add_argument("--skip-deps",
                       help="""skip dependency checks. naaman will attempt to
detect and error when checking an AUR package for other AUR packages that are
NOT installed. setting this will disable this check.""",
                       action="store_true")
    group.add_argument("--reorder-deps",
                       help="""attempt to re-order dependency installs. by
setting this, naaman will no longer try and re-order dependencies. this
setting attempts to detect install order and adjust to resolve any detected
dependency issues (e.g. -S package1 package0 where package1 relies on
package0 will change to install package0 and then package1)""",
                       action="store_false")
    group.add_argument("--rpc-cache",
                       help="""enable rpc caching (minutes). instead of making
a web rpc request to check for updated AUR package information, naaman will
cache the last received information about a package for this duration of time
""",
                       type=int,
                       default=60)
    group.add_argument("-i", "--info",
                       help="""display additional information about packages
when searching for information in the AUR. this is only used during a search
but will present as much information as possible to the user about the result
package set. passing multiple i parameters will increase verbose (e.g. -ii)""",
                       action="count")
    group.add_argument("--vcs-install-only",
                       help="""by default when attempting a force update (-yy)
naaman will attempt to download/clone the package and determine the version for
vcs packages. by settings this flag when force updating naaman will skip the
vcs version check and force-install the current version of the vcs package
regardless of what is currently installed. disabling this would save bandwidth
""",
                       action="store_true")
    group.add_argument('-yyy', '--force-force-refresh',
                       help="""similar to -yy but will force force refresh over
any speciality checking (e.g. --vcs-install-only). Use this flag to update all
AUR packages on the system""",
                       action='store_true')
