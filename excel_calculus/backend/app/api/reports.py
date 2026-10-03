from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from excel_calculus.backend.app.database import get_db
from excel_calculus.backend.app.services.report_service import ReportService

router = APIRouter(prefix="/api/reports", tags=["Safety Reports"])

@router.get("/pbrer/{concern_id}")
def get_pbrer_report(concern_id: str, db: Session = Depends(get_db)):
    service = ReportService(db)
    try:
        return service.generate_pbrer_section_report(concern_id=concern_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/section-16-1")
def get_section_16_1_report(product: str = "Abiraterone", db: Session = Depends(get_db)):
    service = ReportService(db)
    try:
        return service.generate_section_16_1_table(product_name=product)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
