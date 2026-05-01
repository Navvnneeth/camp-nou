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
    requester_role: Optional[str] = "club"


class BookingStatusUpdate(BaseModel):
    status: str
    admin_note: Optional[str] = None


class BookingRoomUpdate(BaseModel):
    room_id: int
    event_date: Optional[date] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None


def times_overlap(start_a: str, end_a: str, start_b: str, end_b: str):
    return start_a < end_b and start_b < end_a


def is_faculty_booking(booking: RoomBooking):
    return booking.club_name.lower().startswith("faculty:")


def get_room_conflicts(db, booking: RoomBooking):
    if not booking.room_id:
        return []

    same_room_bookings = (
        db.query(RoomBooking)
        .filter(RoomBooking.id != booking.id)
        .filter(RoomBooking.room_id == booking.room_id)
        .filter(RoomBooking.event_date == booking.event_date)
        .filter(RoomBooking.status.in_(["approved", "pending", "appealed"]))
        .all()
    )

    return [
        item
        for item in same_room_bookings
        if times_overlap(booking.start_time, booking.end_time, item.start_time, item.end_time)
    ]


def serialize_booking(booking: RoomBooking):
    requester_role = "faculty" if is_faculty_booking(booking) else "club"
    return {
        "id": booking.id,
        "event_name": booking.event_name,
        "club_name": booking.club_name,
        "requester_role": requester_role,
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

    requester_role = (payload.requester_role or "club").strip().lower()
    requester_name = payload.club_name.strip()
    booking_owner = f"Faculty: {requester_name}" if requester_role == "faculty" else requester_name

    booking = RoomBooking(
        event_name=payload.event_name.strip(),
        club_name=booking_owner,
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

    conflicts = get_room_conflicts(db, booking)
    message = "Room booking request sent to admin"
    if requester_role == "faculty" and any(not is_faculty_booking(item) and item.status == "approved" for item in conflicts):
        message = "Faculty request sent to admin for priority evaluation"

    return {
        "message": message,
        "booking": serialize_booking(booking),
        "conflicts": [serialize_booking(item) for item in conflicts],
    }


@router.get("")
async def list_bookings(
    status: Optional[str] = Query(default=None),
    requested_by_user_id: Optional[int] = Query(default=None),
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    db = db_invoker.db
    query = db.query(RoomBooking)
    if status:
        query = query.filter(RoomBooking.status == status.lower())
    if requested_by_user_id:
        query = query.filter(RoomBooking.requested_by_user_id == requested_by_user_id)

    bookings = query.order_by(RoomBooking.event_date, RoomBooking.start_time, RoomBooking.created_at).all()
    return {
        "bookings": [
            {
                **serialize_booking(booking),
                "conflicts": [serialize_booking(item) for item in get_room_conflicts(db, booking)],
            }
            for booking in bookings
        ]
    }


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
    if status not in {"approved", "rejected", "pending", "overridden", "appealed"}:
        raise HTTPException(status_code=400, detail="Status must be pending, approved, rejected, overridden, or appealed")

    booking = db.query(RoomBooking).filter(RoomBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    conflicts = get_room_conflicts(db, booking)
    approved_conflicts = [item for item in conflicts if item.status == "approved"]

    if status == "approved" and approved_conflicts:
        if is_faculty_booking(booking):
            for conflict in approved_conflicts:
                if is_faculty_booking(conflict):
                    raise HTTPException(status_code=409, detail="This room is already approved for another faculty booking")
                conflict.status = "overridden"
                conflict.admin_note = (
                    f"Overridden because a faculty booking has higher priority: "
                    f"{booking.event_name} in {booking.room_name} on {booking.event_date}."
                )
                conflict.updated_at = datetime.utcnow()
        else:
            faculty_conflict = next((item for item in approved_conflicts if is_faculty_booking(item)), None)
            if faculty_conflict:
                raise HTTPException(
                    status_code=409,
                    detail="This room is already approved for a faculty booking. Change the club room before approving.",
                )
            raise HTTPException(status_code=409, detail="This room already has an approved booking")

    booking.status = status
    booking.admin_note = payload.admin_note
    booking.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(booking)

    return {"message": f"Booking {status}", "booking": serialize_booking(booking)}


@router.patch("/{booking_id}/room")
async def update_booking_room(
    booking_id: int,
    payload: BookingRoomUpdate,
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    db = db_invoker.db
    booking = db.query(RoomBooking).filter(RoomBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    room = db.query(Rooms).filter(Rooms.id == payload.room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    booking.room_id = room.id
    booking.room_name = room.name
    if payload.event_date:
        booking.event_date = payload.event_date
    if payload.start_time:
        booking.start_time = payload.start_time
    if payload.end_time:
        booking.end_time = payload.end_time
    booking.admin_note = "Admin changed the room after evaluating booking priority."
    booking.updated_at = datetime.utcnow()

    conflicts = get_room_conflicts(db, booking)
    approved_conflicts = [item for item in conflicts if item.status == "approved"]
    if approved_conflicts:
        raise HTTPException(status_code=409, detail="The selected room still clashes with an approved booking")

    if booking.status in {"overridden", "appealed"}:
        booking.status = "approved"

    db.commit()
    db.refresh(booking)
    return {"message": "Booking room updated", "booking": serialize_booking(booking)}


@router.patch("/{booking_id}/appeal")
async def appeal_booking(
    booking_id: int,
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    db = db_invoker.db
    booking = db.query(RoomBooking).filter(RoomBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.status != "overridden":
        raise HTTPException(status_code=400, detail="Only overridden bookings can be appealed")

    booking.status = "appealed"
    booking.admin_note = f"{booking.admin_note or ''} Club raised an appeal for admin review.".strip()
    booking.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(booking)
    return {"message": "Appeal sent to admin", "booking": serialize_booking(booking)}
