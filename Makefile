.PHONY: help install test test-unit run build up down lint
PYTHON ?= $(VENV)/bin/python
VENV ?= .venv

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "%-12s %s\n", $$1, $$2}'

install: ## Install runtime and test dependencies into .venv
	uv venv $(VENV)
	uv pip install --python $(PYTHON) -r requirements-dev.txt

test: ## Run the full offline test suite
	$(PYTHON) -m pytest -q

test-unit: ## Run unit tests only
	$(PYTHON) -m pytest -q tests/unit

lint: ## Run ruff
	$(PYTHON) -m ruff check app tests

run: ## Run the bot locally (needs .env)
	$(PYTHON) -m app.main

build: ## Build the Docker image
	docker compose build

up: ## Start the service
	docker compose up -d

down: ## Stop the service
	docker compose down
