from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from services.models.base import Base
from services.dependencies.db import engine, get_db_session
from services.models.models import *
from services.api.api import api_router
from services.api.endpoints.rooms import seed_default_rooms


app = FastAPI(title="GTC API 1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        
    allow_credentials=True,
    allow_methods=["*"],        
    allow_headers=["*"],       
)

Base.metadata.create_all(bind=engine)
with engine.begin() as connection:
    connection.execute(text("ALTER TABLE students ADD COLUMN IF NOT EXISTS academic_year INTEGER"))
    connection.execute(text("ALTER TABLE subject_faculty_mapping ADD COLUMN IF NOT EXISTS academic_year INTEGER"))
    connection.execute(text("ALTER TABLE timetable ADD COLUMN IF NOT EXISTS academic_year INTEGER"))
db = get_db_session()
try:
    seed_default_rooms(db)
finally:
    db.close()

app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "API running"}
