"""Shell operations."""
import subprocess
import naaman.logger as log


def has_git(required):
    """Check if we have git installed."""
    log.debug("checking for git")
    try:
        with open("/dev/null", "w") as null:
            subprocess.Popen("git", stdout=null, stderr=null)
        return True
    except Exception as e:
        if required:
            log.console_error("unable to use git")
            log.error(e)
            return None
        return False


def template_script(script_text, replaces, temp_file):
    """Template and run a script."""
    script = script_text
    for r in replaces:
        script = script.replace("{" + r + "}", replaces[r])
    log.trace(script)
    with open(temp_file, 'w') as f:
        f.write(script)
    result = subprocess.call("/bin/bash --rcfile {}".format(temp_file),
                             shell=True)
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
