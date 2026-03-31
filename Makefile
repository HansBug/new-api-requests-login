SHELL := /bin/bash

PYTHON ?= python
SCRIPT ?= newapi.py
ENV_FILE ?= .env

.PHONY: login checkin

login:
	@bash -lc 'if [[ -f "$(ENV_FILE)" ]]; then source "$(ENV_FILE)"; fi; $(PYTHON) $(SCRIPT)'

checkin:
	@bash -lc 'if [[ -f "$(ENV_FILE)" ]]; then source "$(ENV_FILE)"; fi; $(PYTHON) $(SCRIPT) --checkin'
