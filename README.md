naaman
===

N(ot) A(nother) A(UR) Man(ager)

naaman is focused on providing a pacman-ish interface to dealing with AUR packages.

[![Build Status](https://travis-ci.org/enckse/naaman.svg?branch=master)](https://travis-ci.org/enckse/naaman)

# install

Coming soon

## Usage

naaman relies on being similar to pacman while having to do things special for itself

### naaman

naaman supports the following special flags:

output the version
```
--version
```

perform debug output/logging
```
--verbose
```

specify the pacman config (defaults to `/etc/pacman.conf`)
```
--config
```

for sync/update/upgrades

to specify makepkg flags (to pass-thru)
```
--makepkg -sri -abc -xyz
```

to skip vcs-package updates/installs
```
--no-vcs
```

### Sync

you can perform a sync to install new packages from the AUR
```
naaman -S <package> <package1>
```

search for packages in the aur
```
naaman -Ss <package>
```

update all packages
```
naaman -Su
```

or some packages
```
naaman -Su <package> <package1>
```

### Upgrade

to perform an upgrade
```
naaman -U <package> <package1>
```

### Remove

to remove packages
```
naaman -R <package> <package1>
```

### Query

to query the install packages
```
naaman -Q
```

or to check for some packages
```
naaman -Q <package>
```

## Known issues

naaman is:
* not a dependency solver, it's a pyalpm/makepkg wrapper for AUR to _help_ you
* not doing everything for you
* not pacman
* relying on you to check and verify AURs are safe before you use them
* uses some nomenclature strangely due to trying to act like pacman

These items are known and are not currently planned to be solved
* Complicated/multi-AUR package dependency resolution
* Replicating all conceivable pacman args that _might_ be useful for AUR wrappers
* VCS packages are always updated, use `--no-vcs`
