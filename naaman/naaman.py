#!/usr/bin/python
"""
N(ot) A(nother) A(UR) Man(ager).

Is an AUR wrapper/manager that uses pacman as it's backing data store.
"""
import argparse
import os
import getpass
import pyalpm
import urllib.request
import urllib.parse
import json
import signal
import tempfile
import subprocess
import shutil
import time
import naaman.arguments.custom as csm_args
import naaman.arguments.utils as util_args
import naaman.arguments.query as query_args
import naaman.arguments.syncup as sync_args
import naaman.shell as sh
import naaman.version as vers
import naaman.aur as aur
import naaman.logger as log
import naaman.consts as cst
import naaman.pkgbuild as pkgbld
from datetime import datetime, timedelta
from xdg import BaseDirectory
from pycman import config

logger = log.LOGGER

_AUR = "https://aur.archlinux.org{}"
_AUR_GIT = _AUR.format("/{}.git")
_RESULT_JSON = 'results'
_AUR_NAME = "Name"
_AUR_DESC = "Description"
_AUR_RAW_URL = _AUR.format("/rpc?v=5&type={}&arg{}")
_AUR_INFO = _AUR_RAW_URL.format("info", "[]={}")
_AUR_SEARCH = _AUR_RAW_URL.format("search&by=name-desc", "={}")
_AUR_VERS = "Version"
_AUR_URLP = "URLPath"
_AUR_DEPS = "Depends"
_AUR_TARGET_LEN = 4

_CACHE_FILE = ".cache"
_LOCKS = ".lck"
_CACHE_FILES = [_CACHE_FILE, _LOCKS]
_TMP_PREFIX = "naaman."

_DOWNLOAD_GIT = "git"
_DOWNLOAD_TAR = "tar"
_DOWNLOAD_DETECT = "detect"
_DOWNLOADS = [_DOWNLOAD_GIT, _DOWNLOAD_TAR, _DOWNLOAD_DETECT]


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
        self.info = args.info
        self.info_verbose = args.info_verbose
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
        self._custom_args = self.groups[csm_args.CUSTOM_ARGS]
        self._script_dir = self.get_custom_arg(csm_args.CUSTOM_SCRIPTS)
        self.now = datetime.now()
        self.timestamp = self.now.timestamp()
        self.terminal_width = 0
        self.use_git = False
        if args.download and args.download in [_DOWNLOAD_GIT,
                                               _DOWNLOAD_DETECT]:
            git = sh.has_git(args.download != _DOWNLOAD_DETECT)
            if git is not None:
                self.use_git = git
            else:
                self.exiting(1)
        self.builds = args.builds
        if self.builds:
            if not os.path.isdir(self.builds):
                log.console_error("invalid build: {}".format(self.builds))
                self.exiting(1)
            self.builds = os.path.join(self.builds, cst.NAME)
            if not os.path.exists(self.builds):
                os.makedirs(self.builds)
        try:
            rows, columns = os.popen('stty size', 'r').read().split()
            self.terminal_width = int(columns)
        except Exception as e:
            logger.debug("unable to determine tty column size")
            logger.debug(e)
        self.skip_split = args.on_split == pkgbld.SPLIT_SKIP
        self.error_split = args.on_split == pkgbld.SPLIT_ERR
        self.do_split = args.on_split == pkgbld.SPLIT_SPLIT
        if self.use_git and \
           (self.skip_split or self.error_split or self.do_split):
            log.console_error("split package options not available for git")
            self.exiting(1)

        def sigint_handler(signum, frame):
            """Handle ctrl-c."""
            log.console_error("CTRL-C")
            self.exiting(1)
        signal.signal(signal.SIGINT, sigint_handler)

    def build_dir(self):
        """Get a build file area."""
        dir_name = None
        logger.debug("getting tempfile")
        if self.builds:
            dir_name = self.builds
        logger.debug("using {}".format(dir_name))
        return tempfile.TemporaryDirectory(dir=dir_name, prefix=_TMP_PREFIX)

    def get_custom_arg(self, name):
        """Get custom args."""
        if name not in self._custom_args:
            log.console_error("custom argument missing")
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
            log.console_error("missing required script {}".format(script))
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

    def get_cache_pkgs(self):
        """Get the cache pkgs location."""
        return os.path.join(self._cache_dir, "pkg")

    def get_cache_dirs(self):
        """Get cache directories for any builds."""
        if self.builds:
            def remove_fail(func, path, err):
                logger.debug("failed on removal")
                logger.debug(path)
                logger.debug(err)
                log.console_error("unable to cleanup {}".format(path))
            for f in os.listdir(self.builds):
                b_dir = os.path.join(self.builds, f)
                if not os.path.isdir(b_dir):
                    continue
                logger.debug(b_dir)
                yield b_dir
        cache_dir = self.get_cache_pkgs()
        if os.path.exists(cache_dir):
            yield self.get_cache_pkgs()

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
                log.console_error(
                    "sudo required but not allowed, re-run as root")
                self.exiting(1)
        cmd.append("/usr/bin/pacman")
        cmd = cmd + args
        logger.trace(cmd)
        returncode = subprocess.call(cmd)
        logger.trace(returncode)
        return returncode == 0

    def check_pkgcache(self, name, version):
        """Check the pkgcache."""
        if self._pkgcaching is None:
            self._pkgcaching = self.get_packages()
        for pkg in self.db.pkgcache:
            if pkg.name == name:
                if version is not None:
                    if pkg.version < version:
                        continue
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
        log.console_error("lock file exists")
        log.console_error("only one instance of naaman may run at a time")
        log.console_error(
            "delete {} if this is an error".format(self._lock_file))
        exit(1)


def _validate_options(args, unknown, groups):
    """Validate argument options."""
    valid_count = 0
    invalid = False
    need_targets = False
    call_on = None

    if (args.search or args.query) and not args.verbose:
        def no_call(name):
            pass
        call_on = no_call
    else:
        def action(name):
            log.console_output("performing {}".format(name))
        call_on = action

    if args.sync:
        call_on("sync")
        valid_count += 1
        if args.upgrades or args.search or args.clean or args.deps:
            sub_count = 0
            sub_command = None
            if args.upgrades:
                sub_command = "upgrade"
                sub_count += 1
            if args.clean:
                sub_command = "clean"
                sub_count += 1
            if args.search:
                sub_count += 1
            if args.deps:
                sub_count += 1
                sub_command = "deps"
            if sub_count == 1:
                if sub_command is not None:
                    call_on("sync: {}".format(sub_command))
            else:
                log.console_error("cannot perform multiple sub-options")
                invalid = True
        if args.search or args.deps or (not args.upgrades and
                                        not args.clean and
                                        not args.deps):
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
            log.console_error("multiple top-level arguments given")
        elif valid_count == 0:
            log.console_error("no valid top-level arguments given")
        if valid_count != 1:
            invalid = True

    if not invalid and (args.search or args.upgrades or args.clean):
        if not args.sync:
            log.console_error("search, upgrade, and clean are sync only")
            invalid = True

    if not invalid and args.info and not args.search:
        log.console_error("info only works with search")
        invalid = True

    if not invalid and args.info and args.quiet:
        log.console_error("info and quiet do not work together")
        invalid = True

    if not invalid and args.gone and not args.query:
        log.console_error("gone only works with query")
        invalid = True

    if not invalid and need_targets:
        if len(unknown) == 0:
            log.console_error("no targets specified")
            invalid = True

    if not args.pacman or not os.path.exists(args.pacman):
        log.console_error("invalid config file")
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
        if args.deps:
            callback = _deps
        if args.sync:
            if not args.search and \
               not args.upgrades and \
               not args.clean and \
               not args.deps:
                callback = _sync
        if args.remove:
            callback = _remove

    if not invalid and callback is None:
        log.console_error("unable to find callback")
        invalid = True

    if invalid:
        ctx.exiting(1)
    callback(ctx)


def _load_deps(depth, packages, context, resolved, last_report):
    """Load dependencies for a package."""
    timed = datetime.now()
    if last_report is not None:
        seconds = (timed - last_report).total_seconds()
        if seconds > 5:
            log.console_output('still working...')
        else:
            timed = last_report
    if packages is None or len(packages) == 0:
        return timed
    for p in packages:
        matched = [x for x in resolved if x[1] == p]
        if len(matched) > 0:
            continue
        logger.debug("resolving dependencies level {}, {}".format(depth, p))
        dependency = aur.deps_compare(p)
        p = dependency.pkg
        if context.check_pkgcache(p, dependency.version):
            continue
        pkg = _rpc_search(p, True, context, include_deps=True)
        if pkg is None:
            logger.debug("non-aur {}".format(p))
            continue
        timed = _load_deps(depth + 1, pkg.deps, context, resolved, timed)
        resolved.append((depth, p))
    return timed


def _deps(context):
    """Handle dependency resolution."""
    logger.debug("attempt dependency resolution")
    context.deps = False
    targets = context.targets
    for target in targets:
        resolved = []
        logger.debug("resolving {}".format(target))
        pkg = _rpc_search(target, True, context, include_deps=True)
        if pkg is None:
            log.console_error("unable to find package: {}".format(target))
            continue
        if pkg.deps is not None and len(pkg.deps) > 0:
            _load_deps(1, pkg.deps, context, resolved, None)
            resolved.append((0, target))
            actual = reversed(sorted(resolved, key=lambda x: x[0]))
            logger.debug(actual)
            context.targets = [x[1] for x in actual]
        else:
            logger.debug("no deps...")
            context.targets = [target]
        logger.trace(resolved)
        _sync(context)


def _clean(context):
    """Clean cache files."""
    logger.debug("cleaning requested")
    files = [x for x in context.get_cache_files()]
    if len(files) == 0:
        log.console_output("no files to cleanup")
    else:
        _confirm(context, "clear cache files", [x[0] for x in files])
        for f in files:
            log.console_output("removing {}".format(f[0]))
            os.remove(f[1])
    dirs = [x for x in context.get_cache_dirs()]
    if len(dirs) == 0:
        log.console_output("no directories to cleanup")
    else:
        _confirm(context, "clear cache directories", [x for x in dirs])

        def remove_fail(func, path, err):
            logger.debug("failed on removal")
            logger.debug(path)
            logger.debug(err)
            log.console_error("unable to cleanup {}".format(path))
        for d in dirs:
            shutil.rmtree(d, onerror=remove_fail)


def _confirm(ctx, message, package_names, default_yes=True):
    """Confirm package changes."""
    exiting = sh.confirm(message, package_names, default_yes, ctx.confirm)
    if exiting is not None:
        log.console_error("{}cancelled".format(exiting))
        ctx.exiting(1)


def _install(file_definition, makepkg, cache_dirs, context, version):
    """Install a package."""
    can_sudo = context.can_sudo
    script_text = context.load_script("makepkg")
    new_file = context.build_dir
    use_git = context.use_git
    sudo = ""
    if can_sudo:
        sudo = "sudo"
    url = _AUR.format(file_definition.url)
    action = "installing"
    if version is not None:
        action = "checking version"
    log.console_output("{}: {}".format(action, file_definition.name))
    with new_file() as t:
        p = os.path.join(t, file_definition.name)
        os.makedirs(p)
        f_dir = os.path.join(t, file_definition.name)
        if use_git:
            sh.shell(["git",
                      "clone",
                      "--depth=1",
                      _AUR_GIT.format(file_definition.name),
                      "."], suppress_error=True, workingdir=p)
        else:
            logger.debug("using tar")
            f_name = file_definition.name + ".tar.gz"
            file_name = os.path.join(p, f_name)
            logger.debug(file_name)
            urllib.request.urlretrieve(url, file_name)
            sh.shell(["tar", "xf", f_name, "--strip-components=1"],
                     workingdir=p)
            if context.skip_split or context.error_split or context.do_split:
                logger.debug("handling split packages")
                pkgbuild = os.path.join(f_dir, "PKGBUILD")
                logger.trace(pkgbuild)
                if not os.path.exists(pkgbuild):
                    raise Exception("unable to find PKGBUILD")
                split_result = pkgbld.splitting(pkgbuild,
                                                file_definition.name,
                                                context.skip_split,
                                                context.error_split,
                                                context.do_split)
                if split_result == pkgbld.SPLIT_ERRORED:
                    return False
                elif split_result == pkgbld.SPLIT_SKIPPED:
                    return True
        temp_sh = os.path.join(t, cst.NAME + ".sh")
        use_version = ""
        if version is not None:
            use_version = version
        replaces = {}
        replaces["DIRECTORY"] = f_dir
        replaces["MAKEPKG"] = " ".join(makepkg)
        replaces["SUDO"] = sudo
        replaces["VERSION"] = use_version
        replaces["CACHE"] = cache_dirs
        return sh.template_script(script_text, replaces, temp_sh)


def _sync(context):
    """Sync packages (install)."""
    _syncing(context, True, context.targets, False)


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
        log.console_output("updating vcs last cache time")
        with open(cache_check, 'w') as f:
            f.write(str(current_time))
    return result


def _check_vcs(package, context, version):
    """Check current vcs version."""
    result = _install(package, pkgbld.MAKEPKG_VCS, None, context,  version)
    if not result:
        log.console_output("up-to-date: {} ({})".format(package.name, version))
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


def _syncing(context, is_install, targets, updating):
    """Sync/install packages."""
    if context.root:
        log.console_error(
            "can not run install/upgrades as root (uses makepkg)")
        context.exiting(1)
    args = context.groups[sync_args.SYNC_UP_OPTIONS]
    ignored = args.ignore
    skip_filters = False
    if args.force_refresh or is_install:
        logger.debug('skip filtering options')
        skip_filters = True
    if not ignored or skip_filters:
        ignored = []
    no_vcs = False
    if args.no_vcs or (args.refresh and not skip_filters):
        no_vcs = True
    if not no_vcs and args.vcs_ignore > 0 and not skip_filters:
        context.lock()
        try:
            if _check_vcs_ignore(context, args.vcs_ignore) is not None:
                logger.trace("vcs ignore threshold met")
                no_vcs = True
        except Exception as e:
            logger.error("unexpected vcs error")
            logger.error(e)
        context.unlock()
    logger.debug("novcs? {}".format(no_vcs))
    if args.ignore_for and len(args.ignore_for) > 0 and not skip_filters:
        logger.debug("handling ignorefors")
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
            log.console_output("{} is ignored".format(name))
            continue
        vcs = aur.is_vcs(name)
        if no_vcs and vcs:
            logger.debug("skipping vcs package {}".format(name))
            continue
        package = _rpc_search(name, True, context)
        if package:
            if vcs and \
               not args.vcs_install_only and \
               args.force_refresh and \
               not args.force_force_refresh:
                logger.debug("checking vcs version")
                pkg = context.db.get_pkg(package.name)
                if pkg:
                    if not _check_vcs(package, context, pkg.version):
                        continue
                else:
                    logger.debug("unable to find installed package...")
            check_inst.append(package)
        else:
            log.console_error("unknown AUR package: {}".format(name))
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
        vcs = aur.is_vcs(i.name)
        if pkg:
            if pkg.version == i.version or vcs:
                if not vcs and updating:
                    continue
                tag = " [installed]"
        else:
            if not is_install:
                log.console_error("{} not installed".format(i.name))
                context.exiting(1)
        logger.trace(i)
        if vcs:
            vers = vcs
        report.append("{} {}{}".format(i.name, vers, tag))
        do_install.append(i)
    if len(do_install) == 0:
        log.console_output("nothing to do")
        context.exiting(0)
    _confirm(context, "install packages", report)
    makepkg = context.get_custom_arg(csm_args.CUSTOM_MAKEPKG)
    logger.debug("makepkg {}".format(makepkg))
    cache = context.handle.cachedirs
    cache_dirs = ""
    if not args.no_cache and cache and len(cache) > 0:
        use_caches = []
        for c in cache:
            if " " in c:
                logger.warn("cache dir with space is skipped ({})".format(c))
                continue
            use_caches.append(c)
        naaman_pkg = context.get_cache_pkgs()
        if not os.path.exists(naaman_pkg):
            os.makedirs(naaman_pkg)
        use_caches.append(naaman_pkg)
        cache_dirs = " ".join(['{}'.format(x) for x in use_caches])
    context.lock()
    try:
        for i in do_install:
            if not _install(i,
                            makepkg,
                            cache_dirs,
                            context,
                            None):
                log.console_error(
                    "error installing package: {}".format(i.name))
                next_pkgs = []
                after = False
                for e in do_install:
                    if e.name == i.name:
                        after = True
                        continue
                    if not after:
                        continue
                    next_pkgs.append(e.name)
                if len(next_pkgs) > 0:
                    _confirm(context,
                             "attempt to continue",
                             next_pkgs,
                             default_yes=False)
    except Exception as e:
        logger.error("unexpected install error")
        logger.error(e)
    context.unlock()


def _upgrades(context):
    """Ordered upgrade."""
    pkgs = list(_do_query(context))
    deps = aur.get_deps(pkgs)
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
    removals = context.get_custom_arg(csm_args.CUSTOM_REMOVAL)
    call_with = ['-R']
    if len(removals) > 0:
        call_with = call_with + removals
    call_with = call_with + [x.name for x in p]
    result = context.pacman(call_with)
    if not result:
        log.console_error("unable to remove packages")
        context.exiting(1)
    log.console_output("packages removed")


def _handle_deps(root_package, context, dependencies):
    """Handle dependencies resolution."""
    logger.debug("resolving deps")
    missing = False
    syncpkgs = context.get_packages()
    for dep in dependencies:
        d = dep
        dependency = aur.deps_compare(d)
        d = dependency.pkg
        logger.debug(d)
        if context.targets and d in context.targets:
            logger.debug("installing it")
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
            logger.debug("known")
            continue
        search = _rpc_search(d, True, context)
        if search is None:
            logger.debug("not aur")
            continue
        if context.check_pkgcache(d, dependency.version):
            logger.debug("installed")
            continue
        show_version = ""
        if dependency.version is not None:
            show_version = " ({}{})".format(dependency.op, dependency.version)
        log.console_error("unmet AUR dependency: {}{}".format(d, show_version))
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


def _rpc_search(package_name, exact, context, include_deps=False):
    """Search for a package in the aur."""
    if exact and context.check_repos(package_name):
        logger.debug("in repos")
        return None
    if exact or context.info_verbose:
        url = _AUR_INFO
    else:
        url = _AUR_SEARCH
    url = url.format(urllib.parse.quote(package_name))
    logger.debug(url)
    factory = None
    caching = None
    found = False
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
                log.console_error(j['error'])
            result_json = []
            if _RESULT_JSON in j:
                result_json = j[_RESULT_JSON]
            if len(result_json) > 0:
                for result in result_json:
                    try:
                        name = aur.get_segment(result, _AUR_NAME)
                        desc = aur.get_segment(result, _AUR_DESC)
                        vers = aur.get_segment(result, _AUR_VERS)
                        found = True
                        if exact:
                            if name == package_name:
                                deps = None
                                if context.deps or include_deps:
                                    if _AUR_DEPS in result:
                                        _aur_deps = result[_AUR_DEPS]
                                        if context.deps:
                                            _handle_deps(package_name,
                                                         context,
                                                         _aur_deps)
                                        if include_deps:
                                            deps = _aur_deps
                                else:
                                    logger.debug("no dependency checks")
                                return aur.AURPackage(name,
                                                      vers,
                                                      result[_AUR_URLP],
                                                      deps)
                        else:
                            ind = ""
                            if not name or not desc or not vers:
                                logger.debug("unable to read this package")
                                logger.trace(result)
                            if context.quiet:
                                logger.info(name)
                                continue
                            if context.info:
                                keys = [k for k in result.keys()]
                                max_key = max([len(k) for k in keys]) + 3
                                spacing = ""
                                for i in range(0, max_key):
                                    spacing += " "
                                for k in keys:
                                    val = result[k]
                                    if isinstance(val, list):
                                        val = "  ".join(val)
                                    elif isinstance(val, str):
                                        val = aur.get_segment(result, k)
                                    elif val and k in ["FirstSubmitted",
                                                       "LastModified"]:
                                        val = str(datetime.fromtimestamp(val))
                                    else:
                                        val = str(val)
                                    use_key = "{}   {}".format(k, spacing)
                                    use_key = use_key[0:max_key - 2] + ": "
                                    log.terminal_output(val,
                                                        context.terminal_width,
                                                        use_key,
                                                        spacing)
                                logger.info("")
                                continue
                            if context.db.get_pkg(name) is not None:
                                ind = " [installed]"
                            if aur.is_vcs(name):
                                ind += " [vcs]"
                            logger.info("aur/{} {}{}".format(name, vers, ind))
                            if not desc or len(desc) == 0:
                                desc = "no description"
                            log.terminal_output(desc,
                                                context.terminal_width,
                                                None,
                                                "    ")
                    except Exception as e:
                        logger.error("unable to parse package")
                        logger.error(e)
                        logger.trace(result)
                        break
    except Exception as e:
        logger.error("error calling AUR search")
        logger.error(e)
    if not found and context.info_verbose:
        log.console_error("no exact matches for {}".format(package_name))


def _search(context):
    """Perform a search."""
    if len(context.targets) != 1:
        log.console_error("please provide ONE target for search")
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
    matched = False
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
        matched = True
    if not matched and not context.quiet:
        log.console_output("no packages found")


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
                log.console_error("unknown package: {}".format(target))
                context.exiting(1)
    else:
        for pkg in context.db.pkgcache:
            if _is_aur_pkg(pkg, syncpkgs):
                yield pkg


def _load_config(args, config_file):
    """Load configuration into arguments."""
    logger.debug('loading config file: {}'.format(config_file))
    if not os.path.exists(config_file):
        logger.debug("does not exist")
        return args
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
                       "DOWNLAOD",
                       "SCRIPTS",
                       "VCS_INSTALL_ONLY",
                       "IGNORE_FOR",
                       "MAKEPKG",
                       "NO_VCS",
                       "BUILDS",
                       "ON_SPLIT",
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
                    key_checks = {}
                    key_checks["DOWNLOAD"] = _DOWNLOADS
                    key_checks["ON_SPLIT"] = pkgbld.SPLITS
                    if key in key_checks.keys():
                        if val not in key_checks[key]:
                            raise Exception("unknown {} type".format(key))
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


def main():
    """Entry point."""
    cache_dir = BaseDirectory.xdg_cache_home
    cache_dir = os.path.join(cache_dir, cst.NAME)
    config_file = os.path.join(BaseDirectory.xdg_config_home, cst.CONFIG)
    parser = argparse.ArgumentParser()
    parser.add_argument('-S', '--sync',
                        help="""synchronize packages (install/update). a sync
operation will attempt to install and/or update packages. -S by itself will
attempt to install a list of target packages.""",
                        action="store_true")
    parser.add_argument('-R', '--remove',
                        help="""remove a package. this will call pacman on any
AUR based packages and remove them if installed.""",
                        action="store_true")
    parser.add_argument('-Q', '--query',
                        help="""query package database. this option is used to
find out what AUR packages are currently installed on the system.""",
                        action="store_true")
    parser.add_argument('-u', '--upgrades',
                        help="""perform an upgrade of installed packages on the
the system. this will attempt to upgrade ALL AUR installed packages. a list of
target packages may also be passed.""",
                        action="store_true")
    parser.add_argument('-s', '--search',
                        help="""search for packages in the AUR. by passing a
package name to search the AUR rpc endpoints will be called to attempt to find
a package with a name or description matching this input string""",
                        action="store_true")
    parser.add_argument('-c', '--clean',
                        help="""clean the cache. this will clean the naaman
cache area of any cache files. this can be used to invalidate/remove old cache
information for deprecated packages or to reset duration caching options.""",
                        action="store_true")
    parser.add_argument('-d', '--deps',
                        help="""naaman will attempt to build a dependency chain
for the seperately  for each package specified. upon completion naaman will
attempt to install (after confirmation) the determined dependency chain.""",
                        action="store_true")
    parser.add_argument('--version',
                        help="display version information about naaman",
                        action='version',
                        version="{} ({})".format(cst.NAME, vers.__version__))
    parser.add_argument('--no-sudo',
                        help="""disable calling sudo. by default when naaman
has to call pacman directly (e.g. -R), it will call with sudo if required.
passing this option will prevent naaman from using sudo.""",
                        action='store_true')
    parser.add_argument('--verbose',
                        help="""verbose output. this setting will change the
output formatting and enable DEBUG level output. use this to begin to debug
naaman and to see more detail.""",
                        action='store_true')
    parser.add_argument('--trace',
                        help="""trace debug logging. this option is useful to
dump extensive naaman logging information for indepth troubleshooting or
debugging purposes.""",
                        action='store_true')
    parser.add_argument('--pacman',
                        help="""pacman config. when creating the pacman handle
naaman passes a configuration file to pacman for initialization via pyalpm.
this is NOT passed when calling pacman directly (e.g. -R).""",
                        default='/etc/pacman.conf')
    parser.add_argument('--config',
                        help="""naaman config. specify the (optional) naaman
configuration file to use. please use man naaman.conf for available options.
naaman will read configs in the order of (all optional): /etc, XDG_CONFIG_HOME
, and then --config""",
                        default=config_file)
    parser.add_argument('--no-confirm',
                        help="""naaman will not ask for confirmation. when
performing install, update, and remove operations naaman will ask for the user
to confirm the operation. to disable these prompts pass this option. this
option will not suppress makepkg or pacman prompts (use REMOVAL or MAKEPKG in
the naaman.conf)""",
                        action="store_true")
    parser.add_argument('-q', '--quiet',
                        help="""quiet various parts of naaman to display less.
certain operations will display more AUR package information that will be quiet
(displaying minimal package information) if this option is provided.""",
                        action="store_true")
    parser.add_argument('--cache-dir',
                        help="""cache dir for naaman. naaman stores caching and
logging information to this location. naaman will (attempt) to create this
directory if it does not exist.""",
                        default=cache_dir)
    parser.add_argument('--no-config',
                        help="""do not load the config file. to prevent naaman
from loading the configuration file when running specify this option. this can
allow running a specify instance of naaman without certain config options being
loaded.""",
                        action="store_true")
    parser.add_argument('--builds',
                        help="""the location where naaman will perform builds.
if not set this will be in the temp (e.g. /tmp) area. specifying this option
will move where makepkg operations are performed in the system.""",
                        default=None,
                        type=str)
    parser.add_argument('--download',
                        help="""specifies how to retrieve AUR packages from
the AUR repository. 'git' will (attempt, if git is installed) to git clone.
'tar' will download the tarball. 'detect' will try 'git' and fallback to
'tar'""",
                        default=_DOWNLOAD_DETECT,
                        choices=_DOWNLOADS,
                        type=str)
    parser.add_argument("--on-split",
                        help="""select what naaman should do when it encounters
a split package. 'skip' will not install split packages, 'error' will cause
naaman to error and stop, package, 'split' will attempt to split the package,
and 'nothing' will not process the package at all before install (default).""",
                        default=pkgbld.SPLIT_NONE,
                        choices=pkgbld.SPLITS,
                        type=str)
    sync_args.sync_up_options(parser)
    query_args.options(parser)
    args, unknown = parser.parse_known_args()
    log.init(args.verbose, args.trace, args.cache_dir)
    logger.trace("files/folders")
    logger.trace(args.cache_dir)
    logger.trace(args.config)
    if args.no_config:
        logger.debug("not loading config")
    else:
        loaded = []
        for f in ["/etc/" + cst.CONFIG, config_file, args.config]:
            if f in loaded:
                continue
            loaded.append(f)
            args = _load_config(args, f)
    util_args.manual_args(args)
    arg_groups = {}
    dirs = dir(args)
    custom_args = {}
    for k in csm_args.DEFAULT_OPTS:
        if k not in dirs:
            logger.debug('setting default for {}'.format(k))
            setattr(args, k, csm_args.DEFAULT_OPTS[k])
        custom_args[k] = getattr(args, k)
    arg_groups[csm_args.CUSTOM_ARGS] = custom_args
    for group in parser._action_groups:
        g = {a.dest: getattr(args, a.dest, None) for a in group._group_actions}
        arg_groups[group.title] = argparse.Namespace(**g)
    logger.trace(arg_groups)
    _validate_options(args, unknown, arg_groups)


if __name__ == "__main__":
    main()
