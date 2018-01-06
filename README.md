naaman
===

N(ot) A(nother) A(UR) Man(ager) or more like "nah"-"man"

naaman is focused on providing a pacman-ish interface to dealing with AUR packages.

[![Build Status](https://travis-ci.org/enckse/naaman.svg?branch=master)](https://travis-ci.org/enckse/naaman)

# install

## git

git clone this repo

install dependencies
```
sudo make dependencies
```

install naaman
```
sudo make install
```


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

similarly what pacman deems refresh
```
-yy
```

and this will also skip vcs updates and assume you are only interested in AUR rpc "database" changes/refreshes
```
-y
```

similar to pacman, packages can be ignored
```
--ignore <package> <package1>
```

suppress naaman confirm prompts
```
--no-confirm
```

do not place aur makepkg xz into the pacman cache
```
--no-cache
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

### Remove

to remove packages
```
naaman -R <package> <package1>
```

### Query

to query the installed packages
```
naaman -Q
```

or to check for some packages
```
naaman -Q <package>
```

## Workflow

install some packages
```
naaman -S <package1> <package2-vcs-git> <package3>
```

see what AUR packages are installed
```
naaman -Q
```

update non-vcs packages
```
naaman -Syyu
```

remove a package
```
naaman -R <package3>
```

updating everything now
```
pacman -Su
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
