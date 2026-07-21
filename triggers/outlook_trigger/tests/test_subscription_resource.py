from urllib.parse import quote

import pytest

import provider.outlook as outlook_module
from provider.outlook import OutlookSubscriptionConstructor


@pytest.fixture
def constructor() -> OutlookSubscriptionConstructor:
    return OutlookSubscriptionConstructor(None)


def test_resource_defaults_to_personal_inbox(constructor) -> None:
    """Empty parameters falls back to the historical personal-mailbox path."""
    assert (
        constructor._subscription_resource({})
        == "me/mailfolders('Inbox')/messages"
    )


@pytest.mark.parametrize(
    "value",
    ["", "   ", "\n\n", None],
    ids=["empty", "whitespace", "newlines", "none"],
)
def test_resource_ignores_blank_mailbox_address(constructor, value) -> None:
    """Blank or whitespace-only mailbox_address falls back to personal Inbox."""
    assert (
        constructor._subscription_resource({"mailbox_address": value})
        == "me/mailfolders('Inbox')/messages"
    )


def test_resource_uses_shared_mailbox_upn(constructor) -> None:
    """A non-blank UPN routes through the users/{mailbox} form for shared mailboxes."""
    params = {"mailbox_address": "support@company.com"}
    expected = f"users/{quote('support@company.com', safe='')}/mailfolders('Inbox')/messages"
    assert constructor._subscription_resource(params) == expected


def test_resource_preserves_unusual_characters_in_upn(constructor) -> None:
    """Slash and special chars are percent-encoded for graph resource paths."""
    params = {"mailbox_address": "a/b@c.com"}
    assert (
        constructor._subscription_resource(params)
        == f"users/{quote('a/b@c.com', safe='')}/mailfolders('Inbox')/messages"
    )


def test_resource_accepts_guid_mailbox_identifier(constructor) -> None:
    """Mailbox identifiers are not limited to UPNs; raw GUIDs work the same way."""
    params = {"mailbox_address": "00000000-0000-0000-0000-000000000000"}
    expected = f"users/{quote('00000000-0000-0000-0000-000000000000', safe='')}/mailfolders('Inbox')/messages"
    assert constructor._subscription_resource(params) == expected


def test_resource_handles_unicode_mailbox(constructor) -> None:
    """International mailbox UPNs are percent-encoded safely."""
    params = {"mailbox_address": "Søren@eksempel.dk"}
    expected = f"users/{quote('Søren@eksempel.dk', safe='')}/mailfolders('Inbox')/messages"
    assert constructor._subscription_resource(params) == expected


def test_resource_strips_surrounding_whitespace(constructor) -> None:
    """Leading/trailing whitespace is stripped before the resource path is built."""
    params = {"mailbox_address": "  support@company.com  "}
    expected = f"users/{quote('support@company.com', safe='')}/mailfolders('Inbox')/messages"
    assert constructor._subscription_resource(params) == expected
