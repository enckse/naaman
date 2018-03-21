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


class Deps(object):
    """Dependency object."""

    def __init__(self, vers, op, package):
        """Init a new dependency object."""
        self.version = vers
        self.op = op
        self.pkg = package


def deps_compare(package):
    """Compare deps versions."""
    d_compare = None
    d_version = None
    for compare in [">=", "<=", ">", "<", "="]:
        c_idx = package.rfind(compare)
        if c_idx >= 0:
            d_compare = compare
            d_version = package[c_idx + len(compare):len(package)]
            package = package[0:c_idx]
            break
    return Deps(d_version, d_compare, package)


def get_deps(pkgs):
    """Get dependencies."""
    return _get_deps(pkgs, None)


def _get_deps(pkgs, name):
    """Dependency resolution."""
    # NOTE: This will fail at a complicated tree across a variety of packages
    deps = []
    log.debug('getting deps')
    log.trace(name)
    for p in pkgs:
        if p.name == name or not name:
            log.debug('found package')
            dependencies = p.depends + p.optdepends
            for d in dependencies:
                log.debug('resolving {}'.format(d))
                for c in _get_deps(pkgs, d):
                    deps.append(c)
            deps.append(p)
    return deps
