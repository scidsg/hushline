.DEFAULT_GOAL := help

ifndef IS_DOCKER
CMD := docker compose run --rm app
else
CMD :=
endif

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
	docker compose up --build

.PHONY: run-full
run-full: ## Run the app with all features enabled
	docker compose -f docker-compose.stripe.yaml up --build

.PHONY: migrate-dev
migrate-dev: ## Run dev env migrations
	$(CMD) poetry run ./scripts/dev_migrations.py

.PHONY: migrate-prod
migrate-prod: ## Run prod env (alembic) migrations
	$(CMD) poetry run flask db upgrade

.PHONY: dev-data
dev-data: migrate-dev ## Run dev env migrations, and add dev data
	$(CMD) poetry run ./scripts/dev_data.py

.PHONY: lint
lint: ## Lint the code
	$(CMD) poetry run ruff format --check && \
	$(CMD) poetry run ruff check --output-format full && \
	$(CMD) poetry run mypy . && \
	$(CMD) npx prettier --check ./*.md ./docs ./.github/workflows/* ./hushline

.PHONY: fix
fix: ## Format the code
	$(CMD) poetry run ruff format && \
	$(CMD) poetry run ruff check --fix && \
	$(CMD) npx prettier --write ./*.md ./docs ./.github/workflows/* ./hushline

.PHONY: revision
revision: migrate-prod ## Create a new migration
ifndef message
	$(error 'message' must be set when invoking the revision target, eg `make revision message="short message"`)
endif
	$(CMD) poetry run flask db revision -m "$(message)" --autogenerate

TESTS ?= ./tests/
.PHONY: test
test: ## Run the test suite
	$(CMD) poetry run pytest --cov hushline --cov-report term --cov-report html -vv $(PYTEST_ADDOPTS) $(TESTS)
