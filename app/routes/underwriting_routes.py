# app/routes/underwriting_routes.py
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Optional
from ..parsers.underwriting_parser import extract_report_date_iso, parse_report
from ..services.text_extraction_service import extract_text_from_bytes
from ..utils.helpers import read_upload_with_limit, parse_custom_data_field, forward_to_url
from ..config import BUBBLE_URL, BUBBLE_TOKEN, DEFAULT_BEARER

router = APIRouter(prefix="/extract", tags=["underwriting"])

@router.post("")
async def extract_underwriting(
    pdf: UploadFile = File(...),
    document_type: str = Form(...),
    forward_url: Optional[str] = Form(None),
    bearer: Optional[str] = Form(DEFAULT_BEARER),
    basic: Optional[str] = Form(None),
    return_text_sample: Optional[str] = Form(None),
    custom_data: Optional[str] = Form(None),
):
    if not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please send a .pdf file")

    content: bytes = await read_upload_with_limit(pdf)
    await pdf.close()
    
    size_bytes = len(content)
    file_meta = {
        "name": pdf.filename, "size_bytes": size_bytes,
        "size_mb": round(size_bytes / (1024 * 1024), 2),
        "content_type": pdf.content_type or "application/pdf",
    }

    text = extract_text_from_bytes(content)
    report_date = extract_report_date_iso(text)
    data = parse_report(text)

    if report_date:
        for it in data:
            it["report_date"] = report_date

    custom = parse_custom_data_field(custom_data)

    bubble_payload = {
        "report_type": "underwriting", "document_type": document_type, "report_date": report_date,
        "count": len(data), "items": data, "custom_data": custom
    }

    dest_url = (forward_url or BUBBLE_URL)
    auth_bearer = (bearer or BUBBLE_TOKEN)
    forwarded = None
    if dest_url:
        forwarded = forward_to_url(bubble_payload, dest_url, auth_bearer, basic, timeout=30)

    resp = {
        "document_type": document_type, "count": len(data), "report_date": report_date,
        "file": file_meta, "items": data, "forwarded": forwarded,
        "custom_data": custom,
    }
    if (return_text_sample or "").strip().lower() in ("1", "true", "yes"):
        resp["text_sample"] = text[:1500]
        resp["text_len"] = len(text)
    return JSONResponse(resp)
