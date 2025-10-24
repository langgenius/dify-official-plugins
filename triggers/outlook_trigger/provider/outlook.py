from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta
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


class OutlookTrigger(Trigger):
    """Handle Outlook webhook event dispatch."""

    def _dispatch_event(
        self, subscription: Subscription, request: Request
    ) -> EventDispatch:
        client_state = subscription.properties.get("client_state")

        print("subscription", subscription)
        print("request", request)
        print("request.args", request.args)

        body = request.get_data()

        if len(body) == 0:  # validation request

            validationToken = request.args.get("validationToken")
            if validationToken:
                returnText = urllib.parse.unquote(validationToken)
                print("returnText", returnText)
                return EventDispatch(events=[], response=Response(response=returnText, status=200, mimetype="application/text"))
            pass
        else:
            payload = json.loads(body)
            print("payload", payload)
            

            value = payload.get("value")[0]

            resource = value.get("resource")
            print("resource", resource)

            if value.get("clientState") != client_state:
                raise TriggerDispatchError("Invalid client state")
            
            response = Response(response='{"status": "ok"}', status=200, mimetype="application/json")
            events = ["email_received"]

            fetch_url = f"https://graph.microsoft.com/v1.0/{resource}"
            headers = {
                "Authorization": f"Bearer {subscription.properties.get('access_tokens')}",
                "Accept": "application/json",
            }
            response = requests.get(fetch_url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                print("email data", json.dumps(data, indent=4))
                
                response = Response(response='{"status": "ok"}', status=200, mimetype="application/json")

                events = ["email_received"]
                return EventDispatch(events=events, response=response, payload=data)
            else:
                print("response", response.json())
                raise TriggerDispatchError(f"Failed to fetch resource: {response.json().get('message', 'Unknown error')}")


class GithubSubscriptionConstructor(TriggerSubscriptionConstructor):
    """Manage GitHub trigger subscriptions."""

    _AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    _TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    # _API_USER_URL = "https://api.github.com/user"
    _WEBHOOK_TTL = 3 * 24 * 60 * 60

    def _validate_api_key(self, credentials: Mapping[str, Any]) -> None:
        # access_token = credentials.get("access_tokens")
        # if not access_token:
        #     raise TriggerProviderCredentialValidationError("GitHub API Access Token is required.")

        # headers = {
        #     "Authorization": f"Bearer {access_token}",
        #     "Accept": "application/vnd.github+json",
        # }
        # try:
        #     response = requests.get(self._API_USER_URL, headers=headers, timeout=10)
        #     if response.status_code != 200:
        #         raise TriggerProviderCredentialValidationError(response.json().get("message"))
        # except TriggerProviderCredentialValidationError:
        #     raise
        # except Exception as exc:  # pragma: no cover - defensive logging path
        #     raise TriggerProviderCredentialValidationError(str(exc)) from exc
        pass

    def _oauth_get_authorization_url(
        self, redirect_uri: str, system_credentials: Mapping[str, Any]
    ) -> str:
        state = secrets.token_urlsafe(16)
        params = {
            "client_id": system_credentials["client_id"],
            "redirect_uri": redirect_uri,
            "scope": system_credentials.get(
                "scope",
                "offline_access https://graph.microsoft.com/Channel.ReadBasic.All https://graph.microsoft.com/Mail.Read",
            ),
            "response_type": "code",
            "state": state,
        }
        return f"{self._AUTH_URL}?{urllib.parse.urlencode(params)}"

    def _oauth_get_credentials(
        self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    ) -> TriggerOAuthCredentials:
        print("request", request)
        print("request.args", request.args)
        print("request.form", request.form)
        print("request.args.get('code')", request.args.get("code"))
        print("request.args.get('state')", request.args.get("state"))
        print("system_credentials", system_credentials)
        code = request.args.get("code")
        if not code:
            raise TriggerProviderOAuthError("No code provided")

        if not system_credentials.get("client_id") or not system_credentials.get(
            "client_secret"
        ):
            raise TriggerProviderOAuthError("Client ID or Client Secret is required")

        data = {
            "client_id": system_credentials["client_id"],
            "client_secret": system_credentials["client_secret"],
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "scope": system_credentials.get(
                "scope",
                "offline_access https://graph.microsoft.com/Channel.ReadBasic.All https://graph.microsoft.com/Mail.Read",
            ),
        }
        headers = {"Accept": "application/json"}
        response = requests.post(
            self._TOKEN_URL, data=data, headers=headers, timeout=10
        )
        response_json = response.json()
        access_tokens = response_json.get("access_token")
        if not access_tokens:
            raise TriggerProviderOAuthError(f"Error in Outlook OAuth: {response_json}")
        refresh_token = response_json.get("refresh_token")
        if not refresh_token:
            raise TriggerProviderOAuthError("No refresh token in response")

        print("response_json", response_json)

        return TriggerOAuthCredentials(
            credentials={
                "access_tokens": access_tokens,
                "refresh_token": refresh_token,
            },
            expires_at=response_json.get("expires_in", 3599) + int(time.time()),
        )

    def _oauth_refresh_credentials(self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]) -> TriggerOAuthCredentials:
        url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "refresh_token",
            "refresh_token": credentials.get("refresh_token"),
            "client_id": system_credentials.get("client_id"),
            "client_secret": system_credentials.get("client_secret"),
        }
        response = requests.post(url, headers=headers, data=data, timeout=10)
        if response.status_code == 200:
            access_tokens = response.json().get("access_token")
            refresh_token = response.json().get("refresh_token")
            return TriggerOAuthCredentials(
                credentials={
                    "access_tokens": access_tokens,
                    "refresh_token": refresh_token,
                },
                expires_at=response.json().get("expires_in", 3599) + int(time.time()),
            )
        else:
            print("response", response.json())
            raise TriggerProviderOAuthError(f"Failed to refresh access token: {response.json().get('message', 'Unknown error')}") from response.json()

    def _create_subscription(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:

        print("create_subscription", endpoint, parameters, credentials, credential_type)

        url = "https://graph.microsoft.com/v1.0/subscriptions"
        headers = {
            "Authorization": f"Bearer {credentials.get('access_tokens')}",
            "Accept": "application/json",
        }

        client_state = secrets.token_urlsafe(16)
        print("client_state", client_state)
        # 72 hours from now
        expiration_date = datetime.now() + timedelta(seconds=self._WEBHOOK_TTL)
        expiration_date_str = expiration_date.isoformat() + "Z"
        print("expiration_date_str", expiration_date_str)
        data = {
            "changeType": "created,updated",
            "notificationUrl": endpoint,
            "resource": "me/mailfolders('Inbox')/messages",
            "expirationDateTime": expiration_date_str,
            "clientState": client_state,
        }
        

        print("data", data)
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
        except requests.RequestException as exc:
            raise SubscriptionError(
                message=f"Network error while creating subscription: {exc}",
                error_code="NETWORK_ERROR",
                external_response=None,
            ) from exc
            
        if response.status_code == 201:
            subscription = response.json()
            print("subscription", subscription)
            return Subscription(
                expires_at=int(time.time()) + self._WEBHOOK_TTL,
                endpoint=endpoint,
                parameters=parameters,
                properties={
                    "subscription_id": subscription.get("id"),
                    "client_state": client_state,
                    "access_tokens": credentials.get('access_tokens'),
                    "refresh_token": credentials.get('refresh_token'),
                },
            )
        else:
            print("response", response.json())
            raise SubscriptionError(
                message=f"Failed to create subscription: {response.json().get('message', 'Unknown error')}",
                error_code="SUBSCRIPTION_CREATION_FAILED",
                external_response=response.json(),
            )

    def _delete_subscription(
        self,
        subscription: Subscription,
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> UnsubscribeResult:
        print("delete_subscription", subscription, credentials, credential_type)
        subscription_id = subscription.properties.get("subscription_id")
        if not subscription_id:
            raise UnsubscribeError(
                message="Missing subscription ID",
                error_code="MISSING_PROPERTIES",
                external_response=None,
            )
        
        url = f"https://graph.microsoft.com/v1.0/subscriptions/{subscription_id}"
        headers = {
            "Authorization": f"Bearer {credentials.get('access_tokens')}",
            "Accept": "application/json",
        }
        response = requests.delete(url, headers=headers, timeout=10)
        if response.status_code == 204:
            return UnsubscribeResult(success=True, message=f"Successfully deleted subscription {subscription_id}")
        else:
            print("response", response.json())
            raise UnsubscribeError(
                message=f"Failed to delete subscription: {response.json().get('message', 'Unknown error')}",
                error_code="SUBSCRIPTION_DELETION_FAILED",
                external_response=response.json(),
            )

    def _refresh_subscription(
        self,
        subscription: Subscription,
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:
        new_expiration_date = datetime.now() + timedelta(seconds=self._WEBHOOK_TTL)
        new_expiration_date_str = new_expiration_date.isoformat() + "Z"

        subscription_id = subscription.properties.get("subscription_id")
        if not subscription_id:
            raise UnsubscribeError(
                message="Missing subscription ID",
                error_code="MISSING_PROPERTIES",
                external_response=None,
            )

        headers = {
            "Authorization": f"Bearer {credentials.get('access_tokens')}",
            "Accept": "application/json",
        }
        data = {
            "expirationDateTime": new_expiration_date_str,
        }
        url = f"https://graph.microsoft.com/v1.0/subscriptions/{subscription_id}"
        response = requests.patch(url, headers=headers, json=data, timeout=10)
        if response.status_code == 200:
            return Subscription(
                expires_at=int(new_expiration_date.timestamp()),
                endpoint=subscription.endpoint,
                properties={
                    "subscription_id": subscription_id,
                    "client_state": subscription.properties.get("client_state"),
                    "access_tokens": credentials.get('access_tokens'),
                    "refresh_token": credentials.get('refresh_token'),
                },
            )
        else:
            print("response", response.json())
            raise SubscriptionError(
                message=f"Failed to refresh subscription: {response.json().get('message', 'Unknown error')}",
                error_code="SUBSCRIPTION_REFRESH_FAILED",
                external_response=response.json(),
            )

    def _fetch_parameter_options(
        self,
        parameter: str,
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
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

            response = requests.get(
                "https://api.github.com/user/repos",
                headers=headers,
                params=params,
                timeout=10,
            )

            if response.status_code != 200:
                try:
                    err = response.json()
                    message = err.get("message", str(err))
                except Exception:  # pragma: no cover - fallback path
                    message = response.text
                raise ValueError(f"Failed to fetch repositories from GitHub: {message}")

            raw_repos: Any = response.json() or []
            if not isinstance(raw_repos, list):
                raise ValueError(
                    "Unexpected response format from GitHub API when fetching repositories"
                )

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
