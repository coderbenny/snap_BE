#!/usr/bin/env bash
# scripts/publish-main.sh
#
# Derives the public `main` branch from the deployed `deploy` branch.
# Run this AFTER a successful deployment has been verified on `deploy`.
#
# What it does:
#   1. Fetches the latest deploy branch from remote
#   2. Strips internal deployment tooling (scripts/)
#   3. Replaces your live domain/paths with generic placeholders
#   4. Force-pushes a single orphan commit to `main`
#
# This enforces the rule: main always contains code that has already
# been deployed, and never exposes internal infrastructure details.
#
# Usage:
#   ./scripts/publish-main.sh                      # auto message
#   ./scripts/publish-main.sh "release: v1.2.0"

set -euo pipefail

REMOTE="${REMOTE:-origin}"
SOURCE_BRANCH="deploy"
TARGET_BRANCH="main"
TEMP_BRANCH="_main_tmp_$$"
MSG="${1:-chore: publish open-source release $(date -u '+%Y-%m-%d')}"

# ── Guards ─────────────────────────────────────────────────────────────────
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERROR: working tree has uncommitted changes — commit or stash first" >&2; exit 1
fi

CURRENT=$(git symbolic-ref --short HEAD)
echo "→  source  : $REMOTE/$SOURCE_BRANCH  (deployed code)"
echo "→  target  : $REMOTE/$TARGET_BRANCH  (public open-source)"
echo "→  message : $MSG"

cleanup() {
  git checkout "$CURRENT" --quiet 2>/dev/null || true
  git branch -D "$TEMP_BRANCH" --quiet 2>/dev/null || true
}
trap cleanup EXIT

# ── Get latest deploy content into a temp dir ──────────────────────────────
echo ""
echo "→  fetching $REMOTE/$SOURCE_BRANCH ..."
git fetch "$REMOTE" "$SOURCE_BRANCH" --quiet
DEPLOY_SHA=$(git rev-parse FETCH_HEAD)

TMPDIR=$(mktemp -d)
trap "rm -rf '$TMPDIR'; ${FUNCNAME[0]:-cleanup}" EXIT 2>/dev/null || trap "rm -rf '$TMPDIR'; cleanup" EXIT
git archive "$DEPLOY_SHA" | tar -x -C "$TMPDIR"

# ── Strip: internal tooling not relevant to open-source users ──────────────
echo "→  stripping internal files ..."
rm -rf "$TMPDIR/scripts/"

# ── Sanitize: nginx.conf — replace live domain with placeholder ────────────
NGINX="$TMPDIR/nginx/nginx.conf"
if [ -f "$NGINX" ]; then
  sed -i '' \
    -e 's|api\.snapit\.ink|YOUR_DOMAIN_HERE|g' \
    -e 's|/etc/letsencrypt/live/api\.snapit\.ink/|/etc/letsencrypt/live/YOUR_DOMAIN_HERE/|g' \
    "$NGINX"
  echo "   nginx/nginx.conf  — domain placeholder applied"
fi

# ── Sanitize: deploy.yml — replace internal server path ───────────────────
DEPLOY_YML="$TMPDIR/.github/workflows/deploy.yml"
if [ -f "$DEPLOY_YML" ]; then
  sed -i '' \
    -e 's|/home/${{ secrets.SERVER_USERNAME }}/snap_BE|/path/to/your/app|g' \
    "$DEPLOY_YML"
  echo "   .github/workflows/deploy.yml — server path placeholder applied"
fi

# ── Build orphan commit on TARGET_BRANCH ──────────────────────────────────
echo "→  building orphan commit on $TARGET_BRANCH ..."
git checkout --orphan "$TEMP_BRANCH" --quiet
git rm -rf --cached . --quiet
git clean -fd --quiet 2>/dev/null || true

# Copy sanitized content into working tree
cp -r "$TMPDIR/." .

git add .

# Safety: confirm no credentials made it through
LEAKED=$(git diff --cached --name-only | grep -E 'firebase-adminsdk|service-account|\.env$' || true)
if [ -n "$LEAKED" ]; then
  echo "ERROR: sensitive file(s) detected — aborting:" >&2
  echo "$LEAKED" >&2
  exit 1
fi

git commit -m "$MSG" --quiet
git push "$REMOTE" "$TEMP_BRANCH:refs/heads/$TARGET_BRANCH" --force --quiet

echo ""
echo "✓  $REMOTE/$TARGET_BRANCH updated."
echo "   main now reflects the deployed state of $DEPLOY_SHA with internals stripped."
