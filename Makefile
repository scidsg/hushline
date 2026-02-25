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

.PHONY: clean
clean: ## Fully reset local dev state (containers, volumes, caches, generated assets)
	docker compose down --volumes --remove-orphans || true
	docker compose -f docker-compose.stripe.yaml down --volumes --remove-orphans || true
	rm -rf \
		.pytest_cache \
		.mypy_cache \
		.ruff_cache \
		htmlcov \
		node_modules \
		hushline/static/js \
		hushline/static/css \
		hushline/static/fonts \
		hushline/static/img
	rm -f \
		.coverage \
		.coverage.* \
		hushline/static/data/users_directory.json

.PHONY: migrate-dev
migrate-dev: ## Run dev env migrations
	$(CMD) poetry run ./scripts/dev_migrations.py

.PHONY: migrate-prod
migrate-prod: ## Run prod env (alembic) migrations
	$(CMD) poetry run flask db upgrade

.PHONY: dev-data
dev-data: migrate-dev ## Run dev env migrations, and add dev data
	$(CMD) poetry run ./scripts/dev_data.py

.PHONY: issue-bootstrap
issue-bootstrap: ## Reset Docker state and reseed dev_data before issue work
	./scripts/agent_issue_bootstrap.sh

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

.PHONY: new-database-migration
new-database-migration: ## Create a new migration
ifndef message
	$(error Env var 'MESSAGE' must be set, e.g., `MESSAGE=foo make new-database-migration`)
endif
ifdef IS_DOCKER
	$(error Cannot create migrations in docker)
endif
	docker compose down && \
	docker compose run --rm app bash -c \
		'make migrate-prod && poetry run flask db revision -m "$(MESSAGE)" --autogenerate'

TESTS ?= ./tests/
.PHONY: test
test: ## Run the test suite
	$(CMD) poetry run pytest --cov hushline --cov-report term --cov-report html -vv $(PYTEST_ADDOPTS) $(TESTS)

.PHONY: docs-screenshots
docs-screenshots: ## Capture docs screenshots into docs/screenshots/releases/<release>
	docker compose run --rm dev_data && \
	npm install --no-save playwright@1.54.2 && \
	npx playwright install chromium && \
	SCREENSHOT_ADMIN_PASSWORD="$${SCREENSHOT_ADMIN_PASSWORD:-Test-testtesttesttest-1}" \
	SCREENSHOT_ARTVANDELAY_PASSWORD="$${SCREENSHOT_ARTVANDELAY_PASSWORD:-Test-testtesttesttest-1}" \
	SCREENSHOT_NEWMAN_PASSWORD="$${SCREENSHOT_NEWMAN_PASSWORD:-Test-testtesttesttest-1}" \
	node scripts/capture-doc-screenshots.mjs \
		--base-url "$(or $(BASE_URL),http://localhost:8080)" \
		--release "$(or $(RELEASE),local)" \
		--manifest docs/screenshots/scenes.json

.PHONY: docs-screenshots-first-user
docs-screenshots-first-user: migrate-dev ## Capture first-user admin-creation screenshot (brand-new instance) into admin session dir
	npm install --no-save playwright@1.54.2 && \
	npx playwright install chromium && \
	SCREENSHOT_ADMIN_PASSWORD="$${SCREENSHOT_ADMIN_PASSWORD:-Test-testtesttesttest-1}" \
	node scripts/capture-doc-screenshots.mjs \
		--base-url "$(or $(BASE_URL),http://localhost:8080)" \
		--release "$(or $(RELEASE),local)" \
		--manifest docs/screenshots/scenes.first-user.json
