# Execution Security Policy

## Purpose

The security package provides transport-independent permission and approval checks for the future execution engine.

## Trusted execution principal

`ExecutionPrincipal` represents an identity that has already been authenticated by a trusted host component. Its permission set must be derived from server-side policy, account records, or another trusted authorization source.

Never construct an execution principal directly from untrusted request fields or accept client-supplied permission claims as authoritative.

## Permission checks

Each registered capability declares the permissions it requires. `AuthorizationPolicy` verifies that the trusted principal has every required permission. Missing permissions raise `InsufficientPermissionsError`.

Permission identifiers use lowercase namespaced identifiers, for example:

- `files.read`
- `files.write`
- `workspace.delete`
- `github.issues.create`

## Request-scoped approval

Capabilities marked `approval_required: true` require an `ApprovalGrant`. Each grant is bound to:

- An approval identifier.
- The authenticated principal.
- One plugin identifier.
- One capability name.
- One execution request identifier.
- A timezone-aware approval time and expiry time.

A grant is accepted only when every binding matches and the current time is within the validity window. Expiry is exclusive: a grant is invalid at or after `expires_at`.

This prevents an approval from being reused for a different user, plugin, capability, or request.

## Example

```python
from universal_automation.security import (
    ApprovalGrant,
    AuthorizationPolicy,
    ExecutionPrincipal,
)

principal = ExecutionPrincipal(
    subject_id="user-123",
    permissions={"files.delete", "workspace.write"},
)

# The approval grant must be produced by a trusted approval workflow.
policy = AuthorizationPolicy()
policy.authorize(
    principal,
    registered_capability,
    request_id="request-456",
    approval=trusted_approval_grant,
)
```

## Security boundary and limitations

- This package does not authenticate users or API keys.
- It does not issue or persist approval grants.
- It does not provide HTTP or MCP middleware.
- It does not execute plugin code.
- The caller must supply trusted principal and approval objects.
- A plugin manifest cannot grant permissions to itself.
- The future execution service must call this policy before invoking any handler.

These primitives are an authorization gate, not a complete application security system.


## Managed API-key lifecycle

The security package now includes APIKeyManager, APIKeyStore, and InMemoryAPIKeyStore. The manager issues high-entropy keys, stores only SHA-256 digests, authenticates keys into trusted ExecutionPrincipal instances, and supports expiry, rotation, and revocation. The in-memory store is a development default; hosts can supply a persistent implementation of the APIKeyStore protocol.

The REST API can use ManagedAPIKeyAuthenticator with APIKeyManager. The older static API-key mapping remains available for compatibility but has no issuance, expiry, rotation, or revocation lifecycle.

## Approval lifecycle status

ApprovalGrant currently binds a principal, plugin, capability, request ID, and validity window. A full reviewer workflow, resource/input-digest binding, and one-time grant consumption are still being implemented in Batch 4. Do not treat the current primitive as a complete approval-management system.
