#!/usr/bin/env bash
set -euo pipefail
set -x

# usage: ops/agent.sh <issue_number>
if [[ $# -ne 1 ]]; then
  echo "usage: ops/agent.sh <issue_number>" >&2
  exit 2
fi

# Python interpreter (passed from workflow; fallback to 3.11, then python3)
PYTHON_BIN="${PYTHON:-python3.11}"
command -v "$PYTHON_BIN" >/dev/null || PYTHON_BIN="python3"

# Require token via env (workflow secret)
: "${GH_TOKEN:?GH_TOKEN missing}"
export GITHUB_TOKEN="$GH_TOKEN"

# Aider model/provider → Ollama
MODEL="${AIDER_MODEL:-ollama:qwen2.5-coder:7b-instruct}"
export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"

ISSUE="$1"
REPO="scidsg/hushline"

# Minimal deps
for bin in gh git aider; do
  command -v "$bin" >/dev/null || { echo "missing dependency: $bin"; exit 1; }
done
"$PYTHON_BIN" - <<'PY' >/dev/null || { echo "python unusable"; exit 1; }
import sys, importlib; print(sys.version); importlib.import_module("pytest")
PY

# Ensure repo root
[[ -d .git && -e ops/agent_prompt.tmpl ]] || { echo "run from repo root"; exit 2; }

# Git identity (local)
git config user.name  >/dev/null 2>&1 || git config user.name  "hushline-agent"
git config user.email >/dev/null 2>&1 || git config user.email "agent@users.noreply.github.com"

# Issue data
mapfile -t FIELDS < <(gh issue view "$ISSUE" -R "$REPO" --json title,body -q '.title, .body')
ISSUE_TITLE="${FIELDS[0]:-}"
ISSUE_BODY="${FIELDS[1]:-}"

# Default branch: GH API → git remote → main
DEFAULT_BRANCH="$(gh repo view "$REPO" --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null || true)"
if [[ -z "$DEFAULT_BRANCH" ]]; then
  DEFAULT_BRANCH="$(git remote show origin 2>/dev/null | sed -n 's/.*HEAD branch: //p' || true)"
fi
[[ -n "$DEFAULT_BRANCH" ]] || DEFAULT_BRANCH="main"

git fetch origin --prune
BR="agent/issue-${ISSUE}-$(date +%Y%m%d-%H%M%S)"
git checkout -B "$BR" "origin/${DEFAULT_BRANCH}"

# Build prompt inline
TMP_PROMPT="/tmp/agent_prompt.txt"
{
  printf 'You are the Hush Line code assistant. Work only in this repository.\n'
  printf 'Issue #: %s\n' "$ISSUE"
  printf 'Title: %s\n\n' "$ISSUE_TITLE"
  cat <<'EOF'
Task:
- Write minimal pytest tests that reproduce the issue or define the requested feature.
- Implement the smallest change to pass tests.
- Preserve public APIs and security posture (CSP, TOTP, Tor, crypto).
- Use repository conventions (pytest, Black/isort). No new services/env vars.

Output rules:
- Return unified diffs only (no prose).
- If touching auth/CSP/crypto, include tests hardening those paths.

Context:
EOF
  printf '%s\n' "$ISSUE_BODY"
} > "$TMP_PROMPT"

# Aider pass (non-interactive, Ollama model, unified diffs, skip .gitignore prompt)
aider \
  --model "$MODEL" \
  --yes \
  --no-gitignore \
  --edit-format unified \
  --message "$(cat "$TMP_PROMPT")"

# No changes → comment and exit
if git diff --quiet && git diff --cached --quiet; then
  gh issue comment "$ISSUE" -R "$REPO" -b "Agent found no changes to propose for branch \`$BR\`."
  exit 0
fi

# Tests
set +e
"$PYTHON_BIN" -m pytest -q
RC=$?
set -e

# Commit/push
git add -A
git commit -m "Agent pass for #${ISSUE} (tests rc=${RC})" || true
git push -u origin "$BR"

# PR create/update
EXISTING_PR="$(gh pr list -R "$REPO" --head "$BR" --json number -q '.[0].number')"
if [[ -z "${EXISTING_PR}" ]]; then
  gh pr create -R "$REPO" \
    -t "Agent patch for #${ISSUE}: ${ISSUE_TITLE}" \
    -b "Automated patch for #${ISSUE}.\nTest exit code: ${RC}."
else
  gh pr comment -R "$REPO" "${EXISTING_PR}" -b "Updated patch. Test exit code: ${RC}."
fi

# Link PR to issue
gh issue comment "$ISSUE" -R "$REPO" \
  -b "Agent created/updated PR from branch \`$BR\`. Test exit code: ${RC}."
