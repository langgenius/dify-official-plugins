from __future__ import annotations

import base64
import hashlib
import hmac
import time
from collections.abc import Mapping
from typing import Any

import requests
from werkzeug import Request, Response

from dify_plugin.entities import I18nObject, ParameterOption
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.trigger import EventDispatch, Subscription, UnsubscribeResult
from dify_plugin.errors.trigger import (
    SubscriptionError,
    TriggerDispatchError,
    TriggerProviderCredentialValidationError,
    TriggerValidationError,
    UnsubscribeError,
)
from dify_plugin.interfaces.trigger import Trigger, TriggerSubscriptionConstructor


class TwilioTrigger(Trigger):
    """Handle Twilio webhook event dispatch."""

    def _dispatch_event(self, subscription: Subscription, request: Request) -> EventDispatch:
        # Validate Twilio signature if auth_token is available
        auth_token = subscription.properties.get("auth_token")
        if auth_token:
            self._validate_signature(
                request=request,
                auth_token=auth_token,
                url=subscription.endpoint,
            )

        # Parse form-urlencoded payload from Twilio
        payload = self._parse_payload(request)

        # Determine event type based on payload content
        events = self._dispatch_trigger_events(payload)

        # Use From number as user_id
        user_id = payload.get("From", "unknown")

        response = Response(
            response='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            status=200,
            mimetype="application/xml",
        )

        return EventDispatch(user_id=user_id, events=events, response=response, payload=payload)

    def _dispatch_trigger_events(self, payload: Mapping[str, Any]) -> list[str]:
        """Determine event type based on payload content."""
        from_number = payload.get("From", "")

        # Check if it's a WhatsApp message
        if from_number.startswith("whatsapp:"):
            if "Body" in payload:
                return ["whatsapp_received"]

        # Check if it's an SMS (has Body field but not from WhatsApp)
        if "Body" in payload and "MessageSid" in payload:
            return ["sms_received"]

        # Check if it's a call (has CallSid and CallStatus)
        if "CallSid" in payload and "CallStatus" in payload:
            return ["call_received"]

        return []

    def _parse_payload(self, request: Request) -> dict[str, Any]:
        """Parse Twilio webhook payload (form-urlencoded)."""
        try:
            # Twilio sends data as application/x-www-form-urlencoded
            payload = dict(request.form)
            if not payload:
                raise TriggerDispatchError("Empty request body")
            return payload
        except TriggerDispatchError:
            raise
        except Exception as exc:
            raise TriggerDispatchError(f"Failed to parse payload: {exc}") from exc

    def _validate_signature(self, request: Request, auth_token: str, url: str) -> None:
        """Validate Twilio request signature using X-Twilio-Signature header."""
        signature = request.headers.get("X-Twilio-Signature")
        if not signature:
            raise TriggerValidationError("Missing Twilio signature header")

        # Build the data string: URL + sorted POST parameters
        params = dict(request.form)
        sorted_params = "".join(f"{k}{v}" for k, v in sorted(params.items()))
        data = url + sorted_params

        # Compute HMAC-SHA1
        expected_signature = base64.b64encode(
            hmac.new(auth_token.encode("utf-8"), data.encode("utf-8"), hashlib.sha1).digest()
        ).decode("utf-8")

        if not hmac.compare_digest(signature, expected_signature):
            raise TriggerValidationError("Invalid Twilio signature")


class TwilioSubscriptionConstructor(TriggerSubscriptionConstructor):
    """Manage Twilio trigger subscriptions."""

    _API_BASE = "https://api.twilio.com/2010-04-01"
    _WEBHOOK_TTL = 30 * 24 * 60 * 60  # 30 days

    def _validate_api_key(self, credentials: Mapping[str, Any]) -> None:
        """Validate Twilio Account SID and Auth Token."""
        account_sid = credentials.get("account_sid")
        auth_token = credentials.get("auth_token")

        if not account_sid:
            raise TriggerProviderCredentialValidationError("Twilio Account SID is required.")
        if not auth_token:
            raise TriggerProviderCredentialValidationError("Twilio Auth Token is required.")

        # Validate by fetching account info
        url = f"{self._API_BASE}/Accounts/{account_sid}.json"
        try:
            response = requests.get(url, auth=(account_sid, auth_token), timeout=10)
            if response.status_code != 200:
                error_msg = response.json().get("message", "Invalid credentials")
                raise TriggerProviderCredentialValidationError(error_msg)
        except TriggerProviderCredentialValidationError:
            raise
        except Exception as exc:
            raise TriggerProviderCredentialValidationError(str(exc)) from exc

    def _create_subscription(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:
        """Configure Twilio phone number webhook URLs."""
        account_sid = credentials.get("account_sid")
        auth_token = credentials.get("auth_token")
        phone_number_sid = parameters.get("phone_number")

        if not phone_number_sid:
            raise SubscriptionError("Phone number is required", error_code="MISSING_PHONE_NUMBER")

        # Update the phone number's webhook URLs
        url = f"{self._API_BASE}/Accounts/{account_sid}/IncomingPhoneNumbers/{phone_number_sid}.json"

        # Set both SMS and Voice webhook URLs to our endpoint
        data = {
            "SmsUrl": endpoint,
            "SmsMethod": "POST",
            "VoiceUrl": endpoint,
            "VoiceMethod": "POST",
        }

        try:
            response = requests.post(url, data=data, auth=(account_sid, auth_token), timeout=10)
        except requests.RequestException as exc:
            raise SubscriptionError(
                f"Network error while configuring webhook: {exc}", error_code="NETWORK_ERROR"
            ) from exc

        if response.status_code == 200:
            phone_info = response.json()
            return Subscription(
                expires_at=int(time.time()) + self._WEBHOOK_TTL,
                endpoint=endpoint,
                parameters=parameters,
                properties={
                    "phone_number_sid": phone_number_sid,
                    "phone_number": phone_info.get("phone_number"),
                    "friendly_name": phone_info.get("friendly_name"),
                    "auth_token": auth_token,  # Store for signature validation
                },
            )

        response_data = response.json() if response.content else {}
        error_msg = response_data.get("message", "Unknown error")
        raise SubscriptionError(
            f"Failed to configure Twilio webhook: {error_msg}",
            error_code="WEBHOOK_CONFIGURATION_FAILED",
            external_response=response_data,
        )

    def _delete_subscription(
        self, subscription: Subscription, credentials: Mapping[str, Any], credential_type: CredentialType
    ) -> UnsubscribeResult:
        """Remove webhook configuration from Twilio phone number."""
        account_sid = credentials.get("account_sid")
        auth_token = credentials.get("auth_token")
        phone_number_sid = subscription.properties.get("phone_number_sid")

        if not phone_number_sid:
            raise UnsubscribeError(
                message="Missing phone number SID in subscription",
                error_code="MISSING_PROPERTIES",
                external_response=None,
            )

        # Clear the webhook URLs
        url = f"{self._API_BASE}/Accounts/{account_sid}/IncomingPhoneNumbers/{phone_number_sid}.json"
        data = {
            "SmsUrl": "",
            "VoiceUrl": "",
        }

        try:
            response = requests.post(url, data=data, auth=(account_sid, auth_token), timeout=10)
        except requests.RequestException as exc:
            raise UnsubscribeError(
                message=f"Network error while removing webhook: {exc}",
                error_code="NETWORK_ERROR",
                external_response=None,
            ) from exc

        if response.status_code == 200:
            phone_number = subscription.properties.get("phone_number", phone_number_sid)
            return UnsubscribeResult(success=True, message=f"Successfully removed webhook from {phone_number}")

        response_data = response.json() if response.content else {}
        raise UnsubscribeError(
            message=f"Failed to remove webhook: {response_data.get('message', 'Unknown error')}",
            error_code="WEBHOOK_REMOVAL_FAILED",
            external_response=response_data,
        )

    def _refresh_subscription(
        self, subscription: Subscription, credentials: Mapping[str, Any], credential_type: CredentialType
    ) -> Subscription:
        """Refresh subscription expiration."""
        return Subscription(
            expires_at=int(time.time()) + self._WEBHOOK_TTL,
            endpoint=subscription.endpoint,
            parameters=subscription.parameters,
            properties=subscription.properties,
        )

    def _fetch_parameter_options(
        self, parameter: str, credentials: Mapping[str, Any], credential_type: CredentialType
    ) -> list[ParameterOption]:
        """Fetch available Twilio phone numbers."""
        if parameter != "phone_number":
            return []

        account_sid = credentials.get("account_sid")
        auth_token = credentials.get("auth_token")

        if not account_sid or not auth_token:
            raise ValueError("Account SID and Auth Token are required to fetch phone numbers")

        return self._fetch_phone_numbers(account_sid, auth_token)

    def _fetch_phone_numbers(self, account_sid: str, auth_token: str) -> list[ParameterOption]:
        """Fetch all incoming phone numbers from Twilio account."""
        url = f"{self._API_BASE}/Accounts/{account_sid}/IncomingPhoneNumbers.json"
        options: list[ParameterOption] = []
        page_size = 100

        while url:
            response = requests.get(
                url,
                params={"PageSize": page_size},
                auth=(account_sid, auth_token),
                timeout=10,
            )

            if response.status_code != 200:
                try:
                    err = response.json()
                    message = err.get("message", str(err))
                except Exception:
                    message = response.text
                raise ValueError(f"Failed to fetch phone numbers from Twilio: {message}")

            data = response.json()
            phone_numbers = data.get("incoming_phone_numbers", [])

            for phone in phone_numbers:
                sid = phone.get("sid")
                phone_number = phone.get("phone_number")
                friendly_name = phone.get("friendly_name", phone_number)

                # Build display label
                if friendly_name and friendly_name != phone_number:
                    label = f"{friendly_name} ({phone_number})"
                else:
                    label = phone_number

                if sid and phone_number:
                    options.append(
                        ParameterOption(
                            value=sid,
                            label=I18nObject(
                                en_US=label,
                                zh_Hans=label,
                                ja_JP=label,
                            ),
                        )
                    )

            # Check for next page
            next_page_uri = data.get("next_page_uri")
            if next_page_uri:
                url = f"https://api.twilio.com{next_page_uri}"
            else:
                url = None

        return options
