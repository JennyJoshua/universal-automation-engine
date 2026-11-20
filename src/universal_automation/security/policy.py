"""Permission and request-scoped approval policy primitives."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from universal_automation.core.registry import RegisteredCapability

_PERMISSION_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+)*$")
_PLUGIN_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_CAPABILITY_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class SecurityModel(BaseModel):
    """Base class for immutable security context and approval records."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ExecutionPrincipal(SecurityModel):
    """Trusted server-side identity and permissions for one execution request."""

    subject_id: str = Field(min_length=1, max_length=200)
    permissions: frozenset[str] = Field(default_factory=frozenset)

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, values: frozenset[str]) -> frozenset[str]:
        invalid = sorted(
            permission
            for permission in values
            if not _PERMISSION_PATTERN.fullmatch(permission)
        )
        if invalid:
            raise ValueError(f"Invalid permission identifiers: {', '.join(invalid)}")
        return values


class ApprovalGrant(SecurityModel):
    """An expiring approval tied to one principal, capability, and request."""

    approval_id: str = Field(min_length=1, max_length=200)
    subject_id: str = Field(min_length=1, max_length=200)
    plugin_id: str = Field(min_length=1, max_length=100)
    capability_name: str = Field(min_length=1, max_length=64)
    request_id: str = Field(min_length=1, max_length=200)
    approved_at: datetime
    expires_at: datetime

    @field_validator("plugin_id")
    @classmethod
    def validate_plugin_id(cls, value: str) -> str:
        if not _PLUGIN_ID_PATTERN.fullmatch(value):
            raise ValueError("Invalid plugin identifier")
        return value

    @field_validator("capability_name")
    @classmethod
    def validate_capability_name(cls, value: str) -> str:
        if not _CAPABILITY_NAME_PATTERN.fullmatch(value):
            raise ValueError("Invalid capability identifier")
        return value

    @field_validator("approved_at", "expires_at")
    @classmethod
    def require_timezone_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Approval timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def require_positive_validity_window(self) -> ApprovalGrant:
        if self.expires_at <= self.approved_at:
            raise ValueError("Approval expiry must be later than its approval time")
        return self


class AuthorizationError(PermissionError):
    """Base exception raised when an execution request is not authorized."""


class InsufficientPermissionsError(AuthorizationError):
    """Raised when the principal lacks one or more required permissions."""

    def __init__(self, missing_permissions: tuple[str, ...]) -> None:
        self.missing_permissions = missing_permissions
        super().__init__(
            "Missing required permissions: " + ", ".join(missing_permissions)
        )


class ApprovalRequiredError(AuthorizationError):
    """Raised when a capability requires approval but none was supplied."""


class InvalidApprovalError(AuthorizationError):
    """Raised when an approval does not match or is not currently valid."""


class AuthorizationPolicy:
    """Enforce declared permissions and request-bound approval requirements.

    The principal and approval grant must be created by trusted server-side
    authentication/approval components. Never build them directly from client
    claims or accept a client-supplied boolean as proof of approval.
    """

    def authorize(
        self,
        principal: ExecutionPrincipal,
        registered_capability: RegisteredCapability,
        request_id: str,
        approval: ApprovalGrant | None = None,
        *,
        now: datetime | None = None,
    ) -> None:
        """Raise a typed authorization error unless the request is permitted."""
        if not isinstance(principal, ExecutionPrincipal):
            raise TypeError("principal must be a trusted ExecutionPrincipal")
        if not isinstance(registered_capability, RegisteredCapability):
            raise TypeError("registered_capability must come from the plugin registry")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must be a non-empty string")

        required = set(registered_capability.capability.permissions)
        missing = tuple(sorted(required - principal.permissions))
        if missing:
            raise InsufficientPermissionsError(missing)

        if not registered_capability.capability.approval_required:
            return

        if approval is None:
            raise ApprovalRequiredError("This capability requires explicit approval")

        if not isinstance(approval, ApprovalGrant):
            raise TypeError("approval must be a trusted ApprovalGrant")

        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None or current_time.utcoffset() is None:
            raise ValueError("Authorization time must be timezone-aware")

        matches_request = (
            approval.subject_id == principal.subject_id
            and approval.plugin_id == registered_capability.plugin_id
            and approval.capability_name == registered_capability.capability.name
            and approval.request_id == request_id
        )
        is_current = approval.approved_at <= current_time < approval.expires_at

        if not matches_request or not is_current:
            raise InvalidApprovalError(
                "Approval is invalid, expired, not yet active, or bound to another request"
            )
