"""User, UserCredential, and RefreshToken repositories."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, select

from app.models.user import RefreshToken, User, UserCredential
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.username == username.lower())
        )
        return result.scalar_one_or_none()

    async def get_by_google_id(self, google_id: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.google_id == google_id)
        )
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        return await self.exists(User.email == email.lower())

    async def username_exists(self, username: str) -> bool:
        return await self.exists(User.username == username.lower())

    async def search(self, query: str, exclude_id: UUID, limit: int = 30) -> list[User]:
        pattern = f"%{query}%"
        result = await self.session.execute(
            select(User)
            .where(
                and_(
                    User.id != exclude_id,
                    User.is_active == True,
                    (User.name.ilike(pattern) | User.username.ilike(pattern)),
                )
            )
            .limit(limit)
        )
        return list(result.scalars().all())


class CredentialRepository(BaseRepository[UserCredential]):
    model = UserCredential

    async def get_by_user_id(self, user_id: UUID) -> UserCredential | None:
        result = await self.session.execute(
            select(UserCredential).where(UserCredential.user_id == user_id)
        )
        return result.scalar_one_or_none()


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    model = RefreshToken

    async def get_valid(self, token_hash: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshToken).where(
                and_(
                    RefreshToken.token_hash == token_hash,
                    RefreshToken.revoked == False,
                    RefreshToken.expires_at > datetime.now(UTC),
                )
            )
        )
        return result.scalar_one_or_none()

    async def revoke_all_for_user(self, user_id: UUID) -> None:
        from sqlalchemy import update
        await self.session.execute(
            update(RefreshToken)
            .where(
                and_(RefreshToken.user_id == user_id, RefreshToken.revoked == False)
            )
            .values(revoked=True)
        )
