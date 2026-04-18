from typing import List, Dict, Any, TypedDict, Annotated
import operator
import json
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session
from services.dependencies.db import get_db_session
from services.models.models import Students, Rooms, Classrooms
from datetime import datetime
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="google/gemma-4-e4b",
    base_url="http://127.0.0.1:1234/v1",
    api_key="lm-studio",
    temperature=0.2,
)

class SchedulerState(TypedDict):
    students: List[Dict[str, Any]]
    rooms: List[Dict[str, Any]]
    sections: List[Dict[str, Any]]
    assignments: List[Dict[str, Any]]

def fetch_data(state: SchedulerState):
    print("Fetching data...")
    db: Session = get_db_session()
    try:
        students = db.query(Students).all()
        rooms = db.query(Rooms).all()
        
        students_data = [{"id": s.id, "name": s.name, "branch": s.branch} for s in students]
        rooms_data = [{"id": r.id, "name": r.name, "capacity": r.capacity, "room_type": r.room_type or "classroom"} for r in rooms]
        
        print(f"Fetched {len(students_data)} students and {len(rooms_data)} rooms.")
        return {
            "students": students_data, 
            "rooms": rooms_data,
            "sections": [],
            "assignments": [],  
        }
    finally:
        db.close()

def _sort_students_fallback(students, rooms):
    print("[sort_students] Fallback to deterministic algorithm")
    sorted_students = sorted(students, key=lambda x: x["id"])
    sections = []
    current_section = []
    current_capacity = 60 # Assume 60 if not specified
    if rooms:
        classrooms = [r for r in rooms if r.get("room_type") == "classroom"]
        if classrooms:
            current_capacity = max(r["capacity"] for r in classrooms)

    for i, s in enumerate(sorted_students):
        current_section.append(s["id"])
        if len(current_section) == current_capacity or i == len(sorted_students) - 1:
            sections.append({
                "section_name": f"{s['branch']}-Fallback",
                "branch": s["branch"],
                "student_ids": current_section
            })
            current_section = []
    return sections

def sort_students(state: SchedulerState):
    print("Sorting students via AI...")
    students = state["students"]
    rooms = state["rooms"]
    
    if not students:
        return {"sections": []}

    prompt = f"""You are a college scheduling assistant. Group the following students into branch-based sections.
    
    Students: {json.dumps(students)}
    Rooms: {json.dumps(rooms)}
    
    Target: produce named sections (e.g. CS-A, CS-B, EC-A) such that each section fits within one room's capacity. 
    Duplicate section names across branches are allowed, but prefix them with the branch (e.g. CS-A and EC-A).
    Every student must appear in exactly one section (no orphans, no duplicates).
    Each section's student count must not exceed the assigned room's capacity.
    
    Respond in valid JSON only, using exactly this format:
    {{
      "sections": [
        {{
          "section_name": "CS-A",
          "branch": "CS",
          "student_ids": [1, 2, 3]
        }}
      ]
    }}
    """
    
    try:
        response = llm.invoke(prompt)
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].strip()
            
        result = json.loads(content)
        sections = result.get("sections", [])
        
        # Validation
        all_assigned_ids = []
        for s in sections:
            all_assigned_ids.extend(s.get("student_ids", []))
            
        student_ids = [s["id"] for s in students]
        if set(all_assigned_ids) != set(student_ids) or len(all_assigned_ids) != len(student_ids):
            print(f"[sort_students] Validation failed: Student mismatch.")
            sections = _sort_students_fallback(students, rooms)
            
    except Exception as e:
        print(f"[sort_students] Error calling AI: {e}")
        sections = _sort_students_fallback(students, rooms)

    return {"sections": sections}

def _allocate_room_fallback(sections, rooms):
    print("[allocate_room] Fallback to deterministic algorithm")
    allocations = []
    classrooms = [r for r in rooms if r.get("room_type") == "classroom"]
    available_rooms = list(classrooms)
    
    for section in sections:
        if not available_rooms:
            break
        room = available_rooms.pop(0)
        allocations.append({
            "section_name": section["section_name"],
            "room_id": room["id"],
            "room_name": room["name"]
        })
    return allocations

def allocate_room(state: SchedulerState):
    print("Allocating rooms via AI...")
    sections = state.get("sections", [])
    rooms = state.get("rooms", [])
    
    if not sections or not rooms:
        return {"assignments": []}

    prompt = f"""You are a college scheduling assistant. Assign one room to each section.
    
    Sections: {json.dumps(sections)}
    Available rooms: {json.dumps(rooms)}
    
    Constraints:
    - Only `room_type = "classroom"` rooms may be assigned as homerooms to sections.
    - No room may appear twice in the allocations list.
    - Assigned room capacity must be >= section student count.
    
    Respond in valid JSON only, using exactly this format:
    {{
      "allocations": [
        {{ "section_name": "CS-A", "room_id": 1, "room_name": "CR-101" }}
      ]
    }}
    """
    
    try:
        response = llm.invoke(prompt)
        content = response.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].strip()
            
        result = json.loads(content)
        allocations = result.get("allocations", [])
        
        # Validation
        used_rooms = []
        is_valid = True
        for a in allocations:
            if a["room_id"] in used_rooms:
                is_valid = False
                break
            used_rooms.append(a["room_id"])
            
        if not is_valid:
            print("[allocate_room] Validation failed: Duplicate rooms.")
            allocations = _allocate_room_fallback(sections, rooms)
            
    except Exception as e:
        print(f"[allocate_room] Error calling AI: {e}")
        allocations = _allocate_room_fallback(sections, rooms)

    # Convert allocations to old assignments format to avoid breaking save_assignments
    assignments = []
    students_by_id = {s["id"]: s for s in state["students"]}
    
    for alloc in allocations:
        section = next((s for s in sections if s["section_name"] == alloc["section_name"]), None)
        if section:
            assignments.append({
                "room_id": alloc["room_id"],
                "students": [students_by_id[sid]["name"] for sid in section["student_ids"] if sid in students_by_id],
                "class_id": 1 # Placeholder
            })

    return {
        "assignments": assignments
    }


def save_assignments(state: SchedulerState):
    print("Saving assignments...")
    assignments = state["assignments"]
    if not assignments:
        print("No assignments to save.")
        return {}
        
    db: Session = get_db_session()
    try:
        # Clear existing to avoid duplicate conflicts if necessary, but skipping to preserve existing logic if any
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
            db.add(classroom)
        
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
workflow.add_edge("allocate_room", "save_assignments")
workflow.add_edge("save_assignments", END)

app = workflow.compile()

def run_scheduler():
    print("Starting Scheduler Workflow...")
    initial_state = {
        "students": [],
        "rooms": [],
        "sections": [],
        "assignments": [],
    }
    result = app.invoke(initial_state)
    print("Scheduler Workflow Completed.")
    return result

if __name__ == "__main__":
    run_scheduler()
