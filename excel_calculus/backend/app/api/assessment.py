from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from excel_calculus.backend.app.database import get_db
from excel_calculus.backend.app.services.case_service import CaseService

router = APIRouter(prefix="/api/assessment", tags=["Relevance Assessment"])

class AssessmentUpdate(BaseModel):
    case_number: str
    concern_id: str
    status: str # RELEVANT, NOT_RELEVANT, NEEDS_REVIEW, CANDIDATE
    exclusion_reason: Optional[str] = None
    reviewer_notes: Optional[str] = None
    secondary_result: Optional[str] = None
    reviewer_id: Optional[str] = "reviewer"

@router.post("")
def set_assessment(data: AssessmentUpdate, db: Session = Depends(get_db)):
    if data.status not in ("RELEVANT", "NOT_RELEVANT", "NEEDS_REVIEW", "CANDIDATE"):
        raise HTTPException(status_code=400, detail="Invalid assessment status")

    service = CaseService(db)
    try:
        return service.update_assessment(
            case_number=data.case_number,
            concern_id=data.concern_id,
            status=data.status,
            exclusion_reason=data.exclusion_reason,
            reviewer_notes=data.reviewer_notes,
            secondary_result=data.secondary_result,
            reviewer_id=data.reviewer_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
