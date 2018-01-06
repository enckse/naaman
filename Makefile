OPTS=$(shell python naaman.py --help | grep "^\s" | sed "s/^[ ]*//g" | grep "^\-" | sed "s/, /,/g" | cut -d " " -f 1 | sed "s/,/ /g" | sort)
BIN=bin/
INSTALL=
COMPLETION=$(BIN)bash.completions

all: analyze completions

clean:
	rm -rf $(BIN)
	mkdir -p $(BIN)

completions: clean
	cat bash | sed "s/_COMPLETIONS_/$(OPTS)/g" > $(COMPLETION)

analyze:
	pip install pep257 pycodestyle
	pep257 naaman.py
	pycodestyle naaman.py

dependencies:
	pacman -S python-xdg pyalpm bash-completion

install: completions
	install -Dm755 naaman.py $(INSTALL)/usr/bin/naaman
	install -Dm644 LICENSE $(INSTALL)/usr/share/license/naaman/LICENSE
	install -Dm644 $(COMPLETION) $(INSTALL)/usr/share/bash-completion/completions/naaman
