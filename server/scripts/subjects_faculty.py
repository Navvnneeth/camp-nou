import pandas as pd
from services.models.models import Subjects, Faculty, SubjectFacultyMapping
from services.dependencies.db import DBInvoker
from datetime import datetime


def insert_subjects_faculty_from_excel(file, db_invoker: DBInvoker):
    """
    Parse an Excel file with columns: subject, faculty, class, hours_per_week (optional).
    - Auto-detects lab subjects (name contains 'lab', case-insensitive).
    - Lab subjects default to 3 hours/week, lecture subjects default to value in Excel or 1.
    - Creates Subjects, Faculty, and SubjectFacultyMapping entries (get-or-create).
    """
    df = pd.read_excel(file)

    # Normalize column names
    df.columns = df.columns.str.lower().str.strip()

    required_columns = {"subject", "faculty", "class"}
    if not required_columns.issubset(df.columns):
        raise ValueError(
            "Excel must contain 'subject', 'faculty', and 'class' columns"
        )

    db = db_invoker.db
    subject_cache = {}   # name -> Subjects ORM object
    faculty_cache = {}   # name -> Faculty ORM object
    mappings_created = 0

    for _, row in df.iterrows():
        subject_name = str(row["subject"]).strip()
        faculty_name = str(row["faculty"]).strip()
        class_name = str(row["class"]).strip()

        if not subject_name or not faculty_name or not class_name:
            continue

        # --- Get or create Subject ---
        if subject_name not in subject_cache:
            existing = db.query(Subjects).filter(
                Subjects.name == subject_name
            ).first()
            if existing:
                subject_cache[subject_name] = existing
            else:
                is_lab = "lab" in subject_name.lower()
                # Default hours: 3 for lab, else use Excel column or 1
                if "hours_per_week" in df.columns and not pd.isna(row.get("hours_per_week")):
                    hours = int(row["hours_per_week"])
                else:
                    hours = 3 if is_lab else 1

                new_subject = Subjects(
                    name=subject_name,
                    is_lab=is_lab,
                    hours_per_week=hours,
                    created_at=datetime.utcnow(),
                )
                db.add(new_subject)
                db.flush()  # get the ID
                subject_cache[subject_name] = new_subject

        # --- Get or create Faculty ---
        if faculty_name not in faculty_cache:
            existing = db.query(Faculty).filter(
                Faculty.name == faculty_name
            ).first()
            if existing:
                faculty_cache[faculty_name] = existing
            else:
                new_faculty = Faculty(
                    name=faculty_name,
                    created_at=datetime.utcnow(),
                )
                db.add(new_faculty)
                db.flush()
                faculty_cache[faculty_name] = new_faculty

        # --- Create SubjectFacultyMapping (avoid duplicates) ---
        subject_obj = subject_cache[subject_name]
        faculty_obj = faculty_cache[faculty_name]

        existing_mapping = db.query(SubjectFacultyMapping).filter(
            SubjectFacultyMapping.subject_id == subject_obj.id,
            SubjectFacultyMapping.faculty_id == faculty_obj.id,
            SubjectFacultyMapping.class_name == class_name,
        ).first()

        if not existing_mapping:
            mapping = SubjectFacultyMapping(
                subject_id=subject_obj.id,
                faculty_id=faculty_obj.id,
                class_name=class_name,
                created_at=datetime.utcnow(),
            )
            db.add(mapping)
            mappings_created += 1

    db.commit()
    return mappings_created
