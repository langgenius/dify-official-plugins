# Tokener staging-only package

The official plugin under `models/tokener` remains the production source. This manual build
uses the native provider from a specific Git commit and applies the staging overlay to a
temporary copy. It does not change the checkout, use the Marketplace uploader, sign, or deploy.

Requires Git, Bash, `tar`, the normal Dify CLI and `uv`. From a checkout containing the commit,
run with a **full commit SHA** and a new output path (whose parent directory already exists):

```bash
DIFY_CLI=/absolute/path/to/dify \
  bash .github/scripts/tokener-staging/build.sh <full-commit-sha> \
  /absolute/path/to/tokener-staging-unsigned.difypkg
```

Set `DIFY_CLI_CONFIG` to an absolute path if a specific CLI configuration is required. The
CLI exports dependencies from the untouched `uv.lock` in offline mode. The overlay changes
the package version, fixed API URL and key-help link, plus the corresponding documentation
and tests; it does not add legacy forwarding code. If the source no longer matches the
overlay, the build fails rather than using the production address.

Keep the artifacts private. Record the commit and unsigned archive SHA-256, have the official
signer verify and sign that artifact, and recheck the signed members and UID. Upload only to
Dify staging, then set the new-signup bootstrap to `package` mode and the signed package UID.
