"""Argument handling."""
import naaman.arguments.utils as arg


class MockArgs(object):
    """Mock multi-arg object."""

    def __init__(self):
        """Init the mock."""
        self.refresh = 0
        self.info = 0
        self.info_verbose = None
        self.force_refresh = None
        self.force_force_refresh = None


def _info(count, res):
    """Info settings."""
    _check("info", count, res)


def _refresh(count, res):
    """Refresh settings."""
    _check("refresh", count, res)


def _check(cat, count, res):
    """Arg checking."""
    if res:
        print(cat)
        print(count)
        print("invalid settings")
        exit(1)


def manual_args():
    """Manual argument handling."""
    a = MockArgs()
    arg.manual_args(a)
    idx = 0
    _refresh(idx, a.refresh or a.force_refresh or a.force_force_refresh)
    _info(idx, a.info or a.info_verbose)

    a.refresh = 1
    arg.manual_args(a)
    idx += 1
    _refresh(idx, not a.refresh or a.force_refresh or a.force_force_refresh)
    _info(idx, a.info or a.info_verbose)

    a.refresh = 2
    arg.manual_args(a)
    idx += 1
    _refresh(idx, not a.refresh
             or not a.force_refresh or
             a.force_force_refresh)
    _info(idx, a.info or a.info_verbose)

    a.refresh = 3
    arg.manual_args(a)
    idx += 1
    _refresh(idx, not a.refresh
             and not a.force_refresh and not
             a.force_force_refresh)
    _info(idx, a.info or a.info_verbose)
    idx += 1
    a.info = 1
    arg.manual_args(a)
    _info(idx, not a.info or a.info_verbose)


def main():
    """Main-entry harness."""
    manual_args()


if __name__ == "__main__":
    main()
