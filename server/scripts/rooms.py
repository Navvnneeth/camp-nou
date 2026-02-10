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

    rooms = []

    for _, row in df.iterrows():
        if pd.isna(row["name"]) or pd.isna(row["capacity"]):
            continue

        rooms.append(
            Rooms(
                name=str(row["name"]).strip(),
                capacity=int(row["capacity"]),
            )
        )

    db = db_invoker.db

    try:
        db.add_all(rooms)
        db.commit()
    except Exception as e:
        db.rollback()
        raise e

    return len(rooms)
