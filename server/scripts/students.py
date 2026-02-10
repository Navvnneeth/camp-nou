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

    students = []

    for _, row in df.iterrows():
        if pd.isna(row["name"]) or pd.isna(row["branch"]):
            continue

        student = Students(
            name=str(row["name"]).strip(),
            branch=str(row["branch"]).strip(),
        )
        students.append(student)

    db = db_invoker.db

    db.bulk_save_objects(students)
    db.commit()

    return len(students)
