BIN            := bin/
INSTALL        :=
SRC            := $(shell find . -type f -name "*.py")
VERS           := $(shell cat naaman/consts.py | grep "^\_\_version\_\_" | cut -d "=" -f 2 | sed 's/ //g;s/"//g')
COMPLETION     := $(BIN)bash.completions

# tests
TST            := tests/
TESTS          := $(shell find $(TST) -name "*.py")

# doc
MONTH_YEAR     := $(shell date +"%B %Y")
DOC            := docs/
MAN8           := naaman.8
MAN5           := naaman.conf.5
DOCS           := $(MAN8) $(MAN5)
MANPAGE8       := $(BIN)$(MAN8)
MANPAGE5       := $(BIN)$(MAN5)

all: test analyze completions manpages

travis: ci all

test: $(TESTS)

ci: peps
	pip install pyxdg pep257 pycodestyle

peps:
	pip install pep257 pycodestyle

$(TESTS): clean
	@echo $@
	PYTHONPATH=. python $@

clean:
	rm -rf $(BIN)
	mkdir -p $(BIN)
	rm -rf $(TST)$(BIN)
	mkdir -p $(TST)$(BIN)

completions: clean
	cp $(DOC)bash.completions $(COMPLETION)

manpages: $(DOCS)

$(DOCS):
	m4 -DMONTH_YEAR='$(MONTH_YEAR)' -DVERSION='$(VERS)' $(DOC)$@.in | tail -n +3 > $(BIN)$@
	cd $(BIN) && gzip -k $@

analyze:
	@echo $(SRC)
	pep257 $(SRC)
	pycodestyle $(SRC)

dependencies:
	pacman -S python-xdg pyalpm bash-completion

makedepends:
	pacman -S python-pip git help2man

build: makedepends dependencies peps install

regen: clean install
	help2man naaman > $(DOC)$(MAN8)

install: completions manpages
	python setup.py install --root="$(INSTALL)/" --optimize=1
	install -Dm644 LICENSE $(INSTALL)/usr/share/license/naaman/LICENSE
	install -Dm644 $(COMPLETION) $(INSTALL)/usr/share/bash-completion/completions/naaman
	install -Dm644 scripts/makepkg $(INSTALL)/usr/share/naaman/makepkg
	install -Dm644 $(MANPAGE8).gz $(INSTALL)/usr/share/man/man8/
	install -Dm644 $(MANPAGE5).gz $(INSTALL)/usr/share/man/man5/
