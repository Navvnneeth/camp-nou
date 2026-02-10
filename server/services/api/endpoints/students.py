from fastapi import UploadFile, File, Depends, HTTPException, APIRouter
from services.dependencies.db import getDbInvoker, DBInvoker
from scripts.students import insert_students_from_excel

router = APIRouter(prefix="/students", tags=["students"])

@router.post("/students/upload")
async def upload_students(
    file: UploadFile = File(...),
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Invalid file type")

    try:
        count = insert_students_from_excel(file.file, db_invoker)
        return {"message": f"{count} students inserted successfully"}

    except Exception as e:
        db_invoker.db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
