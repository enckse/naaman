"""
Handle AUR requests, information, packages.

e.g.
1. rpc requests
2. AUR package resolution
3. (poor) dependency management
"""
import urllib.parse
import urllib.request
import string
import json
import os
import naaman.consts as cst
import naaman.logger as log
import naaman.shell as sh
from datetime import datetime

_PRINTABLE = set(string.printable)

RPC_NAME_DESC = "name-desc"
RPC_NAME = "name"
RPC_MAINTAINER = "maintainer"
RPC_FIELDS = [RPC_NAME_DESC, RPC_NAME, RPC_MAINTAINER]
_AUR = "https://aur.archlinux.org{}"
_AUR_GIT = _AUR.format("/{}.git")
_RESULT_JSON = 'results'
_AUR_NAME = "Name"
_AUR_DESC = "Description"
_AUR_RAW_URL = _AUR.format("/rpc?v=5&type={}&arg{}")
_AUR_INFO = _AUR_RAW_URL.format("info", "[]={}")
_AUR_SEARCH = _AUR_RAW_URL.format("search&by={}", "{}")
_AUR_VERS = "Version"
_AUR_URLP = "URLPath"
_AUR_DEPS = "Depends"
_AUR_BASE = "PackageBase"
_AUR_MAKEDEPS = "MakeDepends"
_MAKEPKG_VCS = ["-od"]


class DepTree(object):
    """Tracks the dependency tree."""

    def __init__(self, name):
        """Init the tree."""
        self.name = name
        self._children = []

    def add(self, child):
        """Add a child to the tree."""
        self._children.append(child)

    def get(self, visited, depth=0):
        """Get the tree for install."""
        if self.name in visited:
            if visited[self.name] > depth:
                return
        yield (depth, self.name)
        for c in self._children:
            for g in c.get(visited, depth=depth+1):
                yield g
        visited[self.name] = depth


class AURPackage(object):
    """AUR package object."""

    def __init__(self, name, version, url, deps, basepkg):
        """Init the instance."""
        self.name = name
        self.version = version
        self.url = url
        self.deps = deps
        self.base = basepkg


def _get_segment(j, key):
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


def _rpc_caching(package_name, context):
    """Cache RPC area/check."""
    now = context.now
    use_file_name = "rpc-"
    for char in package_name:
        c = char
        if not c.isalnum() and c not in ['-']:
            c = "_"
        use_file_name += c
    cache_file = context.cache_file(use_file_name)
    log.debug(cache_file)
    cache = False
    return_factory = None
    return_cache = None
    if os.path.exists(cache_file):
        mtime = os.path.getmtime(cache_file)
        last = datetime.fromtimestamp(mtime)
        seconds = (now - last).total_seconds()
        minutes = seconds / 60
        log.trace(minutes)
        log.trace(context.rpc_cache)
        if minutes > context.rpc_cache:
            os.remove(cache_file)
            log.debug("over rpc cache threshold")
            cache = True
        else:
            def _open(url):
                log.debug("opening cache")
                return open(cache_file, 'rb')
            return_factory = _open
    else:
        cache = True
    if cache:
        return_cache = cache_file
    return return_cache, return_factory


def rpc_search(package_name, exact, context, include_deps):
    """Search for a package in the aur."""
    if exact and context.check_repos(package_name):
        log.debug("in repos")
        return None
    if exact or context.info_verbose:
        url = _AUR_INFO
    else:
        if context.rpc_field not in RPC_FIELDS:
            log.console_error("unknown rpc field {}".format(context.rpc_field))
            context.exiting(1)
        url = _AUR_SEARCH.format(context.rpc_field, "={}")
    url = url.format(urllib.parse.quote(package_name))
    log.debug(url)
    factory = None
    caching = None
    found = False
    if exact and context.rpc_cache > 0 and not context.force_refresh:
        log.debug("rpc cache enabled")
        context.lock()
        try:
            c, f = _rpc_caching(package_name, context)
            factory = f
            caching = c
            log.trace((c, f))
        except Exception as e:
            log.error("unexpected rpc cache error")
            log.error(e)
        context.unlock()
    if factory is None:
        factory = urllib.request.urlopen
    try:
        with factory(url) as req:
            result = req.read()
            if caching:
                log.debug('writing cache')
                with open(caching, 'wb') as f:
                    f.write(result)
            j = json.loads(result.decode("utf-8"))
            if "error" in j:
                log.console_error(j['error'])
            result_json = []
            if _RESULT_JSON in j:
                result_json = j[_RESULT_JSON]
            if len(result_json) > 0:
                for result in result_json:
                    try:
                        name = _get_segment(result, _AUR_NAME)
                        desc = _get_segment(result, _AUR_DESC)
                        vers = _get_segment(result, _AUR_VERS)
                        found = True
                        if name and context.check_repos(name):
                            log.debug("package in a repository db")
                            # This is in the repos, abort displaying
                            # you can't 'install' this anyway
                            # ...using naaman
                            log.debug("in repos")
                            continue
                        if exact:
                            if name == package_name:
                                deps = None
                                if context.deps or include_deps:
                                    raw_deps = []
                                    if _AUR_DEPS in result:
                                        raw_deps += result[_AUR_DEPS]
                                    if context.makedeps:
                                        if _AUR_MAKEDEPS in result:
                                            raw_deps += result[_AUR_MAKEDEPS]
                                    if len(raw_deps) > 0:
                                        _aur_deps = raw_deps
                                        if context.deps:
                                            _handle_deps(package_name,
                                                         context,
                                                         _aur_deps)
                                        if include_deps:
                                            deps = _aur_deps
                                else:
                                    log.debug("no dependency checks")
                                return AURPackage(name,
                                                  vers,
                                                  result[_AUR_URLP],
                                                  deps,
                                                  result[_AUR_BASE])
                        else:
                            ind = ""
                            if not name or not desc or not vers:
                                log.debug("unable to read this package")
                                log.trace(result)
                            if context.quiet:
                                log.info(name)
                                continue
                            if context.info:
                                keys = [k for k in result.keys()]
                                max_key = max([len(k) for k in keys]) + 3
                                for k in keys:
                                    fmt = None
                                    val = result[k]
                                    if val and k in ["FirstSubmitted",
                                                     "LastModified"]:
                                        fmt = "time"
                                    log.info(context.alpm.format(k,
                                                                 val,
                                                                 format=fmt))
                                log.info("")
                                continue
                            if context.db.get_pkg(name) is not None:
                                ind = " [installed]"
                            if is_vcs(name):
                                ind += " [vcs]"
                            log.info("aur/{} {}{}".format(name, vers, ind))
                            if not desc or len(desc) == 0:
                                desc = "no description"
                            txt = context.alpm.format_line(desc)
                            log.info(txt)
                    except Exception as e:
                        log.error("unable to parse package")
                        log.error(e)
                        log.trace(result)
                        break
    except Exception as e:
        log.error("error calling AUR search")
        log.error(e)
    if not found and context.info_verbose:
        log.console_error("no exact matches for {}".format(package_name))


def _handle_deps(root_package, context, dependencies):
    """Handle dependencies resolution."""
    log.debug("resolving deps")
    missing = False
    syncpkgs = context.get_packages()
    for dep in dependencies:
        d = dep
        dependency = deps_compare(d)
        d = dependency.pkg
        log.debug(d)
        if context.targets and d in context.targets:
            log.debug("installing it")
            root = context.targets.index(root_package)
            pos = context.targets.index(d)
            if pos > root:
                if context.reorder_deps:
                    log.console_output(
                        "switching {} and {}".format(d, root_package))
                    context.reorders.append(d)
                else:
                    log.console_error("verify order of target/deps")
                    context.exiting(1)
            continue
        if context.known_dependency(d):
            log.debug("known")
            continue
        search = rpc_search(d, True, context, False)
        if search is None:
            log.debug("not aur")
            continue
        if context.check_pkgcache(d, dependency.version):
            log.debug("installed")
            continue
        show_version = ""
        if dependency.version is not None:
            show_version = " ({}{})".format(dependency.op, dependency.version)
        log.console_error("unmet AUR dependency: {}{}".format(d, show_version))
        missing = True
    if missing:
        context.exiting(1)


def check_vcs(package, context, version):
    """Check current vcs version."""
    result = install(package, _MAKEPKG_VCS, None, context,  version)
    if not result:
        log.console_output("up-to-date: {} ({})".format(package.name, version))
    return result


def install(file_definition, makepkg, cache_dirs, context, version):
    """Install a package."""
    can_sudo = context.can_sudo
    new_file = context.build_dir
    url = _AUR.format(file_definition.url)
    action = "installing"
    is_installing = version is None
    if not is_installing:
        action = "checking version"
    log.console_output("{}: {}".format(action, file_definition.name))
    with new_file() as t:
        if context.fetching:
            clone_to = file_definition.name
            p = context.fetch_dir
        else:
            clone_to = "."
            p = os.path.join(t, file_definition.name)
            os.makedirs(p)
        f_dir = os.path.join(t, file_definition.name)
        pkg = sh.InstallPkg(can_sudo, f_dir)
        if not pkg.git(_AUR_GIT.format(file_definition.base), clone_to, p):
            return False
        if context.fetching:
            log.console_output("{} was fetched".format(file_definition.name))
            return True
        glob = file_definition.name
        if is_installing:
            log.debug("installing")
            is_split = pkg.is_split()
            if is_split:
                log.debug("split package")
                if sh.confirm("split package - install all",
                              None,
                              False,
                              True) is None:
                    glob = None
                log.debug(glob)
        if not pkg.makepkg(makepkg):
            return False
        if is_installing:
            if not pkg.install(glob):
                return False
            if not pkg.cache(cache_dirs):
                return False
            return True
        else:
            return pkg.version(version)
