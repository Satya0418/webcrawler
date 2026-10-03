from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from excel_calculus.backend.app.database import get_db
from excel_calculus.backend.app.models.entities import SafetyConcern

router = APIRouter(prefix="/api/concerns", tags=["Safety Concerns"])

class ConcernOut(BaseModel):
    id: str
    product_name: str
    reporting_period: str
    name: str
    category: str
    description: Optional[str]
    search_method: str
    search_config: Optional[str]
    requires_secondary_assessment: bool
    secondary_assessment_instructions: Optional[str]

    class Config:
        from_attributes = True

@router.get("", response_model=List[ConcernOut])
def get_concerns(product: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(SafetyConcern)
    if product:
        query = query.filter(SafetyConcern.product_name.ilike(f"%{product}%"))
    return query.all()

@router.get("/{concern_id}", response_model=ConcernOut)
def get_concern_by_id(concern_id: str, db: Session = Depends(get_db)):
    concern = db.query(SafetyConcern).filter_by(id=concern_id).first()
    if not concern:
        raise HTTPException(status_code=404, detail="Safety Concern not found")
    return concern
