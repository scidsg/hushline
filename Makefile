.DEFAULT_GOAL := help

.PHONY: help
help: ## Print the help message
	@awk 'BEGIN {FS = ":.*?## "} /^[0-9a-zA-Z_-]+:.*?## / {printf "\033[36m%s\033[0m : %s\n", $$1, $$2}' $(MAKEFILE_LIST) | \
		sort | \
		column -s ':' -t

.PHONY: run
run: ## Run the app
	@source ./files/dev/env.sh && \
	flask run --debug -h localhost -p 5000

.PHONY: lint
lint: ## Lint the code
	ruff check && \
	mypy

.PHONY: fmt
fmt: ## Format the code
	ruff check --fix

.PHONY: init-db
init-db: ## Initialize the dev database
	flask db-extras init-db

.PHONY: test
test: ## Run the test suite
	docker-compose exec app bash -c "poetry run pytest -vv tests -p no:warnings"

.PHONY: lint
lint: ## Lint the code
	docker-compose exec app poetry run bash -c "isort --check . && black --check . && flake8 --config setup.cfg . && mypy --config-file pyproject.toml ."

.PHONY: fmt
fmt: ## Format the code
	docker-compose exec app poetry run bash -c "isort . && black ."

.PHONY: shell
shell: ## Get a shell in the container
	docker-compose exec app bash
