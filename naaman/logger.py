"""
Logging for naaman.

Wraps python logging to support verbose/trace outputs
"""

import os
import logging
import naaman.consts as consts
import naaman.alpm as alpm


def _noop(message):
    """Noop log call."""
    pass


_LOGGER = logging.getLogger(consts.NAME)
_LOGGER.trace = _noop

_CONSOLE_FORMAT = logging.Formatter('%(message)s')
_FILE_FORMAT = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
_MESSAGE = "{} => {}"
_PROGRESS_MESSAGE = _MESSAGE.format("", "{}{}")


def init(verbose, trace, cache_dir):
    """Initialize logging."""
    ch = logging.StreamHandler()
    if not os.path.exists(cache_dir):
        _LOGGER.debug("creating cache dir")
        os.makedirs(cache_dir)
    fh = logging.FileHandler(os.path.join(cache_dir, consts.NAME + '.log'))
    fh.setFormatter(_FILE_FORMAT)
    if verbose:
        ch.setFormatter(_FILE_FORMAT)
    else:
        ch.setFormatter(_CONSOLE_FORMAT)
    for h in [ch, fh]:
        _LOGGER.addHandler(h)
    if verbose:
        _LOGGER.setLevel(logging.DEBUG)
    else:
        _LOGGER.setLevel(logging.INFO)

    if trace:
        def trace_log(obj):
            _LOGGER.debug(obj)
        trace_call = trace_log
        setattr(_LOGGER, "trace", trace_log)


def trace(message):
    """Write a trace message."""
    _LOGGER.trace(message)


def error(message):
    """Write an error message."""
    _LOGGER.error(message)


def debug(message):
    """Write a simple debug message."""
    _LOGGER.debug(message)


def warn(message):
    """Warning message."""
    _LOGGER.warn(message)


def info(message):
    """Info output."""
    _LOGGER.info(message)


def console_output(string, prefix="", callback=_LOGGER.info):
    """console/pretty output."""
    callback(_MESSAGE.format(prefix, string))


def console_error(string):
    """Console error."""
    console_output(string, prefix="FAILURE", callback=_LOGGER.error)


def update_progress(message):
    """Update working progress."""
    prog = []
    max_level = alpm.Alpm().width()
    local_max = max_level - (len(_PROGRESS_MESSAGE) + 1) - len(message)
    cur = "".join([" " for x in range(0, local_max)])
    _stdout_only(_PROGRESS_MESSAGE.format(message, cur), end='\r')
    debug(message)


def _stdout_only(message, end='\n'):
    """Write to stdout only (no logging)."""
    print(message, end=end)
