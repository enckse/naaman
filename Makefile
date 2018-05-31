BIN            := bin/
INSTALL        :=
SRC            := $(shell find naaman/ -type f -name "*\.py") $(shell find tests/ -type f -name "*\.py")
VERS           := $(shell cat naaman/consts.py | grep "^\_\_version\_\_" | cut -d "=" -f 2 | sed 's/ //g;s/"//g')
COMPLETION     := $(BIN)bash.completions

# tests
TST            := tests/
TESTS          := $(shell ls $(TST) | grep "\.py$$")

# doc
MONTH_YEAR     := $(shell date +"%B %Y")
DOC            := docs/
MAN8           := naaman.8
MAN5           := naaman.conf.5
MANPAGE8       := $(BIN)$(MAN8)
MANPAGE5       := $(BIN)$(MAN5)
NAAMAN8_DEV    := $(BIN)$(MAN8).template
NAAMAN8_FOOTER := $(BIN)$(MAN8).footer
NAAMAN8_HEADER := $(BIN)$(MAN8).header
NAAMAN8_DOC    := $(BIN)$(MAN8).doc
DOC_MAN8       := $(DOC)$(MAN8)
DOC_MAN5       := $(DOC)$(MAN5)

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
	cat $(DOC_MAN8) | head -n 3 > $(NAAMAN8_HEADER)
	cat $(DOC_MAN8) | tail -n 2 > $(NAAMAN8_FOOTER)
	cat $(DOC_MAN5) | sed "s/<Month Year>/$(MONTH_YEAR)/g"  > $(MANPAGE5)
	cat $(DOC_MAN8) | sed "s/<Month Year>/$(MONTH_YEAR)/g;s/<Version>/$(VERS)/g"  > $(MANPAGE8)
	cd $(BIN) && gzip -k $(MAN8)
	cd $(BIN) && gzip -k $(MAN5)

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
	help2man naaman > $(NAAMAN8_DEV)
	$(call diffman,$(NAAMAN8_DEV))
	@cat $(NAAMAN8_HEADER) > $(NAAMAN8_DOC)
	@cat $(NAAMAN8_DEV) >> $(NAAMAN8_DOC)
	@cat $(NAAMAN8_FOOTER) >> $(NAAMAN8_DOC)
	diff -u $(DOC_MAN8) $(NAAMAN8_DOC)
	install -Dm644 LICENSE $(INSTALL)/usr/share/license/naaman/LICENSE
	install -Dm644 $(COMPLETION) $(INSTALL)/usr/share/bash-completion/completions/naaman
	install -Dm644 scripts/makepkg $(INSTALL)/usr/share/naaman/makepkg
	install -Dm644 $(MANPAGE8).gz $(INSTALL)/usr/share/man/man8/
	install -Dm644 $(MANPAGE5).gz $(INSTALL)/usr/share/man/man5/
