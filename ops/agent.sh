#!/usr/bin/env bash
set -euo pipefail
set -x

if [[ $# -ne 1 ]]; then
  echo "usage: ops/agent.sh <issue_number>" >&2
  exit 2
fi

ISSUE="$1"
REPO="scidsg/hushline"

: "${GH_TOKEN:?GH_TOKEN must be set in env}"
export GITHUB_TOKEN="$GH_TOKEN"

# Enforce native Ollama provider for Aider (no litellm)
unset LITELLM_PROVIDER LITELLM_OLLAMA_BASE OPENAI_API_KEY ANTHROPIC_API_KEY
export OLLAMA_API_BASE="${OLLAMA_API_BASE:-http://127.0.0.1:11434}"
MODEL="${AIDER_MODEL:-ollama_chat/qwen2.5-coder:7b-instruct}"

# Ensure repo root and prompt template
[[ -d .git ]] || { echo "must run in repo root"; exit 1; }
[[ -f ops/agent_prompt.tmpl ]] || { echo "missing ops/agent_prompt.tmpl"; exit 1; }

# Ensure git identity
git config user.name  >/dev/null 2>&1 || git config user.name  "hushline-agent"
git config user.email >/dev/null 2>&1 || git config user.email "agent@users.noreply.github.com"

# Dependencies
for bin in gh git aider; do
  command -v "$bin" >/dev/null || { echo "missing dependency: $bin"; exit 1; }
done

# Issue data (preserve newlines)
ISSUE_TITLE="$(gh issue view "$ISSUE" -R "$REPO" --json title -q .title)"
ISSUE_BODY="$(gh issue view "$ISSUE" -R "$REPO" --json body  -q .body)"

# Default branch
DEFAULT_BRANCH="$(gh repo view "$REPO" --json defaultBranchRef -q .defaultBranchRef.name 2>/dev/null || true)"
if [[ -z "$DEFAULT_BRANCH" ]]; then
  DEFAULT_BRANCH="$(git remote show origin 2>/dev/null | sed -n 's/.*HEAD branch: //p' || true)"
fi
[[ -z "$DEFAULT_BRANCH" ]] && DEFAULT_BRANCH="main"

# Working branch
BR="agent/issue-${ISSUE}-$(date +%Y%m%d-%H%M%S)"
git fetch origin --prune
git checkout -B "$BR" "origin/$DEFAULT_BRANCH"

# Prompt
export ISSUE_NUMBER="$ISSUE" ISSUE_TITLE ISSUE_BODY
envsubst < ops/agent_prompt.tmpl > /tmp/agent_prompt.txt

# Candidate files from issue text (CSS/SCSS/JS/TS/HTML/Jinja, etc.)
TARGET_FILES=()
while IFS= read -r f; do
  [[ -f "$f" ]] && TARGET_FILES+=("$f")
done < <(echo "$ISSUE_BODY" | grep -Eo '([A-Za-z0-9._/-]+\.(scss|css|py|js|ts|html|jinja2))' | sort -u)

# Run aider against specific files if we detected any; otherwise whole repo
if [[ ${#TARGET_FILES[@]} -gt 0 ]]; then
  aider --yes --no-gitignore --edit-format udiff --model "$MODEL" "${TARGET_FILES[@]}" --message "$(cat /tmp/agent_prompt.txt)" || true
else
  aider --yes --no-gitignore --edit-format udiff --model "$MODEL" --message "$(cat /tmp/agent_prompt.txt)" || true
fi

# No changes? comment and exit
if git diff --quiet; then
  gh issue comment "$ISSUE" -R "$REPO" -b "Agent attempted patch but no changes were made."
  exit 0
fi

# Lint loop: run, feed failures back to the model up to 2 times
for attempt in 1 2; do
  LINT_LOG=/tmp/lint.log
  if make lint >/dev/null 2> "$LINT_LOG"; then
    break
  else
    FEEDBACK="$(<"$LINT_LOG")"
    echo "Lint failed (attempt $attempt), asking model to fix."
    aider --yes --no-gitignore --edit-format udiff --model "$MODEL" --message "Fix these lint errors:\n$FEEDBACK" || true
  fi
done

# Run tests only if backend files changed
if git diff --name-only "origin/$DEFAULT_BRANCH" | grep -vqE '\.(scss|css|js|ts|html|jinja2)$'; then
  if command -v pytest >/dev/null; then
    set +e
    pytest -q
    RC=$?
    set -e
  else
    RC=0
  fi
else
  RC=0
fi

# Commit and push
git add -A
git commit -m "Agent patch for #$ISSUE (${ISSUE_TITLE}) (tests rc=${RC})" || true
git push -u origin "$BR"

# PR
EXISTING_PR=$(gh pr list -R "$REPO" --head "$BR" --json number -q '.[0].number')
if [[ -z "$EXISTING_PR" ]]; then
  gh pr create -R "$REPO" -t "Agent patch for #$ISSUE: ${ISSUE_TITLE}" -b "Automated patch for #$ISSUE. Test exit code: ${RC}."
else
  gh pr comment -R "$REPO" "$EXISTING_PR" -b "Updated patch. Test exit code: ${RC}."
fi

gh issue comment "$ISSUE" -R "$REPO" -b "Agent created/updated PR from branch \`$BR\`. Test exit code: ${RC}."
