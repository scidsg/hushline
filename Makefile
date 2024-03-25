.DEFAULT_GOAL := help

.PHONY: help
help:
	@awk 'BEGIN {FS = ":.*?## "} /^[0-9a-zA-Z_-]+:.*?## / {printf "\033[36m%s\033[0m : %s\n", $$1, $$2}' $(MAKEFILE_LIST) | \
		sort | \
		column -s ':' -t

.PHONY: install-deps
install-deps:
	poetry install

.PHONY: run
run: ## Run the app
	@source ./env.sh && \
	flask run --debug -h localhost -p 5000

.PHONY: lint
lint:
	poetry run isort --check . && \
		poetry run black --check . && \
		poetry run flake8 . && \
		poetry run mypy .

.PHONY: fmt
fmt:
	poetry run isort . && \
		poetry run black .

.PHONY: init-db
init-db: ## Initialize the dev database
	flask db-extras init-db

.PHONY: test
test: ## Run the test suite
	poetry run pytest -vv tests
