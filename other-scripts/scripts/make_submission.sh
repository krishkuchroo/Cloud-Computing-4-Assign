#!/usr/bin/env bash
# Build the deterministic submission zip:
#   dist/cc-photos-submission.zip
# Excludes secrets, build artefacts, editor cruft.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${ROOT}/dist"
STAGE="${OUT}/submission"
ZIP="${OUT}/cc-photos-submission.zip"

rm -rf "$STAGE"
mkdir -p "$STAGE"

# rsync gives us include/exclude precision and is on every macOS / Linux box.
rsync -a \
  --exclude='.git/' \
  --exclude='dist/' \
  --exclude='node_modules/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.venv/' \
  --exclude='venv/' \
  --exclude='.idea/' \
  --exclude='.vscode/' \
  --exclude='.DS_Store' \
  --exclude='*.zip' \
  --exclude='front-end/config.js' \
  --exclude='.aws-sam/' \
  --exclude='samconfig.toml' \
  --exclude='test-fixtures/' \
  "$ROOT/" "$STAGE/"

# Minimal sanity: no secrets snuck in.
if grep -RIn -E "AKIA[0-9A-Z]{16}" "$STAGE" >/dev/null 2>&1; then
  echo "[fail] AWS access-key pattern found in stage; aborting."
  grep -RIn -E "AKIA[0-9A-Z]{16}" "$STAGE" || true
  exit 2
fi
if [[ -f "$STAGE/front-end/config.js" ]]; then
  echo "[fail] front-end/config.js leaked into stage; aborting."
  exit 2
fi

rm -f "$ZIP"
( cd "$OUT" && zip -qr "$(basename "$ZIP")" "$(basename "$STAGE")" )

echo
echo "[ok] $ZIP"
du -h "$ZIP"
echo
echo "Top-level contents:"
unzip -l "$ZIP" | head -25
echo "..."
unzip -l "$ZIP" | tail -5
