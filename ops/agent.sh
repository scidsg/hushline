#!/usr/bin/env bash
set -euo pipefail
set -x

if [[ $# -ne 1 ]]; then
  echo "usage: ops/agent.sh <issue_number>" >&2
  exit 2
fi

ISSUE="$1"
REPO="scidsg/hushline"

# Require GH_TOKEN from workflow secrets
: "${GH_TOKEN:?GH_TOKEN missing}"
export GITHUB_TOKEN="$GH_TOKEN"

# Dependencies
for bin in gh git aider; do
  command -v "$bin" >/dev/null || { echo "missing dependency: $bin"; exit 1; }
done

# Python check (pytest in venv if set)
PYTHON_BIN="${PYTHON:-python3.11}"
"$PYTHON_BIN" -c 'import sys; print(sys.version)'
"$PYTHON_BIN" -c 'import pytest' || { echo "pytest missing"; exit 1; }

# Ensure repo root
[[ -d .git ]] || { echo "must run in repo root"; exit 1; }
[[ -f ops/agent_prompt.tmpl ]] || { echo "missing ops/agent_prompt.tmpl"; exit 1; }

# Ensure git identity
git config user.name >/dev/null 2>&1 || git config user.name "hushline-agent"
git config user.email >/dev/null 2>&1 || git config user.email "agent@users.noreply.github.com"

# Fetch issue data
mapfile -t FIELDS < <(gh issue view "$ISSUE" -R "$REPO" --json title,body -q '.title, .body')
ISSUE_TITLE="${FIELDS[0]}"
ISSUE_BODY="${FIELDS[1]}"

# Determine default branch: GH API → git remote → fallback
DEFAULT_BRANCH="$(gh repo view "$REPO" --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null || true)"
if [[ -z "$DEFAULT_BRANCH" ]]; then
  DEFAULT_BRANCH="$(git remote show origin 2>/dev/null | sed -n 's/.*HEAD branch: //p' || true)"
fi
if [[ -z "$DEFAULT_BRANCH" ]]; then
  DEFAULT_BRANCH="main"
fi

git fetch origin --prune
BR="agent/issue-${ISSUE}-$(date +%Y%m%d-%H%M%S)"
git checkout -B "$BR" "origin/${DEFAULT_BRANCH}"

# Build prompt
export ISSUE_NUMBER="$ISSUE" ISSUE_TITLE ISSUE_BODY
envsubst < ops/agent_prompt.tmpl > /tmp/agent_prompt.txt

# Run aider with local Ollama model
AIDER_MODEL="ollama:qwen2.5-coder:7b-instruct"
aider --yes \
  --model "$AIDER_MODEL" \
  --edit-format udiff \
  --message "$(cat /tmp/agent_prompt.txt)" || true

# Check if any changes
if git diff --cached --quiet && git diff --quiet; then
  gh issue comment "$ISSUE" -R "$REPO" -b "Agent made no changes for this issue."
  exit 0
fi

# Run tests
set +e
"$PYTHON_BIN" -m pytest -q
RC=$?
set -e

# Commit, push
git add -A
git commit -m "Agent pass for #${ISSUE} (tests rc=${RC})" || true
git push -u origin "$BR"

# Create or update PR
EXISTING_PR="$(gh pr list -R "$REPO" --head "$BR" --json number -q '.[0].number')"
if [[ -z "${EXISTING_PR}" ]]; then
  gh pr create -R "$REPO" \
    -t "Agent patch for #${ISSUE}: ${ISSUE_TITLE}" \
    -b "Automated patch for #${ISSUE}. Test exit code: ${RC}."
else
  gh pr comment -R "$REPO" "${EXISTING_PR}" -b "Updated patch. Test exit code: ${RC}."
fi

# Link PR to issue
gh issue comment "$ISSUE" -R "$REPO" \
  -b "Agent created/updated PR from branch \`$BR\`. Test exit code: ${RC}."
