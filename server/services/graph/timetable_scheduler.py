"""
LangGraph-based Timetable Scheduler with Classroom Scarcity Optimization.

Handles the edge case where physical classrooms < total classes by:
1. Reusing classrooms freed during lab periods (students are in lab rooms)
2. Rescheduling lectures to open slots on other days
3. Rearranging lab periods to maximize classroom availability
4. Suspending classes as a last resort

Graph flow:
  fetch_all_data -> build_constraints -> solve_timetable -> validate_timetable
  -> (retry if invalid) -> save_timetable -> END
"""

from typing import List, Dict, Any, TypedDict, Optional, Set, Tuple
from langgraph.graph import StateGraph, END
from sqlalchemy import or_
from sqlalchemy.orm import Session
from services.dependencies.db import get_db_session
from services.models.models import (
    Subjects, Faculty, SubjectFacultyMapping, Rooms, Timetable
)
from datetime import datetime
import os
from dotenv import load_dotenv
from ortools.sat.python import cp_model

load_dotenv()

# ─── Constants ────────────────────────────────────────────────────────────────

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
SLOTS_PER_DAY = 6          # 1-hour slots numbered 1..6
LAB_DURATION = 3           # lab periods occupy 3 consecutive slots
TARGET_WEEKLY_HOURS = 20
TARGET_LAB_BLOCKS = 2
TARGET_LAB_HOURS = TARGET_LAB_BLOCKS * LAB_DURATION
TARGET_LECTURE_HOURS = TARGET_WEEKLY_HOURS - TARGET_LAB_HOURS


# ─── State ────────────────────────────────────────────────────────────────────

class TimetableState(TypedDict):
    # Input data
    classes: List[str]
    subjects: List[Dict[str, Any]]
    faculty_mappings: List[Dict[str, Any]]
    class_years: Dict[str, Optional[int]]
    classrooms: List[Dict[str, Any]]        # rooms where room_type = "classroom"
    labs: List[Dict[str, Any]]              # rooms where room_type = "lab"

    # Scheduling structures  (class -> day -> slot -> entry)
    timetable: Dict[str, Any]
    room_schedule: Dict[str, Any]           # room_id_str -> day -> slot_str -> class
    faculty_schedule: Dict[str, Any]        # faculty_id_str -> day -> slot_str -> class
    fixed_timetable_entries: List[Dict[str, Any]]

    # Conflict tracking
    conflicts: List[Dict[str, Any]]
    warnings: List[str]
    iteration: int
    retry: int
    academic_year: Optional[int]
    is_feasible: bool
    is_valid: bool


# ─── Helper utilities ─────────────────────────────────────────────────────────

def _slot_key(slot: int) -> str:
    return str(slot)

def _room_key(room_id: int) -> str:
    return str(room_id)

def _faculty_key(fac_id: int) -> str:
    return str(fac_id)

def _is_room_free(room_schedule: dict, room_id: int, day: str, slot: int) -> bool:
    rk = _room_key(room_id)
    if rk not in room_schedule:
        return True
    if day not in room_schedule[rk]:
        return True
    return _slot_key(slot) not in room_schedule[rk][day]

def _is_faculty_free(faculty_schedule: dict, fac_id: int, day: str, slot: int) -> bool:
    fk = _faculty_key(fac_id)
    if fk not in faculty_schedule:
        return True
    if day not in faculty_schedule[fk]:
        return True
    return _slot_key(slot) not in faculty_schedule[fk][day]

def _book_room(room_schedule: dict, room_id: int, day: str, slot: int, class_name: str):
    rk = _room_key(room_id)
    room_schedule.setdefault(rk, {}).setdefault(day, {})[_slot_key(slot)] = class_name

def _book_faculty(faculty_schedule: dict, fac_id: int, day: str, slot: int, class_name: str):
    fk = _faculty_key(fac_id)
    faculty_schedule.setdefault(fk, {}).setdefault(day, {})[_slot_key(slot)] = class_name

def _schedule_class_name(class_name: str, academic_year: Optional[int], target_year: Optional[int]) -> str:
    if target_year or not academic_year:
        return class_name

    prefix = f"y{academic_year}"
    normalized = class_name.lower().replace(" ", "")
    if normalized.startswith(prefix):
        return class_name
    return f"Y{academic_year}-{class_name}"

def _normalize_lecture_hours(lecture_reqs: List[Dict[str, Any]], target_hours: int) -> List[Dict[str, Any]]:
    if not lecture_reqs or target_hours <= 0:
        return []

    normalized = [{**req, "hours": max(1, int(req.get("hours", 1) or 1))} for req in lecture_reqs]
    total = sum(req["hours"] for req in normalized)

    index = 0
    while total < target_hours:
        normalized[index % len(normalized)]["hours"] += 1
        total += 1
        index += 1

    while total > target_hours and any(req["hours"] > 1 for req in normalized):
        candidate = max(normalized, key=lambda req: req["hours"])
        candidate["hours"] -= 1
        total -= 1

    if total > target_hours:
        trimmed = []
        remaining = target_hours
        for req in normalized:
            if remaining <= 0:
                break
            hours = min(req["hours"], remaining)
            trimmed.append({**req, "hours": hours})
            remaining -= hours
        normalized = trimmed

    return [req for req in normalized if req["hours"] > 0]

def _normalize_lab_hours(lab_reqs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not lab_reqs:
        return []

    if len(lab_reqs) == 1:
        return [{**lab_reqs[0], "hours": TARGET_LAB_HOURS}]

    return [
        {**lab_reqs[0], "hours": LAB_DURATION},
        {**lab_reqs[1], "hours": LAB_DURATION},
    ]


# ─── Node: fetch_all_data ─────────────────────────────────────────────────────

def fetch_all_data(state: TimetableState) -> dict:
    """Load subjects, faculty mappings, and rooms from the database."""
    print("[fetch_all_data] Loading data from database...")
    db: Session = get_db_session()
    try:
        subjects = db.query(Subjects).all()
        academic_year = state.get("academic_year")
        mappings_query = db.query(SubjectFacultyMapping)
        if academic_year:
            mappings_query = mappings_query.filter(SubjectFacultyMapping.academic_year == academic_year)
        mappings = mappings_query.all()
        rooms = db.query(Rooms).all()
        fixed_timetable_entries = []
        if academic_year:
            fixed_entries = (
                db.query(Timetable)
                .filter(
                    or_(
                        Timetable.academic_year != academic_year,
                        Timetable.academic_year.is_(None),
                    )
                )
                .all()
            )
            fixed_timetable_entries = [
                {
                    "class_name": entry.class_name,
                    "academic_year": entry.academic_year,
                    "day": entry.day,
                    "slot": entry.slot,
                    "room_id": entry.room_id,
                    "faculty_id": entry.faculty_id,
                }
                for entry in fixed_entries
                if entry.status != "suspended"
            ]

        subjects_data = [
            {
                "id": s.id,
                "name": s.name,
                "is_lab": s.is_lab,
                "hours_per_week": s.hours_per_week,
            }
            for s in subjects
        ]

        mappings_data = []
        class_years = {}
        for m in mappings:
            class_name = _schedule_class_name(m.class_name, m.academic_year, academic_year)
            mappings_data.append({
                "id": m.id,
                "subject_id": m.subject_id,
                "faculty_id": m.faculty_id,
                "class_name": class_name,
                "academic_year": m.academic_year,
            })
            class_years[class_name] = m.academic_year

        classrooms_data = [
            {"id": r.id, "name": r.name, "capacity": r.capacity}
            for r in rooms
            if (r.room_type or "classroom") == "classroom"
        ]

        labs_data = [
            {"id": r.id, "name": r.name, "capacity": r.capacity}
            for r in rooms
            if r.room_type == "lab"
        ]

        # Derive distinct class names from mappings
        class_names = sorted(set(m["class_name"] for m in mappings_data))

        print(
            f"[fetch_all_data] {len(subjects_data)} subjects, "
            f"{len(mappings_data)} mappings, {len(classrooms_data)} classrooms, "
            f"{len(labs_data)} labs, {len(class_names)} classes"
        )

        return {
            "classes": class_names,
            "subjects": subjects_data,
            "faculty_mappings": mappings_data,
            "class_years": class_years,
            "classrooms": classrooms_data,
            "labs": labs_data,
            "timetable": {},
            "room_schedule": {},
            "faculty_schedule": {},
            "fixed_timetable_entries": fixed_timetable_entries,
            "conflicts": [],
            "warnings": [],
            "iteration": 0,
            "retry": 0,
            "academic_year": academic_year,
            "is_feasible": True,
            "is_valid": True,
        }
    finally:
        db.close()


# ─── Node: build_constraints ─────────────────────────────────────────────────

def build_constraints(state: TimetableState) -> dict:
    """
    Pre-compute a per-class teaching load.
    Returns class_requirements: {class_name: [{subject_id, faculty_id, is_lab, hours}]}
    stored inside the timetable dict for convenience.
    """
    print("[build_constraints] Building constraint matrix...")
    mappings = state["faculty_mappings"]
    subjects_by_id = {s["id"]: s for s in state["subjects"]}
    warnings = list(state.get("warnings", []))

    raw_class_reqs: Dict[str, list] = {}
    for m in mappings:
        cn = m["class_name"]
        subj = subjects_by_id.get(m["subject_id"])
        if not subj:
            continue
        raw_class_reqs.setdefault(cn, []).append({
            "subject_id": subj["id"],
            "subject_name": subj["name"],
            "faculty_id": m["faculty_id"],
            "is_lab": subj["is_lab"],
            "hours": subj["hours_per_week"],
        })

    class_reqs: Dict[str, list] = {}
    for cn, reqs in raw_class_reqs.items():
        lab_reqs = [req for req in reqs if req["is_lab"]]
        lecture_reqs = [req for req in reqs if not req["is_lab"]]

        normalized_labs = _normalize_lab_hours(lab_reqs)
        normalized_lectures = _normalize_lecture_hours(lecture_reqs, TARGET_LECTURE_HOURS)

        if not normalized_labs:
            warnings.append(
                f"{cn}: no lab subject found; cannot place the required two 3-hour lab periods."
            )
        elif len(lab_reqs) == 1:
            warnings.append(
                f"{cn}: one lab subject found, so it is scheduled as two separate 3-hour lab periods."
            )
        elif len(lab_reqs) > TARGET_LAB_BLOCKS:
            warnings.append(
                f"{cn}: more than two lab subjects found; only two lab periods are scheduled to keep 20 weekly hours."
            )

        total_hours = sum(req["hours"] for req in normalized_lectures + normalized_labs)
        if total_hours != TARGET_WEEKLY_HOURS:
            warnings.append(f"{cn}: normalized to {total_hours} hours instead of {TARGET_WEEKLY_HOURS}.")

        class_reqs[cn] = normalized_lectures + normalized_labs

    # Store requirements inside timetable metadata
    timetable = state.get("timetable", {})
    timetable["__requirements__"] = class_reqs

    total_hours = sum(
        sum(r["hours"] for r in reqs) for reqs in class_reqs.values()
    )
    print(f"[build_constraints] Total teaching hours across all classes: {total_hours}")
    return {"timetable": timetable, "warnings": warnings}


# ─── Node: solve_timetable ───────────────────────────────────────────────────

def solve_timetable(state: TimetableState) -> dict:
    print("[solve_timetable] Solving timetable with OR-Tools CP-SAT...")
    
    validated_tt = state.get("timetable", {})
    reqs = validated_tt.get("__requirements__", {})
    
    room_schedule = {}
    faculty_schedule = {}
    conflicts = []
    warnings = list(state.get("warnings", []))

    model = cp_model.CpModel()
    
    classrooms = state.get("classrooms", [])
    labs = state.get("labs", [])
    all_rooms = classrooms + labs
    
    if not all_rooms:
        warnings.append("No rooms available for scheduling.")
        return {"warnings": warnings, "is_feasible": False}

    room_ids = [r["id"] for r in all_rooms]
    lab_ids = [r["id"] for r in labs]
    if not lab_ids:
        # Fallback if no labs available but labs are needed
        lab_ids = room_ids
        
    sessions = {}
    
    for cn in state["classes"]:
        class_reqs = reqs.get(cn, [])
        for r in class_reqs:
            subj_id = r["subject_id"]
            fac_id = r["faculty_id"]
            is_lab = r["is_lab"]
            hours = r["hours"]
            
            if is_lab:
                num_blocks = hours // LAB_DURATION
                for b in range(num_blocks):
                    session_key = (cn, subj_id, f"lab_{b}")
                    day_var = model.NewIntVar(0, len(DAYS) - 1, f"day_{session_key}")
                    room_var = model.NewIntVarFromDomain(cp_model.Domain.FromValues(lab_ids), f"room_{session_key}")
                    start_slot_var = model.NewIntVar(1, SLOTS_PER_DAY - LAB_DURATION + 1, f"start_slot_{session_key}")
                    
                    sessions[session_key] = {
                        "type": "lab", "class_name": cn, "subject_id": subj_id,
                        "faculty_id": fac_id, "day": day_var, "start_slot": start_slot_var,
                        "room": room_var, "duration": LAB_DURATION
                    }
            else:
                for h in range(hours):
                    session_key = (cn, subj_id, f"lec_{h}")
                    day_var = model.NewIntVar(0, len(DAYS) - 1, f"day_{session_key}")
                    slot_var = model.NewIntVar(1, SLOTS_PER_DAY, f"slot_{session_key}")
                    room_var = model.NewIntVarFromDomain(cp_model.Domain.FromValues(room_ids), f"room_{session_key}")
                    
                    sessions[session_key] = {
                        "type": "lec", "class_name": cn, "subject_id": subj_id,
                        "faculty_id": fac_id, "day": day_var, "slot": slot_var,
                        "room": room_var, "duration": 1
                    }

    session_list = list(sessions.values())
    
    for i in range(len(session_list)):
        for j in range(i + 1, len(session_list)):
            s1 = session_list[i]
            s2 = session_list[j]
            
            same_class = (s1["class_name"] == s2["class_name"])
            same_fac = (s1["faculty_id"] == s2["faculty_id"])
            
            same_day = model.NewBoolVar(f"same_day_{i}_{j}")
            model.Add(s1["day"] == s2["day"]).OnlyEnforceIf(same_day)
            model.Add(s1["day"] != s2["day"]).OnlyEnforceIf(same_day.Not())
            
            overlap_slots = model.NewBoolVar(f"overlap_slots_{i}_{j}")
            s1_start = s1["start_slot"] if s1["type"] == "lab" else s1["slot"]
            s1_end = s1_start + s1["duration"] - 1
            s2_start = s2["start_slot"] if s2["type"] == "lab" else s2["slot"]
            s2_end = s2_start + s2["duration"] - 1
            
            c1 = model.NewBoolVar(f"c1_{i}_{j}")
            model.Add(s1_start <= s2_end).OnlyEnforceIf(c1)
            model.Add(s1_start > s2_end).OnlyEnforceIf(c1.Not())
            
            c2 = model.NewBoolVar(f"c2_{i}_{j}")
            model.Add(s2_start <= s1_end).OnlyEnforceIf(c2)
            model.Add(s2_start > s1_end).OnlyEnforceIf(c2.Not())
            
            model.AddBoolAnd([c1, c2]).OnlyEnforceIf(overlap_slots)
            model.AddBoolOr([c1.Not(), c2.Not()]).OnlyEnforceIf(overlap_slots.Not())
            
            time_overlap = model.NewBoolVar(f"time_overlap_{i}_{j}")
            model.AddBoolAnd([same_day, overlap_slots]).OnlyEnforceIf(time_overlap)
            model.AddBoolOr([same_day.Not(), overlap_slots.Not()]).OnlyEnforceIf(time_overlap.Not())
            
            if same_class:
                model.Add(time_overlap == 0)
            if same_fac:
                model.Add(time_overlap == 0)
                
            same_room = model.NewBoolVar(f"same_room_{i}_{j}")
            model.Add(s1["room"] == s2["room"]).OnlyEnforceIf(same_room)
            model.Add(s1["room"] != s2["room"]).OnlyEnforceIf(same_room.Not())
            
            model.AddBoolOr([same_room.Not(), time_overlap.Not()])

    fixed_entries = state.get("fixed_timetable_entries", [])
    for session_index, session in enumerate(session_list):
        start_var = session["start_slot"] if session["type"] == "lab" else session["slot"]
        session_duration = session["duration"]
        possible_starts = range(1, SLOTS_PER_DAY - session_duration + 2)

        for fixed_index, fixed in enumerate(fixed_entries):
            if fixed.get("day") not in DAYS or not fixed.get("slot"):
                continue

            fixed_day = DAYS.index(fixed["day"])
            fixed_slot = int(fixed["slot"])
            overlap_starts = [
                start
                for start in possible_starts
                if start <= fixed_slot <= start + session_duration - 1
            ]
            if not overlap_starts:
                continue

            same_day = model.NewBoolVar(f"fixed_same_day_{session_index}_{fixed_index}")
            model.Add(session["day"] == fixed_day).OnlyEnforceIf(same_day)
            model.Add(session["day"] != fixed_day).OnlyEnforceIf(same_day.Not())

            slot_overlap = model.NewBoolVar(f"fixed_slot_overlap_{session_index}_{fixed_index}")
            overlap_table = [(value,) for value in overlap_starts]
            model.AddAllowedAssignments([start_var], overlap_table).OnlyEnforceIf(slot_overlap)
            model.AddForbiddenAssignments([start_var], overlap_table).OnlyEnforceIf(slot_overlap.Not())

            if fixed.get("room_id"):
                same_room = model.NewBoolVar(f"fixed_same_room_{session_index}_{fixed_index}")
                model.Add(session["room"] == fixed["room_id"]).OnlyEnforceIf(same_room)
                model.Add(session["room"] != fixed["room_id"]).OnlyEnforceIf(same_room.Not())
                model.AddBoolOr([same_day.Not(), slot_overlap.Not(), same_room.Not()])

            if fixed.get("faculty_id") and session["faculty_id"] == fixed["faculty_id"]:
                model.AddBoolOr([same_day.Not(), slot_overlap.Not()])

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60.0
    status = solver.Solve(model)
    
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        is_feasible = True
        for cn in state["classes"]:
            if cn not in validated_tt:
                validated_tt[cn] = {}
            for day in DAYS:
                if day not in validated_tt[cn]:
                    validated_tt[cn][day] = {}
        
        for key, s in sessions.items():
            cn = s["class_name"]
            day_idx = solver.Value(s["day"])
            day = DAYS[day_idx]
            room_id = solver.Value(s["room"])
            fac_id = s["faculty_id"]
            subj_id = s["subject_id"]
            
            if s["type"] == "lab":
                start_slot = solver.Value(s["start_slot"])
                for i in range(s["duration"]):
                    slot = start_slot + i
                    sk = _slot_key(slot)
                    validated_tt[cn][day][sk] = {
                        "subject_id": subj_id,
                        "faculty_id": fac_id,
                        "room_id": room_id,
                        "is_lab_period": True,
                        "status": "scheduled"
                    }
                    _book_room(room_schedule, room_id, day, slot, cn)
                    _book_faculty(faculty_schedule, fac_id, day, slot, cn)
            else:
                slot = solver.Value(s["slot"])
                sk = _slot_key(slot)
                validated_tt[cn][day][sk] = {
                    "subject_id": subj_id,
                    "faculty_id": fac_id,
                    "room_id": room_id,
                    "is_lab_period": False,
                    "status": "scheduled"
                }
                _book_room(room_schedule, room_id, day, slot, cn)
                _book_faculty(faculty_schedule, fac_id, day, slot, cn)
    else:
        is_feasible = False
        warnings.append("INFEASIBLE: Could not generate a timetable that satisfies all constraints (e.g. not enough rooms or faculty overlapping).")

    validated_tt["__requirements__"] = reqs
    
    return {
        "timetable": validated_tt,
        "room_schedule": room_schedule,
        "faculty_schedule": faculty_schedule,
        "conflicts": [],
        "warnings": warnings,
        "iteration": 1,
        "is_feasible": is_feasible,
    }


# ─── Node: validate_timetable ─────────────────────────────────────────────────

def validate_timetable(state: TimetableState) -> dict:
    """
    Verify:
      - No faculty teaches two classes in the same slot
      - No room is double-booked
      - Lab periods are consecutive
    Returns updated conflicts list if issues found.
    """
    print("[validate_timetable] Validating...")
    timetable = state["timetable"]
    warnings = list(state.get("warnings", []))
    issues = []

    # Build faculty and room occupancy from timetable entries
    faculty_slots: Dict[str, Set[str]] = {}   # "fac_id|day|slot" -> set of classes
    room_slots: Dict[str, Set[str]] = {}      # "room_id|day|slot" -> set of classes

    for fixed in state.get("fixed_timetable_entries", []):
        day = fixed.get("day")
        slot = fixed.get("slot")
        class_name = fixed.get("class_name", "existing class")
        if not day or not slot:
            continue
        if fixed.get("faculty_id"):
            fkey = f"{fixed['faculty_id']}|{day}|{slot}"
            faculty_slots.setdefault(fkey, set()).add(class_name)
        if fixed.get("room_id"):
            rkey = f"{fixed['room_id']}|{day}|{slot}"
            room_slots.setdefault(rkey, set()).add(class_name)

    for cn in state["classes"]:
        class_tt = timetable.get(cn, {})
        scheduled_slots = 0
        lab_slots = 0
        for day in DAYS:
            day_tt = class_tt.get(day, {})
            for sk, entry in day_tt.items():
                if not isinstance(entry, dict):
                    continue
                fid = entry.get("faculty_id")
                rid = entry.get("room_id")
                status = entry.get("status", "")

                if status == "suspended":
                    continue

                scheduled_slots += 1
                if entry.get("is_lab_period"):
                    lab_slots += 1

                if fid:
                    fkey = f"{fid}|{day}|{sk}"
                    faculty_slots.setdefault(fkey, set()).add(cn)
                if rid:
                    rkey = f"{rid}|{day}|{sk}"
                    room_slots.setdefault(rkey, set()).add(cn)

        if scheduled_slots != TARGET_WEEKLY_HOURS:
            issues.append(f"{cn}: expected {TARGET_WEEKLY_HOURS} scheduled hours, found {scheduled_slots}")
        if lab_slots != TARGET_LAB_HOURS:
            issues.append(f"{cn}: expected {TARGET_LAB_BLOCKS} lab periods ({TARGET_LAB_HOURS} hours), found {lab_slots} lab hours")

    for fkey, classes in faculty_slots.items():
        if len(classes) > 1:
            issues.append(f"Faculty double-booked: {fkey} -> {classes}")

    for rkey, classes in room_slots.items():
        if len(classes) > 1:
            issues.append(f"Room double-booked: {rkey} -> {classes}")

    if issues:
        warnings.extend(issues)
        print(f"[validate_timetable] Found {len(issues)} validation issues")
    else:
        print("[validate_timetable] Timetable is valid ✓")

    return {"warnings": warnings, "conflicts": [], "is_valid": not issues}


# ─── Conditional: valid or retry? ─────────────────────────────────────────────

def check_valid(state: TimetableState) -> str:
    if not state.get("is_feasible", True) or not state.get("is_valid", True):
        return "invalid"
    return "valid"


# ─── Node: save_timetable ─────────────────────────────────────────────────────

def save_timetable(state: TimetableState) -> dict:
    """Persist timetable entries to the database."""
    print("[save_timetable] Saving to database...")
    timetable = state["timetable"]

    db: Session = get_db_session()
    try:
        target_academic_year = state.get("academic_year")
        class_years = state.get("class_years", {})
        query = db.query(Timetable)
        if target_academic_year:
            query = query.filter(Timetable.academic_year == target_academic_year)
        query.delete()
        db.flush()

        count = 0
        for cn in state["classes"]:
            class_tt = timetable.get(cn, {})
            for day in DAYS:
                day_tt = class_tt.get(day, {})
                for sk, entry in day_tt.items():
                    if not isinstance(entry, dict):
                        continue
                    tt = Timetable(
                        class_name=cn,
                        academic_year=target_academic_year or class_years.get(cn),
                        day=day,
                        slot=int(sk),
                        subject_id=entry.get("subject_id"),
                        faculty_id=entry.get("faculty_id"),
                        room_id=entry.get("room_id"),
                        is_lab_period=entry.get("is_lab_period", False),
                        status=entry.get("status", "scheduled"),
                        created_at=datetime.utcnow(),
                    )
                    db.add(tt)
                    count += 1

        db.commit()
        print(f"[save_timetable] Saved {count} timetable entries ✓")
    except Exception as e:
        print(f"[save_timetable] Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()

    return {}


# ─── Build the LangGraph ──────────────────────────────────────────────────────

workflow = StateGraph(TimetableState)

workflow.add_node("fetch_all_data", fetch_all_data)
workflow.add_node("build_constraints", build_constraints)
workflow.add_node("solve_timetable", solve_timetable)
workflow.add_node("validate_timetable", validate_timetable)
workflow.add_node("save_timetable", save_timetable)

workflow.set_entry_point("fetch_all_data")
workflow.add_edge("fetch_all_data", "build_constraints")
workflow.add_edge("build_constraints", "solve_timetable")
workflow.add_edge("solve_timetable", "validate_timetable")

workflow.add_conditional_edges(
    "validate_timetable",
    check_valid,
    {
        "valid": "save_timetable",
        "invalid": END,
        "retry": "solve_timetable",
    },
)

workflow.add_edge("save_timetable", END)

timetable_app = workflow.compile()


# ─── Entry point ──────────────────────────────────────────────────────────────

def run_timetable_scheduler(academic_year: Optional[int] = None) -> dict:
    """Run the full timetable generation workflow and return final state."""
    print("=" * 60)
    print("Starting Timetable Scheduler Workflow")
    print("=" * 60)

    initial_state: TimetableState = {
        "classes": [],
        "subjects": [],
        "faculty_mappings": [],
        "class_years": {},
        "classrooms": [],
        "labs": [],
        "timetable": {},
        "room_schedule": {},
        "faculty_schedule": {},
        "fixed_timetable_entries": [],
        "conflicts": [],
        "warnings": [],
        "iteration": 0,
        "retry": 0,
        "academic_year": academic_year,
        "is_feasible": True,
        "is_valid": True,
    }

    result = timetable_app.invoke(initial_state)

    print("=" * 60)
    print("Timetable Scheduler Workflow Completed")
    print(f"Warnings: {len(result.get('warnings', []))}")
    print("=" * 60)

    return result

if __name__ == "__main__":
    run_timetable_scheduler()
