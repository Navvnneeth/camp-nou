import pandas as pd
from services.models.models import Students
from services.dependencies.db import DBInvoker

def insert_students_from_excel(file, db_invoker: DBInvoker):
    # Read Excel
    df = pd.read_excel(file)

    # Normalize columns
    df.columns = df.columns.str.lower().str.strip()

    required_columns = {"name", "branch"}
    if not required_columns.issubset(df.columns):
        raise ValueError("Excel must contain 'name' and 'branch' columns")

    inserted = 0
    updated = 0

    for _, row in df.iterrows():
        if pd.isna(row["name"]) or pd.isna(row["branch"]):
            continue

        name = str(row["name"]).strip()
        academic_year = None
        for column in ("year", "academic_year", "batch_year"):
            if column in df.columns and not pd.isna(row.get(column)):
                academic_year = int(row[column])
                break

        existing = db_invoker.db.query(Students).filter(Students.name == name).first()
        if existing:
            existing.branch = str(row["branch"]).strip()
            existing.academic_year = academic_year
            updated += 1
        else:
            student = Students(
                name=name,
                branch=str(row["branch"]).strip(),
                academic_year=academic_year,
            )
            db_invoker.db.add(student)
            inserted += 1

    db = db_invoker.db

    db.commit()

    return inserted + updated
