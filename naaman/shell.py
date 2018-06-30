"""
Shell operations.

Output to the shell in certain formats, executing shell commands,
getting response from the user in the shell (as needed)
"""
import subprocess
import naaman.logger as log

_BASH_WRAPPER = """#!/bin/bash
trap '' 2
function _section() {
    cat .SRCINFO \
        | grep \"\\s*$1\" \
        | cut -d \"=\" -f 2- \
        | sed \"s/^\\s//g;s/\\s$//g\" \
        | head -n 1
}"""


def bashpkg(file_name, command, workingdir):
    """Do some shell work in bash."""
    script = [_BASH_WRAPPER]
    script.append(command)
    script.append("exit $?")
    with open(file_name, 'w') as f:
        f.write("\n".join(script))
    result = subprocess.call("/bin/bash --rcfile {}".format(file_name),
                             shell=True,
                             cwd=workingdir)
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
