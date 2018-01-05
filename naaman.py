#!/usr/bin/python
"""
N(ot) A(nother) A(UR) Man(ager)

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


def _validate_options(args):
    valid_count = 0
    if args.sync:
        valid_count += 1

    if valid_count != 1:
        logger.warn("i don't know how to proceed!")
        exit(1)

def main():
    """Entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument('-S', '--sync', help="synchronize packages", action="store_true")
    parser.add_argument('-U', '--upgrade', help="upgrade packages", action="store_true")
    parser.add_argument('-R', '--remove', help='remove a package', metavar='N', nargs='+')
    parser.add_argument('-Q', '--query', help='query package database', action="store_true")
    parser.add_argument('-l', '--list', help='list packages', action="store_true")
    parser.add_argument('-u', '--upgrades', help='perform upgrades', action="store_true")
    parser.add_argument('-s', '--search', help='search for packages', metavar='N', nargs='+')
    parser.add_argument('--verbose', help="verbose output", action='store_true')
    args = parser.parse_args()
    ch = logging.StreamHandler()
    cache_dir = BaseDirectory.xdg_cache_home
    if not os.path.exists(cache_dir):
        os.mkdir(cache_dir)
    fh = logging.FileHandler(os.path.join(BaseDirectory.xdg_cache_home, _NAME + '.log'))
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
