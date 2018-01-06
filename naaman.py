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

_NAME = "naaman"
logger = logging.getLogger(_NAME)
console_format = logging.Formatter('%(message)s')
file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')


def _console_output(string, prefix="", callback=logger.info):
    """console/pretty output."""
    callback("{} => {}".format(prefix, string))


def _console_error(string):
    """Console error."""
    _console_output(string, prefix="FAILURE", callback=logger.error)

class Context(object):
    """Context for operations."""

    def __init__(self, targets, config_file):
        self.root = "root" == getpass.getuser()
        self.targets = []
        if targets and len(targets) > 0:
            self.targets = targets
        self.handle = config.init_with_config(config_file)
        self.db = self.handle.get_localdb()


def _validate_options(args, unknown):
    """Validate argument options."""
    valid_count = 0
    invalid = False
    need_targets = False

    def call_on(name):
        _console_output("performing {}".format(name))

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

    if valid_count != 1:
        _console_error("multiple top-level arguments given (this is invalid)")
        invalid = True

    if need_targets:
        if len(unknown) == 0:
            _console_error("no targets specified")
            invalid = True

    if not args.config or not os.path.exists(args.config):
        _console_error("invalid config file")
        invalid = True

    ctx = Context(unknown, args.config)
    callback = None
    if args.query:
        callback = _query
    if args.search:
        callback = _search
    if args.sync:
        # this handles upgrades and sync (for now)
        callback = _sync_upgrade
    if args.remove:
        callback = _remove

    if callback is None:
        _console_error("unable to find callback")
        invalid = True

    if invalid:
        exit(1)
    callback(ctx)

def _query(context):
    """Query pacman."""
    def _print(pkg):
        logger.info("{} {}".format(pkg.name, pkg.version))
    if len(context.targets) > 0:
        for target in context.targets:
            pkg = context.db.get_pkg(target)
            if not pkg:
                _console_error("unknown package: {}".format(target))
                exit(1)
            _print(pkg)
    else:
        for pkg in context.db.pkgcache:
            if pkg.packager == "Unknown Packager":
                _print(pkg)

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
    args, unknown = parser.parse_known_args()
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
    _validate_options(args, unknown)

if __name__ == "__main__":
    main()
