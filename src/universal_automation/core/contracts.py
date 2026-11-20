"""Typed, transport-independent contracts for automation plugins."""

from __future__ import annotations

import re
from typing import Any, Literal

from jsonschema.validators import validator_for
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_CONTRACT_VERSION = "1.0"
_SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
_PLUGIN_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_CAPABILITY_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_PERMISSION_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[._:-][a-z0-9]+)*$")


class ContractModel(BaseModel):
    """Base model that rejects undeclared fields and field reassignment."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


def _validate_object_schema(schema: dict[str, Any], *, field_name: str) -> None:
    """Validate a JSON Schema document and require an object at its root."""
    if not isinstance(schema, dict):
        raise ValueError(f"{field_name} must be a JSON Schema object")

    if schema.get("type") != "object":
        raise ValueError(f"{field_name} must declare type='object' at its root")

    try:
        validator = validator_for(schema)
        validator.check_schema(schema)
    except Exception as exc:
        raise ValueError(f"{field_name} is not a valid JSON Schema: {exc}") from exc


class CapabilitySpec(ContractModel):
    """A single callable capability exposed by an automation plugin."""

    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=500)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    permissions: tuple[str, ...] = ()
    destructive: bool = False
    approval_required: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not _CAPABILITY_NAME_PATTERN.fullmatch(value):
            raise ValueError(
                "Capability names must start with a lowercase letter and contain "
                "only lowercase letters, digits, or underscores"
            )
        return value

    @field_validator("input_schema", "output_schema")
    @classmethod
    def validate_schema(cls, value: dict[str, Any], info: Any) -> dict[str, Any]:
        _validate_object_schema(value, field_name=info.field_name)
        return value

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for permission in values:
            if not _PERMISSION_PATTERN.fullmatch(permission):
                raise ValueError(f"Invalid permission identifier: {permission}")
        if len(values) != len(set(values)):
            raise ValueError("Permission identifiers must be unique")
        return values

    @model_validator(mode="after")
    def require_approval_for_destructive_actions(self) -> CapabilitySpec:
        if self.destructive and not self.approval_required:
            raise ValueError("Destructive capabilities must require explicit approval")
        return self


class PluginManifest(ContractModel):
    """Versioned metadata and capabilities declared by an automation plugin."""

    plugin_id: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=120)
    version: str
    contract_version: Literal["1.0"] = _CONTRACT_VERSION
    description: str = Field(min_length=1, max_length=1000)
    capabilities: tuple[CapabilitySpec, ...] = Field(min_length=1)

    @field_validator("plugin_id")
    @classmethod
    def validate_plugin_id(cls, value: str) -> str:
        if not _PLUGIN_ID_PATTERN.fullmatch(value):
            raise ValueError(
                "Plugin IDs must be lowercase and use letters, digits, dots, "
                "underscores, or hyphens"
            )
        return value

    @field_validator("version")
    @classmethod
    def validate_semantic_version(cls, value: str) -> str:
        if not _SEMVER_PATTERN.fullmatch(value):
            raise ValueError("Plugin version must follow semantic versioning (MAJOR.MINOR.PATCH)")
        return value

    @model_validator(mode="after")
    def require_unique_capabilities(self) -> PluginManifest:
        names = [capability.name for capability in self.capabilities]
        if len(names) != len(set(names)):
            raise ValueError("Capability names must be unique within a plugin")
        return self
