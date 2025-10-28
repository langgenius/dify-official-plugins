"""
Linear Trigger Plugin - API Key Authentication Version

This version supports automatic webhook creation via Linear GraphQL API using API Key authentication.
Users can select teams dynamically and the plugin automatically manages webhooks.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import urllib.parse
from collections.abc import Mapping
from typing import Any

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


class LinearTrigger(Trigger):
    """Handle Linear webhook event dispatch."""

    def _dispatch_event(self, subscription: Subscription, request: Request) -> EventDispatch:
        """
        Dispatch Linear webhook events.

        Validates signature and timestamp, then dispatches events based on type and action.
        """
        # Validate webhook signature if secret is provided
        webhook_secret = subscription.properties.get("webhook_secret")
        if webhook_secret:
            self._validate_signature(request=request, webhook_secret=webhook_secret)

        # Validate timestamp (must be within 60 seconds)
        self._validate_timestamp(request)

        # Parse and validate payload
        payload: Mapping[str, Any] = self._validate_payload(request)

        # Get event type and action
        event_type: str | None = request.headers.get("Linear-Event") or payload.get("type")
        action: str | None = payload.get("action")

        if not event_type or not action:
            raise TriggerDispatchError("Missing event type or action in webhook")

        # Map to event name (e.g., Issue + create -> issue_created)
        event: str = self._map_event_name(event_type=event_type, action=action)

        # Respond with success
        response = Response(response='{"status": "ok"}', status=200, mimetype="application/json")

        return EventDispatch(events=[event] if event else [], response=response)

    def _map_event_name(self, event_type: str, action: str) -> str:
        """
        Map Linear event type and action to internal event name.

        Linear sends: action="create", type="Issue"
        We map to: "issue_created" (past tense for better UX)

        Format: {type_lowercase}_{action_past_tense}
        Example: Issue + create -> issue_created
        """
        event_type = event_type.lower()
        action = action.lower()

        # Map Linear actions to past tense event names
        action_map = {
            "create": "created",
            "update": "updated",
            "remove": "removed",
        }

        action_suffix = action_map.get(action)
        if not action_suffix:
            # Unknown action, return empty to ignore
            return ""

        return f"{event_type}_{action_suffix}"

    def _validate_payload(self, request: Request) -> Mapping[str, Any]:
        """Parse and validate webhook payload."""
        try:
            payload = request.get_json(force=True)
            if not payload:
                raise TriggerDispatchError("Empty request body")
            return payload
        except Exception as exc:
            raise TriggerDispatchError(f"Failed to parse payload: {exc}") from exc

    def _validate_signature(self, request: Request, webhook_secret: str) -> None:
        """
        Validate Linear webhook signature using HMAC-SHA256.

        Linear sends the signature in the 'Linear-Signature' header.
        """
        signature = request.headers.get("Linear-Signature")
        if not signature:
            raise TriggerValidationError("Missing webhook signature")

        # Compute expected signature
        raw_body = request.get_data()
        expected_signature = hmac.new(
            webhook_secret.encode(),
            raw_body,
            hashlib.sha256
        ).hexdigest()

        # Compare signatures using timing-safe comparison
        if not hmac.compare_digest(signature, expected_signature):
            raise TriggerValidationError("Invalid webhook signature")

    def _validate_timestamp(self, request: Request) -> None:
        """
        Validate webhook timestamp to prevent replay attacks.

        Linear includes webhookTimestamp in the payload (UNIX timestamp in milliseconds).
        We reject webhooks older than 60 seconds.
        """
        try:
            payload = request.get_json(force=True)
            webhook_timestamp = payload.get("webhookTimestamp")

            if not webhook_timestamp:
                # Timestamp validation is optional
                return

            # Convert to seconds (Linear sends milliseconds)
            webhook_time = webhook_timestamp / 1000
            current_time = time.time()

            # Check if timestamp is within 60 seconds
            if abs(current_time - webhook_time) > 60:
                raise TriggerValidationError("Webhook timestamp is too old or too far in the future")

        except TriggerValidationError:
            raise
        except Exception:
            # If timestamp validation fails, just log and continue
            pass


class LinearSubscriptionConstructor(TriggerSubscriptionConstructor):
    """
    Manage Linear trigger subscriptions via GraphQL API.

    Supports automatic webhook creation and deletion using Linear API Key.
    """

    _API_URL = "https://api.linear.app/graphql"
    _WEBHOOK_TTL = 365 * 24 * 60 * 60  # 1 year (webhooks don't auto-expire in Linear)

    def _oauth_refresh_credentials(self, credentials: Mapping[str, Any]) -> TriggerOAuthCredentials:
        """
        Refresh Linear OAuth credentials.
        """
        return TriggerOAuthCredentials(
            credentials=credentials,
            expires_at=-1
        )

    def _validate_api_key(self, credentials: Mapping[str, Any]) -> None:
        """
        Validate Linear API key by making a test request.
        """
        api_key = credentials.get("api_key")
        if not api_key:
            raise TriggerProviderCredentialValidationError("Linear API Key is required.")

        # Test the API key with a simple query
        query = """
        query {
          viewer {
            id
            name
            email
          }
        }
        """

        try:
            response = self._graphql_request(api_key, query, credential_type=CredentialType.API_KEY)
            if "errors" in response:
                error_msg = response["errors"][0].get("message", "Unknown error")
                raise TriggerProviderCredentialValidationError(f"Invalid API key: {error_msg}")

            if "data" not in response or "viewer" not in response["data"]:
                raise TriggerProviderCredentialValidationError("Invalid API key: Could not fetch user info")

        except TriggerProviderCredentialValidationError:
            raise
        except Exception as exc:
            raise TriggerProviderCredentialValidationError(f"Failed to validate API key: {exc}") from exc

    def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
        """
        Generate OAuth authorization URL for Linear.

        Args:
            redirect_uri: The callback URL where Linear will redirect after authorization
            system_credentials: System-level credentials containing client_id and client_secret

        Returns:
            Full authorization URL to redirect user to
        """
        client_id = system_credentials.get("client_id")
        if not client_id:
            raise TriggerProviderOAuthError("client_id is required for OAuth")

        # Generate CSRF protection state
        state = secrets.token_urlsafe(16)

        # Build authorization URL parameters
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "read,write,admin",  # Linear OAuth scopes
            "state": state
        }

        auth_url = f"https://linear.app/oauth/authorize?{urllib.parse.urlencode(params)}"
        return auth_url

    def _oauth_get_credentials(
        self,
        redirect_uri: str,
        system_credentials: Mapping[str, Any],
        request: Request
    ) -> TriggerOAuthCredentials:
        """
        Exchange authorization code for access token.

        Args:
            redirect_uri: The callback URL (must match the one used in authorization)
            system_credentials: System-level credentials containing client_id and client_secret
            request: The callback request containing the authorization code

        Returns:
            OAuth credentials containing access_token
        """
        # Extract authorization code from callback
        code = request.args.get("code")
        if not code:
            raise TriggerProviderOAuthError("No authorization code provided in callback")

        client_id = system_credentials.get("client_id")
        client_secret = system_credentials.get("client_secret")

        if not client_id or not client_secret:
            raise TriggerProviderOAuthError("client_id and client_secret are required")

        # Exchange code for access token
        # Linear requires application/x-www-form-urlencoded format
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }
        headers = {"Accept": "application/json"}

        try:
            response = requests.post(
                "https://api.linear.app/oauth/token",
                data=data,  # Use data= for form-urlencoded (not json=)
                headers=headers,
                timeout=10
            )

            data = response.json()

            # Check for errors in response
            if "error" in data:
                raise TriggerProviderOAuthError(
                    f"OAuth error: {data.get('error_description', data.get('error'))}"
                )

            access_token = data.get("access_token")
            if not access_token:
                raise TriggerProviderOAuthError(f"No access_token in response: {data}")

            # Linear access tokens are long-lived and don't expire
            return TriggerOAuthCredentials(
                credentials={"access_tokens": access_token},
                expires_at=-1  # Never expires
            )

        except TriggerProviderOAuthError:
            raise
        except requests.RequestException as exc:
            raise TriggerProviderOAuthError(f"Network error during token exchange: {exc}") from exc
        except Exception as exc:
            raise TriggerProviderOAuthError(f"Unexpected error during OAuth: {exc}") from exc

    def _create_subscription(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:
        """
        Create a webhook subscription via Linear GraphQL API.

        Supports both API Key and OAuth 2.0 authentication.
        """
        # Extract parameters
        team_id = parameters.get("team_id")
        if isinstance(team_id, list):
            if not team_id:
                team_id = None
            elif len(team_id) == 1:
                team_id = team_id[0]
            else:
                raise SubscriptionError(
                    "Only one team can be selected per webhook subscription",
                    error_code="INVALID_TEAM_SELECTION",
                )
        resource_types_param = parameters.get("resource_types")
        if isinstance(resource_types_param, str):
            resource_types = [
                value.strip()
                for value in resource_types_param.split(",")
                if value and value.strip()
            ]
        elif isinstance(resource_types_param, list):
            resource_types = resource_types_param
        else:
            resource_types = ["Issue"]

        if not resource_types:
            resource_types = ["Issue"]

        if not team_id:
            raise SubscriptionError(
                "team_id is required to create webhook",
                error_code="MISSING_TEAM_ID"
            )

        # Get authentication token based on credential type
        if credential_type == CredentialType.API_KEY:
            api_token = credentials.get("api_key")
        elif credential_type == CredentialType.OAUTH:
            api_token = credentials.get("access_tokens")
        else:
            raise SubscriptionError(
                f"Unsupported credential type: {credential_type}",
                error_code="UNSUPPORTED_CREDENTIAL_TYPE"
            )

        if not api_token:
            raise SubscriptionError(
                "Authentication token is required",
                error_code="MISSING_TOKEN"
            )

        # Generate webhook secret
        webhook_secret = secrets.token_hex(32)

        # Prepare GraphQL mutation
        mutation = """
        mutation WebhookCreate($input: WebhookCreateInput!) {
          webhookCreate(input: $input) {
            success
            webhook {
              id
              enabled
              url
              team {
                id
                name
                key
              }
              resourceTypes
              secret
            }
          }
        }
        """

        variables = {
            "input": {
                "url": endpoint,
                "teamId": team_id,
                "resourceTypes": resource_types,
                "secret": webhook_secret
            }
        }

        try:
            response = self._graphql_request(api_token, mutation, variables, credential_type=credential_type)

            # Check for GraphQL errors
            if "errors" in response:
                error_msg = response["errors"][0].get("message", "Unknown error")
                raise SubscriptionError(
                    f"Failed to create webhook: {error_msg}",
                    error_code="WEBHOOK_CREATION_FAILED",
                    external_response=response
                )

            # Extract webhook data
            webhook_data = response["data"]["webhookCreate"]
            if not webhook_data.get("success"):
                raise SubscriptionError(
                    "Webhook creation returned success=false",
                    error_code="WEBHOOK_CREATION_FAILED",
                    external_response=response
                )

            webhook = webhook_data["webhook"]

            return Subscription(
                expires_at=int(time.time()) + self._WEBHOOK_TTL,
                endpoint=endpoint,
                parameters=parameters,
                properties={
                    "external_id": webhook["id"],
                    "webhook_secret": webhook_secret,
                    "team_id": team_id,
                    "team_name": webhook["team"]["name"],
                    "team_key": webhook["team"]["key"],
                    "resource_types": webhook["resourceTypes"],
                    "enabled": webhook.get("enabled", True),
                },
            )

        except SubscriptionError:
            raise
        except Exception as exc:
            raise SubscriptionError(
                f"Unexpected error creating webhook: {exc}",
                error_code="WEBHOOK_CREATION_ERROR"
            ) from exc

    def _delete_subscription(
        self,
        subscription: Subscription,
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> UnsubscribeResult:
        """
        Delete a webhook subscription via Linear GraphQL API.

        Supports both API Key and OAuth 2.0 authentication.
        """
        external_id = subscription.properties.get("external_id")

        if not external_id:
            # If webhook ID is missing, just return success (idempotent)
            return UnsubscribeResult(
                success=True,
                message="Webhook ID not found (may have been manually deleted)"
            )

        # Get authentication token based on credential type
        if credential_type == CredentialType.API_KEY:
            api_token = credentials.get("api_key")
        elif credential_type == CredentialType.OAUTH:
            api_token = credentials.get("access_tokens")
        else:
            raise UnsubscribeError(
                message=f"Unsupported credential type: {credential_type}",
                error_code="UNSUPPORTED_CREDENTIAL_TYPE",
                external_response=None
            )

        if not api_token:
            raise UnsubscribeError(
                message="Authentication token is required",
                error_code="MISSING_TOKEN",
                external_response=None
            )

        # Prepare GraphQL mutation
        mutation = """
        mutation WebhookDelete($id: String!) {
          webhookDelete(id: $id) {
            success
          }
        }
        """

        variables = {"id": external_id}

        try:
            response = self._graphql_request(api_token, mutation, variables, credential_type=credential_type)

            # Check for GraphQL errors
            if "errors" in response:
                error_msg = response["errors"][0].get("message", "Unknown error")
                # If webhook not found, still return success (idempotent)
                if "not found" in error_msg.lower():
                    return UnsubscribeResult(
                        success=True,
                        message="Webhook already deleted"
                    )

                raise UnsubscribeError(
                    message=f"Failed to delete webhook: {error_msg}",
                    error_code="WEBHOOK_DELETION_FAILED",
                    external_response=response
                )

            # Check success flag
            delete_data = response["data"]["webhookDelete"]
            if delete_data.get("success"):
                return UnsubscribeResult(
                    success=True,
                    message=f"Successfully deleted webhook {external_id}"
                )
            else:
                raise UnsubscribeError(
                    message="Webhook deletion returned success=false",
                    error_code="WEBHOOK_DELETION_FAILED",
                    external_response=response
                )

        except UnsubscribeError:
            raise
        except Exception as exc:
            raise UnsubscribeError(
                message=f"Unexpected error deleting webhook: {exc}",
                error_code="WEBHOOK_DELETION_ERROR",
                external_response=None
            ) from exc

    def _refresh_subscription(
        self,
        subscription: Subscription,
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:
        """
        Refresh subscription by extending its expiration time.

        Linear webhooks don't auto-expire, so we just extend the TTL.
        """
        return Subscription(
            expires_at=int(time.time()) + self._WEBHOOK_TTL,
            endpoint=subscription.endpoint,
            properties=subscription.properties,
        )

    def _fetch_parameter_options(
        self,
        parameter: str,
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> list[ParameterOption]:
        """
        Fetch dynamic parameter options (e.g., team list).

        Supports both API Key and OAuth 2.0 authentication.
        """
        if parameter != "team_id":
            return []

        # Get authentication token based on credential type
        if credential_type == CredentialType.API_KEY:
            api_token = credentials.get("api_key")
        elif credential_type == CredentialType.OAUTH:
            api_token = credentials.get("access_tokens")
        else:
            raise ValueError(f"Unsupported credential type: {credential_type}")

        if not api_token:
            raise ValueError("Authentication token is required to fetch teams")

        # Query to fetch teams
        query = """
        query {
          teams {
            nodes {
              id
              name
              key
              description
              icon
            }
          }
        }
        """

        try:
            response = self._graphql_request(api_token, query, credential_type=credential_type)

            if "errors" in response:
                error_msg = response["errors"][0].get("message", "Unknown error")
                raise ValueError(f"Failed to fetch teams: {error_msg}")

            teams = response["data"]["teams"]["nodes"]

            # Convert to ParameterOption format
            options = []
            for team in teams:
                label_text = f"{team['name']} ({team['key']})"
                if team.get("description"):
                    label_text += f" - {team['description']}"

                options.append(
                    ParameterOption(
                        value=team["id"],
                        label=I18nObject(en_US=label_text),
                        icon=team.get("icon")
                    )
                )

            return options

        except Exception as exc:
            raise ValueError(f"Failed to fetch teams: {exc}") from exc

    # ------------------------------------------------------------------
    # Helper Methods
    # ------------------------------------------------------------------

    def _graphql_request(
        self,
        token: str,
        query: str,
        variables: dict[str, Any] | None = None,
        credential_type: CredentialType | None = None,
    ) -> dict[str, Any]:
        """
        Make a GraphQL request to Linear API.
        """
        auth_value = token
        if credential_type == CredentialType.OAUTH and not token.startswith("Bearer "):
            auth_value = f"Bearer {token}"

        headers = {
            "Authorization": auth_value,
            "Content-Type": "application/json",
        }

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        response = requests.post(
            self._API_URL,
            headers=headers,
            json=payload,
            timeout=30
        )

        # Always return JSON, even on non-200 status
        try:
            return response.json()
        except Exception:
            # If JSON parsing fails, return error structure
            return {
                "errors": [{
                    "message": f"HTTP {response.status_code}: {response.text[:200]}"
                }]
            }
