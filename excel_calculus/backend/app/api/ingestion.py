from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import os
import shutil
import re
from excel_calculus.backend.app.database import get_db
from excel_calculus.backend.app.services.ingestion import IngestionService
from excel_calculus.backend.app.services.smq_loader import SMQLoaderService
from excel_calculus.backend.app.services.concern_seeder import seed_safety_concerns
from excel_calculus.backend.app.models.entities import CaseRecord, CaseEvent, SMQTerm, SafetyConcern, Dataset

router = APIRouter(prefix="/api/ingestion", tags=["Data Ingestion & Admin"])

@router.get("/status")
def get_ingestion_status(db: Session = Depends(get_db)):
    total_cases = db.query(CaseRecord).count()
    total_events = db.query(CaseEvent).count()
    total_smq_terms = db.query(SMQTerm).count()
    total_concerns = db.query(SafetyConcern).count()

    # Get distinct files
    files = db.query(CaseRecord.raw_source_file).distinct().all()
    file_list = [f[0] for f in files if f[0]]

    # Get distinct products
    prods = db.query(CaseRecord.product_name).distinct().all()
    prod_list = [p[0] for p in prods if p[0]]

    datasets = db.query(Dataset).all()
    dataset_list = [
        {
            "id": d.id,
            "product_name": d.product_name,
            "reporting_period": d.reporting_period,
            "data_lock_point": d.data_lock_point,
            "filename": d.source_filename,
            "cases": d.total_cases,
            "events": d.total_events,
            "type": d.dataset_type,
            "created_at": d.created_at.isoformat() if d.created_at else None
        }
        for d in datasets
    ]

    return {
        "total_cases": total_cases,
        "total_exploded_events": total_events,
        "total_smq_terms": total_smq_terms,
        "total_safety_concerns": total_concerns,
        "ingested_files": file_list,
        "products": prod_list,
        "datasets": dataset_list
    }

@router.post("/seed-defaults")
def seed_default_datasets(db: Session = Depends(get_db)):
    """
    Ingests the default real workspace artifacts:
    1. MedDRA SMQ spreadsheet (SMQ_spreadsheet_29_0_English.xlsx)
    2. Abiraterone Interval LL (119 cases, 225 events)
    3. Oxycodone Interval LL (48 cases, 723 events)
    4. Seeds Safety Concerns for Abiraterone and Oxycodone
    """
    base_artifacts = "/Users/satya/Downloads/Required Artifacts for section 16.3 (3)"
    smq_path = os.path.join(base_artifacts, "MedDRA SMQ list/SMQ_spreadsheet_29_0_English.xlsx")
    abi_path = os.path.join(base_artifacts, "Abiraterone/Abiraterone_20260428_CAN-KUW-OMAN-UAE PBRER_Interval Linelisting.xlsx")
    oxy_path = os.path.join(base_artifacts, "Oxycodone/Oxycodone_20260412_CAN PBRER_Interval LL.xlsx")

    # Fallback to local data/uploads if Downloads is missing
    local_uploads = "/Users/satya/projects/webcrwler/excel_calculus/data/uploads"
    if not os.path.exists(smq_path):
        smq_candidates = [os.path.join(local_uploads, f) for f in os.listdir(local_uploads) if "SMQ" in f]
        if smq_candidates:
            smq_path = smq_candidates[0]

    # 1. Seed concerns
    seed_safety_concerns(db)

    # 2. Ingest SMQs
    smq_count = db.query(SMQTerm).count()
    if os.path.exists(smq_path):
        loader = SMQLoaderService(db)
        loader.load_smq_file(smq_path)

    # 3. Ingest Abiraterone LL
    ingestion = IngestionService(db)
    abi_res = None
    if os.path.exists(abi_path):
        abi_res = ingestion.ingest_linelisting_file(
            abi_path,
            primary_product_name="Abiraterone",
            reporting_period="29-Apr-2025 to 28-Apr-2026",
            data_lock_point="28-Apr-2026"
        )

    # 4. Ingest Oxycodone LL
    oxy_res = None
    if os.path.exists(oxy_path):
        oxy_res = ingestion.ingest_linelisting_file(
            oxy_path,
            primary_product_name="Oxycodone",
            reporting_period="13-Apr-2025 to 12-Apr-2026",
            data_lock_point="12-Apr-2026"
        )

    return {
        "status": "success",
        "abiraterone": abi_res,
        "oxycodone": oxy_res,
        "total_cases": db.query(CaseRecord).count(),
        "total_events": db.query(CaseEvent).count(),
        "total_smq_terms": db.query(SMQTerm).count()
    }

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    product_name: Optional[str] = Form(None),
    file_type: Optional[str] = Form("auto"),
    db: Session = Depends(get_db)
):
    """
    Accepts an uploaded Excel (.xlsx) file and processes it:
    - Line Listing: parses cases, products, explodes Event Verbatim into individual events
    - MedDRA SMQ Reference: loads hierarchical SMQ terminology
    """
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only Excel workbooks (.xlsx, .xls) are supported.")

    uploads_dir = "/Users/satya/projects/webcrwler/excel_calculus/data/uploads"
    os.makedirs(uploads_dir, exist_ok=True)

    # Sanitize and create unique file path
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_name = f"{timestamp}_{file.filename}"
    file_path = os.path.join(uploads_dir, safe_name)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Detect file type
    detected_type = file_type
    if detected_type == "auto":
        fname_upper = file.filename.upper()
        if "SMQ" in fname_upper or "MEDDRA" in fname_upper:
            detected_type = "smq_reference"
        else:
            detected_type = "line_listing"

    if detected_type == "smq_reference":
        loader = SMQLoaderService(db)
        try:
            res = loader.load_smq_file(file_path)
            count = res.get("total_smq_terms", 0) if isinstance(res, dict) else (res or 0)
            total_terms = db.query(SMQTerm).count()
            return {
                "status": "success",
                "message": f"Successfully ingested {count:,} MedDRA SMQ terms.",
                "file_name": file.filename,
                "file_type": "smq_reference",
                "terms_loaded": count,
                "total_smq_terms": total_terms
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to process SMQ file: {str(e)}")

    # Line listing processing
    detected_product = product_name
    if not detected_product or not detected_product.strip():
        # Infer from filename
        fname = file.filename
        if "abiraterone" in fname.lower():
            detected_product = "Abiraterone"
        elif "oxycodone" in fname.lower():
            detected_product = "Oxycodone"
        else:
            detected_product = re.split(r"[_ \-\.]", fname)[0].capitalize()

    ingestion = IngestionService(db)
    try:
        ingest_res = ingestion.ingest_linelisting_file(file_path, primary_product_name=detected_product)
        cases_count = ingest_res.get("total_cases", ingest_res.get("cases", 0))
        events_count = ingest_res.get("total_events", ingest_res.get("events", 0))
        products_count = ingest_res.get("total_products", ingest_res.get("products", 0))

        return {
            "status": "success",
            "message": f"Successfully ingested {cases_count} cases with {events_count} exploded events.",
            "file_name": file.filename,
            "file_type": "line_listing",
            "product_name": detected_product,
            "cases_ingested": cases_count,
            "events_exploded": events_count,
            "products_linked": products_count,
            "total_cases_in_db": db.query(CaseRecord).count(),
            "total_events_in_db": db.query(CaseEvent).count()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process line-listing file: {str(e)}")
