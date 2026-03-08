"""
Test the timetable scheduler with realistic data:
- 3 physical classrooms but 5 class sections (scarcity edge case)
- 1 lab room
- 8 subjects (2 are labs), 6 faculty members
- Validates: no double-booking, lab displacement, fallbacks
"""
from services.dependencies.db import get_db_session
from services.models.models import (
    Subjects, Faculty, SubjectFacultyMapping, Rooms, Timetable
)
from services.graph.timetable_scheduler import run_timetable_scheduler
from datetime import datetime


DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def clear_test_data():
    """Remove previously generated data for a clean test run."""
    db = get_db_session()
    try:
        db.query(Timetable).delete()
        db.query(SubjectFacultyMapping).delete()
        db.query(Faculty).delete()
        db.query(Subjects).delete()
        # Don't delete rooms — might have real data. Delete only test rooms.
        db.query(Rooms).filter(Rooms.name.in_([
            "CR-101", "CR-102", "CR-103", "LAB-201"
        ])).delete(synchronize_session="fetch")
        db.commit()
        print("Cleared previous test data.")
    finally:
        db.close()


def setup_test_data():
    """Insert realistic test data simulating the scarcity edge case."""
    db = get_db_session()
    try:
        # ── Rooms: 3 classrooms, 1 lab (fewer classrooms than classes!) ──
        rooms = [
            Rooms(name="CR-101", capacity=60, room_type="classroom", created_at=datetime.utcnow()),
            Rooms(name="CR-102", capacity=60, room_type="classroom", created_at=datetime.utcnow()),
            Rooms(name="CR-103", capacity=60, room_type="classroom", created_at=datetime.utcnow()),
            Rooms(name="LAB-201", capacity=30, room_type="lab", created_at=datetime.utcnow()),
        ]
        db.add_all(rooms)
        db.flush()

        # ── Subjects ──
        subjects = [
            Subjects(name="Mathematics", is_lab=False, hours_per_week=4, created_at=datetime.utcnow()),
            Subjects(name="Physics", is_lab=False, hours_per_week=3, created_at=datetime.utcnow()),
            Subjects(name="Chemistry", is_lab=False, hours_per_week=3, created_at=datetime.utcnow()),
            Subjects(name="English", is_lab=False, hours_per_week=2, created_at=datetime.utcnow()),
            Subjects(name="Computer Science", is_lab=False, hours_per_week=3, created_at=datetime.utcnow()),
            Subjects(name="Electronics", is_lab=False, hours_per_week=2, created_at=datetime.utcnow()),
            Subjects(name="Physics Lab", is_lab=True, hours_per_week=3, created_at=datetime.utcnow()),
            Subjects(name="CS Lab", is_lab=True, hours_per_week=3, created_at=datetime.utcnow()),
        ]
        db.add_all(subjects)
        db.flush()

        sub_map = {s.name: s.id for s in subjects}

        # ── Faculty ──
        faculty = [
            Faculty(name="Dr. Rao", created_at=datetime.utcnow()),
            Faculty(name="Dr. Singh", created_at=datetime.utcnow()),
            Faculty(name="Dr. Patel", created_at=datetime.utcnow()),
            Faculty(name="Prof. Kumar", created_at=datetime.utcnow()),
            Faculty(name="Dr. Sharma", created_at=datetime.utcnow()),
            Faculty(name="Prof. Reddy", created_at=datetime.utcnow()),
        ]
        db.add_all(faculty)
        db.flush()

        fac_map = {f.name: f.id for f in faculty}

        # ── 5 class sections ──
        classes = ["CS-A", "CS-B", "CS-C", "EC-A", "EC-B"]

        # ── Subject-Faculty Mappings ──
        # Note: Some faculty teach multiple classes (realistic constraint)
        mappings_data = [
            # Mathematics — Dr. Rao teaches CS-A, CS-B; Dr. Singh teaches CS-C, EC-A, EC-B
            ("Mathematics", "Dr. Rao", "CS-A"),
            ("Mathematics", "Dr. Rao", "CS-B"),
            ("Mathematics", "Dr. Singh", "CS-C"),
            ("Mathematics", "Dr. Singh", "EC-A"),
            ("Mathematics", "Dr. Singh", "EC-B"),
            # Physics — Dr. Patel teaches all
            ("Physics", "Dr. Patel", "CS-A"),
            ("Physics", "Dr. Patel", "CS-B"),
            ("Physics", "Dr. Patel", "CS-C"),
            ("Physics", "Dr. Patel", "EC-A"),
            ("Physics", "Dr. Patel", "EC-B"),
            # Chemistry — Prof. Kumar
            ("Chemistry", "Prof. Kumar", "CS-A"),
            ("Chemistry", "Prof. Kumar", "CS-B"),
            ("Chemistry", "Prof. Kumar", "EC-A"),
            # English — Dr. Sharma
            ("English", "Dr. Sharma", "CS-A"),
            ("English", "Dr. Sharma", "CS-C"),
            ("English", "Dr. Sharma", "EC-B"),
            # Computer Science — Prof. Reddy for CS classes
            ("Computer Science", "Prof. Reddy", "CS-A"),
            ("Computer Science", "Prof. Reddy", "CS-B"),
            ("Computer Science", "Prof. Reddy", "CS-C"),
            # Electronics — Dr. Sharma for EC classes
            ("Electronics", "Dr. Sharma", "EC-A"),
            ("Electronics", "Dr. Sharma", "EC-B"),
            # Physics Lab — Dr. Patel
            ("Physics Lab", "Dr. Patel", "CS-A"),
            ("Physics Lab", "Dr. Patel", "EC-A"),
            # CS Lab — Prof. Reddy
            ("CS Lab", "Prof. Reddy", "CS-B"),
            ("CS Lab", "Prof. Reddy", "CS-C"),
        ]

        for subj_name, fac_name, class_name in mappings_data:
            m = SubjectFacultyMapping(
                subject_id=sub_map[subj_name],
                faculty_id=fac_map[fac_name],
                class_name=class_name,
                created_at=datetime.utcnow(),
            )
            db.add(m)

        db.commit()
        print(f"Test data inserted: {len(rooms)} rooms, {len(subjects)} subjects, "
              f"{len(faculty)} faculty, {len(mappings_data)} mappings for {len(classes)} classes")
    finally:
        db.close()


def verify_results():
    """Verify the generated timetable for correctness."""
    db = get_db_session()
    try:
        entries = db.query(Timetable).all()
        print(f"\n{'='*60}")
        print(f"VERIFICATION RESULTS — {len(entries)} timetable entries")
        print(f"{'='*60}")

        # Group by class
        by_class = {}
        for e in entries:
            by_class.setdefault(e.class_name, []).append(e)

        for cn in sorted(by_class.keys()):
            class_entries = by_class[cn]
            print(f"\n── {cn} ──")
            for day in DAYS:
                day_entries = [e for e in class_entries if e.day == day]
                if not day_entries:
                    continue
                day_entries.sort(key=lambda x: x.slot)
                slots_str = []
                for e in day_entries:
                    lab = " [LAB]" if e.is_lab_period else ""
                    room = f"R{e.room_id}" if e.room_id else "NO-ROOM"
                    status = f" ({e.status})" if e.status != "scheduled" else ""
                    slots_str.append(f"  Slot {e.slot}: S{e.subject_id} F{e.faculty_id} {room}{lab}{status}")
                print(f"  {day}:")
                for s in slots_str:
                    print(s)

        # ── Check for double-bookings ──
        print(f"\n{'─'*40}")
        print("DOUBLE-BOOKING CHECK:")

        faculty_slots = {}
        room_slots = {}
        issues = []

        for e in entries:
            if e.status == "suspended":
                continue

            fkey = f"{e.faculty_id}|{e.day}|{e.slot}"
            faculty_slots.setdefault(fkey, []).append(e.class_name)

            if e.room_id:
                rkey = f"{e.room_id}|{e.day}|{e.slot}"
                room_slots.setdefault(rkey, []).append(e.class_name)

        for fkey, classes in faculty_slots.items():
            if len(classes) > 1:
                issues.append(f"  ❌ Faculty double-booked: {fkey} -> {classes}")

        for rkey, classes in room_slots.items():
            if len(classes) > 1:
                issues.append(f"  ❌ Room double-booked: {rkey} -> {classes}")

        if issues:
            for i in issues:
                print(i)
        else:
            print("  ✅ No double-bookings found!")

        # ── Count statuses ──
        statuses = {}
        for e in entries:
            statuses[e.status] = statuses.get(e.status, 0) + 1
        print(f"\nSTATUS BREAKDOWN: {statuses}")

        # ── Lab periods check ──
        print(f"\nLAB PERIODS:")
        for cn in sorted(by_class.keys()):
            class_entries = by_class[cn]
            lab_entries = [e for e in class_entries if e.is_lab_period]
            if lab_entries:
                for day in DAYS:
                    day_labs = sorted(
                        [e for e in lab_entries if e.day == day],
                        key=lambda x: x.slot,
                    )
                    if day_labs:
                        slots = [e.slot for e in day_labs]
                        consecutive = all(
                            slots[i + 1] == slots[i] + 1
                            for i in range(len(slots) - 1)
                        )
                        status = "✅ consecutive" if consecutive else "❌ NOT consecutive"
                        print(f"  {cn} {day}: slots {slots} — {status}")

    finally:
        db.close()


if __name__ == "__main__":
    print("Step 1: Clearing old test data...")
    clear_test_data()

    print("\nStep 2: Setting up test data...")
    setup_test_data()

    print("\nStep 3: Running timetable scheduler...")
    result = run_timetable_scheduler()

    print("\nStep 4: Verifying results...")
    verify_results()

    # Print warnings from scheduler
    warnings = result.get("warnings", [])
    if warnings:
        print(f"\n{'─'*40}")
        print(f"SCHEDULER WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  ⚠ {w}")
