#!/usr/bin/python
"""
N(ot) A(nother) A(UR) Man(ager).

Is an AUR wrapper/manager that uses pacman as it's backing data store.
"""
import argparse
import logging
import os
import getpass
import pyalpm
import urllib.request
import urllib.parse
import json
import string
import tempfile
import subprocess
from datetime import datetime, timedelta
from xdg import BaseDirectory
from pycman import config

_VERSION = "0.1.0"
_NAME = "naaman"
logger = logging.getLogger(_NAME)
console_format = logging.Formatter('%(message)s')
file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

_SYNC_UP_OPTIONS = "Sync/Update options"
_REMOVE_OPTIONS = "Remove options"

_AUR = "https://aur.archlinux.org{}"
_RESULT_JSON = 'results'
_AUR_NAME = "Name"
_AUR_DESC = "Description"
_AUR_RAW_URL = _AUR.format("/rpc?v=5&type={}&arg{}")
_AUR_INFO = _AUR_RAW_URL.format("info", "[]={}")
_AUR_SEARCH = _AUR_RAW_URL.format("search&by=name-desc", "={}")
_AUR_VERS = "Version"
_AUR_URLP = "URLPath"
_AUR_DEPS = "Depends"
_PRINTABLE = set(string.printable)
_AUR_TARGET_LEN = 4

_CACHE_FILE = ".cache"
_CACHE_FILES = [_CACHE_FILE]

# Script for installs
_BASH = """#!/bin/bash
trap '' 2
cd {}
makepkg {}
exit_code=$?
if [ $(ls *.pkg.tar.xz | wc -l) -gt 0 ]; then
    for d in $(echo '{}'); do
        {} cp *.pkg.tar.xz $d
    done
fi
exit $exit_code
"""


def _console_output(string, prefix="", callback=logger.info):
    """console/pretty output."""
    callback("{} => {}".format(prefix, string))


def _console_error(string):
    """Console error."""
    _console_output(string, prefix="FAILURE", callback=logger.error)


class Context(object):
    """Context for operations."""

    def __init__(self,
                 targets,
                 config_file,
                 groups,
                 confirm,
                 quiet,
                 cache,
                 sudo,
                 aur_dependencies):
        """Init the context."""
        self.root = "root" == getpass.getuser()
        self.targets = []
        if targets and len(targets) > 0:
            self.targets = targets
        self.handle = config.init_with_config(config_file)
        self.db = self.handle.get_localdb()
        self.groups = groups
        self.confirm = confirm
        self.quiet = quiet
        self._sync = None
        self._repos = None
        self._cache_dir = cache
        self.can_sudo = sudo
        self.deps = aur_dependencies
        self._tracked_depends = []
        self._pkgcaching = None

    def known_dependency(self, package):
        """Check if we know a dependency."""
        known = package in self._tracked_depends
        self._tracked_depends.append(package)
        return known

    def get_cache_files(self):
        """Get cache file list."""
        for f in os.listdir(self._cache_dir):
            name, ext = os.path.splitext(f)
            if ext in _CACHE_FILES:
                yield (f, os.path.join(self._cache_dir, f))

    def cache_file(self, file_name, ext=_CACHE_FILE):
        """Get a cache file."""
        if not os.path.exists(self._cache_dir):
            logger.error("cache directory has gone missing")
            exit(1)
        return os.path.join(self._cache_dir, file_name + ext)

    def _get_dbs(self):
        """Get sync'd dbs."""
        if self._sync:
            return
        self._sync = self.handle.get_syncdbs()

    def get_config_vals(self, array, default=""):
        """Get configuration array values."""
        val = default
        if array and len(array) > 0:
            val = " ".join(array)
        return val

    def get_packages(self):
        """Get mirror packages."""
        self._get_dbs()
        syncpkgs = set()
        for db in self._sync:
            syncpkgs |= set(p.name for p in db.pkgcache)
        return syncpkgs

    def check_repos(self, package_name):
        """Check repos for a package."""
        self._get_dbs()
        for db in self._sync:
            pkg = db.get_pkg(package_name)
            if pkg is not None:
                return True
        return False

    def pacman(self, args, require_sudo=True):
        """Call pacman."""
        cmd = []
        logger.debug("calling pacman")
        if require_sudo and not self.root:
            if self.can_sudo:
                cmd.append("/usr/bin/sudo")
            else:
                _console_error("sudo required but not allowed, re-run as root")
                exit(1)
        cmd.append("/usr/bin/pacman")
        cmd = cmd + args
        logger.debug(cmd)
        returncode = subprocess.call(cmd)
        logger.debug(returncode)
        return returncode == 0

    def check_pkgcache(self, name):
        """Check the pkgcache."""
        if self._pkgcaching is None:
            self._pkgcaching = self.get_packages()
        for pkg in self.db.pkgcache:
            if pkg.name == name:
                return True
        return False


def _validate_options(args, unknown, groups):
    """Validate argument options."""
    valid_count = 0
    invalid = False
    need_targets = False
    call_on = None

    if args.search or args.query:
        def no_call(name):
            pass
        call_on = no_call
    else:
        def action(name):
            _console_output("performing {}".format(name))
        call_on = action

    if args.sync:
        call_on("sync")
        valid_count += 1
        if args.upgrades or args.search or args.clean:
            call_on("sync function")
            sub_count = 0
            if args.upgrades:
                sub_count += 1
            if args.clean:
                sub_count += 1
            if args.search:
                sub_count += 1
            if sub_count != 1:
                _console_error("cannot perform multiple sub-options")
                invalid = True
        if args.search or (not args.upgrades and not args.clean):
            need_targets = True

    if args.remove:
        call_on("remove")
        valid_count += 1
        need_targets = True

    if args.query:
        call_on("query")
        valid_count += 1

    if not invalid:
        if valid_count > 1:
            _console_error("multiple top-level arguments given")
        elif valid_count == 0:
            _console_error("no arguments given")
        if valid_count != 1:
            invalid = True

    if not invalid and (args.search or args.upgrades):
        if not args.sync:
            _console_error("search and upgrade are sync only")
            invalid = True

    if not invalid and need_targets:
        if len(unknown) == 0:
            _console_error("no targets specified")
            invalid = True

    if not args.pacman or not os.path.exists(args.pacman):
        _console_error("invalid config file")
        invalid = True

    ctx = Context(unknown,
                  args.pacman,
                  groups,
                  not args.no_confirm,
                  args.quiet,
                  args.cache_dir,
                  args.sudo,
                  not args.skip_deps)
    callback = None
    if not invalid:
        if args.query:
            callback = _query
        if args.search:
            callback = _search
        if args.upgrades:
            callback = _upgrades
        if args.clean:
            callback = _clean
        if args.sync:
            if not args.search and not args.upgrades and not args.clean:
                callback = _sync
        if args.remove:
            callback = _remove

    if not invalid and callback is None:
        _console_error("unable to find callback")
        invalid = True

    if invalid:
        exit(1)
    callback(ctx)


def _clean(context):
    """Clean cache files."""
    logger.debug("cleaning requested")
    files = [x for x in context.get_cache_files()]
    if len(files) == 0:
        _console_output("nothing to cleanup")
        return
    if context.confirm:
        _confirm("clear cache files", [x[0] for x in files])
    for f in files:
        _console_output("removing {}".format(f[0]))
        os.remove(f[1])


def _confirm(message, package_names):
    """Confirm package changes."""
    logger.info("")
    for p in package_names:
        logger.info("  -> {}".format(p))
    logger.info("")
    msg = " ===> {}, (Y/n)? ".format(message)
    logger.debug(msg)
    c = input(msg)
    logger.debug(c)
    if c == "n":
        _console_error("user cancelled")
        exit(1)


def _shell(command, suppress_error=False, workingdir=None):
    """Run a shell command."""
    logger.debug("shell")
    logger.debug(command)
    logger.debug(workingdir)
    sp = subprocess.Popen(command,
                          cwd=workingdir,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    out, err = sp.communicate()
    logger.debug(out)
    if suppress_error:
        logger.debug(err)
    else:
        if err and len(err) > 0:
            logger.error(err)
    return out


def _install(file_definition, makepkg, cache_dirs, can_sudo):
    """Install a package."""
    sudo = ""
    if can_sudo:
        sudo = "sudo"
    url = _AUR.format(file_definition.url)
    logger.info("installing: {}".format(file_definition.name))
    with tempfile.TemporaryDirectory() as t:
        f_name = file_definition.name + ".tar.gz"
        file_name = os.path.join(t, f_name)
        logger.debug(file_name)
        urllib.request.urlretrieve(url, file_name)
        _shell(["tar", "xf", f_name], workingdir=t)
        f_dir = os.path.join(t, file_definition.name)
        temp_sh = os.path.join(t, _NAME + ".sh")
        with open(temp_sh, 'w') as f:
            script = _BASH.format(f_dir, makepkg, cache_dirs, sudo)
            f.write(script)
        result = subprocess.call("/bin/bash --rcfile {}".format(temp_sh),
                                 shell=True)
        return result == 0


def _sync(context):
    """Sync packages (install)."""
    _syncing(context, True, context.targets, False)


def _is_vcs(name):
    """Check if vcs package."""
    for t in ['-git',
              '-nightly',
              '-hg',
              '-bzr',
              '-cvs',
              '-darcs',
              '-svn']:
        if name.endswith(t):
            logger.debug("tagged as {}".format(t))
            return "latest (vcs version)"


def _get_deltahours(input_str, now):
    """Get a timedelta in hours."""
    last = datetime.fromtimestamp(float(input_str))
    seconds = (now - last).total_seconds()
    minutes = seconds / 60
    hours = minutes / 60
    return hours


def _syncing(context, can_install, targets, updating):
    """Sync/install packages."""
    if context.root:
        _console_error("can not run install/upgrades as root (uses makepkg)")
        exit(1)
    inst = []
    args = context.groups[_SYNC_UP_OPTIONS]
    ignored = args.ignore
    if not ignored:
        ignored = []
    no_vcs = False
    if args.no_vcs or args.force_refresh or args.refresh:
        no_vcs = True
    now = datetime.now()
    current_time = now.timestamp()
    if args.vcs_ignore > 0:
        cache_check = context.cache_file("vcs")
        update_cache = True
        # we have a cache item, has necessary time elapsed?
        if os.path.exists(cache_check):
            with open(cache_check, 'r') as f:
                hours = _get_deltahours(f.read(), now)
                if hours < args.vcs_ignore:
                    update_cache = False
                    no_vcs = True
        if update_cache:
            logger.info("updating vcs last cache time")
            with open(cache_check, 'w') as f:
                f.write(str(current_time))
    logger.debug("vcs? {}".format(no_vcs))
    if args.ignore_for and len(args.ignore_for) > 0:
        logger.debug("checking ignored packages.")
        ignore_for = context.cache_file("ignoring")
        ignore_definition = {}
        if os.path.exists(ignore_for):
            with open(ignore_for, 'r') as f:
                ignore_definition = json.loads(f.read())
        logger.debug(ignore_definition)
        for i in args.ignore_for:
            if "=" not in i:
                logger.warn("invalid ignore definition {}".format(i))
                continue
            parts = i.split("=")
            if len(parts) != 2:
                logger.warn("invalid ignore format {}".format(i))
            package = parts[0]
            hours = 0
            try:
                hours = int(parts[1])
                if hours < 1:
                    raise Exception("hour must be >= 1")
            except Exception as e:
                logger.warn("invalid hour value {}".format(i))
                logger.debug(e)
                continue
            update = True
            if package in ignore_definition:
                last = _get_deltahours(float(ignore_definition[package]), now)
                if last < hours:
                    ignored.append(package)
                    update = False
            if update:
                ignore_definition[package] = str(current_time)
        with open(ignore_for, 'w') as f:
            f.write(json.dumps(ignore_definition))
    logger.debug("ignoring {}".format(ignored))
    for name in targets:
        if name in ignored:
            _console_output("{} is ignored".format(name))
            continue
        if no_vcs and _is_vcs(name):
            logger.debug("skipping vcs package {}".format(name))
            continue
        package = _rpc_search(name, True, context)
        if package:
            inst.append(package)
        else:
            _console_error("unknown AUR package: {}".format(name))
            exit(1)
    report = []
    do_install = []
    for i in inst:
        pkg = context.db.get_pkg(i.name)
        vers = i.version
        tag = ""
        vcs = _is_vcs(i.name)
        if pkg:
            if pkg.version == i.version or vcs:
                if not vcs and updating:
                    continue
                tag = " [installed]"
        else:
            if not can_install:
                _console_error("{} not installed".format(i.name))
                exit(1)
        logger.debug(i)
        if vcs:
            vers = vcs
        report.append("{} {}{}".format(i.name, vers, tag))
        do_install.append(i)
    if len(do_install) == 0:
        _console_output("nothing to do")
        exit(0)
    if context.confirm:
        _confirm("install packages", report)
    makepkg = context.get_config_vals(args.makepkg, default="-sri")
    logger.debug("makepkg {}".format(makepkg))
    cache = context.handle.cachedirs
    cache_dirs = ""
    if not args.no_cache and cache and len(cache) > 0:
        for c in cache:
            if " " in c:
                logger.warn("cache dir with space is skipped ({})".format(c))
                continue
        cache_dirs = " ".join(['{}'.format(x) for x in cache if " " not in x])
    for i in do_install:
        if not _install(i, makepkg, cache_dirs, context.can_sudo):
            _console_error("error installing package: {}".format(i.name))


def _get_deps(pkgs, name):
    """Dependency resolution."""
    # NOTE: This will fail at a complicated tree across a variety of packages
    deps = []
    logger.debug('_get_deps called')
    logger.debug(name)
    for p in pkgs:
        if p.name == name or not name:
            logger.debug('found package')
            dependencies = p.depends + p.optdepends
            for d in dependencies:
                logger.debug('resolving {}'.format(d))
                for c in _get_deps(pkgs, d):
                    deps.append(c)
            deps.append(p)
    return deps


def _upgrades(context):
    """Ordered upgrade."""
    pkgs = list(_do_query(context))
    deps = _get_deps(pkgs, None)
    names = []
    for d in deps:
        if d.name in names:
            continue
        names.append(d.name)
    _syncing(context, False, names, True)


def _remove(context):
    """Remove package."""
    p = list(_do_query(context))
    if context.confirm:
        _confirm("remove packages", ["{} {}".format(x.name,
                                                    x.version) for x in p])
    options = context.groups[_REMOVE_OPTIONS]
    removals = context.get_config_vals(options.removal)
    call_with = ['-R']
    if len(removals) > 0:
        call_with = call_with + removals.split(" ")
    call_with = call_with + [x.name for x in p]
    result = context.pacman(call_with)
    if not result:
        _console_error("unable to remove packages")
        exit(1)
    _console_output("packages removed")


def _get_segment(j, key):
    """Get an ascii printable segment."""
    inputs = j[key]
    if inputs is None:
        return ""
    res = "".join([x for x in inputs if x in _PRINTABLE])
    if len(inputs) != len(res):
        logger.debug("dropped non-ascii characters")
    return res


class AURPackage(object):
    """AUR package object."""

    def __init__(self, name, version, url):
        """Init the instance."""
        self.name = name
        self.version = version
        self.url = url


def _handle_deps(root_package, context, dependencies):
    """Handle dependencies resolution."""
    logger.debug("resolving deps")
    missing = False
    syncpkgs = context.get_packages()
    for d in dependencies:
        logger.debug(d)
        if context.targets and d in context.targets:
            logger.debug("installing it")
            root = context.targets.index(root_package)
            pos = context.targets.index(d)
            if pos > root:
                _console_error("verify order of target/deps")
                exit(1)
            continue
        if context.known_dependency(d):
            logger.debug("known")
            continue
        search = _rpc_search(d, True, context)
        if search is None:
            logger.debug("not aur")
            continue
        if context.check_pkgcache(d):
            logger.debug("installed")
            continue
        _console_error("unmet AUR dependency: {}".format(d))
        missing = True
    if missing:
        exit(1)


def _rpc_search(package_name, exact, context):
    """Search for a package in the aur."""
    if exact and context.check_repos(package_name):
        logger.debug("in repos")
        return None
    if exact:
        url = _AUR_INFO
    else:
        url = _AUR_SEARCH
    url = url.format(urllib.parse.quote(package_name))
    logger.debug(url)
    try:
        with urllib.request.urlopen(url) as req:
            result = req.read()
            j = json.loads(result.decode("utf-8"))
            if "error" in j:
                _console_error(j['error'])
            result_json = []
            if _RESULT_JSON in j:
                result_json = j[_RESULT_JSON]
            if len(result_json) > 0:
                for result in result_json:
                    try:
                        name = _get_segment(result, _AUR_NAME)
                        desc = _get_segment(result, _AUR_DESC)
                        vers = _get_segment(result, _AUR_VERS)
                        if exact:
                            if name == package_name:
                                deps = None
                                if context.deps:
                                    if _AUR_DEPS in result:
                                        _aur_deps = result[_AUR_DEPS]
                                        _handle_deps(package_name,
                                                     context,
                                                     _aur_deps)
                                else:
                                    logger.debug("no dependency checks")
                                return AURPackage(name,
                                                  vers,
                                                  result[_AUR_URLP])
                        else:
                            ind = ""
                            if not name or not desc or not vers:
                                logger.debug("unable to read this package")
                                logger.debug(result)
                            if context.quiet:
                                logger.info(name)
                                continue
                            if context.db.get_pkg(name) is not None:
                                ind = " [installed]"
                            logger.info("aur/{} {}{}".format(name, vers, ind))
                            if not desc or len(desc) == 0:
                                desc = "no description"
                            logger.info("    {}".format(desc))
                    except Exception as e:
                        logger.error("unable to parse package")
                        logger.error(e)
                        logger.debug(result)
                        break
    except Exception as e:
        logger.error("error calling AUR search")
        logger.error(e)


def _search(context):
    """Perform a search."""
    if len(context.targets) != 1:
        _console_error("please provide ONE target for search")
        exit(1)
    for target in context.targets:
        logger.debug("searching for {}".format(target))
        if len(target) < _AUR_TARGET_LEN:
            # NOTE: we are suppressing this ourselves
            logger.debug("target name too short")
            continue
        _rpc_search(target, False, context)


def _query(context):
    """Perform query."""
    for q in _do_query(context):
        if context.quiet:
            output = "{}"
        else:
            output = "{} {}"
        logger.info(output.format(q.name, q.version))


def _is_aur_pkg(pkg, sync_packages):
    """Detect AUR package."""
    return pkg.name not in sync_packages


def _do_query(context):
    """Query pacman."""
    syncpkgs = context.get_packages()
    if len(context.targets) > 0:
        for target in context.targets:
            pkg = context.db.get_pkg(target)
            valid = False
            if pkg and _is_aur_pkg(pkg, syncpkgs):
                    yield pkg
            else:
                _console_error("unknown package: {}".format(target))
                exit(1)
    else:
        for pkg in context.db.pkgcache:
            if _is_aur_pkg(pkg, syncpkgs):
                yield pkg


def _remove_options(parser):
    """Get removal options."""
    group = parser.add_argument_group(_REMOVE_OPTIONS)
    group.add_argument("--removal",
                       metavar='N',
                       type=str,
                       nargs='+',
                       help="pacman -R options")


def _sync_up_options(parser):
    """Sync/update options."""
    group = parser.add_argument_group(_SYNC_UP_OPTIONS)
    group.add_argument("--ignore-for",
                       metavar='N',
                       type=str,
                       nargs='+',
                       help="ignore packages for periods of time (hours)")
    group.add_argument("--makepkg",
                       metavar='N',
                       type=str,
                       nargs='+',
                       help="makepkg options")
    group.add_argument('--vcs-ignore',
                       type=int,
                       default=0,
                       help="time betweeen vcs update checks (hours)")
    group.add_argument('--no-vcs',
                       help="skip vcs packages",
                       action='store_true')
    group.add_argument('-y', '--refresh',
                       help="refresh packages",
                       action='store_true')
    group.add_argument('-yy', '--force-refresh',
                       help="refresh packages",
                       action='store_true')
    group.add_argument("--ignore",
                       help="ignore packages",
                       metavar='N',
                       type=str,
                       nargs='+')
    group.add_argument("--no-cache",
                       help="skip caching package files",
                       action="store_true")
    group.add_argument("--skip-deps",
                       help="skip dependency checks",
                       action="store_true")


def _load_config(args, config_file):
    """Load configuration into arguments."""
    logger.debug('loading config file')
    with open(config_file, 'r') as f:
        for l in f.readlines():
            line = l.strip()
            logger.debug(line)
            if line.startswith("#"):
                continue
            if "=" not in line:
                logger.warn("unable to read line, not k=v")
                continue
            parts = line.split("=")
            key = parts[0]
            value = "=".join(parts[1:])
            if value.startswith('"') and value.endswith('"'):
                value = value[1:len(value) - 1]
            logger.debug((key, value))
            chars = [x for x in key if (x >= 'A' and x <= 'Z' or x in ["_"])]
            if len(key) != len(chars):
                logger.warn("invalid key")
                continue
            if key in ["IGNORE",
                       "PACMAN",
                       "SKIP_DEPS",
                       "REMOVAL",
                       "IGNORE_FOR",
                       "MAKEPKG",
                       "NO_VCS",
                       "SUDO",
                       "VCS_IGNORE"]:
                val = None
                lowered = key.lower()
                try:
                    if key in ["IGNORE", "MAKEPKG", "REMOVAL", "IGNORE_FOR"]:
                        arr = getattr(args, lowered)
                        if not arr:
                            arr = []
                        arr += value.split(" ")
                        setattr(args, lowered, arr)
                    elif key in ["NO_VCS", "SUDO", "SKIP_DEPS"]:
                        val = bool(value)
                    elif key == "VCS_IGNORE":
                        val = int(value)
                    else:
                        val = value
                except Exception as e:
                    logger.error("unable to read value")
                    logger.error(e)
                if val:
                    logger.debug('parsed')
                    logger.debug((key, val))
                    setattr(args, lowered, val)
            else:
                logger.warn("unknown key")
    return args


def main():
    """Entry point."""
    cache_dir = BaseDirectory.xdg_cache_home
    cache_dir = os.path.join(cache_dir, _NAME)
    parser = argparse.ArgumentParser()
    parser.add_argument('-S', '--sync',
                        help="synchronize packages",
                        action="store_true")
    parser.add_argument('-R', '--remove',
                        help='remove a package',
                        action="store_true")
    parser.add_argument('-Q', '--query',
                        help='query package database',
                        action="store_true")
    parser.add_argument('-u', '--upgrades',
                        help='perform upgrades',
                        action="store_true")
    parser.add_argument('-s', '--search',
                        help='search for packages',
                        action="store_true")
    parser.add_argument('-c', '--clean',
                        help="clean the cache",
                        action="store_true")
    parser.add_argument('--version',
                        help="display version",
                        action='store_true')
    parser.add_argument('--sudo',
                        help="allow calling sudo",
                        action='store_false')
    parser.add_argument('--verbose',
                        help="verbose output",
                        action='store_true')
    parser.add_argument('--pacman',
                        help='pacman config',
                        default='/etc/pacman.conf')
    parser.add_argument('--config',
                        help='naaman config',
                        default=os.path.join(BaseDirectory.xdg_config_home,
                                             'naaman.conf'))
    parser.add_argument('--no-confirm',
                        help="naaman will not ask for confirmation",
                        action="store_true")
    parser.add_argument('-q', '--quiet',
                        help='quiet various parts of naaman to display less',
                        action="store_true")
    parser.add_argument('--cache-dir',
                        help="cache dir for naaman",
                        default=cache_dir)
    parser.add_argument('--no-config',
                        help='do not load the config file',
                        action="store_true")
    _remove_options(parser)
    _sync_up_options(parser)
    args, unknown = parser.parse_known_args()
    if args.version:
        print("{} ({})".format(_NAME, _VERSION))
        exit(0)
    ch = logging.StreamHandler()
    if not os.path.exists(args.cache_dir):
        logger.debug("creating cache dir")
        os.makedirs(args.cache_dir)
    fh = logging.FileHandler(os.path.join(args.cache_dir, _NAME + '.log'))
    fh.setFormatter(file_format)
    if args.verbose:
        ch.setFormatter(file_format)
    else:
        ch.setFormatter(console_format)
    for h in [ch, fh]:
        logger.addHandler(h)
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    logger.debug("files/folders")
    logger.debug(args.cache_dir)
    logger.debug(args.config)
    if os.path.exists(args.config):
        if args.no_config:
            logger.debug("not loading config")
        else:
            args = _load_config(args, args.config)
    else:
        logger.debug('no config')
    arg_groups = {}
    for group in parser._action_groups:
        g = {a.dest: getattr(args, a.dest, None) for a in group._group_actions}
        arg_groups[group.title] = argparse.Namespace(**g)
    _validate_options(args, unknown, arg_groups)


if __name__ == "__main__":
    main()
