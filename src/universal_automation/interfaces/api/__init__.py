"""REST API integration for Universal Automation Engine."""

from universal_automation.interfaces.api.app import create_app
from universal_automation.interfaces.api.auth import (
    APIKeyAuthenticator,
    AuthenticationError,
    ManagedAPIKeyAuthenticator,
)

__all__ = [
    "APIKeyAuthenticator",
    "AuthenticationError",
    "ManagedAPIKeyAuthenticator",
    "create_app",
]
