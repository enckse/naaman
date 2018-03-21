"""AUR package testing."""
import naaman.aur as aur


class MockPkg(object):
    """Mock package."""

    def __init__(self):
        """Init the mock."""
        self.name = None
        self.depends = []
        self.optdepends = []


def get_deps():
    """Dependency resolution."""
    p = MockPkg()
    m = MockPkg()
    m.name = "test2"
    p.name = "test"
    p.depends = ["test2"]
    pkgs = [p, m]
    d = aur.get_deps(pkgs)
    if len(d) != 3:
        print("invalid deps")
        exit(1)
    names = [x.name for x in d]
    # test2 was after test but got 'promoted'
    if names != ["test2", "test", "test2"]:
        print("invalid order")
        exit(1)


def get_segment():
    """Segment testing."""
    obj = {}
    obj['non'] = "aÂb"
    obj['null'] = None
    s = aur.get_segment(obj, 'non')
    if s != 'ab':
        print("non-ascii characters not dropped")
        exit(1)
    s = aur.get_segment(obj, 'null')
    if s != '':
        print("should be empty")
        exit(1)


def is_vcs():
    """Check if vcs."""
    v = aur.is_vcs("test-git")
    if v != "latest (vcs version)":
        print("did not detect vcs")
        exit(1)
    v = aur.is_vcs("test")
    if v is not None:
        print("incorrectly found vcs")
        exit(1)


def deps_compare():
    """Dependency comparison parsing."""
    d = aur.deps_compare("test>=1")
    if d.version == "1" and d.pkg == "test" and d.op == ">=":
        d = aur.deps_compare("test=1.2.3-4")
        if d.version == "1.2.3-4" and d.pkg == "test" and d.op == "=":
            d = aur.deps_compare("test")
            if d.version is None and d.op is None and d.pkg == "test":
                return
        else:
            print("unable to parse -")
    else:
        print("unable to parse >=")
    print("deps compare failed")
    exit(1)


def main():
    """Main-entry harness."""
    get_segment()
    is_vcs()
    deps_compare()
    get_deps()


if __name__ == "__main__":
    main()
