naaman
===

N(ot) A(nother) A(UR) Man(ager) or more like "nah"-"man"

naaman is focused on providing a pacman-ish interface to dealing with AUR packages.

[![Build Status](https://travis-ci.org/enckse/naaman.svg?branch=master)](https://travis-ci.org/enckse/naaman)

# install

## AUR

You should install via the AUR to bootstrap yourself and use naaman after that.

[naaman](https://aur.archlinux.org/packages/naaman/)

## development

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
--pacman
```

specify the naaman config file (defaults to `~/.config/naaman.conf`)
```
--config
```
* if the config file does not exist it will be ignore
* see the naaman.conf example for how to use it (only keys in the example are supported)

for sync/update/upgrades

to skip vcs-package updates/installs
```
--no-vcs
```

to ignore vcs updates for a certain number of hours (<= 0 disables this and is default)
```
--vcs-ignore 24
```

to override ignoring/vcs cache/etc (applies to -S and -u)
```
-yy
```

read/see more options via man
```
man naaman
```

or for the config file
```
man naaman.conf
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

remove cache information for naaman
```
naaman -Sc
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

to check for packages that are dropped (gone) from the aur
```
naaman -Qg
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

## Config

Most configuration values map to parameters, with the exception of `REMOVAL` and `MAKEPKG`. Each of which can be listed multiple times (additive).

### REMOVAL

Specify flags to pass to pacman when executing a `-R`
```
REMOVAL="-c"
REMOVAL="-n"
```

### MAKEPKG

Specify flags to pass to makepkg
```
MAKEPKG="-sri"
MAKEPKG="-f"
```

## Known issues

naaman is:
* not a dependency solver, it's a pyalpm/makepkg wrapper for AUR to _help_ you
* not doing everything for you
* not pacman
* relying on you to check and verify AURs are safe before you use them
* uses some nomenclature strangely due to trying to act like pacman
* capable of being tricked/fooled/skipped

These items are known and are not currently planned to be solved
* Complicated/multi-AUR package dependency resolution
* Replicating all conceivable pacman args that _might_ be useful for AUR wrappers
* VCS packages are complicated, you have options to mitigate that
