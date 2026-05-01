from datetime import datetime
import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.dependencies.db import DBInvoker, getDbInvoker
from services.models.models import AppUser


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str
    role: str


DEMO_USERS = [
    {
        "name": "Campus Administrator",
        "email": "admin@campnou.edu",
        "password": "admin123",
        "role": "administrator",
        "club_name": None,
    },
    {
        "name": "Faculty User",
        "email": "faculty@campnou.edu",
        "password": "faculty123",
        "role": "faculty",
        "club_name": None,
    },
    {
        "name": "Coding Club",
        "email": "codingclub@campnou.edu",
        "password": "club123",
        "role": "club",
        "club_name": "Coding Club",
    },
    {
        "name": "Arts Club",
        "email": "artsclub@campnou.edu",
        "password": "club123",
        "role": "club",
        "club_name": "Arts Club",
    },
]


def hash_password(password: str, salt: str) -> str:
    payload = f"{salt}:{password}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def serialize_user(user: AppUser):
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "club_name": user.club_name,
    }


def ensure_demo_users(db):
    for demo_user in DEMO_USERS:
        existing = db.query(AppUser).filter(AppUser.email == demo_user["email"]).first()
        if existing:
            continue

        salt = secrets.token_hex(16)
        user = AppUser(
            name=demo_user["name"],
            email=demo_user["email"],
            role=demo_user["role"],
            club_name=demo_user["club_name"],
            password_salt=salt,
            password_hash=hash_password(demo_user["password"], salt),
            created_at=datetime.utcnow(),
        )
        db.add(user)

    db.commit()


@router.post("/login")
async def login(
    payload: LoginRequest,
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    db = db_invoker.db
    ensure_demo_users(db)

    role = payload.role.strip().lower()
    user = db.query(AppUser).filter(AppUser.email == payload.email.strip().lower()).first()

    if not user or user.role != role:
        raise HTTPException(status_code=401, detail="Invalid email, password, or role")

    expected_hash = hash_password(payload.password, user.password_salt)
    if not secrets.compare_digest(expected_hash, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email, password, or role")

    return {"message": "Login successful", "user": serialize_user(user)}
