#!/usr/bin/env bash
# Builds dist/index_photos.zip and dist/search_photos.zip with deps installed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIST="${ROOT}/dist"
mkdir -p "$DIST"

build_one() {
  local name="$1"  # index_photos or search_photos
  local src="${ROOT}/lambda-functions/${name}"
  local zip="${DIST}/${name}.zip"
  local stage; stage="$(mktemp -d -t cc-photos-${name}-XXXXXX)"

  echo "[build] ${name}: staging in ${stage}"
  cp "${src}/lambda_function.py" "${stage}/"
  # Skip pip if requirements.txt is empty / only-comments (Lambda runtime has boto3/urllib3)
  local has_deps=0
  if [[ -s "${src}/requirements.txt" ]] && grep -qvE '^\s*(#.*)?$' "${src}/requirements.txt"; then
    has_deps=1
  fi
  if (( has_deps )); then
    PIP="${PIP:-python3 -m pip}"
    $PIP install --quiet --target "${stage}" --platform manylinux2014_x86_64 \
      --implementation cp --python-version 3.12 --only-binary=:all: \
      -r "${src}/requirements.txt" || \
    $PIP install --quiet --target "${stage}" -r "${src}/requirements.txt"
  fi

  rm -f "$zip"
  (cd "$stage" && zip -qr "$zip" .)
  echo "[build] ${name}: $(du -h "$zip" | cut -f1) -> ${zip}"
  rm -rf "$stage"
}

build_one index_photos
build_one search_photos
echo "[build] done"
