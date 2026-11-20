"""Security primitives for authorization and approval."""

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
    "ApprovalGrant",
    "ApprovalRequiredError",
    "AuthorizationError",
    "AuthorizationPolicy",
    "ExecutionPrincipal",
    "InsufficientPermissionsError",
    "InvalidApprovalError",
]
