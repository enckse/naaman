"""PKGBUILD handling tests."""
import naaman.pkgbuild as pkgbuild
import os

_PKGBUILD = """# This
# is a test
pkgname=('test' 'test4')
arch=('any')
pkgnamed=('testakldja')
source=()

prepare() {
}"""


def _writepkgbuild(name, transform):
    """Write a test pkgbuild."""
    with open(name, 'w') as f:
        f.write(_PKGBUILD.replace(transform, ""))


def split():
    """Splitting pkgbuild packages/parsing."""
    f = os.path.dirname(os.path.realpath(__file__))
    f = os.path.join(f, "bin", "pkgbuild")
    _writepkgbuild(f, "'test4'")
    result = pkgbuild.splitting(f, 'test100', False, False, False)
    if result != 0:
        print("should be noop")
        exit(1)
    _writepkgbuild(f, "")
    result = pkgbuild.splitting(f, 'test100', False, False, False)
    if result != 1:
        print("should be error")
        exit(1)
    _writepkgbuild(f, "")
    result = pkgbuild.splitting(f, 'test', False, True, False)
    if result != 1:
        print("should be error")
        exit(1)
    _writepkgbuild(f, "")
    result = pkgbuild.splitting(f, 'test', True, False, False)
    if result != 2:
        print("should be error")
        exit(1)
    _writepkgbuild(f, "")
    result = pkgbuild.splitting(f, 'test', False, False, True)
    if result != 3:
        print("should be error")
        exit(1)


def main():
    """Main-entry harness."""
    split()


if __name__ == "__main__":
    main()
