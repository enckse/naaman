OPTS=$(shell python naaman.py --help | grep "^\s" | sed "s/^[ ]*//g" | grep "^\-" | sed "s/, /,/g" | cut -d " " -f 1 | sed "s/,/ /g" | sort)
BIN=bin/
INSTALL=
COMPLETION=$(BIN)bash.completions
MAN8=naaman.8
MANPAGE8=$(BIN)$(MAN8)

all: analyze completions

clean:
	rm -rf $(BIN)
	mkdir -p $(BIN)

completions: clean
	cat scripts/bash | sed "s/_COMPLETIONS_/$(OPTS)/g" > $(COMPLETION)

manpages: clean
	./scripts/naaman-conf.sh
	help2man ./scripts/naaman.sh --output="$(MANPAGE8)" --name="Not Another Aur MANager"
	cd $(BIN) && gzip $(MAN8)

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
