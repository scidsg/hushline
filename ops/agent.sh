#!/usr/bin/env bash
set -euo pipefail
set -x

if [[ $# -ne 1 ]]; then
  echo "usage: ops/agent.sh <issue_number>" >&2
  exit 2
fi

ISSUE="$1"
REPO="scidsg/hushline"

# Environment for Ollama + Aider
export OLLAMA_HOST="http://localhost:11434"
export LITELLM_PROVIDER="ollama"
export LITELLM_OLLAMA_BASE="http://localhost:11434"
export AIDER_MODEL="ollama:qwen2.5-coder:7b-instruct"
export AIDER_MAX_CHAT_HISTORY_TOKENS=8192
export AIDER_MAP_TOKENS=4096

# Ensure repo root
[[ -d .git ]] || { echo "must run in repo root"; exit 1; }
[[ -f ops/agent_prompt.tmpl ]] || { echo "missing ops/agent_prompt.tmpl"; exit 1; }

# Ensure git identity
git config user.name  >/dev/null 2>&1 || git config user.name  "hushline-agent"
git config user.email >/dev/null 2>&1 || git config user.email "agent@users.noreply.github.com"

# Fetch issue data (preserve newlines)
ISSUE_TITLE="$(gh issue view "$ISSUE" -R "$REPO" --json title -q '.title')"
ISSUE_BODY="$(gh issue view "$ISSUE" -R "$REPO" --json body  -q '.body')"

# Determine default branch
DEFAULT_BRANCH="$(gh repo view "$REPO" --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null || true)"
if [[ -z "$DEFAULT_BRANCH" ]]; then
  DEFAULT_BRANCH="$(git remote show origin 2>/dev/null | sed -n 's/.*HEAD branch: //p' || true)"
fi
if [[ -z "$DEFAULT_BRANCH" ]]; then
  DEFAULT_BRANCH="main"
fi

# Prepare branch
BR="agent/issue-${ISSUE}-$(date +%Y%m%d-%H%M%S)"
git fetch origin --prune
git checkout -B "$BR" "origin/$DEFAULT_BRANCH"

# Build prompt
export ISSUE_NUMBER="$ISSUE"
export ISSUE_TITLE
export ISSUE_BODY
envsubst < ops/agent_prompt.tmpl > /tmp/agent_prompt.txt

# Run aider with Ollama, preloading candidate files
TARGET_FILES=()
if grep -q "assets/scss/style.scss" <<<"$ISSUE_BODY"; then
  TARGET_FILES+=("assets/scss/style.scss")
fi

if [[ ${#TARGET_FILES[@]} -eq 0 ]]; then
  TARGET_FILES=("assets/scss/style.scss")
fi

aider --yes \
  --model "$AIDER_MODEL" \
  --edit-format udiff \
  --message "$(cat /tmp/agent_prompt.txt)" \
  "${TARGET_FILES[@]}"

# Test (use SQLite by default)
export DATABASE_URL="${DATABASE_URL:-sqlite:///test.db}"
set +e
pytest -q
RC=$?
set -e

# Commit and push
git add -A
git commit -m "Agent pass for #${ISSUE} (tests rc=${RC})" || true
git push -u origin "$BR"

# Create or update PR
EXISTING_PR=$(gh pr list -R "$REPO" --head "$BR" --json number -q '.[0].number')
if [[ -z "$EXISTING_PR" ]]; then
  gh pr create -R "$REPO" -t "Agent patch for #$ISSUE: ${ISSUE_TITLE}" -b "Automated patch for #$ISSUE. Test exit code: ${RC}."
else
  gh pr comment -R "$REPO" "$EXISTING_PR" -b "Updated patch. Test exit code: ${RC}."
fi

# Link PR to the issue
gh issue comment "$ISSUE" -R "$REPO" -b "Agent created/updated PR from branch \`$BR\`. Test exit code: ${RC}."
