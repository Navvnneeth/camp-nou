from typing import Optional

from fastapi import Depends, HTTPException, APIRouter, Query
from services.dependencies.db import getDbInvoker, DBInvoker
from services.models.models import Faculty, Students, SubjectFacultyMapping, Subjects, Timetable
from services.graph.timetable_scheduler import run_timetable_scheduler

router = APIRouter(prefix="/timetable", tags=["timetable"])

DAYS_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


@router.post("/generate")
async def generate_timetable(
    academic_year: Optional[int] = Query(default=None, ge=1, le=4),
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    """Trigger the LangGraph timetable scheduler and return results."""
    try:
        result = run_timetable_scheduler(academic_year=academic_year)
        if not result.get("is_feasible", True) or not result.get("is_valid", True):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Could not generate a valid timetable with the current constraints.",
                    "warnings": result.get("warnings", []),
                },
            )
        return {
            "message": (
                f"Year {academic_year} timetable generated successfully"
                if academic_year
                else "Timetable generated successfully"
            ),
            "warnings": result.get("warnings", []),
            "classes_scheduled": [
                class_name
                for class_name in result.get("timetable", {}).keys()
                if not class_name.startswith("__")
            ],
            "academic_year": academic_year,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/all")
async def get_all_timetables(
    academic_year: Optional[int] = Query(default=None, ge=1, le=4),
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    """Get all timetable entries grouped by class."""
    db = db_invoker.db
    query = db.query(Timetable)
    if academic_year:
        query = query.filter(Timetable.academic_year == academic_year)
    entries = query.order_by(
        Timetable.class_name, Timetable.day, Timetable.slot
    ).all()

    result = {}
    for entry in entries:
        if entry.class_name not in result:
            result[entry.class_name] = {}
        if entry.day not in result[entry.class_name]:
            result[entry.class_name][entry.day] = []

        result[entry.class_name][entry.day].append({
            "slot": entry.slot,
            "academic_year": entry.academic_year,
            "subject_id": entry.subject_id,
            "faculty_id": entry.faculty_id,
            "room_id": entry.room_id,
            "is_lab_period": entry.is_lab_period,
            "status": entry.status,
        })

    return result


@router.get("/{class_name}")
async def get_timetable_by_class(
    class_name: str,
    academic_year: Optional[int] = Query(default=None, ge=1, le=4),
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    """Get timetable for a specific class, formatted as a grid."""
    db = db_invoker.db
    query = db.query(Timetable).filter(Timetable.class_name == class_name)
    if academic_year:
        query = query.filter(Timetable.academic_year == academic_year)
    entries = query.order_by(Timetable.day, Timetable.slot).all()

    if not entries:
        raise HTTPException(status_code=404, detail=f"No timetable found for class '{class_name}'")

    grid = {}
    for day in DAYS_ORDER:
        grid[day] = {}
        for slot in range(1, 7):
            grid[day][str(slot)] = None

    for entry in entries:
        grid[entry.day][str(entry.slot)] = {
            "academic_year": entry.academic_year,
            "subject_id": entry.subject_id,
            "faculty_id": entry.faculty_id,
            "room_id": entry.room_id,
            "is_lab_period": entry.is_lab_period,
            "status": entry.status,
        }

    return {"class_name": class_name, "timetable": grid}


@router.delete("/admin/reset")
async def reset_timetable_data(
    include_rooms: bool = Query(default=False),
    include_bookings: bool = Query(default=False),
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    """Clear generated timetables and uploaded academic data before a fresh import."""
    from services.models.models import RoomBooking, Rooms

    db = db_invoker.db
    try:
        deleted = {
            "timetable": db.query(Timetable).delete(),
            "subject_faculty_mapping": db.query(SubjectFacultyMapping).delete(),
            "subjects": db.query(Subjects).delete(),
            "faculty": db.query(Faculty).delete(),
            "students": db.query(Students).delete(),
        }

        if include_bookings:
            deleted["room_bookings"] = db.query(RoomBooking).delete()
        if include_rooms:
            deleted["rooms"] = db.query(Rooms).delete()

        db.commit()
        return {"message": "Academic data reset successfully", "deleted": deleted}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
