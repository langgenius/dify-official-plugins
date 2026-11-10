# MistralAI

Configure your [Mistral API key](https://console.mistral.ai/api-keys/) in
Settings → Model Provider after installing the plugin.

## Current chat models

Catalog reviewed on 2026-10-30 against the [official model cards](https://docs.mistral.ai/models).
Prices below are USD per million input/output tokens.

| Model | Explicit API ID | Context | Vision | Input / output |
| --- | --- | --- | --- | --- |
| Medium 3.5 | `mistral-medium-3-5` | 256k | Yes | 1.5 / 7.5 |
| Large 3 | `mistral-large-2512` | 256k | Yes | 0.5 / 1.5 |
| Large 4 (Public Preview) | `mistral-large-4-0` | 1M | Yes | 0.7 / 2.1 |
| Small 4 | `mistral-small-2603` | 256k | Yes | 0.15 / 0.6 |
| Ministral 3 3B | `ministral-3b-2512` | 256k | Yes | 0.1 / 0.1 |
| Ministral 3 8B | `ministral-8b-2512` | 256k | Yes | 0.15 / 0.15 |
| Ministral 3 14B | `ministral-14b-2512` | 256k | Yes | 0.2 / 0.2 |
| Codestral | `codestral-2508` | 128k | No | 0.3 / 0.9 |

The corresponding `-latest` aliases are also available. The
[official alias table](https://docs.mistral.ai/vibe/code/cli/configuration)
currently maps `mistral-large-latest` to **Large 3**, not the Large 4 preview.
Large 4 is also available through its `mistral-large-4` major-version alias.
Aliases can change behavior and pricing upstream; the plugin's capability,
context and pricing metadata only change with plugin updates. Explicit versions
remain subject to Mistral's [model lifecycle](https://docs.mistral.ai/inference/model-lifecycle).

Mistral Embed, Codestral Embed and the existing moderation integration remain
available. OCR and audio endpoints are outside this chat catalog update.

## Upgrade to 0.0.16

Medium/Large and Ministral latest definitions now expose image input. The current
models above have updated context windows and pricing. The request endpoint and
API-key configuration are unchanged.

The following retired definitions have been removed from both the YAML catalog
and model ordering. **Before upgrading, migrate applications and workflow nodes
that reference these IDs.** Saved workflows are not automatically rewritten, and
old IDs are not silently redirected to a different model.

| Removed IDs | Suggested replacement | Official retirement evidence |
| --- | --- | --- |
| `mistral-small-2503` | `mistral-small-2603` | [Small 3.1](https://docs.mistral.ai/models/mistral-small-3-1-25-03) |
| `magistral-medium-2506` | `mistral-medium-3-5` | [Magistral Medium 1.0](https://docs.mistral.ai/models/magistral-medium-1-0-25-06) |
| `magistral-small-2506` | `mistral-small-2603` | [Magistral Small 1.0](https://docs.mistral.ai/models/magistral-small-1-0-25-06) |
| `devstral-small-2505` | `mistral-medium-3-5` | [Devstral Small 1.0](https://docs.mistral.ai/models/devstral-small-1-0-25-05) |
| `mistral-saba-2502`, `mistral-saba-latest` | `mistral-small-2603` | [Saba](https://docs.mistral.ai/models/mistral-saba-25-02) |
| `codestral-2501` | `codestral-2508` | [Codestral 2501](https://docs.mistral.ai/models/codestral-25-01) |
| `open-codestral-mamba` | `codestral-2508` | [Codestral Mamba](https://docs.mistral.ai/models/codestral-mamba-7b-0-1) |
| `mathstral` | `mistral-small-2603` | [Mathstral](https://docs.mistral.ai/models/mathstral-7b-0-1) |

Replacement models can differ in pricing, output and reasoning parameters;
review node settings and test your workflows after migration.

### Deprecated definitions retained for compatibility

The current official cards label `mistral-medium-2505`, `mistral-large-2411`,
`pixtral-large-2411`, the old Ministral 2410 models, Pixtral 12B and Nemo as
**Deprecated**, rather than **Retired**. They remain in this release, after the
current models in the picker. This is not a guarantee of API availability for
an individual account. Prefer current versions for new workflows; remove these
entries when retirement is confirmed by Mistral.

Existing Magistral latest and Devstral latest definitions also remain for
compatibility. No new deprecated model versions are introduced. The legacy
Magistral `reasoning_mode` option continues to map to `prompt_mode`; this option
is not copied to the new Medium/Small models.

This plugin currently supports predefined models only. This release does not
add custom model configuration or change the inference implementation.
