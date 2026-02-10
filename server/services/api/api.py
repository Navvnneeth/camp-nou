from fastapi import APIRouter
from .endpoints.rooms import router as rooms_router
from .endpoints.students import router as students_router

api_router = APIRouter()
api_router.include_router(rooms_router)
api_router.include_router(students_router)