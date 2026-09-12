import uuid
from pathlib import Path
from typing import List, Optional, Union, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from backend.models.schemas import (
    ExtractionRequest,
    ExtractionResult,
    BatchExtractionRequest,
    BatchExtractionResponse,
)
from backend.extraction.section_extractor import SectionExtractor
from backend.services.export_service import ExportService

router = APIRouter(prefix="/api", tags=["extraction"])
extractor = SectionExtractor()


@router.post("/extract", response_model=Union[ExtractionResult, Dict[str, Any]])
async def extract_section(
    req: ExtractionRequest,
    format: Optional[str] = None,
    response_format: Optional[str] = None
):
    """
    Extracts specified parent section and target subsection from a single PDF.
    Stops strictly at the boundary of the next sibling subsection.
    When HTML format is requested (via format, response_format, or query), returns {"Data": "<!DOCTYPE html>..."}.
    """
    if not req.file_path:
        raise HTTPException(
            status_code=400,
            detail="file_path is required for extraction."
        )

    file_p = Path(req.file_path)
    if not file_p.exists():
        raise HTTPException(
            status_code=404,
            detail=f"PDF file not found at path: '{req.file_path}'."
        )

    doc_name = req.filename or file_p.name
    doc_id = uuid.uuid4().hex[:8]

    # Run deterministic extraction
    result = extractor.extract(
        file_path_or_bytes=file_p,
        main_section=req.main_section,
        target_subsection=req.target_subsection,
        natural_query=req.natural_query,
        doc_name=doc_name,
        include_tables=req.include_tables,
        table_mode=req.table_mode,
        section_table_mode=req.section_table_mode,
    )

    # Generate multi-format export files & populate result.Data
    try:
        downloads = ExportService.export_all(result, doc_id)
        result.download_urls = downloads
    except Exception as exp_err:
        result.metadata["export_error"] = str(exp_err)

    if not result.Data:
        result.Data = ExportService.generate_html_content(result)

    # Check if client asked for HTML response format
    requested_fmt = format or req.format
    requested_resp_fmt = response_format or req.response_format
    if SectionExtractor.is_html_requested(requested_fmt, requested_resp_fmt, req.natural_query):
        return {"Data": result.Data}

    return result


@router.post("/extract/html")
async def extract_section_html(req: ExtractionRequest):
    """Convenience endpoint that directly extracts and returns HTML in the format: {"Data": "<!DOCTYPE html>...""}."""
    req.format = "html"
    return await extract_section(req, format="html")


@router.post("/extract/batch", response_model=Union[BatchExtractionResponse, Dict[str, Any]])
async def extract_batch(
    req: BatchExtractionRequest,
    format: Optional[str] = None,
    response_format: Optional[str] = None
):
    """
    Batch processes multiple PDFs using the same extraction criteria.
    Continues processing even if an individual PDF has an error or missing section.
    """
    pdf_paths: List[Path] = []

    # If folder_path provided, scan folder
    if req.folder_path:
        folder = Path(req.folder_path).expanduser().resolve()
        if folder.exists() and folder.is_dir():
            pdf_paths.extend([
                f for f in folder.iterdir()
                if f.is_file() and f.suffix.lower() == ".pdf" and not f.name.startswith(".")
            ])

    # If explicit file list provided
    if req.files:
        for f_str in req.files:
            p = Path(f_str).expanduser().resolve()
            if p.exists() and p.is_file() and p not in pdf_paths:
                pdf_paths.append(p)

    if not pdf_paths:
        raise HTTPException(
            status_code=400,
            detail="No PDF files found to process. Provide either valid 'files' or a 'folder_path'."
        )

    batch_id = uuid.uuid4().hex[:8]
    results: List[ExtractionResult] = []
    success_count = 0
    fail_count = 0

    for p in pdf_paths:
        doc_id = f"{batch_id}_{p.stem[:6]}"
        try:
            res = extractor.extract(
                file_path_or_bytes=p,
                main_section=req.main_section,
                target_subsection=req.target_subsection,
                natural_query=req.natural_query,
                doc_name=p.name,
                include_tables=req.include_tables,
                table_mode=req.table_mode,
                section_table_mode=req.section_table_mode,
            )

            # Export files for this document
            if res.status == "success":
                success_count += 1
                try:
                    downloads = ExportService.export_all(res, doc_id)
                    res.download_urls = downloads
                except Exception:
                    pass
            else:
                fail_count += 1

            results.append(res)
        except Exception as e:
            fail_count += 1
            results.append(
                ExtractionResult(
                    document=p.name,
                    requested_section=req.main_section,
                    requested_subsection=req.target_subsection,
                    start_page=0,
                    end_page=0,
                    status="error",
                    error_message=f"Extraction failure: {str(e)}",
                )
            )

    batch_response = BatchExtractionResponse(
        total_documents=len(pdf_paths),
        successful=success_count,
        failed=fail_count,
        results=results,
    )

    # Generate batch overview summary CSV and Excel
    try:
        csv_url, xlsx_url = ExportService.export_batch_summary(batch_response, batch_id)
        batch_response.summary_csv_url = csv_url
        batch_response.summary_excel_url = xlsx_url
    except Exception:
        pass

    requested_fmt = format or req.format
    requested_resp_fmt = response_format or req.response_format
    if SectionExtractor.is_html_requested(requested_fmt, requested_resp_fmt, req.natural_query):
        combined_html = "\n<hr style='margin: 40px 0; border: 1px solid #ddd;'>\n".join(r.Data for r in results if r.Data)
        batch_response.Data = combined_html

    return batch_response
