#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: bash $0 <full-commit-sha> <new-output.difypkg>" >&2
  exit 2
}

[[ $# == 2 && $1 =~ ^[0-9a-f]{40}$ && $2 == *.difypkg ]] || usage
commit=$1
repo=$(git rev-parse --show-toplevel)
[[ $(git -C "$repo" rev-parse --verify "$commit^{commit}") == "$commit" ]] || usage

output_dir=$(cd -- "$(dirname -- "$2")" && pwd -P)
output="$output_dir/$(basename -- "$2")"
if [[ -e $output || -L $output ]]; then
  echo "Output already exists: $output" >&2
  exit 1
fi

dify_cli=$(command -v "${DIFY_CLI:-dify}")
if [[ $dify_cli != /* ]]; then
  echo 'DIFY_CLI must resolve to an absolute executable path' >&2
  exit 2
fi

scratch=$(mktemp -d "$output_dir/.tokener-staging.XXXXXXXX")
trap 'rm -rf -- "$scratch"' EXIT

patch_path=.github/scripts/tokener-staging/staging.patch
git -C "$repo" archive "$commit" -- models/tokener "$patch_path" | tar -xf - -C "$scratch"
(
  cd -- "$scratch"
  # The export may itself be under a worktree; apply to the export, not its parent Git repo.
  unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR
  export GIT_CEILING_DIRECTORIES="$output_dir"
  git apply --whitespace=error-all "$patch_path"

  if [[ -n ${DIFY_CLI_CONFIG:-} ]]; then
    [[ $DIFY_CLI_CONFIG == /* ]] || usage
    set -- --config "$DIFY_CLI_CONFIG"
  else
    set --
  fi
  UV_OFFLINE=1 UV_NO_CONFIG=1 "$dify_cli" "$@" plugin package models/tokener \
    --output_path "$scratch/staging.difypkg" --max-size 50
)

# The scratch directory and final output share a filesystem; do not replace an existing package.
ln -- "$scratch/staging.difypkg" "$output"
echo "Built unsigned Tokener staging package from $commit: $output"
