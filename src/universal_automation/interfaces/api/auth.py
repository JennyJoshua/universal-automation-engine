"""API-key authentication for trusted server-side execution principals."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping

from universal_automation.security.api_keys import APIKeyAuthenticationError, APIKeyManager
from universal_automation.security.policy import ExecutionPrincipal


class AuthenticationError(Exception):
    """Raised when an API key is missing, invalid, or unknown."""


class APIKeyAuthenticator:
    """Authenticate API keys against host-configured trusted principals.

    Only SHA-256 digests are retained in memory. API keys must be at least
    32 characters long and should be loaded from a secure host-side secret store.
    """

    def __init__(self, api_keys: Mapping[str, ExecutionPrincipal]) -> None:
        entries: list[tuple[bytes, ExecutionPrincipal]] = []
        seen_digests: set[bytes] = set()

        for api_key, principal in api_keys.items():
            if not isinstance(api_key, str) or len(api_key) < 32:
                raise ValueError("API keys must be strings of at least 32 characters")
            if not isinstance(principal, ExecutionPrincipal):
                raise TypeError("Each API key must map to a trusted ExecutionPrincipal")

            digest = hashlib.sha256(api_key.encode("utf-8")).digest()
            if digest in seen_digests:
                raise ValueError("Duplicate API key digest")
            seen_digests.add(digest)
            entries.append((digest, principal.model_copy(deep=True)))

        self._entries = tuple(entries)

    def authenticate(self, api_key: str | None) -> ExecutionPrincipal:
        """Return a defensive copy of the principal bound to a valid API key."""
        if not isinstance(api_key, str) or not api_key:
            raise AuthenticationError("Invalid API key")

        candidate = hashlib.sha256(api_key.encode("utf-8")).digest()
        matched_principal: ExecutionPrincipal | None = None

        for expected_digest, principal in self._entries:
            if hmac.compare_digest(expected_digest, candidate):
                matched_principal = principal

        if matched_principal is None:
            raise AuthenticationError("Invalid API key")

        return matched_principal.model_copy(deep=True)


class ManagedAPIKeyAuthenticator:
    """Authenticate keys using the managed lifecycle and its configured store."""

    def __init__(self, manager: APIKeyManager) -> None:
        self._manager = manager

    def authenticate(self, api_key: str | None) -> ExecutionPrincipal:
        """Return the trusted principal for an active, unexpired managed key."""
        try:
            return self._manager.authenticate(api_key)
        except APIKeyAuthenticationError as exc:
            raise AuthenticationError("Invalid API key") from exc
