"""Logging for naaman."""

import logging
import naaman.consts as consts

# NOTE & TODO: this should not be public
LOGGER = logging.getLogger(consts.NAME)

CONSOLE_FORMAT = logging.Formatter('%(message)s')
FILE_FORMAT = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')


def debug(message):
    """Write a simple debug message."""
    LOGGER.debug(message)
