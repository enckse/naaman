"""
Defines AUR package information.

Handles AUR data management, interfacing, processing
"""
import string
import naaman.logger as log
_PRINTABLE = set(string.printable)


class AURPackage(object):
    """AUR package object."""

    def __init__(self, name, version, url, deps):
        """Init the instance."""
        self.name = name
        self.version = version
        self.url = url
        self.deps = deps


def get_segment(j, key):
    """Get an ascii printable segment."""
    inputs = j[key]
    if inputs is None:
        return ""
    res = "".join([x for x in inputs if x in _PRINTABLE])
    if len(inputs) != len(res):
        log.debug("dropped non-ascii characters")
    return res

def is_vcs(name):
    """Check if vcs package."""
    for t in ['-git',
              '-nightly',
              '-hg',
              '-bzr',
              '-cvs',
              '-darcs',
              '-svn']:
        if name.endswith(t):
            log.debug("tagged as {}".format(t))
            return "latest (vcs version)"

