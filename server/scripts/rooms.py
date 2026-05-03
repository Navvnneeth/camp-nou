import pandas as pd
from services.models.models import Rooms
from services.dependencies.db import DBInvoker

def insert_rooms_from_excel(file, db_invoker: DBInvoker):
    df = pd.read_excel(file)

    # Normalize columns
    df.columns = df.columns.str.lower().str.strip()

    required_columns = {"name", "capacity"}
    if not required_columns.issubset(df.columns):
        raise ValueError("Excel must contain 'name' and 'capacity' columns")

    rows_by_name = {}

    for _, row in df.iterrows():
        if pd.isna(row["name"]) or pd.isna(row["capacity"]):
            continue

        name = str(row["name"]).strip()
        room_type = "classroom"
        if "room_type" in df.columns and not pd.isna(row.get("room_type", None)):
            room_type = str(row["room_type"]).strip().lower()

        rows_by_name[name] = {
            "capacity": int(row["capacity"]),
            "room_type": room_type,
        }

    db = db_invoker.db

    try:
        inserted = 0
        updated = 0

        for name, values in rows_by_name.items():
            existing = db.query(Rooms).filter(Rooms.name == name).first()
            if existing:
                existing.capacity = values["capacity"]
                existing.room_type = values["room_type"]
                updated += 1
            else:
                db.add(
                    Rooms(
                        name=name,
                        capacity=values["capacity"],
                        room_type=values["room_type"],
                    )
                )
                inserted += 1

        db.commit()
    except Exception as e:
        db.rollback()
        raise e

    return inserted + updated
