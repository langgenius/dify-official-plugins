# 17TRACK Dify Plugin

Cross-border e-commerce order tracking for 2900+ carriers with automatic status updates.

## Tools

- **get_quota** — get the current tracking and email quota counters for the 17TRACK account
- **register_trackings** — register up to 40 tracking numbers for automatic tracking by 17TRACK
- **get_tracking_details** — get current tracking details for up to 40 registered tracking numbers
- **list_trackings** — list registered shipments with status and pagination filters

## Credential

17TRACK API key from [17TRACK API Settings](https://api.17track.net/admin/settings),
sent in the `17token` header and validated against `getquota` on save.

## Development

```bash
dify plugin package .   # package as .difypkg
```

Then submit a PR to `langgenius/dify-official-plugins` under `tools/17track` for
marketplace listing.

Domain behavior (envelope check, error-code classes, response normalization) is aligned
with the open-source [OpenConnector](https://github.com/oomol-lab/open-connector)
17TRACK provider.
