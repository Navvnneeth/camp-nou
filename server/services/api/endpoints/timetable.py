from fastapi import Depends, HTTPException, APIRouter
from services.dependencies.db import getDbInvoker, DBInvoker
from services.models.models import Timetable
from services.graph.timetable_scheduler import run_timetable_scheduler

router = APIRouter(prefix="/timetable", tags=["timetable"])

DAYS_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


@router.post("/generate")
async def generate_timetable(
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    """Trigger the LangGraph timetable scheduler and return results."""
    try:
        result = run_timetable_scheduler()
        return {
            "message": "Timetable generated successfully",
            "warnings": result.get("warnings", []),
            "classes_scheduled": list(result.get("timetable", {}).keys()),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/all")
async def get_all_timetables(
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    """Get all timetable entries grouped by class."""
    db = db_invoker.db
    entries = db.query(Timetable).order_by(
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
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    """Get timetable for a specific class, formatted as a grid."""
    db = db_invoker.db
    entries = db.query(Timetable).filter(
        Timetable.class_name == class_name
    ).order_by(Timetable.day, Timetable.slot).all()

    if not entries:
        raise HTTPException(status_code=404, detail=f"No timetable found for class '{class_name}'")

    grid = {}
    for day in DAYS_ORDER:
        grid[day] = {}
        for slot in range(1, 7):
            grid[day][str(slot)] = None

    for entry in entries:
        grid[entry.day][str(entry.slot)] = {
            "subject_id": entry.subject_id,
            "faculty_id": entry.faculty_id,
            "room_id": entry.room_id,
            "is_lab_period": entry.is_lab_period,
            "status": entry.status,
        }

    return {"class_name": class_name, "timetable": grid}
