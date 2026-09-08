import uuid
from pathlib import Path
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException
from backend.config import UPLOAD_DIR

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("")
async def upload_files(files: List[UploadFile] = File(...)):
    """Handles uploading one or more PDF files and stores them in UPLOAD_DIR."""
    uploaded_files = []

    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail=f"File '{file.filename}' is not a PDF. Only PDF files are supported."
            )

        unique_id = uuid.uuid4().hex[:8]
        safe_filename = f"{unique_id}_{Path(file.filename).name}"
        destination = UPLOAD_DIR / safe_filename

        try:
            content = await file.read()
            destination.write_bytes(content)
            uploaded_files.append({
                "original_filename": file.filename,
                "saved_filename": safe_filename,
                "file_path": str(destination),
                "size_bytes": len(content),
            })
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save uploaded file '{file.filename}': {str(e)}"
            )

    return {
        "status": "success",
        "uploaded_count": len(uploaded_files),
        "files": uploaded_files,
    }
