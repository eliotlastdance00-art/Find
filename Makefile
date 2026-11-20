.DEFAULT_GOAL := help
.PHONY: help install run lint format type test check docker docker-run clean

help:            ## Show this help
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F ':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

install:         ## Install CPU PyTorch and the project with dev tools
	./scripts/bootstrap.sh

run:             ## Start the web application on http://localhost:8000
	dfd serve

lint:            ## Static checks
	ruff check .
	ruff format --check .

format:          ## Apply formatting and safe fixes
	ruff format .
	ruff check --fix .

type:            ## Strict type check
	mypy

test:            ## Run the test suite with coverage
	pytest --cov=dfd --cov-report=term-missing

check: lint type test  ## Everything CI runs

docker:          ## Build the container image
	docker build -t deepfake-detektor:latest .

docker-run:      ## Run with docker compose
	docker compose up --build

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov dist build
