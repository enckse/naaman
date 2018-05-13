"""Wrapper around alpm/pycman calls."""
import textwrap

_INDENT = "    "


class Alpm(object):
    """pyalpm/pycman wrapper."""

    def __init__(self):
        """Init the alpm instance wrapper."""
        from pycman import config, pkginfo
        self._width = pkginfo.get_term_size()
        self.format = pkginfo.format_attr
        self.config = config.init_with_config

    def width(self):
        """Get term width."""
        return self._width

    def format_line(self, input_str):
        """Write formatted output to terminal."""
        output_string = "    "
        wrapped = textwrap.fill(input_str,
                                width=self._width,
                                initial_indent=_INDENT,
                                subsequent_indent=_INDENT,
                                break_on_hyphens=False,
                                break_long_words=False)
        return wrapped
