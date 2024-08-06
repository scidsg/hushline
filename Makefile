.DEFAULT_GOAL := help

.PHONY: help
help: ## Print the help message
	@awk 'BEGIN {FS = ":.*?## "} /^[0-9a-zA-Z_-]+:.*?## / {printf "\033[36m%s\033[0m : %s\n", $$1, $$2}' $(MAKEFILE_LIST) | \
		sort | \
		column -s ':' -t

.PHONY: install
install:
	poetry install

.PHONY: run
run: migrate ## Run the app
	. ./dev_env.sh && \
	poetry run flask run --debug -h localhost -p 8080

.PHONY: lint
lint: ## Lint the code
	poetry run ruff format --check && \
	poetry run ruff check && \
	poetry run mypy .

.PHONY: fix
fix: ## Format the code
	poetry run ruff format && \
	poetry run ruff check --fix

.PHONY: migrate
migrate: ## Apply migrations
	. ./dev_env.sh && \
	poetry run flask db upgrade

.PHONY: revision
revision:  ## Create a new migration
ifndef message
	$(error 'message' must be set when invoking the revision target, eg `make revision message="short message"`)
endif
	. ./dev_env.sh && \
	poetry run flask db revision -m "$(message)"

.PHONY: test
test: ## Run the test suite
	. ./dev_env.sh && \
	poetry run pytest -vv tests
