"""Managed API-key lifecycle with hashed storage and trusted principals."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from universal_automation.security.policy import ExecutionPrincipal

_KEY_ID_PATTERN = re.compile(r"^[0-9a-f]{16}$")
_KEY_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class APIKeyError(RuntimeError):
    """Base exception for managed API-key lifecycle operations."""


class APIKeyAuthenticationError(APIKeyError):
    """Raised when a managed API key is missing, invalid, expired, or revoked."""


class APIKeyAlreadyExistsError(APIKeyError):
    """Raised when a generated key identifier collides with an existing record."""


class APIKeyModel(BaseModel):
    """Immutable managed API-key record."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class APIKeyRecord(APIKeyModel):
    """Stored key metadata; the raw secret is never retained."""

    key_id: str = Field(min_length=16, max_length=16)
    key_digest: str = Field(min_length=64, max_length=64, repr=False)
    subject_id: str = Field(min_length=1, max_length=200)
    permissions: frozenset[str] = Field(default_factory=frozenset)
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    @field_validator("key_id")
    @classmethod
    def validate_key_id(cls, value: str) -> str:
        if not _KEY_ID_PATTERN.fullmatch(value):
            raise ValueError("Invalid API key identifier")
        return value

    @field_validator("key_digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if not _KEY_DIGEST_PATTERN.fullmatch(value):
            raise ValueError("API key digest must be a SHA-256 hexadecimal digest")
        return value

    @field_validator("created_at", "expires_at", "revoked_at")
    @classmethod
    def require_aware_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("API key timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_lifecycle_timestamps(self) -> APIKeyRecord:
        if self.expires_at <= self.created_at:
            raise ValueError("API key expiry must be later than creation")
        if self.revoked_at is not None and self.revoked_at < self.created_at:
            raise ValueError("API key revocation cannot precede creation")
        return self


class IssuedAPIKey(APIKeyModel):
    """A newly issued raw API key, returned to the caller exactly once."""

    key_id: str
    api_key: str = Field(repr=False)
    created_at: datetime
    expires_at: datetime


class APIKeyStore(Protocol):
    """Storage seam for persistent host-provided API-key stores."""

    def get(self, key_id: str) -> APIKeyRecord | None:
        """Return a defensive copy of a key record, if present."""

    def create(self, record: APIKeyRecord) -> None:
        """Create a new record; reject an existing key identifier."""

    def revoke(self, key_id: str, revoked_at: datetime) -> bool:
        """Atomically revoke an active key and report whether it changed."""


class InMemoryAPIKeyStore:
    """Thread-safe in-memory store for development, tests, and small deployments."""

    def __init__(self) -> None:
        self._records: dict[str, APIKeyRecord] = {}
        self._lock = RLock()

    def get(self, key_id: str) -> APIKeyRecord | None:
        with self._lock:
            record = self._records.get(key_id)
            return record.model_copy(deep=True) if record is not None else None

    def create(self, record: APIKeyRecord) -> None:
        if not isinstance(record, APIKeyRecord):
            raise TypeError("record must be an APIKeyRecord")
        with self._lock:
            if record.key_id in self._records:
                raise APIKeyAlreadyExistsError("API key identifier already exists")
            self._records[record.key_id] = record.model_copy(deep=True)

    def revoke(self, key_id: str, revoked_at: datetime) -> bool:
        if revoked_at.tzinfo is None or revoked_at.utcoffset() is None:
            raise ValueError("API key revocation time must be timezone-aware")
        with self._lock:
            record = self._records.get(key_id)
            if record is None or record.revoked_at is not None:
                return False
            self._records[key_id] = record.model_copy(
                update={"revoked_at": revoked_at},
                deep=True,
            )
            return True


class APIKeyManager:
    """Issue, authenticate, rotate, and revoke API keys for trusted principals.

    Key format is uae_<16-hex-character-id>.<random-secret>. Only a SHA-256
    digest of the high-entropy secret is stored. The raw key is returned only
    by issue/rotate and must be delivered through a trusted host channel.
    """

    def __init__(self, store: APIKeyStore | None = None) -> None:
        self._store = store if store is not None else InMemoryAPIKeyStore()

    @property
    def store(self) -> APIKeyStore:
        """Return the configured store for host integration and inspection."""
        return self._store

    def issue(
        self,
        subject_id: str,
        permissions: frozenset[str] | set[str],
        expires_at: datetime,
        *,
        now: datetime | None = None,
    ) -> IssuedAPIKey:
        """Create a new high-entropy key for a host-trusted identity and scopes."""
        current = self._current_time(now)
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise ValueError("API key expiry must be timezone-aware")
        if expires_at <= current:
            raise ValueError("API key expiry must be in the future")

        principal = ExecutionPrincipal(
            subject_id=subject_id,
            permissions=frozenset(permissions),
        )
        for _ in range(5):
            key_id = secrets.token_hex(8)
            secret = secrets.token_urlsafe(32)
            raw_key = f"uae_{key_id}.{secret}"
            digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
            record = APIKeyRecord(
                key_id=key_id,
                key_digest=digest,
                subject_id=principal.subject_id,
                permissions=principal.permissions,
                created_at=current,
                expires_at=expires_at,
            )
            try:
                self._store.create(record)
            except APIKeyAlreadyExistsError:
                continue
            return IssuedAPIKey(
                key_id=key_id,
                api_key=raw_key,
                created_at=current,
                expires_at=expires_at,
            )
        raise APIKeyError("Unable to allocate a unique API key identifier")

    def authenticate(
        self,
        api_key: str | None,
        *,
        now: datetime | None = None,
    ) -> ExecutionPrincipal:
        """Validate a raw key and return a server-created execution principal."""
        current = self._current_time(now)
        if not isinstance(api_key, str) or len(api_key) > 128:
            raise APIKeyAuthenticationError("Invalid API key")
        try:
            prefix, secret = api_key.split(".", 1)
            if not prefix.startswith("uae_"):
                raise ValueError
            key_id = prefix[4:]
            if not _KEY_ID_PATTERN.fullmatch(key_id) or len(secret) < 40:
                raise ValueError
        except ValueError as exc:
            raise APIKeyAuthenticationError("Invalid API key") from exc

        record = self._store.get(key_id)
        if record is None:
            raise APIKeyAuthenticationError("Invalid API key")
        candidate = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(record.key_digest, candidate):
            raise APIKeyAuthenticationError("Invalid API key")
        if record.revoked_at is not None or current >= record.expires_at:
            raise APIKeyAuthenticationError("Invalid API key")

        return ExecutionPrincipal(
            subject_id=record.subject_id,
            permissions=record.permissions,
        )

    def rotate(
        self,
        key_id: str,
        expires_at: datetime,
        *,
        now: datetime | None = None,
    ) -> IssuedAPIKey:
        """Issue a replacement key and revoke the previous key."""
        current = self._current_time(now)
        old_record = self._store.get(key_id)
        if (
            old_record is None
            or old_record.revoked_at is not None
            or current >= old_record.expires_at
        ):
            raise APIKeyAuthenticationError("API key cannot be rotated")

        replacement = self.issue(
            old_record.subject_id,
            old_record.permissions,
            expires_at,
            now=current,
        )
        if not self._store.revoke(key_id, current):
            self._store.revoke(replacement.key_id, current)
            raise APIKeyAuthenticationError("API key cannot be rotated")
        return replacement

    def revoke(self, key_id: str, *, now: datetime | None = None) -> bool:
        """Revoke an active key immediately."""
        return self._store.revoke(key_id, self._current_time(now))

    @staticmethod
    def _current_time(now: datetime | None) -> datetime:
        current = now or datetime.now(UTC)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("Current time must be timezone-aware")
        return current
