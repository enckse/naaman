
"""
Handles anything to do with looking at PKGBUILDs.

NOTE: this is NOT a long-term strategy or good idea to go forward with.
"""

import naaman.logger as log

SPLIT_SKIP = "skip"
SPLIT_NONE = "nothing"
SPLIT_ERR = "error"
SPLIT_SPLIT = "split"
SPLITS = [SPLIT_SKIP,  SPLIT_NONE, SPLIT_ERR, SPLIT_SPLIT]
_PKGNAME = ['@', '.', '_', '+', '-']
SPLIT_SKIPPED = 2
_SPLIT_NOOP = 0
SPLIT_ERRORED = 1
_SPLIT_DONE = 3
MAKEPKG_VCS = ["-od"]


def splitting(pkgbuild, pkgname, skip, error, split):
    """Package splitting."""
    splits = []
    all_lines = []
    with open(pkgbuild, 'r') as f:
        in_pkg = False
        for line in f.readlines():
            if split:
                all_lines.append(line)
            if in_pkg:
                current = line.strip()
                for c in current:
                    if c.isalnum():
                        continue
                    if c in _PKGNAME:
                        continue
                    in_pkg = False
            if line.startswith("pkgname="):
                in_pkg = True
            if in_pkg:
                splits.append(line)
    log.trace(splits)
    lines = " ".join(splits)
    new_entry = ""
    entries = []
    in_section = False
    for c in lines:
        if c not in _PKGNAME and not c.isalnum():
            if c in "=":
                in_section = True
            new_entry = new_entry.strip()
            if len(new_entry) > 0:
                entries.append(new_entry)
            new_entry = ""
            continue
        if in_section:
            new_entry += c
    new_entry = new_entry.strip()
    if len(new_entry) > 0:
        entries.append(new_entry)
    log.trace(lines)
    if len(entries) == 1:
        log.debug('not a split package')
        return _SPLIT_NOOP
    if pkgname not in entries:
        log.console_error("unable to find {} in split package".format(pkgname))
        return SPLIT_ERRORED
    if error:
        log.console_error("split package detected but disabled")
        return SPLIT_ERRORED
    if skip:
        log.console_output("skipping (split package)")
        return SPLIT_SKIPPED
    if split:
        log.console_output("splitting package")
        has_done = False
        with open(pkgbuild, 'w') as f:
            for line in all_lines:
                if line in lines:
                    if not has_done:
                        f.write("pkgname={}\n".format(pkgname))
                        has_done = True
                    continue
                f.write(line)
        return _SPLIT_DONE
    raise Exception("unexpected split settings")
