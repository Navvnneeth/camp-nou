from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from services.models.base import Base
from services.dependencies.db import engine
from services.models.models import *
from services.api.api import api_router


app = FastAPI(title="GTC API 1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        
    allow_credentials=True,
    allow_methods=["*"],        
    allow_headers=["*"],       
)

Base.metadata.create_all(bind=engine)

app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "API running"}
