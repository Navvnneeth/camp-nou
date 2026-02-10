from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.dialects.postgresql import ARRAY
from services.models.base import Base

class Rooms(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    capacity = Column(Integer)
    created_at = Column(DateTime)

class Students(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    branch = Column(String)
    created_at = Column(DateTime)

class Classrooms(Base):
    __tablename__ = "classrooms"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer)
    class_id = Column(Integer)
    students = Column(ARRAY(String))
    created_at = Column(DateTime)