"""Security primitives for authorization, approvals, and API-key lifecycle."""

from universal_automation.security.api_keys import (
    APIKeyAlreadyExistsError,
    APIKeyAuthenticationError,
    APIKeyError,
    APIKeyManager,
    APIKeyRecord,
    APIKeyStore,
    InMemoryAPIKeyStore,
    IssuedAPIKey,
)
from universal_automation.security.policy import (
    ApprovalGrant,
    ApprovalRequiredError,
    AuthorizationError,
    AuthorizationPolicy,
    ExecutionPrincipal,
    InsufficientPermissionsError,
    InvalidApprovalError,
)

__all__ = [
    "APIKeyAlreadyExistsError",
    "APIKeyAuthenticationError",
    "APIKeyError",
    "APIKeyManager",
    "APIKeyRecord",
    "APIKeyStore",
    "ApprovalGrant",
    "ApprovalRequiredError",
    "AuthorizationError",
    "AuthorizationPolicy",
    "ExecutionPrincipal",
    "InMemoryAPIKeyStore",
    "InsufficientPermissionsError",
    "InvalidApprovalError",
    "IssuedAPIKey",
]
