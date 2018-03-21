"""Shell operations."""
import subprocess
import naaman.logger as log


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
