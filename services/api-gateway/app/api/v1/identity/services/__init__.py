"""Public interface for identity services.

Import auth helpers from this package (e.g. ``from app.api.v1.identity.services
import AuthService``) — direct imports of ``auth_service`` are banned by lint
(TID251) to keep a single public surface.
"""

from app.api.v1.identity.services.auth_service import AuthService  # noqa: TID251

__all__ = ["AuthService"]
