#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: ops/agent.sh <issue_number>" >&2
  exit 2
fi

ISSUE="$1"
REPO="scidsg/hushline"
TOKEN_FILE="/etc/hushline-agent/token"

export GITHUB_TOKEN="$(cat "$TOKEN_FILE")"

# Fetch issue data
ISSUE_JSON="$(gh issue view "$ISSUE" -R "$REPO" --json number,title,body,url -q '.')"
ISSUE_TITLE="$(jq -r '.title' <<<"$ISSUE_JSON")"
ISSUE_BODY="$(jq -r '.body' <<<"$ISSUE_JSON")"

# Prepare branch
BR="agent/issue-${ISSUE}-$(date +%Y%m%d-%H%M%S)"
git fetch origin
git checkout -B "$BR" origin/$(git symbolic-ref --short refs/remotes/origin/HEAD | cut -d/ -f2)

# Build prompt
export ISSUE_NUMBER="$ISSUE"
export ISSUE_TITLE
export ISSUE_BODY
envsubst < ops/agent_prompt.tmpl > /tmp/agent_prompt.txt

# Run aider (single pass). Review/commit generated diffs automatically.
aider --yes --message "$(cat /tmp/agent_prompt.txt)"

# Test
set +e
pytest -q
RC=$?
set -e

# If tests fail, open PR anyway with note; humans can iterate.
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
