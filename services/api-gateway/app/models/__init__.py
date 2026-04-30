# Import all ORM models here so SQLAlchemy's mapper registry can resolve all
# string-based relationship references (e.g. "ClosetItem" in User.closet_items).
# This file MUST be imported before any query is executed.
from app.models.closet import ClosetItem, Outfit  # noqa: F401
from app.models.social import Follow, Group, GroupMember  # noqa: F401
from app.models.user import RefreshToken, User, UserCredential  # noqa: F401
