# Shortcuts for `python tasks.py <task>` (tasks.py does the work and also runs on Windows).
PY ?= python

.PHONY: setup test test-all lint pipeline pipeline-quick serve export reproduce reproduce-quick golden docker

setup:           ; $(PY) tasks.py setup
test:            ; $(PY) tasks.py test
test-all:        ; $(PY) tasks.py test --all
lint:            ; $(PY) tasks.py lint
pipeline:        ; $(PY) tasks.py pipeline
pipeline-quick:  ; $(PY) tasks.py pipeline --quick
serve:           ; $(PY) tasks.py serve
export:          ; $(PY) tasks.py export
reproduce:       ; $(PY) tasks.py reproduce
reproduce-quick: ; $(PY) tasks.py reproduce --quick
golden:          ; $(PY) tasks.py golden
docker:          ; $(PY) tasks.py docker
