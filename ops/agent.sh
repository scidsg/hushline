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

: "${GH_TOKEN:?GH_TOKEN must be set in env}"
export GITHUB_TOKEN="$GH_TOKEN"

# Hard caps to avoid stalls on Jetson
export OLLAMA_API_BASE="${OLLAMA_API_BASE:-http://127.0.0.1:11434}"
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_KEEP_ALIVE=10m
export AIDER_ANALYTICS_DISABLE=1

# Native Ollama provider for Aider; avoid LiteLLM
unset LITELLM_PROVIDER LITELLM_OLLAMA_BASE OPENAI_API_KEY ANTHROPIC_API_KEY
MODEL="${AIDER_MODEL:-ollama_chat/qwen2.5-coder:7b-instruct}"

# Repo root and prompt
[[ -d .git ]] || { echo "must run in repo root"; exit 1; }
[[ -f ops/agent_prompt.tmpl ]] || { echo "missing ops/agent_prompt.tmpl"; exit 1; }

# Git identity
git config user.name  >/dev/null 2>&1 || git config user.name  "hushline-agent"
git config user.email >/dev/null 2>&1 || git config user.email "agent@users.noreply.github.com"

# Deps
for bin in gh git aider curl jq; do
  command -v "$bin" >/dev/null || { echo "missing dependency: $bin"; exit 1; }
done

# Quick Ollama health check (fail fast instead of hanging)
set +e
curl -sS "${OLLAMA_API_BASE}/api/tags" | jq -r .models[0].name >/dev/null
HEALTH_RC=$?
set -e
[[ $HEALTH_RC -ne 0 ]] && { echo "ollama health check failed"; exit 1; }

# Issue data (preserve newlines)
ISSUE_TITLE="$(gh issue view "$ISSUE" -R "$REPO" --json title -q .title)"
ISSUE_BODY="$(gh issue view "$ISSUE" -R "$REPO" --json body  -q .body)"

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

# Detect target files from the issue to avoid full repo-map
TARGET_FILES=()
while IFS= read -r f; do
  [[ -f "$f" ]] && TARGET_FILES+=("$f")
done < <(echo "$ISSUE_BODY" | grep -Eo '([A-Za-z0-9._/-]+\.(scss|css|py|js|ts|html|jinja2))' | sort -u)

# Aider args tuned for low RAM devices
AIDER_ARGS=(
  --yes
  --no-gitignore
  --model "$MODEL"
  --edit-format udiff
  --timeout 180          # internal aider HTTP timeout
  --no-stream            # avoid TTY/stream stalls
  --map-refresh files    # only map files we pass, not whole repo
  --map-multiplier-no-files 0
  --map-tokens 1024
  --max-chat-history-tokens 2048
)

# Ensure local Ollama endpoint for litellm/Aider
export OLLAMA_API_BASE="${OLLAMA_API_BASE:-http://127.0.0.1:11434}"
export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"  # harmless; some libs read this

run_aider() {
  if [[ ${#TARGET_FILES[@]} -gt 0 ]]; then
    timeout -k 10 240 aider "${AIDER_ARGS[@]}" --message "$(cat /tmp/agent_prompt.txt)" "${TARGET_FILES[@]}" || true
  else
    timeout -k 10 240 aider "${AIDER_ARGS[@]}" --message "$(cat /tmp/agent_prompt.txt)" || true
  fi
}

# First pass
run_aider

# No changes -> report and exit
if git diff --quiet; then
  gh issue comment "$ISSUE" -R "$REPO" -b "Agent attempted patch but no changes were made."
  exit 0
fi

# Lint loop (up to 2 passes); feed failures back in small prompts
lint_once() {
  local log=/tmp/lint.log rc=0
  if [[ -f Makefile ]] && grep -qE '^[[:space:]]*lint:' Makefile; then
    set +e; make lint > /dev/null 2> "$log"; rc=$?; set -e
  elif [[ -f package.json ]] && command -v jq >/dev/null && jq -e '.scripts.lint' package.json >/dev/null; then
    set +e
    npm ci --no-audit --prefer-offline >/dev/null 2>&1 || true
    npm run -s lint > /dev/null 2> "$log"; rc=$?
    set -e
  else
    echo "no linters configured" > "$log"; rc=0
  fi
  echo "$log:$rc"
}

for attempt in 1 2; do
  out_rc="$(lint_once)"; log="${out_rc%:*}"; rc="${out_rc##*:}"
  if [[ "$rc" -eq 0 ]]; then break; fi
  FEEDBACK="$(tail -n 200 "$log")"
  printf '%s\n' "Fix these lint errors. Change only what's needed.

\`\`\`
${FEEDBACK}
\`\`\`
" > /tmp/agent_feedback.txt
  # Replace prompt body with feedback for the fix attempt
  timeout -k 10 180 aider "${AIDER_ARGS[@]}" --message "$(cat /tmp/agent_feedback.txt)" || true
  git add -A || true
  git commit -m "agent: lint fix attempt $attempt" || true
done

# Decide whether to run pytest (skip for frontend-only diffs)
run_tests=true
changed_files="$(git diff --name-only "origin/$DEFAULT_BRANCH"...)"
if grep -qE '\.(scss|css|js|ts|html|jinja2)$' <<<"$changed_files" && ! grep -qE '\.py($| )' <<<"$changed_files"; then
  run_tests=false
fi

RC=0
if $run_tests && command -v pytest >/dev/null 2>&1; then
  export DATABASE_URL="${DATABASE_URL:-sqlite:///./test.db}"
  set +e; timeout -k 10 300 pytest -q; RC=$?; set -e
fi

# Commit & push
git add -A
git commit -m "Agent patch for #${ISSUE} (${ISSUE_TITLE}) (tests rc=${RC})" || true
git push -u origin "$BR"

# PR
EXISTING_PR="$(gh pr list -R "$REPO" --head "$BR" --json number -q '.[0].number')"
if [[ -z "$EXISTING_PR" ]]; then
  gh pr create -R "$REPO" -t "Agent patch for #${ISSUE}: ${ISSUE_TITLE}" -b "Automated patch for #${ISSUE}. Test exit code: ${RC}."
else
  gh pr comment -R "$REPO" "$EXISTING_PR" -b "Updated patch. Test exit code: ${RC}."
fi

gh issue comment "$ISSUE" -R "$REPO" -b "Agent created/updated PR from branch \`$BR\`. Test exit code: ${RC}."
