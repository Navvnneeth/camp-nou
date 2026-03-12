from fastapi import UploadFile, File, Depends, HTTPException, APIRouter
from services.dependencies.db import getDbInvoker, DBInvoker
from scripts.subjects_faculty import insert_subjects_faculty_from_excel

router = APIRouter(prefix="/subjects-faculty", tags=["subjects-faculty"])


@router.post("/upload")
async def upload_subjects_faculty(
    file: UploadFile = File(...),
    db_invoker: DBInvoker = Depends(getDbInvoker),
):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Invalid file type. Use .xlsx or .xls")

    try:
        count = insert_subjects_faculty_from_excel(file.file, db_invoker)
        return {"message": f"{count} subject-faculty mappings created successfully"}

    except Exception as e:
        db_invoker.db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
