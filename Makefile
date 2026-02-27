.DEFAULT_GOAL := help

ifndef IS_DOCKER
CMD := docker compose run --rm app
else
CMD :=
endif
PRETTIER_TARGETS := ./*.md ./docs ./.github/workflows/* ./hushline
RUNNER_APP_URL ?= http://localhost:8080
RUNNER_APP_WAIT_ATTEMPTS ?= 30

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
	$(CMD) sh -lc 'if [ -x node_modules/.bin/prettier ] && node_modules/.bin/prettier --version >/dev/null 2>&1; then node_modules/.bin/prettier --check $(PRETTIER_TARGETS); elif command -v prettier >/dev/null 2>&1 && prettier --version >/dev/null 2>&1; then prettier --check $(PRETTIER_TARGETS); else echo "Error: prettier/node is unavailable in this environment." >&2; exit 1; fi'

.PHONY: fix
fix: ## Format the code
	$(CMD) poetry run ruff format && \
	$(CMD) poetry run ruff check --fix && \
	$(CMD) sh -lc 'if [ -x node_modules/.bin/prettier ] && node_modules/.bin/prettier --version >/dev/null 2>&1; then node_modules/.bin/prettier --write $(PRETTIER_TARGETS); elif command -v prettier >/dev/null 2>&1 && prettier --version >/dev/null 2>&1; then prettier --write $(PRETTIER_TARGETS); else echo "Error: prettier/node is unavailable in this environment." >&2; exit 1; fi'

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

.PHONY: audit-python
audit-python: ## Run Python dependency audit (CI-equivalent)
	$(CMD) bash -lc 'poetry self add poetry-plugin-export && poetry export -f requirements.txt --without-hashes -o /tmp/requirements.txt && python -m pip install --disable-pip-version-check pip-audit==2.10.0 && pip-audit -r /tmp/requirements.txt'

.PHONY: audit-node-runtime
audit-node-runtime: ## Run Node runtime dependency audit (CI-equivalent)
	$(CMD) npm audit --omit=dev --package-lock-only

.PHONY: audit-node-full
audit-node-full: ## Run full Node dependency audit (CI-equivalent)
	$(CMD) npm audit --package-lock-only

.PHONY: test-ci-skip-local-only
test-ci-skip-local-only: ## Run tests with CI skip-local-only options
	$(MAKE) test PYTEST_ADDOPTS="--skip-local-only"

.PHONY: test-ci-alembic
test-ci-alembic: ## Run tests with alembic + CI skip-local-only options
	$(MAKE) test PYTEST_ADDOPTS="--alembic --skip-local-only"

.PHONY: test-ccpa-compliance
test-ccpa-compliance: ## Run CCPA compliance evidence tests (CI-equivalent)
	$(MAKE) test TESTS="tests/test_ccpa_compliance.py" PYTEST_ADDOPTS="--skip-local-only"

.PHONY: test-gdpr-compliance
test-gdpr-compliance: ## Run GDPR compliance evidence tests (CI-equivalent)
	$(MAKE) test TESTS="tests/test_gdpr_compliance.py" PYTEST_ADDOPTS="--skip-local-only"

.PHONY: test-e2ee-privacy-regressions
test-e2ee-privacy-regressions: ## Run E2EE and privacy regression tests (CI-equivalent)
	$(MAKE) test TESTS="tests/test_behavior_contracts.py tests/test_resend_message.py tests/test_crypto.py tests/test_secure_session.py" PYTEST_ADDOPTS="--skip-local-only"

.PHONY: test-migration-smoke
test-migration-smoke: ## Run migration compatibility tests (CI-equivalent)
	$(MAKE) test TESTS="tests/test_migrations.py" PYTEST_ADDOPTS="--alembic --skip-local-only"

.PHONY: workflow-security-checks
workflow-security-checks: ## Run workflow security checks (CI-equivalent)
	docker run --rm -v "$(PWD):/work" -w /work rhysd/actionlint:1.7.7 -color
	@set -euo pipefail; \
	PATTERN='github\.event\.(issue|pull_request|comment|review|review_comment)(\.[A-Za-z_]+)*\.(title|body)'; \
	if rg -n --glob ".github/workflows/*.yml" --glob ".github/workflows/*.yaml" "$$PATTERN" .github/workflows; then \
	  echo "Unsafe interpolation of untrusted event text found in workflow run context."; \
	  echo "Use actions/github-script (or equivalent) to handle untrusted strings safely."; \
	  exit 1; \
	fi; \
	echo "No unsafe event text interpolation patterns found."

.PHONY: runner-wait-for-app
runner-wait-for-app: ## Wait until local app is reachable on localhost:8080
	@attempt=0; \
	until curl -fsS "$(RUNNER_APP_URL)/" > /dev/null; do \
	  attempt=$$((attempt + 1)); \
	  if [ "$$attempt" -ge "$(RUNNER_APP_WAIT_ATTEMPTS)" ]; then \
	    echo "App failed health check at $(RUNNER_APP_URL) after $$attempt attempts."; \
	    exit 1; \
	  fi; \
	  sleep 2; \
	done

.PHONY: w3c-validators
w3c-validators: runner-wait-for-app ## Run W3C HTML and CSS validators (CI-equivalent)
	mkdir -p /tmp/w3c
	curl -fsS "$(RUNNER_APP_URL)/" -o /tmp/w3c/index.html
	curl -fsS "$(RUNNER_APP_URL)/directory" -o /tmp/w3c/directory.html
	docker run --rm \
		-v /tmp/w3c:/work \
		--entrypoint java \
		ghcr.io/validator/validator:latest \
		-jar /vnu.jar --errors-only --no-langdetect /work/index.html /work/directory.html
	@set +e; \
	success=0; \
	for i in 1 2 3 4 5; do \
	  if curl -fsS -o /tmp/w3c/css.json \
	    -F "file=@hushline/static/css/style.css" \
	    -F "output=json" \
	    https://jigsaw.w3.org/css-validator/validator; then \
	    success=1; \
	    break; \
	  fi; \
	  sleep $$((i * 5)); \
	done; \
	set -e; \
	if [ "$$success" -ne 1 ]; then \
	  echo "W3C CSS validator unavailable (rate limited or error); skipping CSS validation."; \
	  exit 0; \
	fi; \
	python3 -c "import json,sys; from pathlib import Path; data=json.loads(Path('/tmp/w3c/css.json').read_text()); errors=data.get('cssvalidation',{}).get('errors',[]); sys.exit(f'W3C CSS validation failed with {len(errors)} error(s).') if errors else print('W3C CSS validation passed.')"

.PHONY: lighthouse-accessibility
lighthouse-accessibility: runner-wait-for-app ## Run Lighthouse accessibility check (CI-equivalent)
	@report_file=$$(mktemp /tmp/lighthouse-accessibility.XXXXXX.json); \
	trap 'rm -f "$$report_file"' EXIT; \
	for i in 1 2 3; do \
	  if docker run --rm --add-host=host.docker.internal:host-gateway --shm-size=1g \
	    --platform=linux/amd64 \
	    femtopixel/google-lighthouse \
	    http://host.docker.internal:8080 \
	    --only-categories=accessibility \
	    --chrome-flags="--headless --no-sandbox --disable-dev-shm-usage --disable-gpu" \
	    --output=json \
	    --output-path=stdout \
	    --quiet > "$$report_file"; then \
	    break; \
	  fi; \
	  if [ "$$i" -eq 3 ]; then \
	    echo "Lighthouse accessibility failed after $$i attempts."; \
	    exit 1; \
	  fi; \
	  sleep $$((i * 5)); \
	done; \
	SCORE=$$(python3 -c "import json,sys; from pathlib import Path; data=json.loads(Path(sys.argv[1]).read_text()); print(round(data['categories']['accessibility']['score'] * 100))" "$$report_file"); \
	if [ "$$SCORE" -lt 95 ]; then \
	  echo "Accessibility score must be at least 95, got $$SCORE"; \
	  exit 1; \
	fi

.PHONY: lighthouse-performance
lighthouse-performance: runner-wait-for-app ## Run Lighthouse performance check (CI-equivalent)
	@report_file=$$(mktemp /tmp/lighthouse-performance.XXXXXX.json); \
	trap 'rm -f "$$report_file"' EXIT; \
	for i in 1 2 3; do \
	  if docker run --rm --add-host=host.docker.internal:host-gateway --shm-size=1g \
	    --platform=linux/amd64 \
	    femtopixel/google-lighthouse \
	    http://host.docker.internal:8080/directory \
	    --only-categories=performance \
	    --preset=desktop \
	    --chrome-flags="--headless --no-sandbox --disable-dev-shm-usage --disable-gpu" \
	    --output=json \
	    --output-path=stdout \
	    --quiet > "$$report_file"; then \
	    break; \
	  fi; \
	  if [ "$$i" -eq 3 ]; then \
	    echo "Lighthouse performance failed after $$i attempts."; \
	    exit 1; \
	  fi; \
	  sleep $$((i * 5)); \
	done; \
	SCORE=$$(python3 -c "import json,sys; from pathlib import Path; data=json.loads(Path(sys.argv[1]).read_text()); print(round(data['categories']['performance']['score'] * 100))" "$$report_file"); \
	if [ "$$SCORE" -lt 95 ]; then \
	  echo "Performance score must be at least 95, got $$SCORE"; \
	  exit 1; \
	fi

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
