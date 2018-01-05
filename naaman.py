#!/usr/bin/python
"""
N(ot) A(nother) A(UR) Man(ager).

Is an AUR wrapper/manager that uses pacman as it's backing data store.
"""
import argparse
import logging
import os
from xdg import BaseDirectory

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


def _validate_options(args):
    """Validate argument options."""
    valid_count = 0
    invalid = False

    def call_on(name):
        _console_output("performing {}".format(name))

    if args.sync:
        call_on("sync")
        valid_count += 1

    if args.upgrade:
        call_on("upgrade")
        valid_count += 1

    if args.remove:
        call_on("remove")
        valid_count += 1

    if args.query:
        call_on("query")
        valid_count += 1

    if valid_count != 1:
        _console_error("multiple top-level arguments given (this is invalid)")
        invalid = True

    if args.list:
        if args.query:
            _console_output("get listing")
        else:
            _console_error("list only available via query")
            invalid = True

    if args.upgrades:
        if args.upgrade or args.sync:
            _console_output("upgrading packages")
        else:
            _console_error("upgrade not available via these functions")
            invalid = True

    if args.search:
        if args.sync:
            _console_output("searching {}".format(args.search))
        else:
            _console_error("search only available via sync")
            invalid = True
    if args.search and args.upgrades:
        _console_error("can not search and upgrade")
        invalid = True
    if invalid:
        exit(1)


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
                        metavar='N', nargs='+')
    parser.add_argument('-Q', '--query',
                        help='query package database',
                        action="store_true")
    parser.add_argument('-l', '--list',
                        help='list packages',
                        action="store_true")
    parser.add_argument('-u', '--upgrades',
                        help='perform upgrades',
                        action="store_true")
    parser.add_argument('-s', '--search',
                        help='search for packages',
                        metavar='N', nargs='+')
    parser.add_argument('--verbose',
                        help="verbose output",
                        action='store_true')
    args = parser.parse_args()
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
    _validate_options(args)

if __name__ == "__main__":
    main()
