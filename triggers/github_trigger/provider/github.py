from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import urllib.parse
import uuid
from collections.abc import Mapping
from typing import Any, cast

import requests
from werkzeug import Request, Response

from dify_plugin.entities import I18nObject, ParameterOption
from dify_plugin.entities.oauth import TriggerOAuthCredentials
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.trigger import EventDispatch, Subscription, UnsubscribeResult
from dify_plugin.errors.trigger import (
    SubscriptionError,
    TriggerDispatchError,
    TriggerProviderCredentialValidationError,
    TriggerProviderOAuthError,
    TriggerValidationError,
    UnsubscribeError,
)
from dify_plugin.interfaces.trigger import Trigger, TriggerSubscriptionConstructor


class GithubTrigger(Trigger):
    """Handle GitHub webhook event dispatch."""

    def _dispatch_event(self, subscription: Subscription, request: Request) -> EventDispatch:
        webhook_secret = subscription.properties.get("webhook_secret")
        if webhook_secret:
            self._validate_signature(request=request, webhook_secret=webhook_secret)

        event_type: str | None = request.headers.get("X-GitHub-Event")
        if not event_type:
            raise TriggerDispatchError("Missing GitHub event type header")

        payload: Mapping[str, Any] = self._validate_payload(request)
        response = Response(response='{"status": "ok"}', status=200, mimetype="application/json")
        events: list[str] = self._dispatch_trigger_events(event_type=event_type, payload=payload)
        return EventDispatch(events=events, response=response)

    def _dispatch_trigger_events(self, event_type: str, payload: Mapping[str, Any]) -> list[str]:
        event_type = event_type.lower()
        action: str | None = payload.get("action")
        # Unified core events (breaking change): issues / issue_comment / pull_request
        if event_type in {"issues", "issue_comment", "pull_request"}:
            return [event_type]

        # Unified review & CI events (breaking change)
        if event_type in {"pull_request_review", "pull_request_review_comment", "check_suite", "check_run", "workflow_run", "workflow_job"}:
            return [event_type]

        if event_type in {"deployment_status", "release"}:
            if not action:
                raise TriggerDispatchError(f"GitHub event '{event_type}' missing action in payload")
            return [f"{event_type}_{action}"]

        if event_type == "push":
            return ["push"]

        if event_type == "star":
            return ["star"]

        # Unified events without action splitting
        if event_type == "code_scanning_alert":
            return ["code_scanning_alert"]

        if event_type in {"secret_scanning_alert", "secret_scanning_alert_location", "secret_scanning_scan"}:
            return ["secret_scanning"]

        if event_type in {"create", "delete"}:
            return ["ref_change"]

        if event_type == "commit_comment":
            return ["commit_comment"]

        if event_type == "status":
            return ["status"]

        if event_type == "deployment":
            return ["deployment"]

        if event_type == "dependabot_alert":
            return ["dependabot_alert"]

        if event_type == "repository_vulnerability_alert":
            return ["repository_vulnerability_alert"]

        if event_type in {"branch_protection_configuration", "branch_protection_rule"}:
            return [event_type]

        if event_type == "repository_ruleset":
            return ["repository_ruleset"]

        # Additional unified GitHub events (breaking change by design)
        if event_type in {
            "discussion",
            "discussion_comment",
            "fork",
            "gollum",
            "issue_dependencies",
            "sub_issues",
            "label",
            "member",
            "merge_group",
            "meta",
            "milestone",
            "package",
            "registry_package",
            "page_build",
            "ping",
            "project",
            "project_column",
            "project_card",
            "public",
            "pull_request_review_thread",
            "repository",
            "repository_import",
            "repository_advisory",
            "security_and_analysis",
            "custom_property_values",
            "deploy_key",
            "watch",
        }:
            return [event_type]

        return []

    def _validate_payload(self, request: Request) -> Mapping[str, Any]:
        try:
            content_type = request.headers.get("Content-Type", "")
            if "application/x-www-form-urlencoded" in content_type:
                form_data = request.form.get("payload")
                if not form_data:
                    raise TriggerDispatchError("Missing payload in form data")
                payload = json.loads(form_data)
            else:
                payload = request.get_json(force=True)
            if not payload:
                raise TriggerDispatchError("Empty request body")
            return payload
        except TriggerDispatchError:
            raise
        except Exception as exc:  # pragma: no cover - defensive logging path
            raise TriggerDispatchError(f"Failed to parse payload: {exc}") from exc

    def _validate_signature(self, request: Request, webhook_secret: str) -> None:
        signature = request.headers.get("X-Hub-Signature-256")
        if not signature:
            raise TriggerValidationError("Missing webhook signature")

        expected_signature = (
            "sha256=" + hmac.new(webhook_secret.encode(), request.get_data(), hashlib.sha256).hexdigest()
        )
        if not hmac.compare_digest(signature, expected_signature):
            raise TriggerValidationError("Invalid webhook signature")


class GithubSubscriptionConstructor(TriggerSubscriptionConstructor):
    """Manage GitHub trigger subscriptions."""

    _AUTH_URL = "https://github.com/login/oauth/authorize"
    _TOKEN_URL = "https://github.com/login/oauth/access_token"
    _API_USER_URL = "https://api.github.com/user"
    _WEBHOOK_TTL = 30 * 24 * 60 * 60

    def _validate_api_key(self, credentials: Mapping[str, Any]) -> None:
        access_token = credentials.get("access_tokens")
        if not access_token:
            raise TriggerProviderCredentialValidationError("GitHub API Access Token is required.")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        }
        try:
            response = requests.get(self._API_USER_URL, headers=headers, timeout=10)
            if response.status_code != 200:
                raise TriggerProviderCredentialValidationError(response.json().get("message"))
        except TriggerProviderCredentialValidationError:
            raise
        except Exception as exc:  # pragma: no cover - defensive logging path
            raise TriggerProviderCredentialValidationError(str(exc)) from exc

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        state = secrets.token_urlsafe(16)
        params = {
            "client_id": system_credentials["client_id"],
            "redirect_uri": redirect_uri,
            "scope": system_credentials.get("scope", "read:user admin:repo_hook"),
            "state": state,
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> TriggerOAuthCredentials:
        code = request.args.get("code")
        if not code:
            raise TriggerProviderOAuthError("No code provided")

        if not system_credentials.get("client_id") or not system_credentials.get("client_secret"):
            raise TriggerProviderOAuthError("Client ID or Client Secret is required")

        data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "code": code,
            "redirect_uri": redirect_uri,
        }
        headers = {"Accept": "application/json"}
        response = requests.post(self._TOKEN_URL, data=data, headers=headers, timeout=10)
        response_json = response.json()
        access_tokens = response_json.get("access_token")
        if not access_tokens:
            raise TriggerProviderOAuthError(f"Error in GitHub OAuth: {response_json}")

        return TriggerOAuthCredentials(credentials={"access_tokens": access_tokens}, expires_at=-1)

    def _create_subscription(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:
        repository = parameters.get("repository")
        if not repository:
            raise ValueError("repository is required (format: owner/repo)")

        try:
            owner, repo = repository.split("/")
        except ValueError:
            raise ValueError("repository must be in format 'owner/repo'") from None

        events: list[str] = parameters.get("events", [])
        webhook_secret = uuid.uuid4().hex
        url = f"https://api.github.com/repos/{owner}/{repo}/hooks"
        headers = {
            "Authorization": f"Bearer {credentials.get('access_tokens')}",
            "Accept": "application/vnd.github+json",
        }

        webhook_data = {
            "name": "web",
            "active": True,
            "events": events,
            "config": {"url": endpoint, "content_type": "json", "insecure_ssl": "0", "secret": webhook_secret},
        }

        try:
            response = requests.post(url, json=webhook_data, headers=headers, timeout=10)
        except requests.RequestException as exc:
            raise SubscriptionError(f"Network error while creating webhook: {exc}", error_code="NETWORK_ERROR") from exc

        if response.status_code == 201:
            webhook = response.json()
            return Subscription(
                expires_at=int(time.time()) + self._WEBHOOK_TTL,
                endpoint=endpoint,
                parameters=parameters,
                properties={
                    "external_id": str(webhook["id"]),
                    "repository": repository,
                    "events": events,
                    "webhook_secret": webhook_secret,
                    "active": webhook.get("active", True),
                },
            )

        response_data: dict[str, Any] = response.json() if response.content else {}
        error_msg = response_data.get("message", "Unknown error")
        error_details = response_data.get("errors", [])
        detailed_error = f"Failed to create GitHub webhook: {error_msg}"
        if error_details:
            detailed_error += f" Details: {error_details}"

        raise SubscriptionError(
            detailed_error,
            error_code="WEBHOOK_CREATION_FAILED",
            external_response=response_data,
        )

    def _delete_subscription(
        self, subscription: Subscription, credentials: Mapping[str, Any], credential_type: CredentialType
    ) -> UnsubscribeResult:
        external_id = subscription.properties.get("external_id")
        repository = subscription.properties.get("repository")

        if not external_id or not repository:
            raise UnsubscribeError(
                message="Missing webhook ID or repository information",
                error_code="MISSING_PROPERTIES",
                external_response=None,
            )

        try:
            owner, repo = repository.split("/")
        except ValueError:
            raise UnsubscribeError(
                message="Invalid repository format in properties",
                error_code="INVALID_REPOSITORY",
                external_response=None,
            ) from None

        url = f"https://api.github.com/repos/{owner}/{repo}/hooks/{external_id}"
        headers = {
            "Authorization": f"Bearer {credentials.get('access_tokens')}",
            "Accept": "application/vnd.github+json",
        }

        try:
            response = requests.delete(url, headers=headers, timeout=10)
        except requests.RequestException as exc:
            raise UnsubscribeError(
                message=f"Network error while deleting webhook: {exc}",
                error_code="NETWORK_ERROR",
                external_response=None,
            ) from exc

        if response.status_code == 204:
            return UnsubscribeResult(
                success=True, message=f"Successfully removed webhook {external_id} from {repository}"
            )

        if response.status_code == 404:
            raise UnsubscribeError(
                message=f"Webhook {external_id} not found in repository {repository}",
                error_code="WEBHOOK_NOT_FOUND",
                external_response=response.json(),
            )

        raise UnsubscribeError(
            message=f"Failed to delete webhook: {response.json().get('message', 'Unknown error')}",
            error_code="WEBHOOK_DELETION_FAILED",
            external_response=response.json(),
        )

    def _refresh_subscription(
        self, subscription: Subscription, credentials: Mapping[str, Any], credential_type: CredentialType
    ) -> Subscription:
        return Subscription(
            expires_at=int(time.time()) + self._WEBHOOK_TTL,
            endpoint=subscription.endpoint,
            properties=subscription.properties,
        )

    def _fetch_parameter_options(
        self, parameter: str, credentials: Mapping[str, Any], credential_type: CredentialType
    ) -> list[ParameterOption]:
        if parameter != "repository":
            return []

        token = credentials.get("access_tokens")
        if not token:
            raise ValueError("access_tokens is required to fetch repositories")
        return self._fetch_repositories(token)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fetch_repositories(self, access_token: str) -> list[ParameterOption]:
        headers: Mapping[str, str] = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        options: list[ParameterOption] = []
        per_page = 100
        page = 1

        while True:
            params = {
                "per_page": per_page,
                "page": page,
                "affiliation": "owner,collaborator,organization_member",
                "sort": "full_name",
                "direction": "asc",
            }

            response = requests.get("https://api.github.com/user/repos", headers=headers, params=params, timeout=10)

            if response.status_code != 200:
                try:
                    err = response.json()
                    message = err.get("message", str(err))
                except Exception:  # pragma: no cover - fallback path
                    message = response.text
                raise ValueError(f"Failed to fetch repositories from GitHub: {message}")

            raw_repos: Any = response.json() or []
            if not isinstance(raw_repos, list):
                raise ValueError("Unexpected response format from GitHub API when fetching repositories")

            repos = cast(list[dict[str, Any]], raw_repos)
            for repo in repos:
                full_name = repo.get("full_name")
                owner: dict[str, Any] = repo.get("owner") or {}
                avatar_url: str | None = owner.get("avatar_url")
                if full_name:
                    options.append(
                        ParameterOption(
                            value=full_name,
                            label=I18nObject(en_US=full_name),
                            icon=avatar_url,
                        )
                    )

            if len(repos) < per_page:
                break

            page += 1

        return options
