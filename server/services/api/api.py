from fastapi import APIRouter
from .endpoints.rooms import router as rooms_router
from .endpoints.students import router as students_router
from .endpoints.subjects_faculty import router as subjects_faculty_router
from .endpoints.timetable import router as timetable_router

api_router = APIRouter()
api_router.include_router(rooms_router)
api_router.include_router(students_router)
api_router.include_router(subjects_faculty_router)
api_router.include_router(timetable_router)
