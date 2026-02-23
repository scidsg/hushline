#!/usr/bin/env bash
set -euo pipefail

STATUS="${1:-}"
SOURCE="${2:-runner}"

if [[ -z "$STATUS" ]]; then
  echo "Usage: scripts/update_agent_health_badge.sh <healthy|unhealthy> [source]" >&2
  exit 1
fi

ENABLED="${HUSHLINE_HEALTH_BADGE_ENABLED:-1}"
BADGE_REPO="${HUSHLINE_HEALTH_BADGE_REPO:-scidsg/hushline-screenshots}"
BADGE_PATH="${HUSHLINE_HEALTH_BADGE_PATH:-badge-agent-health.json}"
BADGE_BRANCH="${HUSHLINE_HEALTH_BADGE_BRANCH:-main}"
BADGE_LABEL="${HUSHLINE_HEALTH_BADGE_LABEL:-agent health}"

if [[ "$ENABLED" != "1" ]]; then
  exit 0
fi

case "$STATUS" in
  healthy)
    BADGE_MESSAGE="healthy"
    BADGE_COLOR="brightgreen"
    ;;
  unhealthy)
    BADGE_MESSAGE="unhealthy"
    BADGE_COLOR="red"
    ;;
  *)
    echo "Invalid status: $STATUS (expected healthy or unhealthy)" >&2
    exit 1
    ;;
esac

BADGE_JSON="$(
  printf '{"schemaVersion":1,"label":"%s","message":"%s","color":"%s"}' \
    "$BADGE_LABEL" "$BADGE_MESSAGE" "$BADGE_COLOR"
)"

CONTENT_B64="$(printf '%s' "$BADGE_JSON" | base64 | tr -d '\n')"

CURRENT_SHA="$(
  gh api "repos/$BADGE_REPO/contents/$BADGE_PATH?ref=$BADGE_BRANCH" --jq '.sha' 2>/dev/null || true
)"

COMMIT_MESSAGE="Update agent health badge: ${BADGE_MESSAGE} (${SOURCE})"

if [[ -n "$CURRENT_SHA" ]]; then
  gh api \
    -X PUT "repos/$BADGE_REPO/contents/$BADGE_PATH" \
    -f message="$COMMIT_MESSAGE" \
    -f content="$CONTENT_B64" \
    -f branch="$BADGE_BRANCH" \
    -f sha="$CURRENT_SHA" >/dev/null
else
  gh api \
    -X PUT "repos/$BADGE_REPO/contents/$BADGE_PATH" \
    -f message="$COMMIT_MESSAGE" \
    -f content="$CONTENT_B64" \
    -f branch="$BADGE_BRANCH" >/dev/null
fi

echo "Published agent health badge: $BADGE_MESSAGE"
