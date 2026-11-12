SPHINXBUILD ?= uv run --project webarena-pro-core --with-requirements docs/requirements.txt sphinx-build
SPHINXOPTS ?=
PYTHON ?= uv run --project webarena-pro-core python
DOCS_SOURCE ?= docs/source
DOCS_BUILD ?= docs/_build/html
DOCS_HOST ?= 127.0.0.1
DOCS_PORT ?= 8000

.PHONY: help docs docs-build docs-serve docs-clean

help:
	@echo "Targets:"
	@echo "  docs        Build the documentation HTML"
	@echo "  docs-serve  Build and serve docs at http://$(DOCS_HOST):$(DOCS_PORT)"
	@echo "  docs-clean  Remove generated documentation"

docs: docs-build

docs-build:
	$(SPHINXBUILD) $(SPHINXOPTS) -b html $(DOCS_SOURCE) $(DOCS_BUILD)

docs-serve: docs-build
	@echo "Serving documentation at http://$(DOCS_HOST):$(DOCS_PORT)"
	$(PYTHON) -m http.server $(DOCS_PORT) --bind $(DOCS_HOST) --directory $(DOCS_BUILD)

docs-clean:
	rm -rf docs/_build
