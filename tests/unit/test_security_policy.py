"""Tests for trusted execution permissions and approval policies."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from universal_automation.core.contracts import CapabilitySpec, PluginManifest
from universal_automation.core.registry import PluginRegistry
from universal_automation.security import (
    ApprovalGrant,
    ApprovalRequiredError,
    AuthorizationPolicy,
    ExecutionPrincipal,
    InsufficientPermissionsError,
    InvalidApprovalError,
)


def make_registered_capability(*, approval_required: bool = False):
    manifest = PluginManifest(
        plugin_id="example.file-tools",
        display_name="Example File Tools",
        version="1.0.0",
        description="File operations for policy tests.",
        capabilities=(
            CapabilitySpec(
                name="delete_files",
                description="Delete files in an approved workspace.",
                input_schema={"type": "object", "properties": {}},
                output_schema={"type": "object", "properties": {}},
                permissions=("files.delete", "workspace.write"),
                destructive=approval_required,
                approval_required=approval_required,
            ),
        ),
    )
    registry = PluginRegistry()
    registry.register(manifest)
    return registry.get_capability("example.file-tools", "delete_files")


def make_approval(
    *,
    subject_id: str = "user-123",
    plugin_id: str = "example.file-tools",
    capability_name: str = "delete_files",
    request_id: str = "request-456",
    approved_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> ApprovalGrant:
    current = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
    return ApprovalGrant(
        approval_id="approval-789",
        subject_id=subject_id,
        plugin_id=plugin_id,
        capability_name=capability_name,
        request_id=request_id,
        approved_at=approved_at or current - timedelta(minutes=1),
        expires_at=expires_at or current + timedelta(minutes=5),
    )


def test_all_required_permissions_allow_authorization() -> None:
    capability = make_registered_capability()
    principal = ExecutionPrincipal(
        subject_id="user-123",
        permissions=frozenset({"files.delete", "workspace.write"}),
    )

    AuthorizationPolicy().authorize(principal, capability, "request-456")


def test_missing_permissions_are_rejected() -> None:
    capability = make_registered_capability()
    principal = ExecutionPrincipal(subject_id="user-123", permissions={"files.delete"})

    with pytest.raises(InsufficientPermissionsError) as error:
        AuthorizationPolicy().authorize(principal, capability, "request-456")

    assert error.value.missing_permissions == ("workspace.write",)


def test_permission_free_capability_needs_no_grants() -> None:
    manifest = PluginManifest(
        plugin_id="example.pure",
        display_name="Pure Function",
        version="1.0.0",
        description="A capability without external side effects.",
        capabilities=(
            CapabilitySpec(
                name="calculate",
                description="Calculate a deterministic result.",
                input_schema={"type": "object", "properties": {}},
                output_schema={"type": "object", "properties": {}},
            ),
        ),
    )
    registry = PluginRegistry()
    registry.register(manifest)
    capability = registry.get_capability("example.pure", "calculate")

    AuthorizationPolicy().authorize(
        ExecutionPrincipal(subject_id="user-123"),
        capability,
        "request-456",
    )


def test_approval_required_capability_rejects_missing_approval() -> None:
    capability = make_registered_capability(approval_required=True)
    principal = ExecutionPrincipal(
        subject_id="user-123",
        permissions={"files.delete", "workspace.write"},
    )

    with pytest.raises(ApprovalRequiredError):
        AuthorizationPolicy().authorize(principal, capability, "request-456")


def test_matching_unexpired_approval_allows_authorization() -> None:
    capability = make_registered_capability(approval_required=True)
    principal = ExecutionPrincipal(
        subject_id="user-123",
        permissions={"files.delete", "workspace.write"},
    )
    now = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)

    AuthorizationPolicy().authorize(
        principal,
        capability,
        "request-456",
        make_approval(),
        now=now,
    )


@pytest.mark.parametrize(
    "approval",
    [
        make_approval(subject_id="another-user"),
        make_approval(plugin_id="example.other-tools"),
        make_approval(capability_name="read_files"),
        make_approval(request_id="another-request"),
        make_approval(
            expires_at=datetime(2026, 11, 20, 11, 59, 30, tzinfo=timezone.utc)
        ),
        make_approval(approved_at=datetime(2026, 11, 20, 12, 1, tzinfo=timezone.utc)),
    ],
)
def test_mismatched_or_inactive_approval_is_rejected(approval: ApprovalGrant) -> None:
    capability = make_registered_capability(approval_required=True)
    principal = ExecutionPrincipal(
        subject_id="user-123",
        permissions={"files.delete", "workspace.write"},
    )
    now = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(InvalidApprovalError):
        AuthorizationPolicy().authorize(
            principal,
            capability,
            "request-456",
            approval,
            now=now,
        )


def test_approval_expiry_is_exclusive() -> None:
    capability = make_registered_capability(approval_required=True)
    principal = ExecutionPrincipal(
        subject_id="user-123",
        permissions={"files.delete", "workspace.write"},
    )
    approval = make_approval()
    now = approval.expires_at

    with pytest.raises(InvalidApprovalError):
        AuthorizationPolicy().authorize(
            principal,
            capability,
            "request-456",
            approval,
            now=now,
        )


def test_naive_approval_timestamps_are_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        make_approval(approved_at=datetime(2026, 11, 20, 11, 59))


def test_approval_expiry_must_follow_approval_time() -> None:
    approved_at = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValidationError, match="later than"):
        make_approval(approved_at=approved_at, expires_at=approved_at)


def test_principal_rejects_invalid_permission_identifiers() -> None:
    with pytest.raises(ValidationError, match="Invalid permission"):
        ExecutionPrincipal(subject_id="user-123", permissions={"Files Delete"})


def test_authorization_rejects_naive_current_time() -> None:
    capability = make_registered_capability(approval_required=True)
    principal = ExecutionPrincipal(
        subject_id="user-123",
        permissions={"files.delete", "workspace.write"},
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        AuthorizationPolicy().authorize(
            principal,
            capability,
            "request-456",
            make_approval(),
            now=datetime(2026, 11, 20, 12, 0),
        )
