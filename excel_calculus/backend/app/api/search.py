from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from excel_calculus.backend.app.database import get_db
from excel_calculus.backend.app.services.search_engine import SearchEngineService

router = APIRouter(prefix="/api/search", tags=["Deterministic Search"])

@router.post("/{concern_id}")
def run_concern_search(concern_id: str, reviewer: str = Query("reviewer"), db: Session = Depends(get_db)):
    service = SearchEngineService(db)
    try:
        return service.execute_concern_search(concern_id=concern_id, reviewer_id=reviewer)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{concern_id}")
def get_concern_search_results(concern_id: str, db: Session = Depends(get_db)):
    service = SearchEngineService(db)
    try:
        return service.get_search_summary(concern_id=concern_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
