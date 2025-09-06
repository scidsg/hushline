#!/usr/bin/env bash
set -euo pipefail

# usage: ops/agent.sh <issue_number>
if [[ $# -ne 1 ]]; then
  echo "usage: ops/agent.sh <issue_number>" >&2
  exit 2
fi

# Require token via env (passed from workflow secrets)
: "${GH_TOKEN:?GH_TOKEN missing}"
export GITHUB_TOKEN="$GH_TOKEN"

ISSUE="$1"
REPO="scidsg/hushline"

# Dependencies (fail fast if missing)
for bin in gh jq envsubst pytest aider git; do
  command -v "$bin" >/dev/null || { echo "missing dependency: $bin"; exit 1; }
done

# Ensure we are at repo root (contains .git and ops/)
if [[ ! -d .git || ! -f ops/agent_prompt.tmpl ]]; then
  echo "run from repo root; missing .git/ or ops/agent_prompt.tmpl" >&2
  exit 2
fi

# Normalize line endings on scripts (defensive)
if command -v sed >/dev/null; then
  sed -i 's/\r$//' ops/agent.sh || true
fi

# Configure git identity locally if unset
if [[ -z "$(git config --get user.name || true)" ]]; then
  git config user.name "hushline-agent"
fi
if [[ -z "$(git config --get user.email || true)" ]]; then
  git config user.email "agent@users.noreply.github.com"
fi

# Fetch issue data
ISSUE_JSON="$(gh issue view "$ISSUE" -R "$REPO" --json number,title,body,url -q '.')"
ISSUE_TITLE="$(jq -r '.title' <<<"$ISSUE_JSON")"
ISSUE_BODY="$(jq -r '.body'  <<<"$ISSUE_JSON")"

# Prepare branch off the repo's default branch
git fetch origin --prune
DEFAULT_BRANCH="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD | cut -d/ -f2)"
BR="agent/issue-${ISSUE}-$(date +%Y%m%d-%H%M%S)"
git checkout -B "$BR" "origin/${DEFAULT_BRANCH}"

# Build prompt from template
export ISSUE_NUMBER="$ISSUE" ISSUE_TITLE ISSUE_BODY
envsubst < ops/agent_prompt.tmpl > /tmp/agent_prompt.txt

# Run aider (single pass). It will write diffs to the working tree; we commit below.
# Use non-interactive flags; rely on repo-local .aider.conf.yml if present.
aider --yes --message "$(cat /tmp/agent_prompt.txt)"

# If nothing changed, exit gracefully with a comment on the issue.
if git diff --quiet && git diff --cached --quiet; then
  gh issue comment "$ISSUE" -R "$REPO" -b "Agent found no changes to propose for branch \`$BR\`."
  exit 0
fi

# Run tests and capture exit code (do not abort on failures)
set +e
pytest -q
RC=$?
set -e

# Commit and push (annotate test RC in message)
git add -A
git commit -m "Agent pass for #${ISSUE} (tests rc=${RC})" || true
git push -u origin "$BR"

# Create or update PR
EXISTING_PR="$(gh pr list -R "$REPO" --head "$BR" --json number -q '.[0].number')"
if [[ -z "${EXISTING_PR}" ]]; then
  gh pr create -R "$REPO" \
    -t "Agent patch for #${ISSUE}: ${ISSUE_TITLE}" \
    -b "Automated patch for #${ISSUE}.\nTest exit code: ${RC}."
else
  gh pr comment -R "$REPO" "${EXISTING_PR}" -b "Updated patch. Test exit code: ${RC}."
fi

# Link PR back to the issue
gh issue comment "$ISSUE" -R "$REPO" \
  -b "Agent created/updated PR from branch \`$BR\`. Test exit code: ${RC}."
