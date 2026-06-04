"""User type stand-in for closet-service.

closet-service does NOT own the users table (it lives in api-gateway). A few
styling modules type-annotate against ``User`` and read its legacy profile
fields; this re-exports the lightweight ``RemoteUser`` (fetched via the internal
API seam) under that name. It is intentionally NOT a SQLAlchemy model and is NOT
imported by ``app.models.__init__``, so no ``users`` table is created here.
"""

from __future__ import annotations

from app.repositories.user_repo import RemoteUser as User

__all__ = ["User"]
