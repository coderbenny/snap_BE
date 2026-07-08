#!/usr/bin/env bash
# scripts/deploy.sh
#
# Publishes a clean single-commit release to the `deploy` branch.
# GitHub Actions picks this up and deploys to production.
#
# Working tree must be clean. Run from the root of the server directory.
#
# Usage:
#   ./scripts/deploy.sh                      # auto timestamp message
#   ./scripts/deploy.sh "release: v1.2.0"

set -euo pipefail

REMOTE="${REMOTE:-origin}"
DEPLOY_BRANCH="deploy"
TEMP_BRANCH="_deploy_tmp_$$"
MSG="${1:-chore: deploy $(date -u '+%Y-%m-%d %H:%M UTC')}"

# ── Guards ─────────────────────────────────────────────────────────────────
if ! git rev-parse --git-dir > /dev/null 2>&1; then
  echo "ERROR: not inside a git repository" >&2; exit 1
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: working tree has uncommitted changes — commit or stash first" >&2; exit 1
fi

CURRENT=$(git symbolic-ref --short HEAD)
echo "→  branch  : $CURRENT → $REMOTE/$DEPLOY_BRANCH"
echo "→  message : $MSG"

cleanup() {
  git checkout "$CURRENT" --quiet 2>/dev/null || true
  git branch -D "$TEMP_BRANCH" --quiet 2>/dev/null || true
}
trap cleanup EXIT

# ── Create orphan commit (no history exposed) ──────────────────────────────
git checkout --orphan "$TEMP_BRANCH" --quiet
git rm -rf --cached . --quiet
git add .

# Safety: reject any service-account key that slipped through .gitignore
LEAKED=$(git diff --cached --name-only | grep -E 'firebase-adminsdk|service-account|\.env$' || true)
if [ -n "$LEAKED" ]; then
  echo "ERROR: sensitive file(s) staged:" >&2
  echo "$LEAKED" >&2
  exit 1
fi

git commit -m "$MSG" --quiet
git push "$REMOTE" "$TEMP_BRANCH:refs/heads/$DEPLOY_BRANCH" --force --quiet
echo "✓  $REMOTE/$DEPLOY_BRANCH updated — GitHub Actions will now deploy."
