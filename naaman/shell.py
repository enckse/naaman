"""
Shell operations.

Output to the shell in certain formats, executing shell commands,
getting response from the user in the shell (as needed)
"""
import subprocess
import os
import naaman.logger as log
from datetime import datetime

_BASH_WRAPPER = r"""#!/bin/bash
trap '' 2
"""
_SRCINFO = r"""
function _section() {
    cat .SRCINFO \
        | grep "\s*$1" \
        | cut -d "=" -f 2- \
        | sed "s/^\s//g;s/\s$//g" \
        | head -n 1
}
makepkg --printsrcinfo > .SRCINFO
vers="$(_section 'pkgver')-$(_section 'pkgrel')"
"""

# Check if pkgver-pkgrel is unchanged
_PKGVER = _SRCINFO + r"""[[ "$vers" == '{VERSION}' ]] && exit 1"""

# handle installing some or all packages
_PACMAN_U = "{SUDO}pacman -U"
_INSTALL_ALL = _PACMAN_U + " *.pkg.tar.xz"
_INSTALL = _SRCINFO + r"""
fname="{PKGNAME}-${vers}-{ARCH}.pkg.tar.xz"
if [ -e "$fname" ]; then
    """ + _PACMAN_U + """ $fname
    if [ $? -ne 0 ]; then
        exit 1
    fi
fi
"""
_ARCH_INSTALLS = [_INSTALL.replace("{ARCH}", x) for x in ["any", "x86_64"]]

# If there are cache files, cache them
_CACHE = r"[ $(ls | grep '*\.pkg\.tar\.{}' | wc -l) -gt 0 ] || {}cp *\.pkg\.tar.{} {}/"

# output the number of produced packages (minus 1, always produce 1 package)
_SPLIT = r"""
pkgs=$(makepkg --packagelist | grep "\.pkg\.tar\.xz")
cnt=$(echo "$pkgs" | wc -l)
if [ $cnt -gt 1 ]; then
    echo
    echo 'detected packages:'
    for f in $(echo "$pkgs" | sed "s/\.pkg\.tar\.xz//g"); do
        basename $f | \
            sed "s/any$//g;s/x86\_64$//g;s/-$//g" | \
            sed "s/^/  -> /g"
    done
    exit 1
fi
"""


class InstallPkg(object):
    """Wrapper for installing packages (via makepkg)."""

    def __init__(self, sudo, workingdir):
        """Init a package install."""
        self._workdir = workingdir
        self._sudo = ""
        if sudo:
            self._sudo = "sudo "
        self._timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        self._idx = 0

    def makepkg(self, args):
        """Run makepkg."""
        self._log_bash("makepkg")
        return self._run(["makepkg {}".format(" ".join(args))])

    def install(self, name):
        """Install a package."""
        self._log_bash("install")
        scripts = []
        if name is None:
            scripts = [_INSTALL_ALL]
        else:
            scripts = [x.replace("{PKGNAME}", name) for x in _ARCH_INSTALLS]
        scripts = [x.replace("{SUDO}", self._sudo) for x in scripts]
        return self._run(scripts)

    def version(self, vers):
        """Check the makepkg output version."""
        self._log_bash("version")
        if vers is None:
            return True
        return self._run([_PKGVER.replace("{VERSION}", vers)])

    def is_split(self):
        """Indicate if split package."""
        self._log_bash("split")
        return not self._run([_SPLIT])

    def cache(self, dirs):
        """Cache output files."""
        self._log_bash("cache")
        if dirs is None or len(dirs.strip()) == 0:
            return True
        scripts = []
        cache_cmd = _CACHE.format("{}", self._sudo, "{}", "{}")
        for f in ["xz"]:
            for cd in dirs.split(" "):
                scripts.append(cache_cmd.format(f, f, cd))
        return self._run(scripts)

    def _log_bash(self, name):
        """Log that a bash step is running."""
        log.debug("bash: {}".format(name))

    def _run(self, scripts):
        """Run a set of scripts."""
        for s in scripts:
            f_name = os.path.join(self._workdir,
                                  "naamanpkg.{}.{}".format(self._timestamp,
                                                           self._idx))
            log.debug(f_name)
            if not self._bashpkg(f_name, s):
                return False
            self._idx += 1
        return True

    def git(self, source, dest, path):
        """Git clone an AUR package."""
        log.debug("git clone")
        return command(["git", "clone", "--depth=1", source, dest],
                       workdir=path)

    def _bashpkg(self, file_name, cmd):
        """Do some shell work in bash."""
        script = [_BASH_WRAPPER]
        script.append(cmd)
        script.append("exit $?")
        with open(file_name, 'w') as f:
            script_text = "\n".join(script)
            log.trace(script_text)
            f.write(script_text)
        res = command(["/bin/bash --rcfile {}".format(file_name)],
                      shell=True,
                      workdir=self._workdir)
        os.remove(file_name)
        return res


def command(command, shell=False, workdir=None):
    """Execute a subprocess command."""
    res = subprocess.call(command, shell=shell, cwd=workdir)
    return res == 0


def confirm(message, display, default_yes, must_confirm):
    """Confirm package changes."""
    exiting = None
    if must_confirm:
        log.info("")
        if display is not None:
            for p in display:
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
