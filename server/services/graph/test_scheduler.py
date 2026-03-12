from services.dependencies.db import get_db_session
from services.models.models import Students, Rooms, Classrooms
from services.graph.scheduler import run_scheduler
from datetime import datetime

def setup_dummy_data():
    db = get_db_session()
    try:
        # Check if data exists
        if db.query(Students).count() > 0:
            print("Data already exists. Skipping setup.")
            return

        print("Inserting dummy data...")
        
        # Rooms
        rooms = [
            Rooms(name="101", capacity=2, created_at=datetime.utcnow()),
            Rooms(name="102", capacity=3, created_at=datetime.utcnow()),
            Rooms(name="103", capacity=5, created_at=datetime.utcnow())
        ]
        db.add_all(rooms)
        
        # Students
        students = []
        for i in range(1, 11): # 10 students
            students.append(Students(name=f"Student_{i}", branch="CS", created_at=datetime.utcnow()))
            
        db.add_all(students)
        db.commit()
        print("Dummy data inserted.")
    finally:
        db.close()

def verify_results():
    db = get_db_session()
    try:
        classrooms = db.query(Classrooms).all()
        print(f"\n--- Verification Results ---")
        print(f"Total Classroom Entries: {len(classrooms)}")
        
        total_assigned = 0
        for c in classrooms:
            print(f"Room ID: {c.room_id}, Assigned Count: {len(c.students)}, Students: {c.students}")
            total_assigned += len(c.students)
            
        print(f"Total Students Assigned: {total_assigned}")
        
    finally:
        db.close()

if __name__ == "__main__":
    setup_dummy_data()
    run_scheduler()
    verify_results()
