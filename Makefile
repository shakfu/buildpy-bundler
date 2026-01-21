STATICPY := build/install/python-static/bin/python3
SHAREDPY := build/install/python-shared/bin/python3
BUILDPY := src/buildpy.py

.PHONY: all sync run debug test build repl format lint typecheck \
		release check publish publish-test clean reset

all: release

sync:
	@uv sync

run: clean
	@COLOR=0 python3 $(BUILDPY) 2>&1 | tee -a log.txt

debug: clean
	@DEBUG=1 COLOR=1 $(BUILDPY) 2>&1 | tee -a log.txt

test:
	@uv run pytest

build:
	@uv build

repl:
	@test -f $(STATICPY) && $(STATICPY) || test -f $(SHAREDPY) && $(SHAREDPY)

format:
	@uv run ruff format $(BUILDPY)

lint:
	@uv run ruff check --fix $(BUILDPY)

typecheck:
	@uv run mypy --strict $(BUILDPY)

release: sync lint typecheck format build check

check:
	@uv run twine check dist/*

publish:
	@uv run twine upload dist/*

publish-test:
	@uv run twine upload -r testpypi dist/*

clean:
	@rm -rf build/src dist log.txt __pycache__

reset: clean
	@rm -rf .venv build


