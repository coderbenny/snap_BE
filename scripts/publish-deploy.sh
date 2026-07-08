#!/usr/bin/env bash
# publish-deploy.sh
#
# Creates (or replaces) the remote `deploy` branch with a single orphan
# commit containing all backend files except those excluded by .gitignore.
#
# The deploy branch always has exactly ONE commit so the public repository
# never exposes the development history from main.
#
# Usage:
#   ./scripts/publish-deploy.sh                    # auto-generates timestamp message
#   ./scripts/publish-deploy.sh "release: v1.2.0"  # custom message
#
# Prerequisites: working tree must be clean (commit or stash changes first).

set -euo pipefail

REMOTE="${REMOTE:-origin}"
DEPLOY_BRANCH="deploy"
TEMP_BRANCH="_deploy_publish_tmp"
MSG="${1:-chore: release $(date -u '+%Y-%m-%d %H:%M UTC')}"

# ── Guard: must be in a git repo ───────────────────────────────────────────
if ! git rev-parse --git-dir > /dev/null 2>&1; then
  echo "ERROR: not inside a git repository" >&2
  exit 1
fi

# ── Guard: working tree must be clean ──────────────────────────────────────
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: working tree has uncommitted changes." >&2
  echo "       Commit or stash them before publishing." >&2
  exit 1
fi

CURRENT=$(git symbolic-ref --short HEAD)
echo "→  source branch : $CURRENT"
echo "→  deploy branch : $REMOTE/$DEPLOY_BRANCH"
echo "→  commit message: $MSG"
echo ""

# ── Cleanup on exit (remove temp branch if anything goes wrong) ────────────
cleanup() {
  git checkout "$CURRENT" --quiet 2>/dev/null || true
  git branch -D "$TEMP_BRANCH" --quiet 2>/dev/null || true
}
trap cleanup EXIT

# ── Create orphan branch (no history) ─────────────────────────────────────
git checkout --orphan "$TEMP_BRANCH" --quiet
# After --orphan the index still mirrors the previous branch; clear it.
git rm -rf --cached . --quiet

# Stage everything that is NOT in .gitignore (credentials, caches, etc.)
git add .

# Sanity-check: warn if any known-sensitive patterns slipped through
LEAKED=$(git diff --cached --name-only | grep -E 'firebase-adminsdk|service-account|\.env$' || true)
if [ -n "$LEAKED" ]; then
  echo "ERROR: sensitive file(s) about to be committed:" >&2
  echo "$LEAKED" >&2
  exit 1
fi

git commit -m "$MSG" --quiet

# ── Force-push to deploy branch ────────────────────────────────────────────
echo "→  pushing to $REMOTE/$DEPLOY_BRANCH (force) ..."
git push "$REMOTE" "$TEMP_BRANCH:refs/heads/$DEPLOY_BRANCH" --force --quiet
echo "✓  done — $REMOTE/$DEPLOY_BRANCH now has 1 commit."
