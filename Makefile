.DEFAULT_GOAL := help

.PHONY: help
help: ## Print the help message
	@awk 'BEGIN {FS = ":.*?## "} /^[0-9a-zA-Z_-]+:.*?## / {printf "\033[36m%s\033[0m : %s\n", $$1, $$2}' $(MAKEFILE_LIST) | \
		sort | \
		column -s ':' -t

.PHONY: run
run: ## Run the app
	. ./dev_env.sh && \
	flask run --debug -h localhost -p 5000

.PHONY: lint
lint: ## Lint the code
	ruff check && \
	mypy .

.PHONY: fix
fix: ## Format the code
	ruff check --fix

.PHONY: migrate
migrate:
	. ./dev_env.sh && \
	flask db upgrade

.PHONY: test
test: ## Run the test suite
	. ./dev_env.sh && \
	pytest -vv tests -p no:warnings
