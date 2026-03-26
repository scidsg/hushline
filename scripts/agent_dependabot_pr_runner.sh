#!/usr/bin/env bash
set -euo pipefail

FORCE_PR_NUMBER=""
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_REPO_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"

REPO_DIR="${HUSHLINE_REPO_DIR:-$DEFAULT_REPO_DIR}"
REPO_SLUG="${HUSHLINE_REPO_SLUG:-scidsg/hushline}"
BASE_BRANCH="${HUSHLINE_BASE_BRANCH:-main}"
BOT_LOGIN="${HUSHLINE_BOT_LOGIN:-hushline-dev}"
BOT_GIT_NAME="${HUSHLINE_BOT_GIT_NAME:-$BOT_LOGIN}"
BOT_GIT_EMAIL="${HUSHLINE_BOT_GIT_EMAIL:-git-dev@scidsg.org}"
BOT_GIT_GPG_FORMAT="${HUSHLINE_BOT_GIT_GPG_FORMAT:-ssh}"
BOT_GIT_SIGNING_KEY="${HUSHLINE_BOT_GIT_SIGNING_KEY:-}"
DEFAULT_BOT_GIT_SSH_SIGNING_KEY_PATH="${HUSHLINE_BOT_GIT_DEFAULT_SSH_SIGNING_KEY_PATH:-}"
CODEX_MODEL="${HUSHLINE_CODEX_MODEL:-gpt-5.4}"
CODEX_REASONING_EFFORT="${HUSHLINE_CODEX_REASONING_EFFORT:-high}"
DEPENDABOT_APP_SLUG="${HUSHLINE_DEPENDABOT_APP_SLUG:-dependabot}"
DEPENDABOT_BASE_BRANCH="${HUSHLINE_DEPENDABOT_BASE_BRANCH:-$BASE_BRANCH}"
DEPENDABOT_PR_LIMIT="${HUSHLINE_DEPENDABOT_PR_LIMIT:-30}"
MAX_FIX_ATTEMPTS="${HUSHLINE_DEPENDABOT_MAX_FIX_ATTEMPTS:-8}"
RUNTIME_BOOTSTRAP_ATTEMPTS="${HUSHLINE_DAILY_RUNTIME_BOOTSTRAP_ATTEMPTS:-3}"
RUNTIME_BOOTSTRAP_RETRY_DELAY_SECONDS="${HUSHLINE_DAILY_RUNTIME_BOOTSTRAP_RETRY_DELAY_SECONDS:-10}"
HOST_PORTS_TO_CLEAR="${HUSHLINE_DAILY_KILL_PORTS:-4566 4571 5432 8080}"

CHECK_LOG_FILE=""
PROMPT_FILE=""
COMMENT_BODY_FILE=""
CODEX_OUTPUT_FILE=""
CODEX_TRANSCRIPT_FILE=""
RUN_LOG_TMP_FILE=""
RUN_LOG_TIMESTAMP=""
RUN_LOG_GIT_PATH=""
RUN_LOG_RETENTION_COUNT="${HUSHLINE_DAILY_RUN_LOG_RETENTION:-10}"
VERBOSE_CODEX_OUTPUT="${HUSHLINE_DAILY_VERBOSE_CODEX_OUTPUT:-0}"
DEPENDABOT_PR_JSON_FILE=""
PR_NUMBER=""
PR_TITLE=""
PR_URL=""
PR_BODY=""
PR_HEAD_REF_NAME=""
PR_BASE_REF_NAME=""

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --pr)
        FORCE_PR_NUMBER="${2:-}"
        if [[ -z "$FORCE_PR_NUMBER" ]]; then
          echo "Missing value for --pr" >&2
          exit 1
        fi
        shift 2
        ;;
      *)
        echo "Unknown argument: $1" >&2
        exit 1
        ;;
    esac
  done
}

initialize_run_state() {
  CHECK_LOG_FILE="$(mktemp)"
  PROMPT_FILE="$(mktemp)"
  COMMENT_BODY_FILE="$(mktemp)"
  CODEX_OUTPUT_FILE="$(mktemp)"
  CODEX_TRANSCRIPT_FILE="$(mktemp)"
  RUN_LOG_TMP_FILE="$(mktemp)"
  DEPENDABOT_PR_JSON_FILE="$(mktemp)"
  RUN_LOG_TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

  exec 3>&1
  exec > >(tee -a "$RUN_LOG_TMP_FILE") 2>&1
  echo "Dependabot runner Codex config: model=$CODEX_MODEL reasoning_effort=$CODEX_REASONING_EFFORT verbose_codex_output=$VERBOSE_CODEX_OUTPUT"
}

cleanup() {
  rm -f "${CHECK_LOG_FILE:-}" "${PROMPT_FILE:-}" "${COMMENT_BODY_FILE:-}" "${CODEX_OUTPUT_FILE:-}" "${CODEX_TRANSCRIPT_FILE:-}" "${RUN_LOG_TMP_FILE:-}" "${DEPENDABOT_PR_JSON_FILE:-}"
  if [[ -d "$REPO_DIR/.git" ]]; then
    git -C "$REPO_DIR" checkout "$BASE_BRANCH" >/dev/null 2>&1 || true
    git -C "$REPO_DIR" reset --hard "origin/$BASE_BRANCH" >/dev/null 2>&1 || git -C "$REPO_DIR" reset --hard "$BASE_BRANCH" >/dev/null 2>&1 || true
    git -C "$REPO_DIR" clean -fd >/dev/null 2>&1 || true
  fi
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_positive_integer() {
  local name="$1"
  local value="$2"

  if ! [[ "$value" =~ ^[0-9]+$ ]] || (( value < 1 )); then
    echo "${name} must be a positive integer (got '${value}')." >&2
    return 1
  fi
}

resolve_bot_git_signing_key() {
  local configured_signing_key=""
  local configured_gpg_format=""

  if [[ "$BOT_GIT_GPG_FORMAT" != "ssh" ]]; then
    printf '%s\n' "$BOT_GIT_SIGNING_KEY"
    return 0
  fi

  if [[ -n "$BOT_GIT_SIGNING_KEY" ]]; then
    printf '%s\n' "$BOT_GIT_SIGNING_KEY"
    return 0
  fi

  configured_signing_key="$(git config --get user.signingkey 2>/dev/null || true)"
  configured_gpg_format="$(git config --get gpg.format 2>/dev/null || true)"
  if [[ -n "$configured_signing_key" ]]; then
    if [[ "$configured_gpg_format" == "ssh" ]] \
      || [[ "$configured_signing_key" == ssh-*' '* ]] \
      || [[ "$configured_signing_key" == *.pub ]]; then
      printf '%s\n' "$configured_signing_key"
      return 0
    fi
  fi

  if [[ -n "$DEFAULT_BOT_GIT_SSH_SIGNING_KEY_PATH" && -f "$DEFAULT_BOT_GIT_SSH_SIGNING_KEY_PATH" ]]; then
    printf '%s\n' "$DEFAULT_BOT_GIT_SSH_SIGNING_KEY_PATH"
    return 0
  fi

  return 1
}

assert_ssh_signing_ready() {
  local signing_key="$1"
  local private_key_hint=""
  local smoke_dir=""
  local smoke_output=""

  if [[ -z "$signing_key" ]]; then
    printf '%s\n' "Blocked: SSH signing key is not configured." >&2
    return 1
  fi

  if [[ "$signing_key" != ssh-*' '* && ! -f "$signing_key" ]]; then
    printf '%s\n' "Blocked: SSH signing key file not found: $signing_key" >&2
    return 1
  fi

  if [[ "$signing_key" == *.pub ]]; then
    private_key_hint="${signing_key%.pub}"
  fi

  smoke_dir="$(mktemp -d)"
  set +e
  smoke_output="$(
    cd "$smoke_dir" &&
      git init -q &&
      git config user.name "$BOT_GIT_NAME" &&
      git config user.email "$BOT_GIT_EMAIL" &&
      git config commit.gpgsign true &&
      git config gpg.format ssh &&
      git config user.signingkey "$signing_key" &&
      git commit --allow-empty -m "runner signing preflight" 2>&1
  )"
  local smoke_rc=$?
  set -e
  rm -rf "$smoke_dir"

  if (( smoke_rc == 0 )); then
    return 0
  fi

  if printf '%s\n' "$smoke_output" | grep -Eqi '(incorrect passphrase supplied to decrypt private key|enter passphrase for)'; then
    if [[ -n "$private_key_hint" ]]; then
      printf '%s\n' "Blocked: SSH signing key is present but unavailable to Git. Load the matching private key into ssh-agent first, for example: ssh-add $private_key_hint" >&2
    else
      printf '%s\n' "Blocked: SSH signing key is present but unavailable to Git. Load the matching private key into ssh-agent first." >&2
    fi
    return 1
  fi

  printf '%s\n' "Blocked: SSH signing preflight failed for $signing_key" >&2
  printf '%s\n' "$smoke_output" >&2
  return 1
}

run_step() {
  local description="$1"
  shift
  echo "==> ${description}"
  "$@"
}

run_check_capture() {
  local description="$1"
  shift
  echo "==> ${description}" | tee -a "$CHECK_LOG_FILE"
  local rc=0
  set +e
  "$@" 2>&1 | tee -a "$CHECK_LOG_FILE"
  rc=${PIPESTATUS[0]}
  set -e
  return "$rc"
}

reseed_runtime_for_self_heal() {
  echo "Self-heal: restarting local runtime stack and reseeding dev data." | tee -a "$CHECK_LOG_FILE"
  reset_runtime_stack_and_seed_dev_data
}

run_runtime_check_with_self_heal() {
  local description="$1"
  shift
  if run_check_capture "$description" "$@"; then
    return 0
  fi

  reseed_runtime_for_self_heal
  run_check_capture "${description} (self-heal retry after runtime reset)" "$@"
}

reset_runtime_stack_and_seed_dev_data() {
  docker compose down -v --remove-orphans >/dev/null 2>&1 || true
  start_runtime_stack_and_seed_dev_data postgres blob-storage app
}

changed_files_match() {
  local pattern="$1"
  {
    git diff --name-only "origin/${PR_BASE_REF_NAME:-$BASE_BRANCH}...HEAD"
    git diff --name-only
    git diff --cached --name-only
    git ls-files --others --exclude-standard
  } | awk 'NF && !seen[$0]++' | grep -Eq "$pattern"
}

runtime_schema_files_changed() {
  changed_files_match '^(hushline/model/|migrations/|scripts/dev_data\.py$|scripts/dev_migrations\.py$)'
}

python_dependency_files_changed() {
  changed_files_match '(^|/)(pyproject\.toml|poetry\.lock|requirements[^/]*\.txt)$'
}

node_runtime_dependency_files_changed() {
  changed_files_match '(^|/)(package\.json|package-lock\.json|npm-shrinkwrap\.json)$'
}

refresh_runtime_after_schema_changes() {
  echo "==> Refresh local runtime after schema changes" | tee -a "$CHECK_LOG_FILE"
  if ! runtime_schema_files_changed; then
    echo "Skipped: no schema-affecting files changed." | tee -a "$CHECK_LOG_FILE"
    return 0
  fi

  reset_runtime_stack_and_seed_dev_data
}

start_runtime_stack_and_seed_dev_data() {
  local compose_up_args=("$@")
  local attempt=1
  local attempt_log=""
  local compose_up_rc=0
  local seed_rc=0

  while (( attempt <= RUNTIME_BOOTSTRAP_ATTEMPTS )); do
    attempt_log="$(mktemp)"

    echo "==> Start Docker stack"
    set +e
    docker compose up -d --build "${compose_up_args[@]}" 2>&1 | tee "$attempt_log"
    compose_up_rc=${PIPESTATUS[0]}
    set -e

    if (( compose_up_rc == 0 )); then
      echo "==> Seed development data"
      set +e
      docker compose run --rm dev_data 2>&1 | tee -a "$attempt_log"
      seed_rc=${PIPESTATUS[0]}
      set -e

      if (( seed_rc == 0 )); then
        rm -f "$attempt_log"
        return 0
      fi
    fi

    if (( attempt >= RUNTIME_BOOTSTRAP_ATTEMPTS )); then
      rm -f "$attempt_log"
      if (( compose_up_rc != 0 )); then
        return "$compose_up_rc"
      fi
      return "$seed_rc"
    fi

    echo "Retrying runtime bootstrap in ${RUNTIME_BOOTSTRAP_RETRY_DELAY_SECONDS}s."
    sleep "$RUNTIME_BOOTSTRAP_RETRY_DELAY_SECONDS"
    rm -f "$attempt_log"
    attempt=$((attempt + 1))
  done
}

kill_all_docker_containers() {
  local containers
  containers="$(docker ps -aq || true)"
  if [[ -n "$containers" ]]; then
    docker rm -f $containers >/dev/null 2>&1 || true
  fi
}

kill_processes_on_ports() {
  local ports="$1"
  local port pids
  for port in $ports; do
    pids="$(lsof -nP -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      kill $pids >/dev/null 2>&1 || true
    fi
  done
}

count_open_bot_prs() {
  gh pr list \
    --repo "$REPO_SLUG" \
    --state open \
    --author "$BOT_LOGIN" \
    --limit 100 \
    --json number \
    --jq 'length'
}

count_open_human_prs() {
  gh pr list \
    --repo "$REPO_SLUG" \
    --state open \
    --limit 200 \
    --json author \
    | node -e '
let data = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  data += chunk;
});
process.stdin.on("end", () => {
  const botLogin = String(process.argv[1] || "").toLowerCase();
  const dependabotSlug = String(process.argv[2] || "dependabot").toLowerCase();
  const prs = JSON.parse(data || "[]");
  const count = prs.filter((pr) => {
    const login = String((pr && pr.author && pr.author.login) || "").toLowerCase();
    if (!login) {
      return false;
    }
    if (login === botLogin) {
      return false;
    }
    if (login.includes(dependabotSlug)) {
      return false;
    }
    if (login.endsWith("[bot]")) {
      return false;
    }
    return true;
  }).length;
  process.stdout.write(String(count));
});
' "$BOT_LOGIN" "$DEPENDABOT_APP_SLUG"
}

run_dependency_audits() {
  if python_dependency_files_changed; then
    run_check_capture "Run Python dependency audit" make audit-python || return 1
  else
    echo "==> Skip Python dependency audit" | tee -a "$CHECK_LOG_FILE"
    echo "Skipped: no Python dependency files changed." | tee -a "$CHECK_LOG_FILE"
  fi

  if node_runtime_dependency_files_changed; then
    run_check_capture "Run Node runtime dependency audit" make audit-node-runtime || return 1
    run_check_capture "Run full Node dependency audit" make audit-node-full || return 1
  else
    echo "==> Skip Node dependency audits" | tee -a "$CHECK_LOG_FILE"
    echo "Skipped: no Node dependency files changed." | tee -a "$CHECK_LOG_FILE"
  fi
}

run_local_workflow_checks() {
  : > "$CHECK_LOG_FILE"
  refresh_runtime_after_schema_changes || return 1
  run_check_capture "Run lint" make lint || return 1
  run_runtime_check_with_self_heal "Run test (full suite)" make test || return 1
  run_dependency_audits || return 1
}

configure_bot_git_identity() {
  local resolved_signing_key=""
  git config user.name "$BOT_GIT_NAME"
  git config user.email "$BOT_GIT_EMAIL"
  git config commit.gpgsign true
  if [[ -n "$BOT_GIT_GPG_FORMAT" ]]; then
    git config gpg.format "$BOT_GIT_GPG_FORMAT"
  fi
  if resolved_signing_key="$(resolve_bot_git_signing_key)"; then
    git config user.signingkey "$resolved_signing_key"
  elif [[ "$BOT_GIT_GPG_FORMAT" == "ssh" ]]; then
    printf '%s\n' "Blocked: SSH commit signing is enabled, but no signing key is configured." >&2
    return 1
  elif [[ -n "$BOT_GIT_SIGNING_KEY" ]]; then
    git config user.signingkey "$BOT_GIT_SIGNING_KEY"
  fi

  if [[ "$BOT_GIT_GPG_FORMAT" == "ssh" ]]; then
    assert_ssh_signing_ready "$resolved_signing_key"
  fi
}

remote_branch_exists() {
  local branch="$1"
  git ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1
}

push_branch_for_pr() {
  local branch="$1"

  if remote_branch_exists "$branch"; then
    echo "Remote branch '$branch' exists; pushing with --force-with-lease."
    if git push -u --force-with-lease origin "$branch"; then
      return 0
    fi

    echo "Push was rejected (likely stale remote info); refreshing and retrying once."
    git fetch origin "$branch":"refs/remotes/origin/$branch" >/dev/null 2>&1 || true
    git push -u --force-with-lease origin "$branch"
    return $?
  fi

  echo "Remote branch '$branch' does not exist; creating it with a standard push."
  git push -u origin "$branch"
}

load_pr_context() {
  local pr_number="$1"
  gh pr view "$pr_number" \
    --repo "$REPO_SLUG" \
    --json number,title,body,url,headRefName,headRefOid,baseRefName,baseRefOid,author,files,changedFiles,additions,deletions,maintainerCanModify,isCrossRepository,createdAt,updatedAt,mergeStateStatus,mergeable \
    > "$DEPENDABOT_PR_JSON_FILE"

  IFS=$'\t' read -r PR_NUMBER PR_TITLE PR_URL PR_BODY PR_HEAD_REF_NAME PR_BASE_REF_NAME < <(
    node - "$DEPENDABOT_PR_JSON_FILE" <<'NODE'
const fs = require("fs");
const data = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const fields = [
  data.number,
  String(data.title || "").replace(/\t/g, " ").replace(/\n/g, " ").trim(),
  String(data.url || ""),
  String(data.body || "").replace(/\t/g, "    ").replace(/\r?\n/g, " ").trim(),
  String(data.headRefName || ""),
  String(data.baseRefName || ""),
];
process.stdout.write(fields.join("\t") + "\n");
NODE
  )
}

dependabot_pr_is_eligible() {
  node - "$DEPENDABOT_PR_JSON_FILE" <<'NODE'
const fs = require("fs");
const pr = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const authorLogin = String((pr.author && pr.author.login) || "").toLowerCase();
const maintainerCanModify = Boolean(pr.maintainerCanModify);
const isOpenDependabot =
  authorLogin.includes("dependabot") &&
  String(pr.baseRefName || "") !== "" &&
  String(pr.headRefName || "") !== "";
if (isOpenDependabot && maintainerCanModify) {
  process.exit(0);
}
process.exit(1);
NODE
}

select_dependabot_pr() {
  local selected_pr=""

  if [[ -n "$FORCE_PR_NUMBER" ]]; then
    load_pr_context "$FORCE_PR_NUMBER"
    if ! dependabot_pr_is_eligible; then
      echo "Blocked: PR #$FORCE_PR_NUMBER is not an eligible open Dependabot PR that maintainers can modify." >&2
      exit 1
    fi
    return 0
  fi

  selected_pr="$(
    gh pr list \
      --repo "$REPO_SLUG" \
      --app "$DEPENDABOT_APP_SLUG" \
      --state open \
      --base "$DEPENDABOT_BASE_BRANCH" \
      --limit "$DEPENDABOT_PR_LIMIT" \
      --json number,createdAt,maintainerCanModify,title \
      | node -e '
        const fs = require("fs");
        const items = JSON.parse(fs.readFileSync(0, "utf8"));
        const eligible = (Array.isArray(items) ? items : [])
          .filter((pr) => pr && pr.maintainerCanModify)
          .sort((a, b) => String(a.createdAt || "").localeCompare(String(b.createdAt || "")));
        if (eligible.length > 0) {
          process.stdout.write(String(eligible[0].number));
        }
      '
  )"

  if [[ -z "$selected_pr" ]]; then
    return 1
  fi

  load_pr_context "$selected_pr"
}

pr_files_summary() {
  node - "$DEPENDABOT_PR_JSON_FILE" <<'NODE'
const fs = require("fs");
const pr = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const files = Array.isArray(pr.files) ? pr.files : [];
if (files.length === 0) {
  process.stdout.write("No file metadata reported.\n");
  process.exit(0);
}
for (const file of files) {
  const path = String(file.path || file.name || "");
  const additions = Number(file.additions || 0);
  const deletions = Number(file.deletions || 0);
  process.stdout.write(`${path} (+${additions} / -${deletions})\n`);
}
NODE
}

current_pr_diff_stat() {
  git diff --stat "origin/$PR_BASE_REF_NAME...HEAD" || true
}

current_change_summary() {
  {
    echo "Current git status:"
    git status --short
    echo
    echo "Current diff stat:"
    git diff --stat
  } 2>/dev/null
}

has_changes() {
  [[ -n "$(git status --porcelain)" ]]
}

sanitize_failure_excerpt() {
  local text="$1"
  local escaped_repo_dir escaped_home

  escaped_repo_dir="$(printf '%s\n' "$REPO_DIR" | sed 's/[.[\*^$()+?{|]/\\&/g')"
  escaped_home="$(printf '%s\n' "$HOME" | sed 's/[.[\*^$()+?{|]/\\&/g')"

  printf '%s\n' "$text" | sed -E \
    -e "s#${escaped_repo_dir}/##g" \
    -e "s#${escaped_home}/#~/#g" \
    -e 's#/var/folders/[^[:space:]]+#/var/folders/[redacted]#g' \
    -e 's#/tmp/[^[:space:]]+#/tmp/[redacted]#g' \
    -e 's#(https?://)[^/@[:space:]]+:[^/@[:space:]]+@#\1[redacted]@#g' \
    -e 's/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/[redacted-email]/g'
}

recent_failure_block_from_text() {
  local text="$1"
  local filtered=""

  filtered="$(printf '%s\n' "$text" | awk '
    /^[[:space:]]*Container / { next }
    /^#([0-9]+|[[:space:]])/ { next }
    /^collecting \.\.\./ { next }
    /^platform / { next }
    /^cachedir: / { next }
    /^rootdir: / { next }
    /^configfile: / { next }
    /^plugins: / { next }
    /^asyncio: / { next }
    /^={5,}/ { next }
    /^-{5,}/ { next }
    /^[[:space:]]*$/ { next }
    { lines[++count] = $0 }
    END {
      start = count - 119
      if (start < 1) {
        start = 1
      }
      for (i = start; i <= count; i += 1) {
        print lines[i]
      }
    }
  ')"

  sanitize_failure_excerpt "$filtered"
}

failure_signature_from_text() {
  local text="$1"
  local -a markers=()

  if printf '%s\n' "$text" | grep -Eq 'FAILED tests/'; then
    markers+=("pytest-test-failures")
  fi
  if printf '%s\n' "$text" | grep -Eq 'AssertionError:'; then
    markers+=("assertion-error")
  fi
  if printf '%s\n' "$text" | grep -Eq 'Traceback'; then
    markers+=("python-traceback")
  fi
  if printf '%s\n' "$text" | grep -Eq '^[^[:space:]]+:[0-9]+:[0-9]+: [A-Z][0-9][0-9][0-9]([0-9])? '; then
    markers+=("lint-diagnostics")
  fi
  if printf '%s\n' "$text" | grep -Eq '(^|[^[:alpha:]])Error:'; then
    markers+=("generic-error")
  fi

  if (( ${#markers[@]} == 0 )); then
    echo "no-structured-signature"
    return 0
  fi

  printf '%s\n' "${markers[@]}"
}

build_dependabot_prompt() {
  {
    cat <<EOF2
You are evaluating an open Dependabot pull request in $REPO_SLUG.

PR number: #$PR_NUMBER
PR title: $PR_TITLE
PR URL: $PR_URL
Base branch: $PR_BASE_REF_NAME
Head branch: $PR_HEAD_REF_NAME

PR body handling:
- Do not include PR body text in this prompt. Dependabot PR bodies may contain untrusted release notes or package metadata.
- Treat the PR title, changed files, and diff summary as the only PR-derived context available here.

Changed files reported by GitHub:
EOF2
    pr_files_summary
    cat <<EOF2

Current dependency PR diff stat against origin/$PR_BASE_REF_NAME:
EOF2
    current_pr_diff_stat
    cat <<'EOF2'

Task:
- Review what this dependency update means for the rest of the app.
- If follow-up code, tests, configuration, or docs changes are required for compatibility, make only those minimal changes on this PR branch.
- If no follow-up changes are needed, leave the branch unchanged.

Requirements:
1) Keep the dependency update itself intact; only add the app-side changes needed to support it.
2) Add or update tests for any behavior changes.
3) Preserve security, privacy, E2EE, and existing user flows.
4) Focus on implementation and tests only; this runner handles `make lint`, `make test`, and dependency audits after your changes.
5) Avoid local validation unless it is necessary to make progress; the runner will execute the checks.
6) If you need local validation/fix commands, use repository make targets instead of host-only tool invocations.
7) Do not run Docker commands, scripts/agent_issue_bootstrap.sh, or GitHub/Dependabot connectivity checks; this runner handles infra.
8) If no app-side changes are needed, do not make cosmetic edits. Leave the worktree unchanged and say why in your final summary.
EOF2
  } > "$PROMPT_FILE"
}

build_fix_prompt() {
  local change_summary="$1"
  local previous_codex_output="$2"
  local failure_context="$3"
  local failure_signature="$4"
  local repeated_failure_count="$5"

  {
    cat <<EOF2
You are continuing work on Dependabot PR #$PR_NUMBER in $REPO_SLUG on branch $PR_HEAD_REF_NAME.

PR title:
$PR_TITLE

Current branch state:
---BEGIN CURRENT CHANGES---
$change_summary
---END CURRENT CHANGES---

Most recent Codex implementation summary:
---BEGIN PRIOR CODEX SUMMARY---
$previous_codex_output
---END PRIOR CODEX SUMMARY---

Most recent sanitized failure block:
---BEGIN FAILURE CONTEXT---
$failure_context
---END FAILURE CONTEXT---

Failure signature:
---BEGIN FAILURE SIGNATURE---
$failure_signature
---END FAILURE SIGNATURE---

EOF2
    if [[ "$repeated_failure_count" =~ ^[0-9]+$ ]] && (( repeated_failure_count > 1 )); then
      printf 'This same failure signature has repeated %s times. Reassess root cause before editing; do not repeat the prior partial fix.\n\n' "$repeated_failure_count"
    fi
    cat <<'EOF2'
Requirements:
1) Fix only what is required for the Dependabot branch to pass checks.
2) Preserve the dependency update itself and any already-valid compatibility work on the branch.
3) Keep diffs minimal and focused.
4) Preserve security, privacy, E2EE, and existing user flows.
5) Do not run Docker commands, scripts/agent_issue_bootstrap.sh, or GitHub/Dependabot connectivity checks; this runner handles infra.
6) Focus on code/test fixes only; the runner executes `make lint`, `make test`, and dependency audits.
EOF2
  } > "$PROMPT_FILE"
}

persist_run_log() {
  local pr_number="$1"
  local log_dir="$REPO_DIR/docs/agent-logs"
  local raw_log_file
  RUN_LOG_GIT_PATH="docs/agent-logs/run-${RUN_LOG_TIMESTAMP}-dependabot-pr-${pr_number}.txt"
  raw_log_file="$(mktemp)"

  mkdir -p "$log_dir"
  {
    printf 'Dependabot runner log\n'
    printf 'Timestamp (UTC): %s\n' "$RUN_LOG_TIMESTAMP"
    printf 'Pull request: #%s\n' "$pr_number"
    printf 'Repository: %s\n\n' "$REPO_SLUG"
    cat "$RUN_LOG_TMP_FILE"
  } > "$raw_log_file"
  python3 "$SCRIPT_DIR/sanitize_agent_run_log.py" "$raw_log_file" "$REPO_DIR/$RUN_LOG_GIT_PATH"
  rm -f "$raw_log_file"

  if [[ "$RUN_LOG_RETENTION_COUNT" =~ ^[0-9]+$ ]] && (( RUN_LOG_RETENTION_COUNT > 0 )); then
    local -a logs_to_delete=()
    while IFS= read -r log_path; do
      [[ -n "$log_path" ]] && logs_to_delete+=("$log_path")
    done < <(
      find "$log_dir" -maxdepth 1 -type f -name 'run-*-dependabot-pr-*.txt' \
        | sort -r \
        | tail -n "+$((RUN_LOG_RETENTION_COUNT + 1))"
    )

    if (( ${#logs_to_delete[@]} > 0 )); then
      echo "Pruning old Dependabot runner logs, keeping newest ${RUN_LOG_RETENTION_COUNT}."
      rm -f "${logs_to_delete[@]}"
    fi
  fi
}

run_codex_from_prompt() {
  local rc=0
  : > "$CODEX_OUTPUT_FILE"
  : > "$CODEX_TRANSCRIPT_FILE"

  if [[ "$VERBOSE_CODEX_OUTPUT" == "1" ]]; then
    echo "Codex execution started; streaming transcript to console only."
  else
    echo "Codex execution started; transcript output is excluded from persisted run logs."
  fi
  set +e
  codex exec \
    --model "$CODEX_MODEL" \
    -c "model_reasoning_effort=\"$CODEX_REASONING_EFFORT\"" \
    --full-auto \
    --sandbox workspace-write \
    -C "$REPO_DIR" \
    -o "$CODEX_OUTPUT_FILE" \
    - < "$PROMPT_FILE" 2>&1 | {
      if [[ "$VERBOSE_CODEX_OUTPUT" == "1" ]] && : >&3 2>/dev/null; then
        tee "$CODEX_TRANSCRIPT_FILE" >&3
      else
        cat > "$CODEX_TRANSCRIPT_FILE"
      fi
    }
  rc=${PIPESTATUS[0]}
  set -e

  if (( rc != 0 )); then
    echo "Codex execution failed (exit ${rc})."
    return "$rc"
  fi

  echo "Codex execution completed."
  if [[ -s "$CODEX_OUTPUT_FILE" ]]; then
    echo "Codex final message:"
    sed -n '1,60p' "$CODEX_OUTPUT_FILE"
    printf '\n'
  fi
}

run_fix_attempt_loop() {
  local fix_attempt=1
  local previous_failure_signature=""
  local failure_signature=""
  local repeated_failure_count=0

  while (( fix_attempt <= MAX_FIX_ATTEMPTS )); do
    if run_local_workflow_checks; then
      return 0
    fi

    if (( fix_attempt == MAX_FIX_ATTEMPTS )); then
      echo "Blocked: workflow checks failed after $MAX_FIX_ATTEMPTS self-heal attempt(s) for PR #$PR_NUMBER." >&2
      return 1
    fi

    echo "Workflow checks failed; Codex self-heal attempt $fix_attempt."
    local failure_log_tail
    local failure_context
    failure_log_tail="$(tail -n 400 "$CHECK_LOG_FILE")"
    failure_context="$(recent_failure_block_from_text "$failure_log_tail")"
    failure_signature="$(failure_signature_from_text "$failure_log_tail")"
    if [[ -n "$failure_signature" && "$failure_signature" == "$previous_failure_signature" ]]; then
      repeated_failure_count=$((repeated_failure_count + 1))
    else
      repeated_failure_count=1
      previous_failure_signature="$failure_signature"
    fi

    build_fix_prompt \
      "$(current_change_summary)" \
      "$(sed -n '1,80p' "$CODEX_OUTPUT_FILE")" \
      "$failure_context" \
      "$failure_signature" \
      "$repeated_failure_count"
    run_codex_from_prompt
    fix_attempt=$((fix_attempt + 1))
  done

  return 1
}

write_pr_comment_body() {
  local mode="$1"
  local summary
  summary="$(sed -n '1,80p' "$CODEX_OUTPUT_FILE" || true)"

  {
    if [[ "$mode" == "updated" ]]; then
      printf 'Dependabot runner applied follow-up app changes for PR #%s.\n\n' "$PR_NUMBER"
      printf 'Head branch: `%s`\n' "$PR_HEAD_REF_NAME"
    else
      printf 'Dependabot runner reviewed PR #%s and did not find any required app-side follow-up changes.\n\n' "$PR_NUMBER"
      printf 'Head branch: `%s`\n' "$PR_HEAD_REF_NAME"
    fi
    printf 'Run log: `%s`\n\n' "$RUN_LOG_GIT_PATH"
    if [[ -n "$summary" ]]; then
      printf 'Codex summary:\n\n%s\n' "$summary"
    fi
  } > "$COMMENT_BODY_FILE"
}

main() {
  trap cleanup EXIT
  local branch_has_follow_up_changes=0

  parse_args "$@"
  initialize_run_state

  require_positive_integer "HUSHLINE_DEPENDABOT_PR_LIMIT" "$DEPENDABOT_PR_LIMIT"
  require_positive_integer "HUSHLINE_DEPENDABOT_MAX_FIX_ATTEMPTS" "$MAX_FIX_ATTEMPTS"
  require_positive_integer "HUSHLINE_DAILY_RUNTIME_BOOTSTRAP_ATTEMPTS" "$RUNTIME_BOOTSTRAP_ATTEMPTS"
  require_positive_integer "HUSHLINE_DAILY_RUNTIME_BOOTSTRAP_RETRY_DELAY_SECONDS" "$RUNTIME_BOOTSTRAP_RETRY_DELAY_SECONDS"

  require_cmd git
  require_cmd gh
  require_cmd codex
  require_cmd docker
  require_cmd make
  require_cmd node
  require_cmd python3

  cd "$REPO_DIR"
  run_step "Fetch latest from origin" git fetch origin
  run_step "Checkout $BASE_BRANCH" git checkout "$BASE_BRANCH"
  run_step "Reset to origin/$BASE_BRANCH" git reset --hard "origin/$BASE_BRANCH"
  run_step "Clean untracked files" git clean -fd

  local open_human_prs
  local open_bot_prs
  open_human_prs="$(count_open_human_prs)"
  echo "Open human-authored PR count: ${open_human_prs}"
  if [[ "$open_human_prs" != "0" ]]; then
    echo "Skipped: found ${open_human_prs} open human-authored PR(s)."
    return 0
  fi

  open_bot_prs="$(count_open_bot_prs)"
  echo "Open bot PR count: ${open_bot_prs}"
  if [[ "$open_bot_prs" != "0" ]]; then
    echo "Skipped: found ${open_bot_prs} open PR(s) by ${BOT_LOGIN}."
    return 0
  fi

  if ! select_dependabot_pr; then
    echo "Skipped: no eligible open Dependabot PRs were found."
    return 0
  fi

  echo "Selected Dependabot PR #$PR_NUMBER: $PR_TITLE"
  run_step "Configure bot git identity" configure_bot_git_identity
  run_step "Stop and remove Docker resources" docker compose down -v --remove-orphans
  run_step "Kill all Docker containers" kill_all_docker_containers
  run_step "Kill processes on runner ports" kill_processes_on_ports "$HOST_PORTS_TO_CLEAR"
  start_runtime_stack_and_seed_dev_data

  if remote_branch_exists "$PR_HEAD_REF_NAME"; then
    run_step "Fetch branch $PR_HEAD_REF_NAME" git fetch origin "$PR_HEAD_REF_NAME:refs/remotes/origin/$PR_HEAD_REF_NAME"
    run_step "Checkout branch $PR_HEAD_REF_NAME from origin/$PR_HEAD_REF_NAME" git checkout -B "$PR_HEAD_REF_NAME" "origin/$PR_HEAD_REF_NAME"
  else
    echo "Blocked: remote branch '$PR_HEAD_REF_NAME' was not found." >&2
    return 1
  fi

  build_dependabot_prompt
  run_codex_from_prompt

  if ! run_fix_attempt_loop; then
    persist_run_log "$PR_NUMBER"
    return 1
  fi

  if has_changes; then
    branch_has_follow_up_changes=1
  fi

  persist_run_log "$PR_NUMBER"

  if (( branch_has_follow_up_changes == 1 )); then
    run_step "Stage follow-up changes" git add -A
    run_step "Commit follow-up changes" git commit -m "chore: follow up dependabot PR #$PR_NUMBER"
    push_branch_for_pr "$PR_HEAD_REF_NAME"
    write_pr_comment_body "updated"
  else
    write_pr_comment_body "noop"
  fi

  run_step "Comment on PR #$PR_NUMBER" gh pr comment "$PR_NUMBER" --repo "$REPO_SLUG" --body-file "$COMMENT_BODY_FILE"
  run_step "Return to $BASE_BRANCH" git checkout "$BASE_BRANCH"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
