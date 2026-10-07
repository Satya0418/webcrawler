from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from excel_calculus.backend.app.database import get_db
from excel_calculus.backend.app.services.case_service import CaseService
from excel_calculus.backend.app.models.entities import CaseRecord

router = APIRouter(prefix="/api/cases", tags=["Case Review"])

@router.get("")
def list_cases(
    product: Optional[str] = None,
    country: Optional[str] = None,
    serious_only: bool = False,
    page: int = 1,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    query = db.query(CaseRecord)
    if product:
        query = query.filter(CaseRecord.product_name.ilike(f"%{product}%"))
    if country:
        query = query.filter(CaseRecord.country.ilike(f"%{country}%"))
    if serious_only:
        query = query.filter(CaseRecord.is_serious == True)

    total = query.count()
    offset = (page - 1) * limit
    cases = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": [
            {
                "case_number": c.case_number,
                "product_name": c.product_name,
                "country": c.country,
                "report_type": c.report_type,
                "age": c.age,
                "sex": c.sex,
                "is_serious": c.is_serious,
                "initial_receipt_date": c.initial_receipt_date,
                "primary_soc": c.primary_soc,
                "outcome": c.case_outcome
            }
            for c in cases
        ]
    }

@router.get("/{case_number}")
def get_case_detail(case_number: str, concern_id: Optional[str] = None, db: Session = Depends(get_db)):
    service = CaseService(db)
    try:
        return service.get_complete_case(case_number=case_number, concern_id=concern_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
