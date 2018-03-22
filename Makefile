BIN=bin/
INSTALL=
COMPLETION=$(BIN)bash.completions
MAN8=naaman.8
MAN5=naaman.conf.5
MANPAGE8=$(BIN)$(MAN8)
MANPAGE5=$(BIN)$(MAN5)
MONTH_YEAR=$(shell date +"%B %Y")
DOC=docs/
SRC=$(shell find naaman/ -type f -name "*\.py") $(shell find tests/ -type f -name "*\.py")
VERS=$(shell cat naaman/consts.py | grep "^\_\_version\_\_" | cut -d "=" -f 2 | sed 's/ //g;s/"//g')
TST=tests/
TESTS=$(shell ls $(TST) | grep "\.py$$")

all: test analyze completions manpages

travis: ci all

test: $(TESTS)

ci: peps
	pip install pyxdg pep257 pycodestyle

peps:
	pip install pep257 pycodestyle

$(TESTS): clean
	@echo $@
	PYTHONPATH=. python $(TST)$@

clean:
	rm -rf $(BIN)
	mkdir -p $(BIN)
	rm -rf $(TST)$(BIN)
	mkdir -p $(TST)$(BIN)

completions: clean
	cp $(DOC)bash.completions $(COMPLETION)

manpages: clean
	cat $(DOC)$(MAN5) | sed "s/<Month Year>/$(MONTH_YEAR)/g"  > $(MANPAGE5)
	cat $(DOC)$(MAN8) | sed "s/<Month Year>/$(MONTH_YEAR)/g;s/<Version>/$(VERS)/g"  > $(MANPAGE8)
	cd $(BIN) && gzip $(MAN8)
	cd $(BIN) && gzip $(MAN5)

analyze:
	@echo $(SRC)
	pep257 $(SRC)
	pycodestyle $(SRC)

dependencies:
	pacman -S python-xdg pyalpm bash-completion

makedepends:
	pacman -S python-pip git

build: makedepends dependencies peps install

install: completions manpages
	python setup.py install
	install -Dm644 LICENSE $(INSTALL)/usr/share/license/naaman/LICENSE
	install -Dm644 $(COMPLETION) $(INSTALL)/usr/share/bash-completion/completions/naaman
	install -Dm644 scripts/makepkg $(INSTALL)/usr/share/naaman/makepkg
	install -Dm644 $(MANPAGE8).gz $(INSTALL)/usr/share/man/man8/
	install -Dm644 $(MANPAGE5).gz $(INSTALL)/usr/share/man/man5/
