#!/usr/bin/python
"""
N(ot) A(nother) A(UR) Man(ager).

Is an AUR wrapper/manager that uses pacman as it's backing data store.
"""
import argparse
import logging
import os
from xdg import BaseDirectory
import getpass
import pyalpm
from pycman import config
import urllib.request
import urllib.parse
import json
import string
from pycman import transaction
import tempfile
import subprocess


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

    def __init__(self, targets, config_file, groups):
        """Init the context."""
        self.root = "root" == getpass.getuser()
        self.targets = []
        if targets and len(targets) > 0:
            self.targets = targets
        self.handle = config.init_with_config(config_file)
        self.db = self.handle.get_localdb()
        self.groups = groups


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

    if not invalid and valid_count != 1:
        _console_error("multiple top-level arguments given (this is invalid)")
        invalid = True

    if not invalid and need_targets:
        if len(unknown) == 0:
            _console_error("no targets specified")
            invalid = True

    if not args.config or not os.path.exists(args.config):
        _console_error("invalid config file")
        invalid = True

    ctx = Context(unknown, args.config, groups)
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
    url = _AUR.format(file_definition[2])
    logger.info("installing: {}".format(file_definition[0]))
    with tempfile.TemporaryDirectory() as t:
        f_name = file_definition[0] + ".tar.gz"
        file_name = os.path.join(t, f_name)
        logger.debug(file_name)
        urllib.request.urlretrieve(url, file_name)
        _shell(["tar", "xf", f_name], workingdir=t)
        f_dir = os.path.join(t, file_definition[0])
        temp_sh = os.path.join(t, _NAME + ".sh")
        with open(temp_sh, 'w') as f:
            script = _BASH.format(f_dir, makepkg)
            f.write(script)
        result = subprocess.call("/bin/bash --rcfile {}".format(temp_sh),
                                 shell=True)
        return result == 0


def _sync(context):
    """Sync packages (install)."""
    _syncing(context, True, context.targets)


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


def _syncing(context, can_install, targets):
    """Sync/install packages."""
    if context.root:
        _console_error("can not run install/upgrades as root (uses makepkg)")
        exit(1)
    inst = []
    args = context.groups[_SYNC_UP_OPTIONS]
    for name in targets:
        if args.no_vcs and _is_vcs(name):
            logger.debug("skipping vcs package {}".format(name))
            continue
        package = _rpc_search(name, _AUR_NAME_TYPE, True, context)
        if package:
            inst.append(package)
        else:
            _console_error("unknown AUR package: {}".format(name))
            exit(1)
    report = []
    for i in inst:
        pkg = context.db.get_pkg(i[0])
        vers = i[1]
        tag = ""
        if pkg:
            if pkg.version == i[1]:
                tag = " [installed]"
        else:
            if not can_install:
                _console_error("{} not installed".format(i[0]))
                exit(1)
        vcs = _is_vcs(i[0])
        if vcs:
            vers = vcs
        logger.debug(i)
        report.append("{} {}{}".format(i[0], vers, tag))
    _confirm("install packages", report)
    makepkg = "-sri"
    if args.makepkg and len(args.makepkg) > 0:
        makepkg = " ".join(args.makepkg)
    logger.debug("makepkg {}".format(makepkg))
    for i in inst:
        if not _install(i, makepkg):
            _console_error("error installing package: {}".format(i[0]))


def _upgrade(context):
    """Upgrade packages."""
    _syncing(context, False, context.targets)


def _upgrades(context):
    """Ordered upgrade."""


def _remove(context):
    """Remove package."""
    p = list(_do_query(context))
    _confirm("remove packages", ["{} {}".format(x.name, x.version) for x in p])
    options = context.groups[_REMOVE_OPTIONS]
    ok = True
    try:
        t = transaction.init_from_options(context.handle, options)
        for p in pkgs:
            t.remove_pkg(p)
        ok = transaction.finalize(t)
    except Exception as e:
        logger.error("transaction failed")
        logger.error(e)
        ok = False
    if not ok:
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
                                return (name, vers, result[_AUR_URLP])
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
    parser.add_argument('--verbose',
                        help="verbose output",
                        action='store_true')
    parser.add_argument('--config',
                        help='pacman config',
                        default='/etc/pacman.conf')
    _remove_options(parser)
    _sync_up_options(parser)
    args, unknown = parser.parse_known_args()
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
