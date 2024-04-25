.DEFAULT_GOAL := help

.PHONY: help
help: ## Print the help message
	@awk 'BEGIN {FS = ":.*?## "} /^[0-9a-zA-Z_-]+:.*?## / {printf "\033[36m%s\033[0m : %s\n", $$1, $$2}' $(MAKEFILE_LIST) | \
		sort | \
		column -s ':' -t

.PHONY: run
run: ## Run the app
	@source ./env.sh && \
	flask run --debug -h localhost -p 5000

.PHONY: lint
lint: ## Lint the code
	isort --check . && \
		black --check . && \
		flake8 . && \
		mypy .

.PHONY: fmt
fmt: ## Format the code
	isort . && \
		black .

.PHONY: init-db
init-db: ## Initialize the dev database
	flask db-extras init-db

.PHONY: test
test: ## Run the test suite
ifeq ($(CI),true)
	pytest -vv tests
else
	@source ./env.sh && pytest -vv tests
endif
