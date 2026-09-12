import fitz
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse
from backend.models.schemas import (
    BrowseFolderRequest,
    BrowseFolderResponse,
    DiscoveredFile,
)
from backend.config import OUTPUT_DIR, UPLOAD_DIR, SAMPLE_DIR

router = APIRouter(prefix="/api", tags=["files"])


def format_size(bytes_size: int) -> str:
    """Formats bytes into human readable KB/MB."""
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.1f} KB"
    else:
        return f"{bytes_size / (1024 * 1024):.1f} MB"


@router.post("/files/browse", response_model=BrowseFolderResponse)
async def browse_folder(req: BrowseFolderRequest):
    """Mode A: Validates folder path, finds all .pdf files, and returns metadata."""
    path_str = req.folder_path.strip()
    folder = Path(path_str).expanduser().resolve()

    if not folder.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Folder not found: '{path_str}'. Please check the directory path."
        )

    if not folder.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Path is not a directory: '{path_str}'."
        )

    try:
        pdf_files = [
            f for f in folder.iterdir()
            if f.is_file() and f.suffix.lower() == ".pdf" and not f.name.startswith(".")
        ]
        pdf_files.sort(key=lambda x: x.name.lower())

        discovered = []
        for p in pdf_files:
            size_b = p.stat().st_size
            discovered.append(
                DiscoveredFile(
                    filename=p.name,
                    full_path=str(p),
                    size_bytes=size_b,
                    size_formatted=format_size(size_b),
                )
            )

        return BrowseFolderResponse(
            folder_path=str(folder),
            total_found=len(discovered),
            files=discovered,
        )
    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied when accessing folder: '{path_str}'."
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error reading folder '{path_str}': {str(e)}"
        )


@router.get("/files/samples", response_model=BrowseFolderResponse)
async def get_sample_files():
    """Lists pre-generated sample test PDFs for instant testing."""
    files = [
        f for f in SAMPLE_DIR.iterdir()
        if f.is_file() and f.suffix.lower() == ".pdf" and not f.name.startswith(".")
    ]
    files.sort(key=lambda x: x.name.lower())

    discovered = []
    for p in files:
        size_b = p.stat().st_size
        discovered.append(
            DiscoveredFile(
                filename=p.name,
                full_path=str(p),
                size_bytes=size_b,
                size_formatted=format_size(size_b),
            )
        )

    return BrowseFolderResponse(
        folder_path=str(SAMPLE_DIR),
        total_found=len(discovered),
        files=discovered,
    )


@router.get("/source/{filename}/{page}")
async def get_source_page_image(
    filename: str,
    page: int,
    bbox: Optional[str] = Query(None, description="Comma-separated coordinates x0,y0,x1,y1")
):
    """
    Renders high-resolution image of a PDF page with an optional highlighted bounding box.
    Enables instant source verification for any extracted block or table.
    """
    safe_name = Path(filename).name
    # Search candidates
    candidate_paths = [
        UPLOAD_DIR / safe_name,
        SAMPLE_DIR / safe_name,
        Path.home() / "Downloads" / safe_name,
    ]
    target_file = None
    for cp in candidate_paths:
        if cp.exists():
            target_file = cp
            break

    if not target_file:
        raise HTTPException(status_code=404, detail=f"Source document '{filename}' not found.")

    try:
        doc = fitz.open(target_file)
        if page < 1 or page > len(doc):
            doc.close()
            raise HTTPException(status_code=400, detail=f"Page {page} out of bounds (1-{len(doc)}).")

        p = doc[page - 1]

        # If bbox passed, draw highlight rectangle
        if bbox:
            try:
                coords = [float(v.strip()) for v in bbox.split(",") if v.strip()]
                if len(coords) == 4:
                    rect = fitz.Rect(coords[0], coords[1], coords[2], coords[3])
                    # Draw highlight box with red border and soft fill
                    annot = p.add_rect_annot(rect)
                    annot.set_colors(stroke=(0.95, 0.2, 0.2), fill=(1.0, 0.9, 0.2))
                    annot.set_opacity(0.35)
                    annot.update()
            except Exception:
                pass

        # Render at 150 DPI for crisp viewing
        pix = p.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        doc.close()

        return Response(content=img_bytes, media_type="image/png")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to render source page: {str(e)}")


@router.get("/download/{filename}")
async def download_file(filename: str):
    """Securely serves generated exports (TXT, JSON, CSV, XLSX, HTML) or processed files."""
    safe_name = Path(filename).name
    file_path = OUTPUT_DIR / safe_name

    if not file_path.exists():
        file_path = UPLOAD_DIR / safe_name

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Requested file not found.")

    media_type = "application/octet-stream"
    if safe_name.endswith(".html"):
        media_type = "text/html"
    elif safe_name.endswith(".json"):
        media_type = "application/json"
    elif safe_name.endswith(".txt"):
        media_type = "text/plain"
    elif safe_name.endswith(".csv"):
        media_type = "text/csv"
    elif safe_name.endswith(".xlsx"):
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return FileResponse(
        path=file_path,
        filename=safe_name,
        media_type=media_type
    )
