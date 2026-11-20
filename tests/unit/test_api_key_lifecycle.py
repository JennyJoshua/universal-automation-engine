"""Tests for managed API-key issuance, authentication, rotation, and revocation."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from universal_automation.security import (
    APIKeyAuthenticationError,
    APIKeyManager,
    APIKeyRecord,
    InMemoryAPIKeyStore,
)


NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


def issue(manager=None):
    manager = manager or APIKeyManager()
    issued = manager.issue(
        "staff-user-1",
        {"files.read", "reports.create"},
        NOW + timedelta(days=30),
        now=NOW,
    )
    return manager, issued


def test_issue_stores_only_a_digest_and_returns_a_high_entropy_key():
    manager, issued = issue()
    record = manager.store.get(issued.key_id)

    assert issued.api_key.startswith(f"uae_{issued.key_id}.")
    assert len(issued.api_key.split(".", 1)[1]) >= 40
    assert record is not None
    assert record.key_digest not in issued.api_key
    assert issued.api_key not in repr(record)
    assert record.subject_id == "staff-user-1"
    assert record.permissions == {"files.read", "reports.create"}


def test_authentication_returns_a_trusted_principal():
    manager, issued = issue()

    principal = manager.authenticate(issued.api_key, now=NOW)

    assert principal.subject_id == "staff-user-1"
    assert principal.permissions == {"files.read", "reports.create"}


@pytest.mark.parametrize("candidate", [None, "", "malformed", "uae_1234.bad"])
def test_malformed_keys_fail_closed(candidate):
    manager, _ = issue()

    with pytest.raises(APIKeyAuthenticationError):
        manager.authenticate(candidate, now=NOW)


def test_unknown_and_tampered_keys_fail_closed():
    manager, issued = issue()

    with pytest.raises(APIKeyAuthenticationError):
        manager.authenticate("uae_" + "0" * 16 + "." + "x" * 48, now=NOW)
    with pytest.raises(APIKeyAuthenticationError):
        manager.authenticate(issued.api_key + "tampered", now=NOW)


def test_expiry_is_exclusive():
    manager, issued = issue()
    record = manager.store.get(issued.key_id)
    assert record is not None

    with pytest.raises(APIKeyAuthenticationError):
        manager.authenticate(issued.api_key, now=record.expires_at)


def test_revoke_invalidates_key_and_is_idempotently_reported():
    manager, issued = issue()

    assert manager.revoke(issued.key_id, now=NOW) is True
    assert manager.revoke(issued.key_id, now=NOW) is False
    with pytest.raises(APIKeyAuthenticationError):
        manager.authenticate(issued.api_key, now=NOW)


def test_rotation_preserves_identity_and_permissions_but_invalidates_old_key():
    manager, old_key = issue()

    new_key = manager.rotate(
        old_key.key_id,
        NOW + timedelta(days=60),
        now=NOW,
    )

    with pytest.raises(APIKeyAuthenticationError):
        manager.authenticate(old_key.api_key, now=NOW)
    principal = manager.authenticate(new_key.api_key, now=NOW)
    assert principal.subject_id == "staff-user-1"
    assert principal.permissions == {"files.read", "reports.create"}


def test_expired_key_cannot_be_rotated():
    manager, issued = issue()
    record = manager.store.get(issued.key_id)
    assert record is not None

    with pytest.raises(APIKeyAuthenticationError):
        manager.rotate(
            issued.key_id,
            record.expires_at + timedelta(days=1),
            now=record.expires_at,
        )


def test_expiry_must_be_future_and_timezone_aware():
    manager = APIKeyManager()
    with pytest.raises(ValueError, match="future"):
        manager.issue("user", set(), NOW, now=NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        manager.issue("user", set(), datetime(2026, 12, 1))


def test_naive_record_timestamps_are_rejected():
    with pytest.raises(ValidationError, match="timezone-aware"):
        APIKeyRecord(
            key_id="a" * 16,
            key_digest="b" * 64,
            subject_id="user",
            created_at=datetime(2026, 11, 20, 12, 0),
            expires_at=NOW + timedelta(days=1),
        )


def test_store_returns_defensive_record_copies():
    manager, issued = issue()
    first = manager.store.get(issued.key_id)
    second = manager.store.get(issued.key_id)

    assert first is not None and second is not None
    assert first == second
    assert isinstance(manager.store, InMemoryAPIKeyStore)


def test_permissions_are_validated_by_execution_principal():
    manager = APIKeyManager()
    with pytest.raises(ValidationError, match="Invalid permission"):
        manager.issue("user", {"Admin Access"}, NOW + timedelta(days=1), now=NOW)
