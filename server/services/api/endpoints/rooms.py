from datetime import date, datetime
import json
import os
from pathlib import Path
import urllib.error
import urllib.request
from typing import Optional

from dotenv import load_dotenv
from fastapi import UploadFile, File, Depends, HTTPException, APIRouter
from pydantic import BaseModel, Field

from services.dependencies.db import getDbInvoker, DBInvoker
from services.models.models import RoomBooking, Rooms
from scripts.rooms import insert_rooms_from_excel

router = APIRouter(prefix="/rooms", tags=["rooms"])


DEFAULT_ROOMS = [
    {"name": "Seminar Hall A", "capacity": 180, "room_type": "seminar"},
    {"name": "Auditorium", "capacity": 500, "room_type": "auditorium"},
    {"name": "CS Lab 1", "capacity": 60, "room_type": "lab"},
    {"name": "Innovation Lab", "capacity": 45, "room_type": "lab"},
    {"name": "Lecture Hall 204", "capacity": 120, "room_type": "classroom"},
    {"name": "Mini Seminar Room", "capacity": 40, "room_type": "seminar"},
]


class RoomCreate(BaseModel):
    name: str
    capacity: int = Field(gt=0)
    room_type: str = "classroom"


class RoomRecommendationRequest(BaseModel):
    event_name: str
    expected_attendees: int = Field(gt=0)
    event_date: date
    start_time: str
    end_time: str
    equipment_needs: Optional[str] = ""


def serialize_room(room: Rooms):
    return {
        "id": room.id,
        "name": room.name,
        "capacity": room.capacity,
        "room_type": room.room_type,
    }


def seed_default_rooms(db):
    if db.query(Rooms).count() > 0:
        return 0

    for room in DEFAULT_ROOMS:
        db.add(Rooms(**room, created_at=datetime.utcnow()))
    db.commit()
    return len(DEFAULT_ROOMS)


def times_overlap(start_a: str, end_a: str, start_b: str, end_b: str):
    return start_a < end_b and start_b < end_a


def availability_for_room(db, room: Rooms, payload: RoomRecommendationRequest):
    bookings = (
        db.query(RoomBooking)
        .filter(RoomBooking.event_date == payload.event_date)
        .filter(RoomBooking.room_id == room.id)
        .filter(RoomBooking.status.in_(["approved", "pending"]))
        .all()
    )

    conflicts = [
        booking
        for booking in bookings
        if times_overlap(payload.start_time, payload.end_time, booking.start_time, booking.end_time)
    ]
    approved_conflicts = [booking for booking in conflicts if booking.status == "approved"]
    pending_conflicts = [booking for booking in conflicts if booking.status == "pending"]

    return {
        "available": not approved_conflicts,
        "pending_conflicts": len(pending_conflicts),
        "conflicts": [
            {
                "event_name": booking.event_name,
                "club_name": booking.club_name,
                "status": booking.status,
                "start_time": booking.start_time,
                "end_time": booking.end_time,
            }
            for booking in conflicts
        ],
    }


def deterministic_score(room: Rooms, payload: RoomRecommendationRequest, pending_conflicts: int):
    capacity_gap = max(room.capacity - payload.expected_attendees, 0)
    fit_score = max(0, 45 - min(capacity_gap, 45))
    capacity_score = 30 if room.capacity >= payload.expected_attendees else -100
    pending_penalty = pending_conflicts * 12
    type_text = f"{room.name} {room.room_type}".lower()
    needs = (payload.equipment_needs or "").lower()
    equipment_score = 0

    if any(word in needs for word in ["projector", "seminar", "presentation", "speaker", "stage"]):
        if any(word in type_text for word in ["seminar", "auditorium", "lecture"]):
            equipment_score += 15
    if any(word in needs for word in ["computer", "coding", "lab", "system", "pc"]):
        if "lab" in type_text:
            equipment_score += 18
    if any(word in needs for word in ["large", "cultural", "fest", "audience"]):
        if "auditorium" in type_text:
            equipment_score += 18

    return capacity_score + fit_score + equipment_score - pending_penalty


def load_gemini_env():
    current_file = Path(__file__).resolve()
    candidate_envs = [
        current_file.parents[3] / ".env",  # server/.env
        current_file.parents[5] / ".env",  # outer project .env
    ]
    for env_path in candidate_envs:
        if env_path.exists():
            load_dotenv(env_path, override=False)


def call_gemini_for_room_ranking(payload: RoomRecommendationRequest, candidates: list):
    load_gemini_env()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or not candidates:
        return None

    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    prompt = {
        "role": "college_room_booking_advisor",
        "instruction": (
            "Rank available college rooms for a club event. Use only the room candidates provided. "
            "Return strict JSON with key recommendations. Each recommendation must include room_id, "
            "score from 0 to 100, and reason in one concise sentence. Do not invent rooms."
        ),
        "event": payload.model_dump(mode="json"),
        "room_candidates": candidates,
    }
    body = json.dumps({
        "contents": [
            {
                "parts": [
                    {
                        "text": json.dumps(prompt)
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }).encode("utf-8")

    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
    except (KeyError, json.JSONDecodeError, TimeoutError, urllib.error.URLError):
        return None


@router.get("")
async def list_rooms(
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    rooms = db_invoker.db.query(Rooms).order_by(Rooms.name).all()
    return {"rooms": [serialize_room(room) for room in rooms]}


@router.post("")
async def create_room(
    payload: RoomCreate,
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    db = db_invoker.db
    existing = db.query(Rooms).filter(Rooms.name == payload.name.strip()).first()
    if existing:
        raise HTTPException(status_code=400, detail="A room with this name already exists")

    room = Rooms(
        name=payload.name.strip(),
        capacity=payload.capacity,
        room_type=payload.room_type.strip().lower() or "classroom",
        created_at=datetime.utcnow(),
    )
    db.add(room)
    db.commit()
    db.refresh(room)
    return {"message": "Room added successfully", "room": serialize_room(room)}


@router.post("/seed")
async def seed_rooms(
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    count = seed_default_rooms(db_invoker.db)
    return {"message": f"{count} demo rooms added", "inserted": count}


@router.post("/recommend")
async def recommend_rooms(
    payload: RoomRecommendationRequest,
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    db = db_invoker.db
    rooms = db.query(Rooms).order_by(Rooms.capacity).all()
    if not rooms:
        seed_default_rooms(db)
        rooms = db.query(Rooms).order_by(Rooms.capacity).all()

    candidates = []
    unavailable = []
    for room in rooms:
        availability = availability_for_room(db, room, payload)
        room_payload = {
            **serialize_room(room),
            "capacity_gap": room.capacity - payload.expected_attendees,
            "pending_conflicts": availability["pending_conflicts"],
            "conflicts": availability["conflicts"],
            "base_score": deterministic_score(room, payload, availability["pending_conflicts"]),
        }
        if room.capacity >= payload.expected_attendees and availability["available"]:
            candidates.append(room_payload)
        else:
            unavailable.append(room_payload)

    candidates = sorted(candidates, key=lambda item: item["base_score"], reverse=True)[:6]
    gemini_result = call_gemini_for_room_ranking(payload, candidates)
    gemini_recommendations = {
        item.get("room_id"): item
        for item in (gemini_result or {}).get("recommendations", [])
        if item.get("room_id")
    }

    recommendations = []
    for candidate in candidates:
        ai_item = gemini_recommendations.get(candidate["id"], {})
        recommendations.append({
            **candidate,
            "score": ai_item.get("score", max(0, min(100, candidate["base_score"]))),
            "reason": ai_item.get(
                "reason",
                (
                    f"{candidate['name']} fits {payload.expected_attendees} attendees "
                    f"with {candidate['capacity_gap']} spare seats and no approved clash."
                ),
            ),
        })

    recommendations = sorted(recommendations, key=lambda item: item["score"], reverse=True)
    return {
        "recommendations": recommendations,
        "unavailable": unavailable,
        "ai_used": gemini_result is not None,
        "message": (
            "AI recommendations generated"
            if gemini_result is not None
            else "Fallback recommendations generated without Gemini"
        ),
    }

@router.post("/rooms/upload")
async def upload_rooms(
    file: UploadFile = File(...),
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Invalid file type")

    try:
        count = insert_rooms_from_excel(file.file, db_invoker)
        return {"message": f"{count} rooms inserted successfully"}

    except Exception as e:
        db_invoker.db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
