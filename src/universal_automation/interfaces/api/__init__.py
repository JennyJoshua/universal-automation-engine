"""REST API integration for Universal Automation Engine."""

from universal_automation.interfaces.api.app import create_app
from universal_automation.interfaces.api.auth import APIKeyAuthenticator, AuthenticationError

__all__ = ["APIKeyAuthenticator", "AuthenticationError", "create_app"]
