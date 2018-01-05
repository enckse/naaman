all: analyze

analyze:
	pip install pep257 pycodestyle
	pep257 naaman.py
	pycodestyle naaman.py
