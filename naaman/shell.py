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
