"""Backend authorization contract. No authentication provider ships in Phase 1."""

from typing import Protocol


class AccessDenied(PermissionError):
    """Private data requires a trusted application-issued session."""


class CustomerAuthorizer(Protocol):
    """Implemented and injected by a trusted backend, never selected by a tool call.

    Context is opaque. A provider must verify its authenticity before resolving a
    customer ID; reading a user-supplied dictionary or attribute is insufficient.
    """

    def require_customer_id(self, context: object | None) -> int:
        """Resolve a verified identity, or raise AccessDenied."""
        ...


class DenyAllAuthorizer:
    """The production default until a real verification flow exists."""

    def require_customer_id(self, context: object | None) -> int:
        raise AccessDenied("private access is unavailable without verified authentication")
