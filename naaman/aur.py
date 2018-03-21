"""
Defines AUR package information.

Handles AUR data management, interfacing, processing
"""
import string
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
        logger.debug("dropped non-ascii characters")
    return res
