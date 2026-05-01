from fastapi import UploadFile, File, Depends, HTTPException, APIRouter
from services.dependencies.db import getDbInvoker, DBInvoker
from services.models.models import Rooms
from scripts.rooms import insert_rooms_from_excel

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("")
async def list_rooms(
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    rooms = db_invoker.db.query(Rooms).order_by(Rooms.name).all()
    return {
        "rooms": [
            {
                "id": room.id,
                "name": room.name,
                "capacity": room.capacity,
                "room_type": room.room_type,
            }
            for room in rooms
        ]
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
