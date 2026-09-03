PY := .venv/bin/python

.PHONY: help venv data external pipeline figures notebooks site test all clean clean-results

help:
	@echo "make venv       create the virtualenv and install the package"
	@echo "make external   fetch daily bars, splits, dividends and VIX (~1 min)"
	@echo "make data       download and ingest 5-minute bars   (~25 min, ~20 GB transferred)"
	@echo "make pipeline   run the full analysis into results/ (~6 min)"
	@echo "make figures    rebuild every figure from saved tables"
	@echo "make notebooks  execute the notebooks in place"
	@echo "make test       run the test suite"
	@echo "make site       sync figures into the static presentation layer"
	@echo "make all        external + data + pipeline + figures"

venv:
	uv venv --python 3.12 .venv
	uv pip install --python $(PY) -e ".[dev]"

external:
	$(PY) -m closingbell.external

data:
	$(PY) -m closingbell.ingest --workers 3

pipeline:
	$(PY) -m closingbell.pipeline

figures:
	$(PY) -m closingbell.figures

notebooks:
	cd notebooks && for n in *.ipynb; do \
		../$(PY) -m jupyter nbconvert --to notebook --execute --inplace \
			--ExecutePreprocessor.timeout=900 $$n || exit 1; \
	done

# The static presentation layer serves copies of the generated figures so that
# `site/` can be deployed on its own.  This target keeps them in step.
site:
	cp results/figures/*.png site/figures/

test:
	$(PY) -m pytest tests/ -q

all: external data pipeline figures

clean:
	rm -rf data/raw/* data/interim/*

clean-results:
	rm -rf results/tables/* results/figures/* results/summary.json
