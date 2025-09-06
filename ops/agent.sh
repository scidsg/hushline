#!/usr/bin/env bash
set -euo pipefail

# usage: ops/agent.sh <issue_number>
if [[ $# -ne 1 ]]; then
  echo "usage: ops/agent.sh <issue_number>" >&2
  exit 2
fi

# Interpreter selection (default to python3.11 if available)
PYTHON_BIN="${PYTHON:-python3.11}"
if ! command -v "$PYTHON_BIN" >/dev/null; then
  PYTHON_BIN="python3"
fi

# Require token via env (passed from workflow secrets)
: "${GH_TOKEN:?GH_TOKEN missing}"
export GITHUB_TOKEN="$GH_TOKEN"

ISSUE="$1"
REPO="scidsg/hushline"

# Dependencies
for bin in gh jq envsubst aider git; do
  command -v "$bin" >/dev/null || { echo "missing dependency: $bin"; exit 1; }
done
# Python deps check
"$PYTHON_BIN" -c 'import sys; print(sys.version)' >/dev/null || { echo "python not usable"; exit 1; }
"$PYTHON_BIN" -c 'import pytest' >/dev/null || { echo "missing dependency: pytest (for selected python)"; exit 1; }

# Ensure repo root
[[ -d .git && -f ops/agent_prompt.tmpl ]] || { echo "run from repo root"; exit 2; }

# Git identity (local)
git config user.name  >/dev/null || git config user.name  "hushline-agent"
git config user.email >/dev/null || git config user.email "agent@users.noreply.github.com"

# Fetch issue data
ISSUE_JSON="$(gh issue view "$ISSUE" -R "$REPO" --json number,title,body,url -q '.')"
ISSUE_TITLE="$(jq -r '.title' <<<"$ISSUE_JSON")"
ISSUE_BODY="$(jq -r '.body'  <<<"$ISSUE_JSON")"

# Branch
git fetch origin --prune
DEFAULT_BRANCH="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD | cut -d/ -f2)"
BR="agent/issue-${ISSUE}-$(date +%Y%m%d-%H%M%S)"
git checkout -B "$BR" "origin/${DEFAULT_BRANCH}"

# Prompt
export ISSUE_NUMBER="$ISSUE" ISSUE_TITLE ISSUE_BODY
envsubst < ops/agent_prompt.tmpl > /tmp/agent_prompt.txt

# Aider pass (non-interactive)
aider --yes --message "$(cat /tmp/agent_prompt.txt)"

# Nothing changed? Exit with comment.
if git diff --quiet && git diff --cached --quiet; then
  gh issue comment "$ISSUE" -R "$REPO" -b "Agent found no changes to propose for branch \`$BR\`."
  exit 0
fi

# Tests under selected Python
set +e
"$PYTHON_BIN" -m pytest -q
RC=$?
set -e

git add -A
git commit -m "Agent pass for #${ISSUE} (tests rc=${RC})" || true
git push -u origin "$BR"

EXISTING_PR="$(gh pr list -R "$REPO" --head "$BR" --json number -q '.[0].number')"
if [[ -z "${EXISTING_PR}" ]]; then
  gh pr create -R "$REPO" \
    -t "Agent patch for #${ISSUE}: ${ISSUE_TITLE}" \
    -b "Automated patch for #${ISSUE}.\nTest exit code: ${RC}."
else
  gh pr comment -R "$REPO" "${EXISTING_PR}" -b "Updated patch. Test exit code: ${RC}."
fi

gh issue comment "$ISSUE" -R "$REPO" \
  -b "Agent created/updated PR from branch \`$BR\`. Test exit code: ${RC}."
