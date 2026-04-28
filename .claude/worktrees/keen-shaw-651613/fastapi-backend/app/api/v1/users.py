"""
User profile endpoints.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Query

from app.core.deps import DB, CurrentUser, OptionalUserID
from app.schemas.social import UserSearchItem
from app.schemas.user import UserProfileResponse
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/search", response_model=List[UserSearchItem])
async def search_users(
    q: str = Query(..., min_length=1, max_length=100, description="Name or username query"),
    db: DB = ...,
    viewer_id: OptionalUserID = None,
) -> List[UserSearchItem]:
    """Search users by name or username."""
    return await UserService.search_users(db, q, viewer_id=viewer_id)


@router.get("/{username}", response_model=UserProfileResponse)
async def get_user_profile(
    username: str,
    db: DB,
    viewer_id: OptionalUserID = None,
) -> UserProfileResponse:
    """Get a user's public profile by username."""
    user = await UserService.get_by_username(db, username)
    if user is None:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return await UserService.get_profile(db, user.id, viewer_id=viewer_id)
