"""
Shell operations.

Output to the shell in certain formats, executing shell commands,
getting response from the user in the shell (as needed)
"""
import subprocess
import os
import naaman.logger as log
from datetime import datetime

_BASH_WRAPPER = """#!/bin/bash
trap '' 2
function _section() {
    cat .SRCINFO \
        | grep \"\\s*$1\" \
        | cut -d \"=\" -f 2- \
        | sed \"s/^\\s//g;s/\\s$//g\" \
        | head -n 1
}"""
_PKGVER = """
makepkg --printsrcinfo > .SRCINFO
[[ "$(_section 'pkgver')-$(_section 'pkgrel')" == '{}' ]] && exit 1
"""
_CACHE = """
test -e *.tar{} && {}cp *.tar.{} {}/
"""


class InstallPkg(object):
    """Wrapper for installing packages (via makepkg)."""

    def __init__(self, sudo, workingdir):
        """Init a package install."""
        self._workdir = workingdir
        self._sudo = sudo
        self._timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        self._idx = 0

    def makepkg(self, args):
        """Run makepkg."""
        return self._run(["makepkg {}".format(args)])

    def version(self, vers):
        """Check the makepkg output version."""
        if vers is None:
            return True
        return self._run([_PKGVER.format(vers)])

    def cache(self, dirs):
        """Cache output files."""
        if dirs is None or len(dirs.strip()) == 0:
            return True
        scripts = []
        cache_cmd = _CACHE.format("{}", self._sudo, "{}", "{}")
        for f in ["xz"]:
            for cd in dirs.split(" "):
                scripts.append(cache_cmd.format(f, f, cd))
        return self._run(scripts)

    def _run(self, scripts):
        """Run a set of scripts."""
        for s in scripts:
            f_name = os.path.join(self._workdir,
                                  "naamanpkg.{}.{}".format(self._timestamp,
                                                           self._idx))
            if not self._bashpkg(f_name, s):
                return False
            self._idx += 1
        return True

    def _bashpkg(self, file_name, command):
        """Do some shell work in bash."""
        script = [_BASH_WRAPPER]
        script.append(command)
        script.append("exit $?")
        print(file_name)
        with open(file_name, 'w') as f:
            f.write("\n".join(script))
        result = subprocess.call("/bin/bash --rcfile {}".format(file_name),
                                 shell=True,
                                 cwd=self._workdir)
        return result == 0


def shell(command, suppress_error=False, workingdir=None):
    """Run a shell command."""
    log.debug("shell")
    log.trace(command)
    log.trace(workingdir)
    sp = subprocess.Popen(command,
                          cwd=workingdir,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    out, err = sp.communicate()
    log.trace(out)
    if suppress_error:
        log.trace(err)
    else:
        if err and len(err) > 0:
            log.error(err)
    return out


def confirm(message, package_names, default_yes, must_confirm):
    """Confirm package changes."""
    exiting = None
    if must_confirm:
        log.info("")
        for p in package_names:
            log.info("  -> {}".format(p))
        log.info("")
        defaulting = "Y/n"
        if not default_yes:
            defaulting = "y/N"
        msg = " ===> {}, ({})? ".format(message, defaulting)
        log.trace(msg)
        c = input(msg)
        log.trace(c)
        if (default_yes and c == "n") or (not default_yes and c != "y"):
            exiting = "user "
    else:
        if default_yes:
            log.debug("no confirmation needed.")
            return
        exiting = ""
    return exiting
