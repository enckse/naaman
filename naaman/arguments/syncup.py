"""
Sync/update/upgrade options.

Options for controlling (fine-grained) how a sync/update works
"""
import naaman.aur as aur


SYNC_UP_OPTIONS = "Sync/Update options"


def sync_up_options(parser):
    """Sync/update options."""
    group = parser.add_argument_group(SYNC_UP_OPTIONS)
    group.add_argument("--ignore-for",
                       metavar='N',
                       type=str,
                       nargs='+',
                       help="""ignore packages for periods of time (hours).
specifying this options allows for ignoring certain packages over a known
duration. this is specified as <package>=<hours>, where <package> will only
check for updates every <hours> period.""")
    group.add_argument('--vcs-ignore',
                       type=int,
                       default=720,
                       help="""time betweeen vcs update checks (hours).
specifying this option will result in vcs-based AUR packages to only be
updated every <hour> threshold. default is 720 (30 days)""")
    group.add_argument('--no-vcs',
                       help="""perform all sync operations but
skip updating any vcs packages. this will allow for performing various
sync operations without always having vcs packages attempting to update.""",
                       action='store_true')
    group.add_argument('-y', '--refresh',
                       help="""refresh non-vcs packages if there are updates
in the AUR for the package. packages with detected updates in the AUR will be
refreshed.""",
                       action='count')
    group.add_argument('-yy', '--force-refresh',
                       help="""similar to -y but will force refresh over any
--ignore, --ignore-for, --vcs-ignore and disable any rpc caching. Use this
option to override the mentioned flags and force updating or installing a
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
                       help="""by default naaman will reorder the input package
set install order if it detects certain packages must be installed others given
as input (e.g. -S package1 package0 where package1 relies on package0 will
change to -S package0 package1). to disable this behavior, set this flag.""",
                       action="store_false")
    group.add_argument("--rpc-cache",
                       help="""enable rpc caching (minutes). instead of making
a web rpc request to check for updated AUR package information, naaman will
cache the last received information about a package for this duration of time.
default is 60 minutes.
""",
                       type=int,
                       default=60)
    group.add_argument("-i", "--info",
                       help="""display additional information about packages
when searching for information in the AUR. this can only be used during a
search but will present as much information as possible to the user about the
result package set. passing multiple i parameters will increase verbosity
(e.g. -ii)""",
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
    group.add_argument('-f', "--fetch",
                       action='store_true',
                       help="""normally naaman will manage source retrieval and
package building without problem. though this relies on knowing a PKGBUILD is
safe to use and install. utilize this option to tell naaman to fetch to a
location and not manage the files/perform the build. the user can then verify
the PKGBUILD and run makepkg manually.""")
    group.add_argument('--fetch-dir',
                       help="""specifies the location to store fetched
(--fetch) packages on the file system. whenever fetch is used this is the
directory that naaman will write to (defaults to '.').""")
    group.add_argument('--rpc-field',
                       help="""when querying the AUR RPC endpoint, naaman will
use a default search field to search for packages. by setting this argument
naaman will be instructed to, instead, search using the specified field when
querying the RPC endpoint during a search.""",
                       default=aur.RPC_NAME_DESC,
                       choices=aur.RPC_FIELDS)
    group.add_argument("--do-not-track",
                       help="""specify package names (1 or more) that naaman
is NOT responsible for tracking and should skip during processing. naaman will
not attempt to process these packages at any point.""",
                       metavar='N',
                       type=str,
                       nargs='+')
    group.add_argument("--makedeps",
                       help="""include the make dependencies as part of the
dependency resolution when handling/resolving dependencies.""",
                       action="store_true")
