from typing import List, Dict, Any, TypedDict, Annotated
import operator
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session
from services.dependencies.db import get_db_session
from services.models.models import Students, Rooms, Classrooms
from datetime import datetime

class SchedulerState(TypedDict):
    students: List[Dict[str, Any]]
    rooms: List[Dict[str, Any]]
    assignments: List[Dict[str, Any]]
    current_room_index: int

def fetch_data(state: SchedulerState):
    print("Fetching data...")
    db: Session = get_db_session()
    try:
        students = db.query(Students).all()
        rooms = db.query(Rooms).all()
        
        students_data = [{"id": s.id, "name": s.name, "branch": s.branch} for s in students]
        rooms_data = [{"id": r.id, "name": r.name, "capacity": r.capacity} for r in rooms]
        
        print(f"Fetched {len(students_data)} students and {len(rooms_data)} rooms.")
        return {
            "students": students_data, 
            "rooms": rooms_data,
            "assignments": [],  
            "current_room_index": 0
        }
    finally:
        db.close()

def sort_students(state: SchedulerState):
    print("Sorting students...")
    students = state["students"]
    # Sort by id (number)
    sorted_students = sorted(students, key=lambda x: x["id"])
    return {"students": sorted_students}

def allocate_room(state: SchedulerState):
    current_index = state["current_room_index"]
    rooms = state["rooms"]
    students = state["students"]
    assignments = state["assignments"]
    
    if current_index >= len(rooms):
        # No more rooms available
        return {"assignments": assignments}

    room = rooms[current_index]
    capacity = room["capacity"]
    
    # Take students up to capacity
    to_assign = students[:capacity]
    remaining_students = students[capacity:]
    
    print(f"Allocating room {room['name']} (Capacity: {capacity}). Assigning: {len(to_assign)} students.")
    
    assignment = {
        "room_id": room["id"],
        "students": [s["name"] for s in to_assign],
        "class_id": 1 # Placeholder as no class_id logic specified
    }
    
    # We need to return the *updated* full state or just updates?
    # LangGraph usually merges updates.
    # But for lists, we want to replace or specific merge strategy.
    # Here we are returning full replacement for simplified TypedDict state logic usually used in basic examples.
    # To be safe, we return the keys we want to update.
    
    return {
        "students": remaining_students,
        "assignments": assignments + [assignment],
        "current_room_index": current_index + 1
    }

def check_availability(state: SchedulerState):
    # If we have students left AND rooms available
    if state["students"] and state["current_room_index"] < len(state["rooms"]):
        return "continue"
    return "end"

def save_assignments(state: SchedulerState):
    print("Saving assignments...")
    assignments = state["assignments"]
    if not assignments:
        print("No assignments to save.")
        return {}
        
    db: Session = get_db_session()
    try:
        new_classrooms = []
        for assign in assignments:
            if not assign["students"]:
                continue
            
            classroom = Classrooms(
                room_id=assign["room_id"],
                class_id=assign["class_id"],
                students=assign["students"],
                created_at=datetime.utcnow()
            )
            new_classrooms.append(classroom)
            db.add(classroom) # Add individually to be safe or add_all
        
        db.commit()
        print(f"Saved {len(new_classrooms)} classroom entries.")
    except Exception as e:
        print(f"Error saving assignments: {e}")
        db.rollback()
    finally:
        db.close()
    return {}

# Define the graph
workflow = StateGraph(SchedulerState)

workflow.add_node("fetch_data", fetch_data)
workflow.add_node("sort_students", sort_students)
workflow.add_node("allocate_room", allocate_room)
workflow.add_node("save_assignments", save_assignments)

workflow.set_entry_point("fetch_data")
workflow.add_edge("fetch_data", "sort_students")
workflow.add_edge("sort_students", "allocate_room")

workflow.add_conditional_edges(
    "allocate_room",
    check_availability,
    {
        "continue": "allocate_room",
        "end": "save_assignments"
    }
)

workflow.add_edge("save_assignments", END)

app = workflow.compile()

def run_scheduler():
    print("Starting Scheduler Workflow...")
    initial_state = {
        "students": [],
        "rooms": [],
        "assignments": [],
        "current_room_index": 0
    }
    result = app.invoke(initial_state)
    print("Scheduler Workflow Completed.")
    return result

if __name__ == "__main__":
    run_scheduler()
