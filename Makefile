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
run: ## Run the app in a limited mode
	docker compose up

.PHONY: run-full
run-full: ## Run the app with all features enabled
	docker compose -f docker-compose.stripe.yaml up

.PHONY: migrate-dev
migrate-dev: ## Run dev env migrations
	poetry run ./scripts/dev_migrations.py

.PHONY: migrate-prod
migrate-prod: ## Run prod env (alembic) migrations
	poetry run flask db upgrade

.PHONY: dev-data
dev-data: migrate-dev ## Run dev env migrations, and add dev data
	poetry run ./scripts/dev_data.py

.PHONY: lint
lint: ## Lint the code
	poetry run ruff format --check && \
	poetry run ruff check --output-format full && \
	poetry run mypy . && \
	docker compose run --rm app npx prettier --check ./*.md ./docs ./.github/workflows/* ./hushline

.PHONY: fix
fix: ## Format the code
	poetry run ruff format && \
	poetry run ruff check --fix && \
	docker compose run --rm app npx prettier --write ./*.md ./docs ./.github/workflows/* ./hushline

.PHONY: revision
revision: migrate-prod ## Create a new migration
ifndef message
	$(error 'message' must be set when invoking the revision target, eg `make revision message="short message"`)
endif
	poetry run flask db revision -m "$(message)" --autogenerate

TESTS ?= ./tests
.PHONY: test
test: ## Run the test suite
	docker compose run --rm app \
		poetry run pytest --cov hushline --cov-report term --cov-report html -vv $(PYTEST_ADDOPTS) $(TESTS)

.PHONY: test/ui
test/ui: # Only run the ui tests
	docker compose run --rm app \
		poetry run pytest --cov hushline --cov-report term --cov-report html -vv $(PYTEST_ADDOPTS) $(TESTS)/ui
