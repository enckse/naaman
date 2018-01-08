NAAMAN_SH=./scripts/naaman.sh
OPTS=$(shell $(NAAMAN_SH) --help | grep "^\s" | sed "s/^[ ]*//g" | grep "^\-" | sed "s/, /,/g" | cut -d " " -f 1 | sed "s/,/ /g" | sort)
BIN=bin/
INSTALL=
COMPLETION=$(BIN)bash.completions
MAN8=naaman.8
MAN5=naaman.conf.5
MANPAGE8=$(BIN)$(MAN8)
MANPAGE5=$(BIN)$(MAN5)
MONTH_YEAR=$(shell date +"%B %Y")

all: analyze completions manpages

travis: ci all

ci:
	pip install pyxdg

clean:
	rm -rf $(BIN)
	mkdir -p $(BIN)

completions: clean
	cat scripts/bash | sed "s/_COMPLETIONS_/$(OPTS)/g" > $(COMPLETION)

manpages: clean
	./scripts/naaman-conf.sh
	cat scripts/$(MAN5) | sed "s/<Month Year>/$(MONTH_YEAR)/g"  > $(MANPAGE5)
	help2man $(NAAMAN_SH) --output="$(MANPAGE8)" --name="Not Another Aur MANager"
	cd $(BIN) && gzip $(MAN8)
	cd $(BIN) && gzip $(MAN5)

analyze:
	pip install pep257 pycodestyle
	pep257 naaman.py
	pycodestyle naaman.py

dependencies:
	pacman -S python-xdg pyalpm bash-completion

install: completions manpages
	install -Dm755 naaman.py $(INSTALL)/usr/bin/naaman
	install -Dm644 LICENSE $(INSTALL)/usr/share/license/naaman/LICENSE
	install -Dm644 $(COMPLETION) $(INSTALL)/usr/share/bash-completion/completions/naaman
	install -Dm644 scripts/makepkg $(INSTALL)/usr/share/naaman/makepkg
	install -Dm644 $(MANPAGE8).gz $(INSTALL)/usr/share/man/man8/
	install -Dm644 $(MANPAGE5).gz $(INSTALL)/usr/share/man/man5/
