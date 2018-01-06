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
_AUR_URL = _AUR.format("/rpc?v=5&type=search&by={}&arg={}")
_AUR_VERS = "Version"
_AUR_URLP = "URLPath"
_AUR_NAME_DESC_TYPE = "name-desc"
_AUR_NAME_TYPE = "name"
_PRINTABLE = set(string.printable)

# Script for installs
_BASH = """#!/bin/bash
trap '' 2
cd {}
makepkg {}
exit $?
"""


def _console_output(string, prefix="", callback=logger.info):
    """console/pretty output."""
    callback("{} => {}".format(prefix, string))


def _console_error(string):
    """Console error."""
    _console_output(string, prefix="FAILURE", callback=logger.error)


class Context(object):
    """Context for operations."""

    def __init__(self, targets, config_file, groups, confirm):
        """Init the context."""
        self.root = "root" == getpass.getuser()
        self.targets = []
        if targets and len(targets) > 0:
            self.targets = targets
        self.handle = config.init_with_config(config_file)
        self.db = self.handle.get_localdb()
        self.groups = groups
        self.confirm = confirm


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
        if args.upgrades or args.search:
            call_on("sync function")
            if args.upgrades and args.search:
                _console_error("cannot perform multiple sub-options")
                invalid = True
        if args.search or not args.upgrades:
            need_targets = True

    if args.upgrade:
        call_on("upgrade")
        valid_count += 1
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

    if not invalid and need_targets:
        if len(unknown) == 0:
            _console_error("no targets specified")
            invalid = True

    if not args.config or not os.path.exists(args.config):
        _console_error("invalid config file")
        invalid = True

    ctx = Context(unknown, args.config, groups, not args.no_confirm)
    callback = None
    if not invalid:
        if args.query:
            callback = _query
        if args.search:
            callback = _search
        if args.upgrade:
            callback = _upgrade
        if args.upgrades:
            callback = _upgrades
        if args.sync and not args.search and not args.upgrades:
            callback = _sync
        if args.remove:
            callback = _remove

    if not invalid and callback is None:
        _console_error("unable to find callback")
        invalid = True

    if invalid:
        exit(1)
    callback(ctx)


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


def _install(file_definition, makepkg):
    """Install a package."""
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
            script = _BASH.format(f_dir, makepkg)
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
    logger.debug("vcs? {}".format(no_vcs))
    for name in targets:
        if name in ignored:
            _console_output("{} is ignored".format(name))
            continue
        if no_vcs and _is_vcs(name):
            logger.debug("skipping vcs package {}".format(name))
            continue
        package = _rpc_search(name, _AUR_NAME_TYPE, True, context)
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
    makepkg = "-sri"
    if args.makepkg and len(args.makepkg) > 0:
        makepkg = " ".join(args.makepkg)
    logger.debug("makepkg {}".format(makepkg))
    for i in do_install:
        if not _install(i, makepkg):
            _console_error("error installing package: {}".format(i.name))


def _upgrade(context):
    """Upgrade packages."""
    _syncing(context, False, context.targets, False)


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
    _syncing(context, False, [d.name for d in deps], True)


def _remove(context):
    """Remove package."""
    p = list(_do_query(context))
    if context.confirm:
        _confirm("remove packages", ["{} {}".format(x.name,
                                                    x.version) for x in p])
    options = context.groups[_REMOVE_OPTIONS]
    returncode = subprocess.call(["/usr/bin/sudo",
                                  '/usr/bin/pacman',
                                  '-R'] + [x.name for x in p])
    if returncode != 0:
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


def _rpc_search(package_name, typed, exact, context):
    """Search for a package in the aur."""
    url = _AUR_URL
    url = url.format(typed, urllib.parse.quote(package_name))
    try:
        with urllib.request.urlopen(url) as req:
            result = req.read()
            j = json.loads(result.decode("utf-8"))
            if _RESULT_JSON in j:
                for result in j[_RESULT_JSON]:
                    try:
                        name = _get_segment(result, _AUR_NAME)
                        desc = _get_segment(result, _AUR_DESC)
                        vers = _get_segment(result, _AUR_VERS)
                        if exact:
                            if name == package_name:
                                return AURPackage(name,
                                                  vers,
                                                  result[_AUR_URLP])
                        else:
                            ind = ""
                            if not name or not desc or not vers:
                                logger.debug("unable to read this package")
                                logger.debug(result)
                                continue
                            if context.db.get_pkg(name) is not None:
                                ind = " [installed]"
                            logger.info("aur/{} {}{}".format(name, vers, ind))
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
        _rpc_search(target, _AUR_NAME_DESC_TYPE, False, context)


def _query(context):
    """Perform query."""
    for q in _do_query(context):
        logger.info("{} {}".format(q.name, q.version))


def _is_aur_pkg(pkg, sync_packages):
    """Detect AUR package."""
    return pkg.name not in sync_packages


def _do_query(context):
    """Query pacman."""
    syncpkgs = set()
    for db in context.handle.get_syncdbs():
        syncpkgs |= set(p.name for p in db.pkgcache)
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
    group.add_argument('--cascade',
                       action='store_true', default=False,
                       help='remove packages and dependent packages')
    group.add_argument('--nodeps', action='store_true', default=False,
                       help='skip dependency checks')
    group.add_argument('--dbonly', action='store_true', default=False,
                       help='only modify database entries, not files')
    group.add_argument('--nosave', action='store_true', default=False,
                       help='remove configuration files as well')
    group.add_argument('--recursive',
                       action='store_true', default=False,
                       help="remove dependencies also")


def _sync_up_options(parser):
    """Sync/update options."""
    group = parser.add_argument_group(_SYNC_UP_OPTIONS)
    group.add_argument("--makepkg",
                       metavar='N',
                       type=str,
                       nargs='+',
                       help="makepkg options")
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


def main():
    """Entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument('-S', '--sync',
                        help="synchronize packages",
                        action="store_true")
    parser.add_argument('-U', '--upgrade',
                        help="upgrade packages",
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
    parser.add_argument('--version',
                        help="display version",
                        action='store_true')
    parser.add_argument('--verbose',
                        help="verbose output",
                        action='store_true')
    parser.add_argument('--config',
                        help='pacman config',
                        default='/etc/pacman.conf')
    parser.add_argument('--no-confirm',
                        help="naaman will not ask for confirmation",
                        action="store_true")
    _remove_options(parser)
    _sync_up_options(parser)
    args, unknown = parser.parse_known_args()
    if args.version:
        print("{} ({})".format(_NAME, _VERSION))
        exit(0)
    arg_groups = {}
    for group in parser._action_groups:
        g = {a.dest: getattr(args, a.dest, None) for a in group._group_actions}
        arg_groups[group.title] = argparse.Namespace(**g)
    ch = logging.StreamHandler()
    cache_dir = BaseDirectory.xdg_cache_home
    if not os.path.exists(cache_dir):
        os.mkdir(cache_dir)
    fh = logging.FileHandler(os.path.join(BaseDirectory.xdg_cache_home,
                                          _NAME + '.log'))
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
    _validate_options(args, unknown, arg_groups)


if __name__ == "__main__":
    main()
