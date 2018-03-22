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


def search_crit():
    """Test search criteria."""
    s = aur.can_package_search(None)
    if s:
        print("none is invalid")
        exit(1)
    s = aur.can_package_search("123")
    if s:
        print("too short")
        exit(1)
    s = aur.can_package_search("1234")
    if not s:
        print("just long enough")
        exit(1)


def main():
    """Main-entry harness."""
    is_vcs()
    deps_compare()
    get_deps()
    search_crit()


if __name__ == "__main__":
    main()
