from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY
from services.models.base import Base


class Rooms(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    capacity = Column(Integer)
    room_type = Column(String, default="classroom")  # "classroom" or "lab"
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


class Subjects(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    is_lab = Column(Boolean, default=False)
    hours_per_week = Column(Integer, default=1)
    created_at = Column(DateTime)


class Faculty(Base):
    __tablename__ = "faculty"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    created_at = Column(DateTime)


class SubjectFacultyMapping(Base):
    __tablename__ = "subject_faculty_mapping"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    faculty_id = Column(Integer, ForeignKey("faculty.id"), nullable=False)
    class_name = Column(String, nullable=False)  # e.g. "CS-A", "CS-B"
    created_at = Column(DateTime)


class Timetable(Base):
    __tablename__ = "timetable"

    id = Column(Integer, primary_key=True, index=True)
    class_name = Column(String, nullable=False, index=True)
    day = Column(String, nullable=False)          # "Monday", "Tuesday", etc.
    slot = Column(Integer, nullable=False)         # 1-6
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=True)
    faculty_id = Column(Integer, ForeignKey("faculty.id"), nullable=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=True)
    is_lab_period = Column(Boolean, default=False)
    status = Column(String, default="scheduled")   # "scheduled", "suspended"
    created_at = Column(DateTime)