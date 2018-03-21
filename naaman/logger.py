"""Logging for naaman."""

import os
import logging
import naaman.consts as consts


def _noop(message):
    """Noop log call."""
    pass


_LOGGER = logging.getLogger(consts.NAME)
_LOGGER.trace = _noop

_CONSOLE_FORMAT = logging.Formatter('%(message)s')
_FILE_FORMAT = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')


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
    callback("{} => {}".format(prefix, string))


def console_error(string):
    """Console error."""
    console_output(string, prefix="FAILURE", callback=_LOGGER.error)


def terminal_output(input_str, terminal_width, first_string, output_string):
    """Write multiple lines to output terminal with wrapper."""
    lines = []
    c_len = terminal_width
    if c_len > 0:
        c_len = c_len - len(output_string) - 4
        cur = []
        words = input_str.split(" ")
        for c_idx in range(0, len(words)):
            next_word = words[c_idx]
            cur_len = sum([len(x) + 1 for x in cur])
            next_len = cur_len + len(next_word) + 1
            if next_len > c_len:
                lines.append(" ".join(cur))
                cur = []
            else:
                cur.append(next_word)
        if len(cur) > 0:
            lines.append(" ".join(cur))
    else:
        lines.append(input_str)
    is_first = True
    for l in lines:
        out_string = output_string
        if is_first and first_string is not None:
            out_string = first_string
            is_first = False
        _LOGGER.info("{}{}".format(out_string, l))
