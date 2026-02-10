from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv
import os
load_dotenv()

DATABASE_URL = os.getenv("NEON_DB_URL")

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

class DBInvoker:
    def __init__(self, db: Session):
        self.db = db

def getDbInvoker():
    db = SessionLocal()
    try:
        yield DBInvoker(db)
    finally:
        db.close()

def get_db_session() -> Session:
    return SessionLocal()

