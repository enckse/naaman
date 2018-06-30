"""
Operating context for naaman operations.

Handles things like:
1. locking/unlocking instance
2. user state (is root?)
3. Caching information
4. Backing package store/caching
"""
import os
import getpass
import json
import signal
import tempfile
import subprocess
import naaman.arguments.custom as csm_args
import naaman.shell as sh
import naaman.logger as log
import naaman.consts as cst
import naaman.alpm as alpm
from datetime import datetime


_CACHE_FILE = ".cache"
_LOCKS = ".lck"
_CACHE_FILES = [_CACHE_FILE, _LOCKS]
_TMP_PREFIX = "naaman."


class Context(object):
    """Context for operations."""

    def __init__(self, targets, groups, args):
        """Init the context."""
        self.root = "root" == getpass.getuser()
        self.alpm = alpm.Alpm()
        self.targets = []
        if targets and len(targets) > 0:
            self.targets = targets
        self.handle = self.alpm.config(args.pacman)
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
        self.do_not_track = []
        if args.do_not_track and len(args.do_not_track) > 0:
            self.do_not_track = args.do_not_track
        self.rpc_cache = args.rpc_cache
        self._lock_file = os.path.join(self._cache_dir, "file" + _LOCKS)
        self.force_refresh = args.force_refresh
        self._custom_args = self.groups[csm_args.CUSTOM_ARGS]
        self.now = datetime.now()
        self.timestamp = self.now.timestamp()
        self.fetching = args.fetch
        self.makedeps = args.makedeps
        self.fetch_dir = "."
        self.rpc_field = args.rpc_field
        if args.fetch_dir and len(args.fetch_dir) > 0:
            valid = os.path.isdir(args.fetch_dir) and \
                    os.path.exists(args.fetch_dir)
            if not valid:
                log.console_error("invalid fetch directory")
                self.exiting(1)
            self.fetch_dir = args.fetch_dir
            log.trace(self.fetch_dir)
        self.builds = args.builds
        if self.builds:
            if not os.path.isdir(self.builds):
                log.console_error("invalid build: {}".format(self.builds))
                self.exiting(1)
            self.builds = os.path.join(self.builds, cst.NAME)
            if not os.path.exists(self.builds):
                os.makedirs(self.builds)

        def sigint_handler(signum, frame):
            """Handle ctrl-c."""
            log.console_error("CTRL-C")
            self.exiting(1)
        signal.signal(signal.SIGINT, sigint_handler)

    def build_dir(self):
        """Get a build file area."""
        dir_name = None
        log.debug("getting tempfile")
        if self.builds:
            dir_name = self.builds
        log.debug("using {}".format(dir_name))
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
                log.debug("failed on removal")
                log.debug(path)
                log.debug(err)
                log.console_error("unable to cleanup {}".format(path))
            for f in os.listdir(self.builds):
                b_dir = os.path.join(self.builds, f)
                if not os.path.isdir(b_dir):
                    continue
                log.debug(b_dir)
                yield b_dir
        cache_dir = self.get_cache_pkgs()
        if os.path.exists(cache_dir):
            yield self.get_cache_pkgs()

    def cache_file(self, file_name, ext=_CACHE_FILE):
        """Get a cache file."""
        if not os.path.exists(self._cache_dir):
            log.error("cache directory has gone missing")
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
        log.debug("calling pacman")
        if require_sudo and not self.root:
            if self.can_sudo:
                cmd.append("/usr/bin/sudo")
            else:
                log.console_error(
                    "sudo required but not allowed, re-run as root")
                self.exiting(1)
        cmd.append("/usr/bin/pacman")
        cmd = cmd + args
        log.trace(cmd)
        returncode = subprocess.call(cmd)
        log.trace(returncode)
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
        log.debug("unlocking")
        if os.path.exists(self._lock_file):
            os.remove(self._lock_file)
            log.debug("unlocked")

    def lock(self):
        """Lock to a single instance."""
        log.debug("locking")
        if not os.path.exists(self._lock_file):
            log.debug("locked")
            with open(self._lock_file, 'w') as f:
                obj = {}
                obj["time"] = str(self.now)
                obj["pid"] = str(os.getpid())
                log.trace(obj)
                f.write(json.dumps(obj))
            return
        log.console_error("lock file exists")
        log.console_error("only one instance of naaman may run at a time")
        log.console_error(
            "delete {} if this is an error".format(self._lock_file))
        exit(1)
