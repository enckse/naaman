OPTS=$(shell python naaman.py --help | grep "^\s" | sed "s/^[ ]*//g" | grep "^\-" | sed "s/, /,/g" | cut -d " " -f 1 | sed "s/,/ /g" | sort)
BIN=bin/

all: analyze completions

clean:
	rm -rf $(BIN)
	mkdir -p $(BIN)

completions: clean
	cat bash | sed "s/_COMPLETIONS_/$(OPTS)/g" > $(BIN)bash.completions

analyze:
	pip install pep257 pycodestyle
	pep257 naaman.py
	pycodestyle naaman.py
