from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from services.dependencies.db import DBInvoker, getDbInvoker
from services.models.models import RoomBooking, Rooms


router = APIRouter(prefix="/bookings", tags=["bookings"])


class BookingCreate(BaseModel):
    event_name: str
    club_name: str
    requested_by_user_id: Optional[int] = None
    room_id: Optional[int] = None
    room_name: Optional[str] = None
    event_date: date
    start_time: str
    end_time: str


class BookingStatusUpdate(BaseModel):
    status: str
    admin_note: Optional[str] = None


def serialize_booking(booking: RoomBooking):
    return {
        "id": booking.id,
        "event_name": booking.event_name,
        "club_name": booking.club_name,
        "requested_by_user_id": booking.requested_by_user_id,
        "room_id": booking.room_id,
        "room_name": booking.room_name,
        "event_date": booking.event_date.isoformat(),
        "start_time": booking.start_time,
        "end_time": booking.end_time,
        "status": booking.status,
        "admin_note": booking.admin_note,
        "created_at": booking.created_at.isoformat() if booking.created_at else None,
        "updated_at": booking.updated_at.isoformat() if booking.updated_at else None,
    }


@router.post("")
async def create_booking(
    payload: BookingCreate,
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    db = db_invoker.db

    room = None
    if payload.room_id:
        room = db.query(Rooms).filter(Rooms.id == payload.room_id).first()
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")

    room_name = room.name if room else (payload.room_name or "").strip()
    if not room_name:
        raise HTTPException(status_code=400, detail="Choose a room before requesting a booking")

    booking = RoomBooking(
        event_name=payload.event_name.strip(),
        club_name=payload.club_name.strip(),
        requested_by_user_id=payload.requested_by_user_id,
        room_id=payload.room_id,
        room_name=room_name,
        event_date=payload.event_date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        status="pending",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    db.add(booking)
    db.commit()
    db.refresh(booking)

    return {"message": "Room booking request sent to admin", "booking": serialize_booking(booking)}


@router.get("")
async def list_bookings(
    status: Optional[str] = Query(default=None),
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    db = db_invoker.db
    query = db.query(RoomBooking)
    if status:
        query = query.filter(RoomBooking.status == status.lower())

    bookings = query.order_by(RoomBooking.event_date, RoomBooking.start_time, RoomBooking.created_at).all()
    return {"bookings": [serialize_booking(booking) for booking in bookings]}


@router.get("/calendar")
async def approved_calendar(
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    db = db_invoker.db
    bookings = (
        db.query(RoomBooking)
        .filter(RoomBooking.status == "approved")
        .order_by(RoomBooking.event_date, RoomBooking.start_time)
        .all()
    )
    return {"events": [serialize_booking(booking) for booking in bookings]}


@router.patch("/{booking_id}/status")
async def update_booking_status(
    booking_id: int,
    payload: BookingStatusUpdate,
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    db = db_invoker.db
    status = payload.status.strip().lower()
    if status not in {"approved", "rejected", "pending"}:
        raise HTTPException(status_code=400, detail="Status must be pending, approved, or rejected")

    booking = db.query(RoomBooking).filter(RoomBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    booking.status = status
    booking.admin_note = payload.admin_note
    booking.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(booking)

    return {"message": f"Booking {status}", "booking": serialize_booking(booking)}
