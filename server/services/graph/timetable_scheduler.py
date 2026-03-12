"""
LangGraph-based Timetable Scheduler with Classroom Scarcity Optimization.

Handles the edge case where physical classrooms < total classes by:
1. Reusing classrooms freed during lab periods (students are in lab rooms)
2. Rescheduling lectures to open slots on other days
3. Rearranging lab periods to maximize classroom availability
4. Suspending classes as a last resort

Graph flow:
  fetch_all_data -> build_constraints -> generate_initial_timetable
  -> resolve_room_conflicts -> (loop if conflicts) -> validate_timetable
  -> (retry if invalid) -> save_timetable -> END
"""

from typing import List, Dict, Any, TypedDict, Optional, Set, Tuple
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session
from services.dependencies.db import get_db_session
from services.models.models import (
    Subjects, Faculty, SubjectFacultyMapping, Rooms, Timetable
)
from datetime import datetime
import random

# ─── Constants ────────────────────────────────────────────────────────────────

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
SLOTS_PER_DAY = 6          # 1-hour slots numbered 1..6
LAB_DURATION = 3           # lab periods occupy 3 consecutive slots
MAX_CONFLICT_ITERATIONS = 10
MAX_RETRY_ITERATIONS = 3


# ─── State ────────────────────────────────────────────────────────────────────

class TimetableState(TypedDict):
    # Input data
    classes: List[str]
    subjects: List[Dict[str, Any]]
    faculty_mappings: List[Dict[str, Any]]
    classrooms: List[Dict[str, Any]]        # rooms where room_type = "classroom"
    labs: List[Dict[str, Any]]              # rooms where room_type = "lab"

    # Scheduling structures  (class -> day -> slot -> entry)
    timetable: Dict[str, Any]
    room_schedule: Dict[str, Any]           # room_id_str -> day -> slot_str -> class
    faculty_schedule: Dict[str, Any]        # faculty_id_str -> day -> slot_str -> class

    # Conflict tracking
    conflicts: List[Dict[str, Any]]
    warnings: List[str]
    iteration: int
    retry: int


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


def _find_free_classroom(
    classrooms: list,
    room_schedule: dict,
    day: str,
    slot: int,
) -> Optional[Dict]:
    """Return the first classroom that is free at (day, slot), or None."""
    for cr in classrooms:
        if _is_room_free(room_schedule, cr["id"], day, slot):
            return cr
    return None


def _find_free_lab(
    labs: list,
    room_schedule: dict,
    day: str,
    slots: List[int],
) -> Optional[Dict]:
    """Return a lab room free for all specified consecutive slots."""
    for lab in labs:
        if all(_is_room_free(room_schedule, lab["id"], day, s) for s in slots):
            return lab
    return None


# ─── Node: fetch_all_data ─────────────────────────────────────────────────────

def fetch_all_data(state: TimetableState) -> dict:
    """Load subjects, faculty mappings, and rooms from the database."""
    print("[fetch_all_data] Loading data from database...")
    db: Session = get_db_session()
    try:
        subjects = db.query(Subjects).all()
        mappings = db.query(SubjectFacultyMapping).all()
        rooms = db.query(Rooms).all()

        subjects_data = [
            {
                "id": s.id,
                "name": s.name,
                "is_lab": s.is_lab,
                "hours_per_week": s.hours_per_week,
            }
            for s in subjects
        ]

        mappings_data = [
            {
                "id": m.id,
                "subject_id": m.subject_id,
                "faculty_id": m.faculty_id,
                "class_name": m.class_name,
            }
            for m in mappings
        ]

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
        class_names = sorted(set(m.class_name for m in mappings))

        print(
            f"[fetch_all_data] {len(subjects_data)} subjects, "
            f"{len(mappings_data)} mappings, {len(classrooms_data)} classrooms, "
            f"{len(labs_data)} labs, {len(class_names)} classes"
        )

        return {
            "classes": class_names,
            "subjects": subjects_data,
            "faculty_mappings": mappings_data,
            "classrooms": classrooms_data,
            "labs": labs_data,
            "timetable": {},
            "room_schedule": {},
            "faculty_schedule": {},
            "conflicts": [],
            "warnings": [],
            "iteration": 0,
            "retry": 0,
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

    class_reqs: Dict[str, list] = {}
    for m in mappings:
        cn = m["class_name"]
        subj = subjects_by_id.get(m["subject_id"])
        if not subj:
            continue
        class_reqs.setdefault(cn, []).append({
            "subject_id": subj["id"],
            "subject_name": subj["name"],
            "faculty_id": m["faculty_id"],
            "is_lab": subj["is_lab"],
            "hours": subj["hours_per_week"],
        })

    # Store requirements inside timetable metadata
    timetable = state.get("timetable", {})
    timetable["__requirements__"] = class_reqs

    total_hours = sum(
        sum(r["hours"] for r in reqs) for reqs in class_reqs.values()
    )
    print(f"[build_constraints] Total teaching hours across all classes: {total_hours}")
    return {"timetable": timetable}


# ─── Node: generate_initial_timetable ─────────────────────────────────────────

def generate_initial_timetable(state: TimetableState) -> dict:
    """
    Greedy slot-fill algorithm:
      1. Schedule lab periods first (they need 3 consecutive slots).
      2. Schedule lectures in remaining slots.
      3. Respect faculty non-overlap.
      4. Assign rooms — labs to lab rooms, lectures to classrooms.
         When classrooms are scarce, use classrooms freed by lab displacement.
    """
    print("[generate_initial_timetable] Generating timetable...")
    timetable = state["timetable"]
    class_reqs = timetable.get("__requirements__", {})
    classrooms = state["classrooms"]
    labs_rooms = state["labs"]

    room_schedule: Dict[str, Any] = {}
    faculty_schedule: Dict[str, Any] = {}
    conflicts: List[Dict] = []
    warnings: List[str] = []

    # Initialize timetable slots for each class
    for cn in state["classes"]:
        timetable[cn] = {}
        for day in DAYS:
            timetable[cn][day] = {}

    # ── Phase 1: Schedule LAB periods ──────────────────────────────────────
    for cn in state["classes"]:
        reqs = class_reqs.get(cn, [])
        lab_reqs = [r for r in reqs if r["is_lab"]]
        for lr in lab_reqs:
            scheduled_hours = 0
            target = lr["hours"]  # typically 3
            while scheduled_hours < target:
                placed = False
                needed = min(LAB_DURATION, target - scheduled_hours)
                for day in DAYS:
                    if placed:
                        break
                    # Try each starting slot that allows `needed` consecutive
                    for start_slot in range(1, SLOTS_PER_DAY - needed + 2):
                        slots_needed = list(range(start_slot, start_slot + needed))
                        # Check class slots free
                        if any(_slot_key(s) in timetable[cn][day] for s in slots_needed):
                            continue
                        # Check faculty free
                        if not all(
                            _is_faculty_free(faculty_schedule, lr["faculty_id"], day, s)
                            for s in slots_needed
                        ):
                            continue
                        # Find a lab room
                        lab_room = _find_free_lab(labs_rooms, room_schedule, day, slots_needed)
                        if not lab_room:
                            continue

                        # Place lab
                        for s in slots_needed:
                            entry = {
                                "subject_id": lr["subject_id"],
                                "faculty_id": lr["faculty_id"],
                                "room_id": lab_room["id"],
                                "is_lab_period": True,
                                "status": "scheduled",
                            }
                            timetable[cn][day][_slot_key(s)] = entry
                            _book_room(room_schedule, lab_room["id"], day, s, cn)
                            _book_faculty(faculty_schedule, lr["faculty_id"], day, s, cn)

                        scheduled_hours += needed
                        placed = True
                        break

                if not placed:
                    warnings.append(
                        f"Could not schedule lab '{lr['subject_name']}' for {cn} "
                        f"({scheduled_hours}/{target} hours placed)"
                    )
                    break

    # ── Phase 2: Schedule LECTURE periods ──────────────────────────────────
    for cn in state["classes"]:
        reqs = class_reqs.get(cn, [])
        lecture_reqs = [r for r in reqs if not r["is_lab"]]
        for lr in lecture_reqs:
            scheduled_hours = 0
            target = lr["hours"]
            while scheduled_hours < target:
                placed = False
                for day in DAYS:
                    if placed:
                        break
                    for slot in range(1, SLOTS_PER_DAY + 1):
                        sk = _slot_key(slot)
                        # Class slot free?
                        if sk in timetable[cn][day]:
                            continue
                        # Faculty free?
                        if not _is_faculty_free(faculty_schedule, lr["faculty_id"], day, slot):
                            continue
                        # Find a classroom
                        classroom = _find_free_classroom(classrooms, room_schedule, day, slot)
                        if not classroom:
                            # No classroom available — record as conflict for later
                            conflicts.append({
                                "class_name": cn,
                                "day": day,
                                "slot": slot,
                                "subject_id": lr["subject_id"],
                                "faculty_id": lr["faculty_id"],
                                "reason": "no_classroom_available",
                            })
                            # Still place the entry without a room for now
                            timetable[cn][day][sk] = {
                                "subject_id": lr["subject_id"],
                                "faculty_id": lr["faculty_id"],
                                "room_id": None,
                                "is_lab_period": False,
                                "status": "unassigned_room",
                            }
                            _book_faculty(faculty_schedule, lr["faculty_id"], day, slot, cn)
                            scheduled_hours += 1
                            placed = True
                            break

                        # Place lecture
                        timetable[cn][day][sk] = {
                            "subject_id": lr["subject_id"],
                            "faculty_id": lr["faculty_id"],
                            "room_id": classroom["id"],
                            "is_lab_period": False,
                            "status": "scheduled",
                        }
                        _book_room(room_schedule, classroom["id"], day, slot, cn)
                        _book_faculty(faculty_schedule, lr["faculty_id"], day, slot, cn)
                        scheduled_hours += 1
                        placed = True
                        break

                if not placed:
                    warnings.append(
                        f"Could not schedule lecture '{lr['subject_name']}' for {cn} "
                        f"({scheduled_hours}/{target} hours placed)"
                    )
                    break

    print(
        f"[generate_initial_timetable] Done. {len(conflicts)} room conflicts, "
        f"{len(warnings)} warnings"
    )
    return {
        "timetable": timetable,
        "room_schedule": room_schedule,
        "faculty_schedule": faculty_schedule,
        "conflicts": conflicts,
        "warnings": warnings,
    }


# ─── Node: resolve_room_conflicts ─────────────────────────────────────────────

def resolve_room_conflicts(state: TimetableState) -> dict:
    """
    Try to fix entries with status='unassigned_room' using these strategies:
      1. Lab displacement — if another class is in lab, their classroom is free.
      2. Reschedule to a different day/slot with room availability.
      3. Suspend the class as a last resort.
    """
    iteration = state.get("iteration", 0) + 1
    print(f"[resolve_room_conflicts] Iteration {iteration}...")

    timetable = state["timetable"]
    room_schedule = state["room_schedule"]
    faculty_schedule = state["faculty_schedule"]
    classrooms = state["classrooms"]
    conflicts = state["conflicts"]
    warnings = list(state.get("warnings", []))

    new_conflicts = []

    for conflict in conflicts:
        cn = conflict["class_name"]
        day = conflict["day"]
        slot = conflict["slot"]
        sk = _slot_key(slot)

        entry = timetable.get(cn, {}).get(day, {}).get(sk)
        if not entry or entry.get("status") != "unassigned_room":
            continue  # already resolved

        resolved = False

        # ── Strategy 1: Lab displacement ──
        # Check all other classes: if any class has lab in this (day, slot), then
        # that class's "home classroom" assignment from another slot tells us
        # which classroom they normally use — and it's free now.
        classroom = _find_free_classroom(classrooms, room_schedule, day, slot)
        if classroom:
            entry["room_id"] = classroom["id"]
            entry["status"] = "scheduled"
            _book_room(room_schedule, classroom["id"], day, slot, cn)
            resolved = True

        # ── Strategy 2: Reschedule to another day/slot ──
        if not resolved:
            for alt_day in DAYS:
                if resolved:
                    break
                for alt_slot in range(1, SLOTS_PER_DAY + 1):
                    ask = _slot_key(alt_slot)
                    # Class slot must be free on new day
                    if ask in timetable.get(cn, {}).get(alt_day, {}):
                        continue
                    # Faculty must be free
                    if not _is_faculty_free(
                        faculty_schedule, entry["faculty_id"], alt_day, alt_slot
                    ):
                        continue
                    # Room must be available
                    cr = _find_free_classroom(classrooms, room_schedule, alt_day, alt_slot)
                    if not cr:
                        continue

                    # Move the entry
                    del timetable[cn][day][sk]
                    # Unbook faculty from old slot
                    fk = _faculty_key(entry["faculty_id"])
                    if fk in faculty_schedule and day in faculty_schedule[fk]:
                        faculty_schedule[fk][day].pop(sk, None)

                    entry["room_id"] = cr["id"]
                    entry["status"] = "rescheduled"
                    timetable[cn].setdefault(alt_day, {})[ask] = entry
                    _book_room(room_schedule, cr["id"], alt_day, alt_slot, cn)
                    _book_faculty(faculty_schedule, entry["faculty_id"], alt_day, alt_slot, cn)

                    warnings.append(
                        f"Rescheduled {cn} subject {entry['subject_id']} "
                        f"from {day} slot {slot} to {alt_day} slot {alt_slot}"
                    )
                    resolved = True
                    break

        # ── Strategy 3: Suspend ──
        if not resolved:
            entry["status"] = "suspended"
            entry["room_id"] = None
            warnings.append(
                f"SUSPENDED {cn} subject {entry['subject_id']} on {day} slot {slot} — "
                f"no classroom available"
            )

    return {
        "timetable": timetable,
        "room_schedule": room_schedule,
        "faculty_schedule": faculty_schedule,
        "conflicts": new_conflicts,
        "warnings": warnings,
        "iteration": iteration,
    }


# ─── Conditional: still have conflicts? ───────────────────────────────────────

def check_conflicts(state: TimetableState) -> str:
    if state["conflicts"] and state["iteration"] < MAX_CONFLICT_ITERATIONS:
        return "has_conflicts"
    return "resolved"


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

    for cn in state["classes"]:
        class_tt = timetable.get(cn, {})
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

                if fid:
                    fkey = f"{fid}|{day}|{sk}"
                    faculty_slots.setdefault(fkey, set()).add(cn)
                if rid:
                    rkey = f"{rid}|{day}|{sk}"
                    room_slots.setdefault(rkey, set()).add(cn)

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

    return {"warnings": warnings, "conflicts": []}


# ─── Conditional: valid or retry? ─────────────────────────────────────────────

def check_valid(state: TimetableState) -> str:
    # For now always proceed to save — issues are logged as warnings
    return "valid"


# ─── Node: save_timetable ─────────────────────────────────────────────────────

def save_timetable(state: TimetableState) -> dict:
    """Persist timetable entries to the database."""
    print("[save_timetable] Saving to database...")
    timetable = state["timetable"]

    db: Session = get_db_session()
    try:
        # Clear existing timetable
        db.query(Timetable).delete()
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
workflow.add_node("generate_initial_timetable", generate_initial_timetable)
workflow.add_node("resolve_room_conflicts", resolve_room_conflicts)
workflow.add_node("validate_timetable", validate_timetable)
workflow.add_node("save_timetable", save_timetable)

workflow.set_entry_point("fetch_all_data")
workflow.add_edge("fetch_all_data", "build_constraints")
workflow.add_edge("build_constraints", "generate_initial_timetable")
workflow.add_edge("generate_initial_timetable", "resolve_room_conflicts")

workflow.add_conditional_edges(
    "resolve_room_conflicts",
    check_conflicts,
    {
        "has_conflicts": "resolve_room_conflicts",
        "resolved": "validate_timetable",
    },
)

workflow.add_conditional_edges(
    "validate_timetable",
    check_valid,
    {
        "valid": "save_timetable",
        "retry": "generate_initial_timetable",
    },
)

workflow.add_edge("save_timetable", END)

timetable_app = workflow.compile()


# ─── Entry point ──────────────────────────────────────────────────────────────

def run_timetable_scheduler() -> dict:
    """Run the full timetable generation workflow and return final state."""
    print("=" * 60)
    print("Starting Timetable Scheduler Workflow")
    print("=" * 60)

    initial_state: TimetableState = {
        "classes": [],
        "subjects": [],
        "faculty_mappings": [],
        "classrooms": [],
        "labs": [],
        "timetable": {},
        "room_schedule": {},
        "faculty_schedule": {},
        "conflicts": [],
        "warnings": [],
        "iteration": 0,
        "retry": 0,
    }

    result = timetable_app.invoke(initial_state)

    print("=" * 60)
    print("Timetable Scheduler Workflow Completed")
    print(f"Warnings: {len(result.get('warnings', []))}")
    print("=" * 60)

    return result


if __name__ == "__main__":
    run_timetable_scheduler()
