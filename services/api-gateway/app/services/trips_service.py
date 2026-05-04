"""TripsService for MVP trip management."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, NotFoundError
from app.models.trips import Trip
from app.schemas.trips import TripCreate, TripListResponse, TripResponse


class TripsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_trips(self, user_id: UUID) -> TripListResponse:
        stmt = select(Trip).where(Trip.user_id == user_id).order_by(Trip.start_date.desc())
        result = await self.session.execute(stmt)
        trips = result.scalars().all()
        return TripListResponse(
            trips=[self._to_response(t) for t in trips],
            total=len(trips),
        )

    async def get_trip(self, trip_id: UUID, user_id: UUID) -> TripResponse:
        stmt = select(Trip).where(Trip.id == trip_id, Trip.user_id == user_id)
        result = await self.session.execute(stmt)
        trip = result.scalar_one_or_none()
        if not trip:
            raise NotFoundError(f"Trip {trip_id} not found")
        return self._to_response(trip)

    async def create_trip(self, user_id: UUID, data: TripCreate) -> TripResponse:
        if data.end_date <= data.start_date:
            raise BadRequestError("end_date must be after start_date")
        trip = Trip(
            user_id=user_id,
            destination=data.destination,
            start_date=data.start_date,
            end_date=data.end_date,
            purpose=data.purpose,
            notes=data.notes,
        )
        self.session.add(trip)
        await self.session.commit()
        await self.session.refresh(trip)
        return self._to_response(trip)

    async def update_trip(self, trip_id: UUID, user_id: UUID, data: TripCreate) -> TripResponse:
        if data.end_date <= data.start_date:
            raise BadRequestError("end_date must be after start_date")
        stmt = select(Trip).where(Trip.id == trip_id, Trip.user_id == user_id)
        result = await self.session.execute(stmt)
        trip = result.scalar_one_or_none()
        if not trip:
            raise NotFoundError(f"Trip {trip_id} not found")

        trip.destination = data.destination
        trip.start_date = data.start_date
        trip.end_date = data.end_date
        trip.purpose = data.purpose
        trip.notes = data.notes

        await self.session.commit()
        await self.session.refresh(trip)
        return self._to_response(trip)

    async def delete_trip(self, trip_id: UUID, user_id: UUID) -> None:
        stmt = select(Trip).where(Trip.id == trip_id, Trip.user_id == user_id)
        result = await self.session.execute(stmt)
        trip = result.scalar_one_or_none()
        if not trip:
            raise NotFoundError(f"Trip {trip_id} not found")

        await self.session.delete(trip)
        await self.session.commit()

    def _to_response(self, trip: Trip) -> TripResponse:
        return TripResponse(
            id=trip.id,
            user_id=trip.user_id,
            destination=trip.destination,
            start_date=trip.start_date,
            end_date=trip.end_date,
            purpose=trip.purpose,
            notes=trip.notes,
            created_at=trip.created_at.isoformat(),
            updated_at=trip.updated_at.isoformat(),
        )
