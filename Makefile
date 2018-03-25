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
NAAMAN_DEV=$(BIN)naaman.8.dev

all: test version analyze completions manpages

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
	cd $(BIN) && gzip -k $(MAN8)
	cd $(BIN) && gzip -k $(MAN5)

version:
	@echo $(VERS)
ifndef TRAVIS
	@exit $(shell git tag -l | grep "^v$(VERS)" | wc -l)
endif

analyze:
	@echo $(SRC)
	pep257 $(SRC)
	pycodestyle $(SRC)

dependencies:
	pacman -S python-xdg pyalpm bash-completion

makedepends:
	pacman -S python-pip git help2man

build: makedepends dependencies peps install

define diffman =
	sed -i '/^\.\\" DO NOT MODIFY THIS FILE/ d' $1;
	sed -i -e '1,3d' $1;
	sed -i -n '/.SH "SEE ALSO"/q;p' $1;
endef

install: completions manpages
	python setup.py install
	help2man naaman > $(NAAMAN_DEV)
	$(call diffman,$(NAAMAN_DEV))
	$(call diffman,$(MANPAGE8))
	diff -u $(NAAMAN_DEV) $(MANPAGE8)
	install -Dm644 LICENSE $(INSTALL)/usr/share/license/naaman/LICENSE
	install -Dm644 $(COMPLETION) $(INSTALL)/usr/share/bash-completion/completions/naaman
	install -Dm644 scripts/makepkg $(INSTALL)/usr/share/naaman/makepkg
	install -Dm644 $(MANPAGE8).gz $(INSTALL)/usr/share/man/man8/
	install -Dm644 $(MANPAGE5).gz $(INSTALL)/usr/share/man/man5/
