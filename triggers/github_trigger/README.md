GitHub Trigger (Unified Events)

Overview
- GitHub Trigger is a Dify provider that receives GitHub webhooks and emits trigger events into your workflows.
- Events are unified by family (e.g., issues, pull_request, check_run) with an actions filter, instead of splitting every action into separate events. This reduces noise and aligns with product usage.
- Each event exposes clear parameters and a comprehensive output schema (including full repository and sender objects) for reliable automation.

Quick Start
- Install dependencies: `pip install -r requirements.txt`
- In Dify, add the GitHub Trigger provider and configure Credentials.
- Create a Subscription with:
  - `repository`: pick one repository (dynamic select)
  - `events`: choose the webhook families you want (e.g., issues, pull_request, check_run)
  - `webhook_secret` (optional): used to validate signatures; see “Webhook Secret”.

Credentials
- Access Token (recommended for simplicity)
  - Generate a fine-grained or classic token with repo/webhook scopes.
  - Where to create: https://github.com/settings/tokens?type=beta
- OAuth (optional)
  - Register a GitHub OAuth app and provide Client ID/Secret.
  - Used to obtain an access token during subscription construction.

Webhook Secret
- Purpose: verify the HMAC signature on incoming requests.
- If Dify creates the webhook: a random secret is generated and stored with the subscription.
- If you configure the webhook manually in Repository Settings → Webhooks: set the same secret in GitHub and paste it into `webhook_secret` so signatures validate.
- Reference: https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries

Unified Event Model
- Design: unify events per family and expose an `actions` multi-select parameter to filter actions when payload shapes are identical (e.g., star created/deleted, label created/edited/deleted).
- Benefits: fewer choices for users, simpler mental model, consistent schemas, easier reuse.
- Breaking change: legacy per-action events (e.g., issue_opened) are replaced by unified families; configure the desired actions in parameters.

Parameter Semantics
- Multi-select parameters: choose specific actions/states; leave empty to accept all supported values.
- String lists: comma-separated exact matches, case-insensitive where noted (e.g., authors, labels).
- Contains filters: “*_contains” parameters check substrings and accept comma-separated keywords; any match passes.
- Boolean flags: when set, they filter strictly (true/false). When omitted, they do not filter.
- Glob patterns: where supported (e.g., changed_files_glob), match file paths with comma-separated globs.

Implemented Events (high-level)
- Collaboration: issues, issue_comment, pull_request, pull_request_review, pull_request_review_comment, pull_request_review_thread
- CI/Automation: check_suite, check_run, workflow_run, workflow_job, status
- SCM: push, ref_change (create/delete), commit_comment, release (published), deployment, deployment_status (created)
- Governance/Security: code_scanning_alert, secret_scanning, dependabot_alert, repository_vulnerability_alert, repository_advisory, security_and_analysis, branch_protection_configuration, branch_protection_rule, repository_ruleset
- Community/Growth: discussion, discussion_comment, star, watch, fork, label, gollum (Wiki)
- Projects/Planning: milestone, project, project_column, project_card, member, merge_group, meta
- Packages: package, registry_package
- Advanced: repository, repository_import, public, custom_property_values, issue_dependencies, sub_issues, deploy_key

Output Schema Consistency
- Every unified event includes a detailed `repository` and `sender` block modeled after the Issues event style.
- Each family adds its specific object (e.g., `issue`, `pull_request`, `check_run`, `package`, `deployment`, `pages`) with commonly used fields and URLs.
- See the YAML under `events/**/` for complete schemas and parameter help.

Subscription Flow
- Provider manifest: `github_trigger/provider/github.yaml` lists all registered events.
- Dispatch: `github_trigger/provider/github.py` routes GitHub headers and payloads to the appropriate unified event.
- Subscriptions automatically create and manage webhooks on the target repository using your credentials.

Examples
- Subscribe to PR review automation
  - Events: `pull_request`, `pull_request_review`, `pull_request_review_comment`
  - Parameters: set `actions` to the review states you care about; optionally filter by `reviewer`, `author`, `body_contains`.
- Security guardrails
  - Events: `code_scanning_alert`, `dependabot_alert`, `secret_scanning`
  - Parameters: filter by `severity`, `state`, `branch`, or `subtypes` for secret scanning.
- Branch governance
  - Event: `ref_change` with `event_types=create,delete` and `ref_type=branch` to detect branch creation/deletion.

Extending the Provider
- Add a new event family
  - Create a folder under `events/<family>/` with `<family>.py` and `<family>.yaml`.
  - Implement a subclass of `dify_plugin.interfaces.trigger.Event` with `_on_event` returning `Variables(payload)`.
  - In YAML, provide `identity`, `description`, `parameters` (include helpful `help` text), and a complete `output_schema`.
  - Register the YAML path in `provider/github.yaml` under `events:`.
- Utilities
  - Common helpers live in `events/utils/` (payload loading, PR filters, etc.).

Troubleshooting
- Webhook not triggering: verify repository, events, and that the webhook delivery logs show 2xx.
- Signature validation failed: confirm `webhook_secret` is identical on both GitHub and the subscription.
- Filter didn’t match: check your parameter values against the actual payload (comma-separated vs exact match; action names).
- Payload variance: some security events differ by repo/app configuration; schemas cover common fields but you may need to adjust filters.

Directory Layout
- `provider/github.py`: webhook dispatch, subscription lifecycle, OAuth/API key handling
- `provider/github.yaml`: manifest, credential schemas, events listing
- `events/**`: unified event handlers (`.py`) and schemas (`.yaml`)
- `EVENTS_TODO.md`: planning and status for event coverage

Author
- langgenius
