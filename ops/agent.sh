#!/usr/bin/env bash
set -euo pipefail
set -x

# usage: ops/agent.sh <issue_number>
if [[ $# -ne 1 ]]; then
  echo "usage: ops/agent.sh <issue_number>" >&2
  exit 2
fi

ISSUE="$1"
REPO="${REPO:-scidsg/hushline}"

# Auth
: "${GH_TOKEN:?GH_TOKEN not set}"
export GITHUB_TOKEN="$GH_TOKEN"

# LLM/Aider config (Ollama local)
export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
export LITELLM_PROVIDER="${LITELLM_PROVIDER:-ollama}"
export LITELLM_OLLAMA_BASE="${LITELLM_OLLAMA_BASE:-$OLLAMA_HOST}"
MODEL="${AIDER_MODEL:-ollama:qwen2.5-coder:7b-instruct}"

# Repo root + prompt template
[[ -d .git ]] || { echo "must run in repo root"; exit 1; }
[[ -f ops/agent_prompt.tmpl ]] || { echo "missing ops/agent_prompt.tmpl"; exit 1; }

# Git identity
git config user.name  >/dev/null 2>&1 || git config user.name  "hushline-agent"
git config user.email >/dev/null 2>&1 || git config user.email "agent@users.noreply.github.com"

# Dependencies
for bin in gh git aider; do command -v "$bin" >/dev/null || { echo "missing dependency: $bin"; exit 1; }; done

# Python/pytest if needed
PYTHON_BIN="${PYTHON:-$(command -v python3)}"
"$PYTHON_BIN" - <<'PY'
import sys
print(sys.version)
PY
set +e
"$PYTHON_BIN" -c 'import pytest' >/dev/null 2>&1
HAVE_PYTEST=$?
set -e

# Issue data (preserve newlines)
ISSUE_TITLE="$(gh issue view "$ISSUE" -R "$REPO" --json title -q '.title')"
ISSUE_BODY="$(gh issue view "$ISSUE" -R "$REPO" --json body  -q '.body')"

# Default branch
DEFAULT_BRANCH="$(gh repo view "$REPO" --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null || true)"
[[ -z "$DEFAULT_BRANCH" ]] && DEFAULT_BRANCH="$(git remote show origin 2>/dev/null | sed -n 's/.*HEAD branch: //p' || true)"
[[ -z "$DEFAULT_BRANCH" ]] && DEFAULT_BRANCH="main"

# Branch
BR="agent/issue-${ISSUE}-$(date +%Y%m%d-%H%M%S)"
git fetch origin --prune
git checkout -B "$BR" "origin/$DEFAULT_BRANCH"

# Prompt
export ISSUE_NUMBER="$ISSUE" ISSUE_TITLE ISSUE_BODY
envsubst < ops/agent_prompt.tmpl > /tmp/agent_prompt.txt

# Candidate files (non-interactive)
TARGET_FILES=()
if grep -q "assets/scss/style.scss" <<<"$ISSUE_BODY"; then TARGET_FILES+=("assets/scss/style.scss"); fi
[[ ${#TARGET_FILES[@]} -eq 0 ]] && TARGET_FILES=("assets/scss/style.scss")

# --- helper: run aider with message and optional extra context ---
run_aider() {
  local msg="$1"
  aider \
    --yes \
    --no-gitignore \
    --model "$MODEL" \
    --edit-format udiff \
    --max-chat-history-tokens 12000 \
    --map-tokens 12000 \
    --message "$msg" \
    "${TARGET_FILES[@]}" || true
}

# Initial edit pass
run_aider "$(cat /tmp/agent_prompt.txt)"

# If nothing changed, note and exit
if git diff --quiet; then
  gh issue comment "$ISSUE" -R "$REPO" -b "Agent run: no changes were made."
  exit 0
fi

# --- Lint phase with feedback loop (up to 2 fixer iterations) ---
lint_once() {
  local report=""
  local rc=0

  # Prefer repo-native lint target
  if [[ -f Makefile ]] && grep -qE '^[[:space:]]*lint:' Makefile; then
    set +e
    report="$(make lint 2>&1)"
    rc=$?
    set -e
  # npm lint script if present
  elif [[ -f package.json ]] && command -v jq >/dev/null && jq -e '.scripts.lint' package.json >/dev/null; then
    command -v npm >/dev/null || { echo "npm not found"; return 0; }
    set +e
    npm ci --no-audit --prefer-offline >/dev/null 2>&1 || true
    report="$(npm run -s lint 2>&1)"
    rc=$?
    set -e
  else
    # Fallback Python linters if available
    local had_any=0
    report=""
    rc=0
    if "$PYTHON_BIN" -m black --version >/dev/null 2>&1; then
      had_any=1
      set +e; out="$("$PYTHON_BIN" -m black --check . 2>&1)"; r=$?; set -e
      [[ $r -ne 0 ]] && rc=1 && report+=$'\n'"[black]:"$'\n'"$out"$'\n'
    fi
    if "$PYTHON_BIN" -m isort --version >/dev/null 2>&1; then
      had_any=1
      set +e; out="$("$PYTHON_BIN" -m isort --check-only . 2>&1)"; r=$?; set -e
      [[ $r -ne 0 ]] && rc=1 && report+=$'\n'"[isort]:"$'\n'"$out"$'\n'
    fi
    if "$PYTHON_BIN" -m ruff --version >/dev/null 2>&1; then
      had_any=1
      set +e; out="$("$PYTHON_BIN" -m ruff check . 2>&1)"; r=$?; set -e
      [[ $r -ne 0 ]] && rc=1 && report+=$'\n'"[ruff]:"$'\n'"$out"$'\n'
    fi
    [[ $had_any -eq 0 ]] && return 0
    [[ -z "$report" ]] && report="linters passed"
  fi

  echo "$report"
  return $rc
}

fix_with_lint_feedback() {
  local attempts=0 max=2
  while : ; do
    lint_output="$(lint_once)"
    lint_rc=$?
    if [[ $lint_rc -eq 0 ]]; then
      echo "Linters passed"
      return 0
    fi
    if (( attempts >= max )); then
      echo "Linters still failing after $max fixes"
      gh issue comment "$ISSUE" -R "$REPO" -b "Linters failing after $max attempts:\n\n```\n${lint_output}\n```"
      return 1
    fi
    run_aider "Fix these linter errors/warnings. Change only what's needed.\n\n```\n${lint_output}\n```"
    attempts=$((attempts+1))
    # stage intermediate fixes so subsequent diffs are smaller
    git add -A || true
    git commit -m "agent: lint-driven fix attempt ${attempts}" || true
  done
}

fix_with_lint_feedback || true

# --- Tests (optional; skip if pytest unavailable) ---
TEST_RC=0
if [[ $HAVE_PYTEST -eq 0 ]]; then
  export DATABASE_URL="${DATABASE_URL:-sqlite:///test.db}"
  set +e
  "$PYTHON_BIN" -m pytest -q
  TEST_RC=$?
  set -e
else
  echo "pytest not available; skipping tests"
fi

# Final commit and push
git add -A
git commit -m "Agent pass for #${ISSUE} (tests rc=${TEST_RC})" || true
git push -u origin "$BR"

# PR
EXISTING_PR="$(gh pr list -R "$REPO" --head "$BR" --json number -q '.[0].number')"
if [[ -z "$EXISTING_PR" ]]; then
  gh pr create -R "$REPO" \
    -t "Agent patch for #${ISSUE}: ${ISSUE_TITLE}" \
    -b "Automated patch for #${ISSUE}. Test exit code: ${TEST_RC}."
else
  gh pr comment -R "$REPO" "$EXISTING_PR" -b "Updated patch. Test exit code: ${TEST_RC}."
fi

# Link back to issue
gh issue comment "$ISSUE" -R "$REPO" \
  -b "Agent created/updated PR from branch \`$BR\`. Test exit code: ${TEST_RC}."
