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


def _validate_options(args, unknown):
    """Validate argument options."""
    valid_count = 0
    invalid = False
    need_targets = False
    optional_targets = False

    def call_on(name):
        _console_output("performing {}".format(name))

    if args.sync:
        call_on("sync")
        valid_count += 1
        if args.upgrades or args.search:
            _console_output("performing sync function")
            if args.upgrades and args.search:
                _console_error("cannot perform multiple sub-options")
                invalid = True
        if args.search:
            need_targets = True
        else:
            optional_targets = True

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
        optional_targets = True

    if valid_count != 1:
        _console_error("multiple top-level arguments given (this is invalid)")
        invalid = True

    if need_targets:
        if len(unknown) == 0:
            _console_error("no targets specified")
            invalid = True

    if invalid:
        exit(1)
    #ctx = Context()
    #ctx.root = root = getpass.getuser()
    


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
