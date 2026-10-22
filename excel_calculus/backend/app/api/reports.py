import io
import os
import shutil
import re
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from excel_calculus.backend.app.database import get_db
from excel_calculus.backend.app.services.report_service import ReportService
from excel_calculus.backend.app.services.ingestion import IngestionService
from excel_calculus.backend.app.config import UPLOAD_DIR

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
def get_section_16_1_report(
    product: str = "Abiraterone",
    dataset_id: Optional[str] = None,
    auto_search: bool = False,
    db: Session = Depends(get_db)
):
    """
    Retrieves or generates the Section 16.1 Summary of Safety Concerns table.
    - Scoped strictly to product and optional dataset_id.
    - If auto_search=True, proactively re-calculates all searches on the target dataset.
    """
    service = ReportService(db)
    try:
        return service.generate_section_16_1_table(
            product_name=product,
            dataset_id=dataset_id,
            auto_execute_all=auto_search
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/section-16-1/generate")
async def generate_section_16_1_automated(
    file: Optional[UploadFile] = File(None),
    product: Optional[str] = Form("Abiraterone"),
    dataset_id: Optional[str] = Form(None),
    reporting_period: Optional[str] = Form(None),
    data_lock_point: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    Nearly one-click automated workflow for Section 16.1 table creation:
    1. If an Excel file is uploaded:
       - Validates file format (.xlsx, .xls)
       - Ingests cases, products, and explodes events using streaming read_only openpyxl
       - Assigns isolated dataset identity
    2. Runs all deterministic safety concern searches automatically for the target product & dataset
    3. Compiles and immediately returns the official Section 16.1 table.
    """
    target_product = product or "Abiraterone"
    target_dataset_id = dataset_id

    if file and file.filename:
        if not file.filename.endswith((".xlsx", ".xls")):
            raise HTTPException(status_code=400, detail="Only Excel workbooks (.xlsx, .xls) are supported.")

        os.makedirs(UPLOAD_DIR, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_name = f"{timestamp}_{file.filename}"
        saved_path = os.path.join(UPLOAD_DIR, safe_name)

        try:
            with open(saved_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save uploaded workbook: {str(e)}")

        # Infer product name if needed
        fname_lower = file.filename.lower()
        if not product or product.strip() == "" or product.lower() == "unknown":
            if "abiraterone" in fname_lower:
                target_product = "Abiraterone"
            elif "oxycodone" in fname_lower:
                target_product = "Oxycodone"
            else:
                target_product = re.split(r"[_ \-\.]", file.filename)[0].capitalize()

        # Ingest line listing
        ingestion = IngestionService(db)
        try:
            ingest_res = ingestion.ingest_linelisting_file(
                file_path=saved_path,
                primary_product_name=target_product,
                reporting_period=reporting_period,
                data_lock_point=data_lock_point
            )
            target_dataset_id = ingest_res.get("dataset_id")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Workbook validation error: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ingestion processing failure: {str(e)}")

    service = ReportService(db)
    try:
        # Run all searches automatically and compile table
        table_result = service.generate_section_16_1_table(
            product_name=target_product,
            dataset_id=target_dataset_id,
            auto_execute_all=True
        )
        return {
            "status": "success",
            "message": f"Section 16.1 table generated successfully for {target_product}.",
            "data": table_result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Table generation failed: {str(e)}")

@router.get("/section-16-1/pdf")
def get_section_16_1_pdf(
    product: str = "Abiraterone",
    dataset_id: Optional[str] = None,
    preview: bool = False,
    include_subsequent: bool = False,
    db: Session = Depends(get_db)
):
    """
    Renders the official PBRER Section 16.1 table as a formal regulatory A4 PDF.
    By default (include_subsequent=False), does NOT append unrelated 16.2 / 16.3 narrative sections.
    """
    service = ReportService(db)
    try:
        pdf_bytes = service.generate_section_16_1_pdf(
            product_name=product,
            dataset_id=dataset_id,
            include_subsequent_sections=include_subsequent
        )
        disposition = "inline" if preview else f'attachment; filename="{product}_Section_16.1_PBRER_Report.pdf"'
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": disposition}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/section-16-1/excel")
def get_section_16_1_excel(
    product: str = "Abiraterone",
    dataset_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Generates and downloads the official PBRER Section 16.1 Summary of Safety Concerns
    table as a professional Microsoft Excel (.xlsx) spreadsheet.
    """
    service = ReportService(db)
    try:
        excel_bytes = service.generate_section_16_1_excel(
            product_name=product,
            dataset_id=dataset_id
        )
        filename = f"{product}_Section_16.1_PBRER_Table.xlsx"
        return StreamingResponse(
            io.BytesIO(excel_bytes),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
