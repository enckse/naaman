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
import signal
import tempfile
import subprocess
import time
from datetime import datetime, timedelta
from xdg import BaseDirectory
from pycman import config

_VERSION = "0.2.0"
_NAME = "naaman"
logger = logging.getLogger(_NAME)
console_format = logging.Formatter('%(message)s')
file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

_CUSTOM_ARGS = "Custom options"
_SYNC_UP_OPTIONS = "Sync/Update options"
_QUERY_OPTIONS = "Query options"
_CUSTOM_REMOVAL = "removal"
_CUSTOM_SCRIPTS = "scripts"
_CUSTOM_MAKEPKG = "makepkg"
_DEFAULT_OPTS = {}
_DEFAULT_OPTS[_CUSTOM_REMOVAL] = []
_DEFAULT_OPTS[_CUSTOM_MAKEPKG] = ["-sri"]
_DEFAULT_OPTS[_CUSTOM_SCRIPTS] = "/usr/share/naaman/"

_AUR = "https://aur.archlinux.org{}"
_RESULT_JSON = 'results'
_AUR_NAME = "Name"
_AUR_DESC = "Description"
_AUR_RAW_URL = _AUR.format("/rpc?v=5&type={}&arg{}")
_AUR_INFO = _AUR_RAW_URL.format("info", "[]={}")
_AUR_SEARCH = _AUR_RAW_URL.format("search&by=name-desc", "={}")
_AUR_VERS = "Version"
_AUR_URLP = "URLPath"
_AUR_DEPS = "Depends"
_PRINTABLE = set(string.printable)
_AUR_TARGET_LEN = 4

_CACHE_FILE = ".cache"
_LOCKS = ".lck"
_CACHE_FILES = [_CACHE_FILE, _LOCKS]


def _console_output(string, prefix="", callback=logger.info):
    """console/pretty output."""
    callback("{} => {}".format(prefix, string))


def _console_error(string):
    """Console error."""
    _console_output(string, prefix="FAILURE", callback=logger.error)


class Context(object):
    """Context for operations."""

    def __init__(self, targets, groups, args):
        """Init the context."""
        self.root = "root" == getpass.getuser()
        self.targets = []
        if targets and len(targets) > 0:
            self.targets = targets
        self.handle = config.init_with_config(args.pacman)
        self.db = self.handle.get_localdb()
        self.groups = groups
        self.confirm = not args.no_confirm
        self.quiet = args.quiet
        self._sync = None
        self._repos = None
        self._cache_dir = args.cache_dir
        self.can_sudo = not args.no_sudo
        self.deps = not args.skip_deps
        self._tracked_depends = []
        self._pkgcaching = None
        self._scripts = {}
        self.reorder_deps = args.reorder_deps
        self.reorders = []
        self.rpc_cache = args.rpc_cache
        self._lock_file = os.path.join(self._cache_dir, "file" + _LOCKS)
        self.force_refresh = args.force_refresh
        self._custom_args = self.groups[_CUSTOM_ARGS]
        self._script_dir = self.get_custom_arg(_CUSTOM_SCRIPTS)
        self.now = datetime.now()
        self.timestamp = self.now.timestamp()

        def sigint_handler(signum, frame):
            """Handle ctrl-c."""
            _console_error("CTRL-C")
            self.exiting(1)
        signal.signal(signal.SIGINT, sigint_handler)

    def get_custom_arg(self, name):
        """Get custom args."""
        if name not in self._custom_args:
            _console_error("custom argument missing")
            self.exiting(1)
        return self._custom_args[name]

    def exiting(self, code):
        """Exiting via context."""
        self.unlock()
        exit(code)

    def load_script(self, name):
        """Load a script file."""
        script = os.path.join(self._script_dir, name)
        if not os.path.exists(script):
            _console_error("missing required script {}".format(script))
            self.exiting(1)
        if name not in self._scripts:
            logger.debug("loading script {}".format(name))
            with open(script, 'r') as f:
                self._scripts[name] = f.read()
        return self._scripts[name]

    def known_dependency(self, package):
        """Check if we know a dependency."""
        known = package in self._tracked_depends
        self._tracked_depends.append(package)
        return known

    def get_cache_files(self):
        """Get cache file list."""
        for f in os.listdir(self._cache_dir):
            name, ext = os.path.splitext(f)
            if ext in _CACHE_FILES:
                yield (f, os.path.join(self._cache_dir, f))

    def cache_file(self, file_name, ext=_CACHE_FILE):
        """Get a cache file."""
        if not os.path.exists(self._cache_dir):
            logger.error("cache directory has gone missing")
            self.exiting(1)
        return os.path.join(self._cache_dir, file_name + ext)

    def _get_dbs(self):
        """Get sync'd dbs."""
        if self._sync:
            return
        self._sync = self.handle.get_syncdbs()

    def get_packages(self):
        """Get mirror packages."""
        self._get_dbs()
        syncpkgs = set()
        for db in self._sync:
            syncpkgs |= set(p.name for p in db.pkgcache)
        return syncpkgs

    def check_repos(self, package_name):
        """Check repos for a package."""
        self._get_dbs()
        for db in self._sync:
            pkg = db.get_pkg(package_name)
            if pkg is not None:
                return True
        return False

    def pacman(self, args, require_sudo=True):
        """Call pacman."""
        cmd = []
        logger.debug("calling pacman")
        if require_sudo and not self.root:
            if self.can_sudo:
                cmd.append("/usr/bin/sudo")
            else:
                _console_error("sudo required but not allowed, re-run as root")
                self.exiting(1)
        cmd.append("/usr/bin/pacman")
        cmd = cmd + args
        logger.trace(cmd)
        returncode = subprocess.call(cmd)
        logger.trace(returncode)
        return returncode == 0

    def check_pkgcache(self, name):
        """Check the pkgcache."""
        if self._pkgcaching is None:
            self._pkgcaching = self.get_packages()
        for pkg in self.db.pkgcache:
            if pkg.name == name:
                return True
        return False

    def unlock(self):
        """Unlock an instance."""
        logger.debug("unlocking")
        if os.path.exists(self._lock_file):
            os.remove(self._lock_file)
            logger.debug("unlocked")

    def lock(self):
        """Lock to a single instance."""
        logger.debug("locking")
        if not os.path.exists(self._lock_file):
            logger.debug("locked")
            with open(self._lock_file, 'w') as f:
                obj = {}
                obj["time"] = str(self.now)
                obj["pid"] = str(os.getpid())
                logger.trace(obj)
                f.write(json.dumps(obj))
            return
        _console_error("lock file exists")
        _console_error("only one instance of naaman may run at a time")
        _console_error("delete {} if this is an error".format(self._lock_file))
        exit(1)


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
        if args.upgrades or args.search or args.clean:
            call_on("sync function")
            sub_count = 0
            if args.upgrades:
                sub_count += 1
            if args.clean:
                sub_count += 1
            if args.search:
                sub_count += 1
            if sub_count != 1:
                _console_error("cannot perform multiple sub-options")
                invalid = True
        if args.search or (not args.upgrades and not args.clean):
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

    if not invalid and (args.search or args.upgrades or args.clean):
        if not args.sync:
            _console_error("search, upgrade, and clean are sync only")
            invalid = True

    if not invalid and args.gone and not args.query:
        _console_error("gone only works with query")
        invalid = True

    if not invalid and need_targets:
        if len(unknown) == 0:
            _console_error("no targets specified")
            invalid = True

    if not args.pacman or not os.path.exists(args.pacman):
        _console_error("invalid config file")
        invalid = True

    ctx = Context(unknown, groups, args)
    callback = None
    if not invalid:
        if args.query:
            if args.gone:
                callback = _gone
            else:
                callback = _query
        if args.search:
            callback = _search
        if args.upgrades:
            callback = _upgrades
        if args.clean:
            callback = _clean
        if args.sync:
            if not args.search and not args.upgrades and not args.clean:
                callback = _sync
        if args.remove:
            callback = _remove

    if not invalid and callback is None:
        _console_error("unable to find callback")
        invalid = True

    if invalid:
        ctx.exiting(1)
    callback(ctx)


def _clean(context):
    """Clean cache files."""
    logger.debug("cleaning requested")
    files = [x for x in context.get_cache_files()]
    if len(files) == 0:
        _console_output("nothing to cleanup")
        return
    _confirm(context, "clear cache files", [x[0] for x in files])
    for f in files:
        _console_output("removing {}".format(f[0]))
        os.remove(f[1])


def _confirm(context, message, package_names):
    """Confirm package changes."""
    if not context.confirm:
        logger.debug("no confirmation needed.")
        return
    logger.info("")
    for p in package_names:
        logger.info("  -> {}".format(p))
    logger.info("")
    msg = " ===> {}, (Y/n)? ".format(message)
    logger.trace(msg)
    c = input(msg)
    logger.trace(c)
    if c == "n":
        _console_error("user cancelled")
        context.exiting(1)


def _shell(command, suppress_error=False, workingdir=None):
    """Run a shell command."""
    logger.debug("shell")
    logger.trace(command)
    logger.trace(workingdir)
    sp = subprocess.Popen(command,
                          cwd=workingdir,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    out, err = sp.communicate()
    logger.trace(out)
    if suppress_error:
        logger.trace(err)
    else:
        if err and len(err) > 0:
            logger.error(err)
    return out


def _install(file_definition, makepkg, cache_dirs, can_sudo, script_text):
    """Install a package."""
    sudo = ""
    if can_sudo:
        sudo = "sudo"
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
        replaces = {}
        replaces["DIRECTORY"] = f_dir
        replaces["MAKEPKG"] = " ".join(makepkg)
        replaces["SUDO"] = sudo
        script = script_text
        for r in replaces:
            script = script.replace("{" + r + "}", replaces[r])
        with open(temp_sh, 'w') as f:
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


def _get_deltahours(input_str, now):
    """Get a timedelta in hours."""
    logger.debug("timedelta (hours)")
    last = datetime.fromtimestamp(float(input_str))
    seconds = (now - last).total_seconds()
    minutes = seconds / 60
    hours = minutes / 60
    logger.trace((last, seconds, minutes, hours))
    return hours


def _check_vcs_ignore(context, threshold):
    """VCS caching check."""
    logger.debug("checking vcs ignore cache")
    cache_check = context.cache_file("vcs")
    update_cache = True
    result = None
    now = context.now
    current_time = context.timestamp
    # we have a cache item, has necessary time elapsed?
    if os.path.exists(cache_check):
        with open(cache_check, 'r') as f:
            hours = _get_deltahours(f.read(), now)
            if hours < threshold:
                update_cache = False
                result = True
    if update_cache:
        logger.info("updating vcs last cache time")
        with open(cache_check, 'w') as f:
            f.write(str(current_time))
    return result


def _ignore_for(context, ignore_for, ignored):
    """Ignore for settings."""
    logger.debug("checking ignored packages.")
    ignore_file = context.cache_file("ignoring")
    ignore_definition = {}
    now = context.now
    current_time = context.timestamp
    if os.path.exists(ignore_file):
        with open(ignore_file, 'r') as f:
            ignore_definition = json.loads(f.read())
    logger.trace(ignore_definition)
    for i in ignore_for:
        if "=" not in i:
            logger.warn("invalid ignore definition {}".format(i))
            continue
        parts = i.split("=")
        if len(parts) != 2:
            logger.warn("invalid ignore format {}".format(i))
        package = parts[0]
        hours = 0
        try:
            hours = int(parts[1])
            if hours < 1:
                raise Exception("hour must be >= 1")
        except Exception as e:
            logger.warn("invalid hour value {}".format(i))
            logger.trace(e)
            continue
        update = True
        if package in ignore_definition:
            last = _get_deltahours(float(ignore_definition[package]), now)
            if last < hours:
                ignored.append(package)
                update = False
        if update:
            ignore_definition[package] = str(current_time)
    with open(ignore_file, 'w') as f:
        logger.debug("writing ignore definitions")
        f.write(json.dumps(ignore_definition))


def _syncing(context, can_install, targets, updating):
    """Sync/install packages."""
    if context.root:
        _console_error("can not run install/upgrades as root (uses makepkg)")
        context.exiting(1)
    args = context.groups[_SYNC_UP_OPTIONS]
    ignored = args.ignore
    if not ignored or args.force_refresh:
        ignored = []
    no_vcs = False
    if args.no_vcs or (args.refresh and not args.force_refresh):
        no_vcs = True
    if args.vcs_ignore > 0 and not args.force_refresh:
        context.lock()
        try:
            if _check_vcs_ignore(context, args.vcs_ignore) is not None:
                no_vcs = True
        except Exception as e:
            logger.error("unexpected vcs error")
            logger.error(e)
        context.unlock()
    logger.debug("novcs? {}".format(no_vcs))
    if args.ignore_for and len(args.ignore_for) > 0 and not args.force_refresh:
        context.lock()
        try:
            _ignore_for(context, args.ignore_for, ignored)
        except Exception as e:
            logger.error("unexpected ignore_for error")
            logger.error(e)
        context.unlock()
    logger.trace("ignoring {}".format(ignored))
    check_inst = []
    for name in targets:
        if name in ignored:
            _console_output("{} is ignored".format(name))
            continue
        if no_vcs and _is_vcs(name):
            logger.debug("skipping vcs package {}".format(name))
            continue
        package = _rpc_search(name, True, context)
        if package:
            check_inst.append(package)
        else:
            _console_error("unknown AUR package: {}".format(name))
            context.exiting(1)
    inst = []
    for item in context.reorders:
        obj = [x for x in check_inst if x.name == item]
        if len(obj) > 0:
            inst += obj
    for item in check_inst:
        obj = [x for x in inst if x.name == item.name]
        if len(obj) == 0:
            inst += [item]
    logger.trace(inst)
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
                context.exiting(1)
        logger.trace(i)
        if vcs:
            vers = vcs
        report.append("{} {}{}".format(i.name, vers, tag))
        do_install.append(i)
    if len(do_install) == 0:
        _console_output("nothing to do")
        context.exiting(0)
    _confirm(context, "install packages", report)
    makepkg = context.get_custom_arg(_CUSTOM_MAKEPKG)
    logger.debug("makepkg {}".format(makepkg))
    cache = context.handle.cachedirs
    cache_dirs = ""
    if not args.no_cache and cache and len(cache) > 0:
        for c in cache:
            if " " in c:
                logger.warn("cache dir with space is skipped ({})".format(c))
                continue
        cache_dirs = " ".join(['{}'.format(x) for x in cache if " " not in x])
    context.lock()
    try:
        for i in do_install:
            if not _install(i,
                            makepkg,
                            cache_dirs,
                            context.can_sudo,
                            context.load_script("makepkg")):
                _console_error("error installing package: {}".format(i.name))
    except Exception as e:
        logger.error("unexpected install error")
        logger.error(e)
    context.unlock()


def _get_deps(pkgs, name):
    """Dependency resolution."""
    # NOTE: This will fail at a complicated tree across a variety of packages
    deps = []
    logger.debug('getting deps')
    logger.trace(name)
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
    names = []
    for d in deps:
        if d.name in names:
            continue
        names.append(d.name)
    _syncing(context, False, names, True)


def _remove(context):
    """Remove package."""
    p = list(_do_query(context))
    _confirm(context,
             "remove packages",
             ["{} {}".format(x.name, x.version) for x in p])
    removals = context.get_custom_arg(_CUSTOM_REMOVAL)
    call_with = ['-R']
    if len(removals) > 0:
        call_with = call_with + removals
    call_with = call_with + [x.name for x in p]
    result = context.pacman(call_with)
    if not result:
        _console_error("unable to remove packages")
        context.exiting(1)
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


def _handle_deps(root_package, context, dependencies):
    """Handle dependencies resolution."""
    logger.debug("resolving deps")
    missing = False
    syncpkgs = context.get_packages()
    for d in dependencies:
        logger.debug(d)
        if context.targets and d in context.targets:
            logger.debug("installing it")
            root = context.targets.index(root_package)
            pos = context.targets.index(d)
            if pos > root:
                if context.reorder_deps:
                    logger.info("switching {} and {}".format(d, root_package))
                    context.reorders.append(d)
                else:
                    _console_error("verify order of target/deps")
                    context.exiting(1)
            continue
        if context.known_dependency(d):
            logger.debug("known")
            continue
        search = _rpc_search(d, True, context)
        if search is None:
            logger.debug("not aur")
            continue
        if context.check_pkgcache(d):
            logger.debug("installed")
            continue
        _console_error("unmet AUR dependency: {}".format(d))
        missing = True
    if missing:
        context.exiting(1)


def _rpc_caching(package_name, context):
    """rpc caching area/check."""
    now = context.now
    use_file_name = "rpc-"
    for char in package_name:
        c = char
        if not c.isalnum() and c not in ['-']:
            c = "_"
        use_file_name += c
    cache_file = context.cache_file(use_file_name)
    logger.debug(cache_file)
    cache = False
    return_factory = None
    return_cache = None
    if os.path.exists(cache_file):
        mtime = os.path.getmtime(cache_file)
        last = datetime.fromtimestamp(mtime)
        seconds = (now - last).total_seconds()
        minutes = seconds / 60
        logger.trace(minutes)
        logger.trace(context.rpc_cache)
        if minutes > context.rpc_cache:
            os.remove(cache_file)
            logger.debug("over rpc cache threshold")
            cache = True
        else:
            def _open(url):
                logger.debug("opening cache")
                return open(cache_file, 'rb')
            return_factory = _open
    else:
        cache = True
    if cache:
        return_cache = cache_file
    return return_cache, return_factory


def _rpc_search(package_name, exact, context):
    """Search for a package in the aur."""
    if exact and context.check_repos(package_name):
        logger.debug("in repos")
        return None
    if exact:
        url = _AUR_INFO
    else:
        url = _AUR_SEARCH
    url = url.format(urllib.parse.quote(package_name))
    logger.debug(url)
    factory = None
    caching = None
    if exact and context.rpc_cache > 0 and not context.force_refresh:
        logger.debug("rpc cache enabled")
        context.lock()
        try:
            c, f = _rpc_caching(package_name, context)
            factory = f
            caching = c
            logger.trace((c, f))
        except Exception as e:
            logger.error("unexpected rpc cache error")
            logger.error(e)
        context.unlock()
    if factory is None:
        factory = urllib.request.urlopen
    try:
        with factory(url) as req:
            result = req.read()
            if caching:
                logger.debug('writing cache')
                with open(caching, 'wb') as f:
                    f.write(result)
            j = json.loads(result.decode("utf-8"))
            if "error" in j:
                _console_error(j['error'])
            result_json = []
            if _RESULT_JSON in j:
                result_json = j[_RESULT_JSON]
            if len(result_json) > 0:
                for result in result_json:
                    try:
                        name = _get_segment(result, _AUR_NAME)
                        desc = _get_segment(result, _AUR_DESC)
                        vers = _get_segment(result, _AUR_VERS)
                        if exact:
                            if name == package_name:
                                deps = None
                                if context.deps:
                                    if _AUR_DEPS in result:
                                        _aur_deps = result[_AUR_DEPS]
                                        _handle_deps(package_name,
                                                     context,
                                                     _aur_deps)
                                else:
                                    logger.debug("no dependency checks")
                                return AURPackage(name,
                                                  vers,
                                                  result[_AUR_URLP])
                        else:
                            ind = ""
                            if not name or not desc or not vers:
                                logger.debug("unable to read this package")
                                logger.trace(result)
                            if context.quiet:
                                logger.info(name)
                                continue
                            if context.db.get_pkg(name) is not None:
                                ind = " [installed]"
                            logger.info("aur/{} {}{}".format(name, vers, ind))
                            if not desc or len(desc) == 0:
                                desc = "no description"
                            logger.info("    {}".format(desc))
                    except Exception as e:
                        logger.error("unable to parse package")
                        logger.error(e)
                        logger.trace(result)
                        break
    except Exception as e:
        logger.error("error calling AUR search")
        logger.error(e)


def _search(context):
    """Perform a search."""
    if len(context.targets) != 1:
        _console_error("please provide ONE target for search")
        context.exiting(1)
    for target in context.targets:
        logger.debug("searching for {}".format(target))
        if len(target) < _AUR_TARGET_LEN:
            # NOTE: we are suppressing this ourselves
            logger.debug("target name too short")
            continue
        _rpc_search(target, False, context)


def _query(context):
    """Perform query."""
    _querying(context, False)


def _gone(context):
    """Perform query for dropped aur packages."""
    _querying(context, True)


def _querying(context, gone):
    """Querying for package information."""
    for q in _do_query(context):
        if gone:
            found = _rpc_search(q.name, True, context)
            if found:
                continue
        if context.quiet:
            output = "{}"
        else:
            output = "{} {}"
        logger.info(output.format(q.name, q.version))


def _is_aur_pkg(pkg, sync_packages):
    """Detect AUR package."""
    return pkg.name not in sync_packages


def _do_query(context):
    """Query pacman."""
    syncpkgs = context.get_packages()
    if len(context.targets) > 0:
        for target in context.targets:
            pkg = context.db.get_pkg(target)
            valid = False
            if pkg and _is_aur_pkg(pkg, syncpkgs):
                    yield pkg
            else:
                _console_error("unknown package: {}".format(target))
                context.exiting(1)
    else:
        for pkg in context.db.pkgcache:
            if _is_aur_pkg(pkg, syncpkgs):
                yield pkg


def _query_options(parser):
    """Get query options."""
    group = parser.add_argument_group(_QUERY_OPTIONS)
    group.add_argument('-g', "--gone",
                       help="""specifying this option will check for packages
installed from the AUR but are no longer in the AUR.""",
                       action="store_true")


def _sync_up_options(parser):
    """Sync/update options."""
    group = parser.add_argument_group(_SYNC_UP_OPTIONS)
    group.add_argument("--ignore-for",
                       metavar='N',
                       type=str,
                       nargs='+',
                       help="""ignore packages for periods of time (hours).
specifying this options allows for ignoring certain packages over time.
this is specified as <package>=<hours>, where <package> will only check
for updates every <hours> period.""")
    group.add_argument('--vcs-ignore',
                       type=int,
                       default=720,
                       help="""time betweeen vcs update checks (hours).
specifying this option will result in vcs-based AUR packages to only be
updated (they will always update) every <hour> threshold.
default is 720 (30 days)""")
    group.add_argument('--no-vcs',
                       help="""perform all sync operations but
skip updating any vcs packages. this will allow for performing various
sync operations without always having vcs packages updating.""",
                       action='store_true')
    group.add_argument('-y', '--refresh',
                       help="""refresh non-vcs packages if there are updates
in the AUR for the package. packages with detected updates in the AUR will be
refreshed.""",
                       action='store_true')
    group.add_argument('-yy', '--force-refresh',
                       help="""similar to -y but will force refresh over any
--ignore, --ignore-for, --vcs-ignore and disable any rpc caching. Use this
option to make sure all packages are updated.""",
                       action='store_true')
    group.add_argument("--ignore",
                       help="ignore packages",
                       metavar='N',
                       type=str,
                       nargs='+')
    group.add_argument("--no-cache",
                       help="skip caching package files",
                       action="store_true")
    group.add_argument("--skip-deps",
                       help="skip dependency checks",
                       action="store_true")
    group.add_argument("--reorder-deps",
                       help="attempt to re-order dependency installs",
                       action="store_false")
    group.add_argument("--rpc-cache",
                       help="enable rpc caching (minutes)",
                       type=int,
                       default=60)


def _load_config(args, config_file):
    """Load configuration into arguments."""
    logger.debug('loading config file')
    with open(config_file, 'r') as f:
        dirs = dir(args)
        for l in f.readlines():
            line = l.strip()
            logger.trace(line)
            if line.startswith("#"):
                continue
            if not line or len(line) == 0:
                continue
            if "=" not in line:
                logger.warn("unable to read line, not k=v ({})".format(line))
                continue
            parts = line.split("=")
            key = parts[0]
            value = "=".join(parts[1:])
            if value.startswith('"') and value.endswith('"'):
                value = value[1:len(value) - 1]
            logger.trace((key, value))
            chars = [x for x in key if (x >= 'A' and x <= 'Z' or x in ["_"])]
            if len(key) != len(chars):
                logger.warn("invalid key")
                continue
            if key in ["IGNORE",
                       "PACMAN",
                       "RPC_CACHE",
                       "SKIP_DEPS",
                       "NO_CACHE",
                       "REMOVAL",
                       "SCRIPTS",
                       "IGNORE_FOR",
                       "MAKEPKG",
                       "NO_VCS",
                       "NO_SUDO",
                       "VCS_IGNORE"]:
                val = None
                lowered = key.lower()
                try:
                    if key in ["IGNORE", "MAKEPKG", "REMOVAL", "IGNORE_FOR"]:
                        arr = None
                        if key in dirs:
                            arr = getattr(args, lowered)
                        else:
                            dirs.append(key)
                        if arr is None:
                            arr = []
                        if value is not None:
                            arr.append(value)
                            setattr(args, lowered, arr)
                    elif key in ["NO_VCS",
                                 "NO_SUDO",
                                 "SKIP_DEPS",
                                 "NO_CACHE",
                                 "REORDER_DEPS"]:
                        val == value == "True"
                    elif key in ["VCS_IGNORE", "RPC_CACHE"]:
                        val = int(value)
                    else:
                        val = value
                except Exception as e:
                    logger.error("unable to read value")
                    logger.error(e)
                if val:
                    logger.trace('parsed')
                    logger.trace((key, val))
                    setattr(args, lowered, val)
            else:
                logger.warn("unknown configuration key")
    return args


def _manual_args(args):
    """Manual arg parse."""
    if args.refresh and not args.force_refresh:
        import sys
        if len(sys.argv) > 0:
            checks = [x for x in sys.argv if x.startswith("-") and "y" in x]
            for check in checks:
                if "yy" in check:
                    args.force_refresh = True
                    break
    if args.refresh or args.force_refresh:
        if not args.upgrades:
            logger.debug('forcing upgrade')
            args.upgrades = True


def main():
    """Entry point."""
    cache_dir = BaseDirectory.xdg_cache_home
    cache_dir = os.path.join(cache_dir, _NAME)
    parser = argparse.ArgumentParser()
    parser.add_argument('-S', '--sync',
                        help="synchronize packages",
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
    parser.add_argument('-c', '--clean',
                        help="clean the cache",
                        action="store_true")
    parser.add_argument('--version',
                        help="display version",
                        action='store_true')
    parser.add_argument('--no-sudo',
                        help="disable calling sudo",
                        action='store_true')
    parser.add_argument('--verbose',
                        help="verbose output",
                        action='store_true')
    parser.add_argument('--trace',
                        help="trace debug logging",
                        action='store_true')
    parser.add_argument('--pacman',
                        help='pacman config',
                        default='/etc/pacman.conf')
    parser.add_argument('--config',
                        help='naaman config',
                        default=os.path.join(BaseDirectory.xdg_config_home,
                                             'naaman.conf'))
    parser.add_argument('--no-confirm',
                        help="naaman will not ask for confirmation",
                        action="store_true")
    parser.add_argument('-q', '--quiet',
                        help='quiet various parts of naaman to display less',
                        action="store_true")
    parser.add_argument('--cache-dir',
                        help="cache dir for naaman",
                        default=cache_dir)
    parser.add_argument('--no-config',
                        help='do not load the config file',
                        action="store_true")
    _sync_up_options(parser)
    _query_options(parser)
    args, unknown = parser.parse_known_args()
    if args.version:
        print("{} ({})".format(_NAME, _VERSION))
        exit(0)
    ch = logging.StreamHandler()
    if not os.path.exists(args.cache_dir):
        logger.debug("creating cache dir")
        os.makedirs(args.cache_dir)
    fh = logging.FileHandler(os.path.join(args.cache_dir, _NAME + '.log'))
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

    def noop_trace(obj):
        """No-operation trace."""
        pass

    trace_call = noop_trace
    if args.trace:
        def trace_log(obj):
            logger.debug(obj)
        trace_call = trace_log
    setattr(logger, "trace", trace_call)
    logger.trace("files/folders")
    logger.trace(args.cache_dir)
    logger.trace(args.config)
    if os.path.exists(args.config):
        if args.no_config:
            logger.debug("not loading config")
        else:
            args = _load_config(args, args.config)
    else:
        logger.debug('no config')
    _manual_args(args)
    arg_groups = {}
    dirs = dir(args)
    custom_args = {}
    for k in _DEFAULT_OPTS:
        if k not in dirs:
            logger.debug('setting default for {}'.format(k))
            setattr(args, k, _DEFAULT_OPTS[k])
        custom_args[k] = getattr(args, k)
    arg_groups[_CUSTOM_ARGS] = custom_args
    for group in parser._action_groups:
        g = {a.dest: getattr(args, a.dest, None) for a in group._group_actions}
        arg_groups[group.title] = argparse.Namespace(**g)
    logger.trace(arg_groups)
    _validate_options(args, unknown, arg_groups)


if __name__ == "__main__":
    main()
