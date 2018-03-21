#!/usr/bin/python
"""
N(ot) A(nother) A(UR) Man(ager).

Is an AUR wrapper/manager that uses pacman as it's backing data store.
"""
import argparse
import os
import urllib.request
import json
import shutil
import naaman.arguments.common as common_args
import naaman.arguments.config as config_args
import naaman.arguments.custom as csm_args
import naaman.arguments.utils as util_args
import naaman.arguments.query as query_args
import naaman.arguments.syncup as sync_args
import naaman.shell as sh
import naaman.aur as aur
import naaman.context as nctx
import naaman.logger as log
import naaman.consts as cst
import naaman.pkgbuild as pkgbld
from datetime import datetime, timedelta

logger = log.LOGGER


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

    ctx = nctx.Context(unknown, groups, args)
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
    url = aur.AUR.format(file_definition.url)
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
                      aur.AUR_GIT.format(file_definition.name),
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


def _rpc_search(package_name, exact, context, include_deps=False):
    """Search for a package in the aur."""
    return aur.rpc_search(package_name, exact, context, include_deps)


def _search(context):
    """Perform a search."""
    if len(context.targets) != 1:
        log.console_error("please provide ONE target for search")
        context.exiting(1)
    for target in context.targets:
        logger.debug("searching for {}".format(target))
        if len(target) < aur.AUR_TARGET_LEN:
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


def main():
    """Entry point."""
    cache_dir = config_args.get_default_cache()
    config_file = config_args.get_default_config()
    parser = common_args.build(config_file, cache_dir)
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
            args = config_args.load_config(args, f)
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
