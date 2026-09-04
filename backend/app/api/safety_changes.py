"""
API routes for safety-related labeling changes and version history.
"""
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.drug import SafetyLabelingChangeResponse, SafetyChangeVersionResponse
from app.services.database_service import DatabaseService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{record_id}", response_model=SafetyLabelingChangeResponse)
async def get_safety_change(
    record_id: int,
    db: Session = Depends(get_db),
):
    """
    Get a specific safety-related labeling change record.
    """
    change = DatabaseService.get_safety_change_by_id(db, record_id)
    if not change:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Safety labeling change with ID {record_id} not found",
        )
    return SafetyLabelingChangeResponse.from_orm(change)


@router.get("/{record_id}/history", response_model=List[SafetyChangeVersionResponse])
async def get_safety_change_history(
    record_id: int,
    db: Session = Depends(get_db),
):
    """
    Get version history for a safety-related labeling change.
    Returns all historical versions archived whenever content hashes changed.
    """
    change = DatabaseService.get_safety_change_by_id(db, record_id)
    if not change:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Safety labeling change with ID {record_id} not found",
        )

    versions = DatabaseService.get_versions_by_change_id(db, record_id)
    return [SafetyChangeVersionResponse.from_orm(v) for v in versions]


@router.get("/{record_id}/versions", response_model=List[SafetyChangeVersionResponse])
async def get_safety_change_versions(
    record_id: int,
    db: Session = Depends(get_db),
):
    """Alias for /history."""
    return await get_safety_change_history(record_id, db)
