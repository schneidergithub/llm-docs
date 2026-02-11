BOOTSTRAP_PYTHON ?= python3.11
PYTHON ?= .venv/bin/python
VERSION ?= dev-local

.PHONY: setup validate build test

setup:
	$(BOOTSTRAP_PYTHON) -m venv .venv
	.venv/bin/pip install -r tools/requirements.txt

validate:
	$(PYTHON) tools/validate_docs.py

build:
	$(PYTHON) tools/build_corpus.py --corpus-version $(VERSION) --out-dir dist/dev-local/$(VERSION)

test:
	$(PYTHON) -m unittest discover -s tests -p "test_*.py"
