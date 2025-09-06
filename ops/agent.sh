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

# Auth for gh
: "${GH_TOKEN:?GH_TOKEN not set}"
export GITHUB_TOKEN="$GH_TOKEN"

# Force native Ollama in Aider (no litellm)
unset LITELLM_PROVIDER LITELLM_OLLAMA_BASE OPENAI_API_KEY ANTHROPIC_API_KEY
export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
MODEL="${AIDER_MODEL:-ollama/qwen2.5-coder:7b-instruct}"  # NOTE: slash, not colon

# Repo root + prompt template
[[ -d .git ]] || { echo "must run in repo root"; exit 1; }
[[ -f ops/agent_prompt.tmpl ]] || { echo "missing ops/agent_prompt.tmpl"; exit 1; }

# Git identity
git config user.name  >/dev/null 2>&1 || git config user.name  "hushline-agent"
git config user.email >/dev/null 2>&1 || git config user.email "agent@users.noreply.github.com"

# Dependencies
for bin in gh git aider; do command -v "$bin" >/dev/null || { echo "missing dependency: $bin"; exit 1; }; done

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

# Candidate files from issue text (add more patterns as needed)
TARGET_FILES=()
grep -Eo '([A-Za-z0-9._/-]+\.scss)' <<<"$ISSUE_BODY" | while read -r f; do [[ -f "$f" ]] && TARGET_FILES+=("$f"); done
[[ ${#TARGET_FILES[@]} -eq 0 ]] && TARGET_FILES=("assets/scss/style.scss")

# Helper to run aider
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

# Initial edit
run_aider "$(cat /tmp/agent_prompt.txt)"

# No changes -> note and exit
if git diff --quiet; then
  gh issue comment "$ISSUE" -R "$REPO" -b "Agent run: no changes were made."
  exit 0
fi

# Lint loop (up to 2 passes), send failures back to aider
lint_once() {
  local report rc=0
  if [[ -f Makefile ]] && grep -qE '^[[:space:]]*lint:' Makefile; then
    set +e; report="$(make lint 2>&1)"; rc=$?; set -e
  elif [[ -f package.json ]] && command -v jq >/dev/null && jq -e '.scripts.lint' package.json >/dev/null; then
    command -v npm >/dev/null || { echo "npm not found"; return 0; }
    set +e
    npm ci --no-audit --prefer-offline >/dev/null 2>&1 || true
    report="$(npm run -s lint 2>&1)"; rc=$?
    set -e
  else
    report="linters passed (none configured)"
    rc=0
  fi
  echo "$report"; return $rc
}

attempts=0; max=2
while : ; do
  lint_output="$(lint_once)"; lint_rc=$?
  if [[ $lint_rc -eq 0 ]]; then break; fi
  (( attempts >= max )) && { gh issue comment "$ISSUE" -R "$REPO" -b "Linters failing after $max attempts:\n\n\`\`\`\n${lint_output}\n\`\`\`"; break; }
  run_aider "Fix these linter errors. Change only what's needed.\n\n\`\`\`\n${lint_output}\n\`\`\`"
  git add -A || true
  git commit -m "agent: lint-driven fix attempt $((attempts+1))" || true
  attempts=$((attempts+1))
done

# Decide whether to run pytest (skip for frontend-only diffs)
run_tests=true
changed_files="$(git diff --name-only "origin/$DEFAULT_BRANCH"...)"
if grep -qE '^[^/]*assets/|\.scss$|\.css$|\.html$|\.js$' <<<"$changed_files"; then
  if ! grep -qE '\.py$|pyproject\.toml|poetry\.lock|setup\.cfg|setup\.py' <<<"$changed_files"; then
    run_tests=false
  fi
fi

TEST_RC=0
if $run_tests; then
  # Only run tests if repo already ensures deps; otherwise skip to avoid ModuleNotFoundError
  if command -v pytest >/dev/null 2>&1; then
    export DATABASE_URL="${DATABASE_URL:-sqlite:///./test.db}"
    set +e; pytest -q; TEST_RC=$?; set -e
  else
    echo "pytest not available; skipping tests"; TEST_RC=0
  fi
else
  echo "frontend-only change detected; skipping pytest"; TEST_RC=0
fi

# Commit & push
git add -A
git commit -m "Agent pass for #${ISSUE} (tests rc=${TEST_RC})" || true
git push -u origin "$BR"

# PR create/update
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
