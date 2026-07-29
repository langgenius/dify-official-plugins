#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: $0 <plugin-path>" >&2
  exit 1
fi

plugin_path=$1

if [ ! -d "$plugin_path" ]; then
  echo "!!! Plugin path does not exist: $plugin_path" >&2
  exit 1
fi

if [ ! -f "$plugin_path/uv.lock" ]; then
  echo "No uv.lock found in $plugin_path; skipping legacy requirements export"
  exit 0
fi

if [ ! -f "$plugin_path/pyproject.toml" ]; then
  echo "!!! uv.lock exists but pyproject.toml is missing in $plugin_path" >&2
  exit 1
fi

echo "Generating requirements.txt for legacy package compatibility: $plugin_path"
uv export \
  --project "$plugin_path" \
  --frozen \
  --format requirements.txt \
  --no-hashes \
  --no-header \
  --no-annotate \
  --no-emit-project \
  --no-dev \
  --output-file "$plugin_path/requirements.txt" \
  > /dev/null
