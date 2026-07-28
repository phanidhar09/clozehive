# Import all ORM models here so SQLAlchemy's mapper registry can resolve all
# string-based relationship references (e.g. "ClosetItem" in User.closet_items).
# This file MUST be imported before any query is executed.
from app.models.ai_chat import (  # noqa: F401
    AIChatMessage,
    AIChatSession,
    DailyNudge,
    OutfitFeedback,
)
from app.models.closet import ClosetItem, Outfit, PlannedOutfit, WearEvent  # noqa: F401
from app.models.learning import ItemPairScore  # noqa: F401
from app.models.packing import PackingPlan  # noqa: F401
from app.models.purge_outbox import PurgeOutbox  # noqa: F401
from app.models.rag import FashionKnowledgeDocument, OutfitHistory, PackingMemory, PurchaseGap  # noqa: F401
from app.models.social import Follow, Group, GroupMember  # noqa: F401
from app.models.trips import Trip  # noqa: F401
from app.models.user import RefreshToken, User, UserCredential  # noqa: F401
from app.models.user_style_profile import UserStyleProfile  # noqa: F401
